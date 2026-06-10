"""D3-6 Experience Mining Agent — external signals → candidates → theorem review → library.

Pipeline: mine → review (CT3) → pending queue → owner approve → ExperienceLibrary.
"""

from __future__ import annotations

from butler.env_parse import int_env, float_env
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

ReviewStatus = Literal["approved", "pending", "rejected"]

CATEGORY_THEOREM_MAP: dict[str, set[str]] = {
    "deployment": {"T08", "T06"},
    "ci_cd": {"T06", "T04"},
    "dependency": {"T07", "T05"},
    "project_setup": {"T05"},
    "build_system": {"T08", "T04"},
    "changelog": {"T06", "T09"},
    "external_feed": {"T09", "T10"},
    "development_activity": set(),
}

# Safe code templates that satisfy theorem_basis for non-code mined signals.
_PATTERN_TEMPLATES: dict[str, str] = {
    "deployment": (
        "def read_deploy_config(path: str) -> str:\n"
        "    try:\n"
        "        with open(path, encoding='utf-8') as fh:\n"
        "            return fh.read()\n"
        "    except FileNotFoundError:\n"
        "        return ''\n"
    ),
    "ci_cd": (
        "def run_ci_step(argv: list[str]) -> int:\n"
        "    import subprocess\n"
        "    try:\n"
        "        proc = subprocess.run(argv, check=False, timeout=60)\n"
        "        return proc.returncode\n"
        "    except subprocess.TimeoutExpired:\n"
        "        return 1\n"
    ),
    "dependency": (
        "def upsert_dep(key: str, value: str, store: dict[str, str]) -> dict[str, str]:\n"
        "    if key not in store:\n"
        "        store[key] = value\n"
        "    else:\n"
        "        store[key] = value\n"
        "    return dict(store)\n"
    ),
    "project_setup": (
        "def project_flag(name: str, enabled: bool) -> bool:\n"
        "    flags = {'lint': True, 'test': True}\n"
        "    flags[name] = enabled\n"
        "    return flags.get(name, False)\n"
    ),
    "build_system": (
        "def build_once(target: str) -> bool:\n"
        "    steps = [target]\n"
        "    for step in steps:\n"
        "        if not step:\n"
        "            return False\n"
        "    return True\n"
    ),
    "changelog": (
        "def parse_release_note(line: str) -> str:\n"
        "    text = line.strip()\n"
        "    if not text:\n"
        "        return ''\n"
        "    return text[:200]\n"
    ),
    "external_feed": (
        "def validate_feed_item(payload: dict) -> bool:\n"
        "    if not isinstance(payload, dict):\n"
        "        return False\n"
        "    title = payload.get('title', '')\n"
        "    return bool(title)\n"
    ),
}


def mining_enabled() -> bool:
    return os.getenv("BUTLER_EXPERIENCE_MINING", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def auto_ingest_enabled() -> bool:
    return os.getenv("BUTLER_EXPERIENCE_MINING_AUTO_INGEST", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def min_confidence() -> float:
    try:
        return float_env("BUTLER_EXPERIENCE_MINING_MIN_CONFIDENCE", 0.7)
    except ValueError:
        return 0.7


def default_mining_days() -> int:
    try:
        return int_env("BUTLER_EXPERIENCE_MINING_DAYS", 7, min=1)
    except ValueError:
        return 7


def _metrics_dir() -> Path:
    from butler.config import get_butler_home

    d = get_butler_home() / "metrics"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pending_path() -> Path:
    return _metrics_dir() / "mining_pending.json"


def feeds_path() -> Path:
    from butler.config import get_butler_home

    d = get_butler_home() / "feeds"
    d.mkdir(parents=True, exist_ok=True)
    return d / "experience_feeds.jsonl"


def experience_library_path() -> str:
    from butler.config import get_butler_home

    return str(get_butler_home() / "coding_experiences.json")


@dataclass
class CandidateExperience:
    """A candidate experience entry discovered by mining."""

    source: str
    category: str
    content: str
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= min_confidence()

    def candidate_id(self) -> str:
        raw = f"{self.source}:{self.category}:{self.content[:120]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class MiningReport:
    """Summary of an experience mining run."""

    candidates: list[CandidateExperience] = field(default_factory=list)
    sources_scanned: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def high_confidence_count(self) -> int:
        return sum(1 for c in self.candidates if c.is_high_confidence)

    def summary(self) -> dict[str, Any]:
        return {
            "total_candidates": len(self.candidates),
            "high_confidence": self.high_confidence_count,
            "sources_scanned": self.sources_scanned,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "errors": self.errors[:5],
        }


@dataclass
class ReviewResult:
    candidate_id: str
    status: ReviewStatus
    reason: str = ""
    experience: Any = None  # CodingExperience when built


@dataclass
class PipelineResult:
    report: MiningReport
    reviewed: list[ReviewResult] = field(default_factory=list)
    ingested: int = 0
    pending_saved: int = 0
    skipped: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "mining": self.report.summary(),
            "reviewed": len(self.reviewed),
            "approved": sum(1 for r in self.reviewed if r.status == "approved"),
            "pending": sum(1 for r in self.reviewed if r.status == "pending"),
            "rejected": sum(1 for r in self.reviewed if r.status == "rejected"),
            "ingested": self.ingested,
            "pending_saved": self.pending_saved,
            "skipped": self.skipped,
        }


def mine_workspace_patterns(workspace: Path) -> list[CandidateExperience]:
    """Scan workspace for tooling / deployment / dependency signals."""
    candidates: list[CandidateExperience] = []

    pattern_files: dict[str, str] = {
        ".gitignore": "project_setup",
        "Dockerfile": "deployment",
        "docker-compose.yml": "deployment",
        "docker-compose.yaml": "deployment",
        "Makefile": "build_system",
        "pyproject.toml": "dependency",
        "package.json": "dependency",
        "requirements.txt": "dependency",
    }

    for rel_path, category in pattern_files.items():
        fp = workspace / rel_path
        if fp.exists() and fp.is_file():
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")[:500]
                candidates.append(CandidateExperience(
                    source=f"workspace:{rel_path}",
                    category=category,
                    content=f"Project uses {rel_path}: {content[:160]}",
                    confidence=0.65,
                    tags=[category, "auto-mined", rel_path],
                ))
            except Exception as exc:
                logger.debug("Failed to read %s: %s", fp, exc)

    workflows = workspace / ".github" / "workflows"
    if workflows.is_dir():
        for wf in sorted(workflows.glob("*.yml"))[:5]:
            try:
                snippet = wf.read_text(encoding="utf-8", errors="replace")[:300]
                candidates.append(CandidateExperience(
                    source=f"workspace:{wf.relative_to(workspace)}",
                    category="ci_cd",
                    content=f"CI workflow {wf.name}: {snippet[:120]}",
                    confidence=0.7,
                    tags=["ci_cd", "github-actions", wf.stem],
                ))
            except Exception as exc:
                logger.debug("workflow read skipped %s: %s", wf, exc)

    return candidates


def mine_changelog(workspace: Path) -> list[CandidateExperience]:
    """Extract release-note signals from CHANGELOG* files."""
    candidates: list[CandidateExperience] = []
    names = ("CHANGELOG.md", "CHANGELOG", "changelog.md", "HISTORY.md")
    for name in names:
        fp = workspace / name
        if not fp.is_file():
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.debug("changelog read skipped: %s", exc)
            continue
        sections = re.split(r"(?m)^#{1,3}\s+", text)
        for block in sections[1:6]:
            line = block.strip().splitlines()[0] if block.strip() else ""
            body = block.strip()[:400]
            if not line:
                continue
            candidates.append(CandidateExperience(
                source=f"changelog:{name}:{line[:40]}",
                category="changelog",
                content=body,
                confidence=0.75,
                tags=["changelog", "release"],
                metadata={"heading": line[:80]},
            ))
        break
    return candidates


def mine_feeds(feed_file: Path | None = None) -> list[CandidateExperience]:
    """Load external feed rows (user / cron supplied)."""
    path = feed_file or feeds_path()
    if not path.is_file():
        return []
    candidates: list[CandidateExperience] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = str(row.get("content") or row.get("summary") or "").strip()
                if not content:
                    continue
                candidates.append(CandidateExperience(
                    source=str(row.get("source") or "feed:external"),
                    category=str(row.get("category") or "external_feed"),
                    content=content[:600],
                    confidence=float(row.get("confidence") or 0.8),
                    tags=list(row.get("tags") or ["external-feed"]),
                    metadata=dict(row.get("metadata") or {}),
                ))
    except OSError as exc:
        logger.debug("mine_feeds skipped: %s", exc)
    return candidates


def mine_recent_edits(workspace: Path, days: int = 7) -> list[CandidateExperience]:
    """Recently modified files as low-confidence activity signals."""
    candidates: list[CandidateExperience] = []
    cutoff = time.time() - days * 86400

    try:
        for fp in workspace.rglob("*"):
            if not fp.is_file():
                continue
            rel = fp.relative_to(workspace)
            if any(p.startswith(".") for p in rel.parts):
                continue
            if fp.suffix.lower() not in {".py", ".md", ".yaml", ".yml", ".toml", ".json"}:
                continue
            try:
                if fp.stat().st_mtime >= cutoff:
                    candidates.append(CandidateExperience(
                        source=f"recent_edit:{rel}",
                        category="development_activity",
                        content=f"Recently edited: {rel}",
                        confidence=0.35,
                        tags=["recent-edit", fp.suffix.lstrip(".")],
                    ))
            except OSError:
                continue
    except Exception as exc:
        logger.debug("mine_recent_edits error: %s", exc)

    return candidates[:30]


def run_mining(
    workspace: Path | None = None,
    *,
    days: int | None = None,
    include_feeds: bool = True,
) -> MiningReport:
    """Run a complete experience mining pass."""
    if not mining_enabled():
        return MiningReport(errors=["mining disabled (BUTLER_EXPERIENCE_MINING=0)"])

    t0 = time.time()
    report = MiningReport()
    days = days or default_mining_days()

    if include_feeds:
        try:
            feeds = mine_feeds()
            report.candidates.extend(feeds)
            if feeds:
                report.sources_scanned += 1
        except Exception as exc:
            report.errors.append(f"feeds: {exc}")

    if workspace and workspace.exists():
        for fn, label in (
            (mine_workspace_patterns, "workspace_patterns"),
            (mine_changelog, "changelog"),
            (lambda ws: mine_recent_edits(ws, days=days), "recent_edits"),
        ):
            try:
                report.candidates.extend(fn(workspace))
                report.sources_scanned += 1
            except Exception as exc:
                report.errors.append(f"{label}: {exc}")

    report.elapsed_seconds = time.time() - t0
    return report


def _pattern_for_candidate(cand: CandidateExperience) -> str:
    template = _PATTERN_TEMPLATES.get(cand.category, "")
    if template:
        return template
    if cand.category == "development_activity":
        return (
            "def note_activity(path: str) -> str:\n"
            "    return path.strip()[:120]\n"
        )
    return "def mined_note() -> str:\n    return 'mined'\n"


def candidate_to_experience(cand: CandidateExperience) -> Any:
    from butler.dev_engine.coding_knowledge import CodingExperience

    basis = set(CATEGORY_THEOREM_MAP.get(cand.category, set()))
    exp_id = f"MINED_{cand.candidate_id()}"
    title = cand.metadata.get("heading") or f"Mined: {cand.source}"
    if isinstance(title, str) and len(title) > 80:
        title = title[:77] + "..."
    return CodingExperience(
        id=exp_id,
        title=str(title),
        domain=cand.tags[:4] or [cand.category],
        theorem_basis=basis,
        context=cand.content[:400],
        pattern=_pattern_for_candidate(cand),
        validity_start=cand.timestamp,
        validity_end=cand.timestamp + 180 * 86400,
    )


def review_candidate(cand: CandidateExperience) -> ReviewResult:
    """Theorem review gate (CT3): map category → basis → verify pattern."""
    from butler.dev_engine.coding_knowledge import TheoremLibrary, verify_theorems

    cid = cand.candidate_id()
    basis = CATEGORY_THEOREM_MAP.get(cand.category, set())
    if not basis:
        return ReviewResult(cid, "rejected", "category has no theorem mapping")

    tlib = TheoremLibrary()
    activated = {tid: t for tid in basis if (t := tlib.get(tid))}
    if not activated:
        return ReviewResult(cid, "rejected", "theorem basis unresolved")

    exp = candidate_to_experience(cand)
    results = verify_theorems(exp.pattern, activated)
    failed = [r for r in results if not r.passed]
    if failed:
        detail = "; ".join(f"{r.theorem_id}: {r.detail}" for r in failed[:3])
        return ReviewResult(cid, "pending", f"theorem check pending: {detail}", exp)

    return ReviewResult(cid, "approved", "theorem ok", exp)


def load_pending() -> dict[str, dict[str, Any]]:
    path = pending_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_pending(entries: dict[str, dict[str, Any]]) -> None:
    path = pending_path()
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _serialize_candidate(cand: CandidateExperience) -> dict[str, Any]:
    return {
        "source": cand.source,
        "category": cand.category,
        "content": cand.content,
        "confidence": cand.confidence,
        "tags": cand.tags,
        "metadata": cand.metadata,
        "timestamp": cand.timestamp,
    }


def _deserialize_candidate(row: dict[str, Any]) -> CandidateExperience:
    return CandidateExperience(
        source=str(row.get("source") or ""),
        category=str(row.get("category") or ""),
        content=str(row.get("content") or ""),
        confidence=float(row.get("confidence") or 0.5),
        tags=list(row.get("tags") or []),
        metadata=dict(row.get("metadata") or {}),
        timestamp=float(row.get("timestamp") or time.time()),
    )


def queue_pending(cand: CandidateExperience, review: ReviewResult) -> None:
    pending = load_pending()
    pending[cand.candidate_id()] = {
        "candidate": _serialize_candidate(cand),
        "status": review.status,
        "reason": review.reason,
        "queued_at": time.time(),
    }
    save_pending(pending)


def remove_pending(candidate_ids: list[str]) -> int:
    pending = load_pending()
    removed = 0
    for cid in candidate_ids:
        if pending.pop(cid, None) is not None:
            removed += 1
    if removed:
        save_pending(pending)
    return removed


def ingest_experiences(
    experiences: list[Any],
    xlib_path: str | None = None,
) -> dict[str, int]:
    """Persist approved experiences with full theorem validation."""
    from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary

    path = xlib_path or experience_library_path()
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary.load_from_file(path, theorem_lib=tlib)
    xlib.load_seed_if_empty()

    added = skipped = 0
    for exp in experiences:
        if xlib.get(exp.id):
            skipped += 1
            continue
        ok, detail = xlib.add(exp, skip_validation=False)
        if ok:
            added += 1
        else:
            skipped += 1
            logger.debug("ingest skip %s: %s", exp.id, detail)

    if added:
        xlib.save_to_file(path)
        logger.info("Ingested %d mined experiences to %s", added, path)

    return {"added": added, "skipped": skipped}


def run_pipeline(
    workspace: Path | None = None,
    *,
    days: int | None = None,
    xlib_path: str | None = None,
    auto_ingest: bool | None = None,
) -> PipelineResult:
    """Mine → review → auto-ingest or pending queue."""
    report = run_mining(workspace, days=days)
    result = PipelineResult(report=report)
    auto = auto_ingest if auto_ingest is not None else auto_ingest_enabled()
    to_ingest: list[Any] = []

    for cand in report.candidates:
        review = review_candidate(cand)
        result.reviewed.append(review)

        if review.status == "rejected":
            result.skipped += 1
            continue

        if review.status == "approved" and cand.is_high_confidence and auto:
            if review.experience is not None:
                to_ingest.append(review.experience)
            continue

        if review.status in ("approved", "pending"):
            queue_pending(cand, review)
            result.pending_saved += 1
        else:
            result.skipped += 1

    if to_ingest:
        counts = ingest_experiences(to_ingest, xlib_path=xlib_path)
        result.ingested = counts["added"]
        result.skipped += counts["skipped"]

    return result


def approve_pending(
    candidate_ids: list[str] | None = None,
    *,
    approve_all: bool = False,
    xlib_path: str | None = None,
) -> dict[str, int]:
    """Owner-approved ingest from pending queue."""
    pending = load_pending()
    if not pending:
        return {"approved": 0, "added": 0, "skipped": 0}

    ids = list(pending.keys()) if approve_all else list(candidate_ids or [])
    experiences: list[Any] = []
    approved_ids: list[str] = []

    for cid in ids:
        row = pending.get(cid)
        if not row:
            continue
        cand = _deserialize_candidate(row.get("candidate") or {})
        review = review_candidate(cand)
        if review.status != "approved" or review.experience is None:
            continue
        experiences.append(review.experience)
        approved_ids.append(cid)

    counts = ingest_experiences(experiences, xlib_path=xlib_path)
    remove_pending(approved_ids)
    return {
        "approved": len(approved_ids),
        "added": counts["added"],
        "skipped": counts["skipped"],
    }


def format_pending_lines(limit: int = 8) -> list[str]:
    pending = load_pending()
    if not pending:
        return ["经验挖掘待审: 0 条"]
    lines = [f"经验挖掘待审: {len(pending)} 条"]
    for cid, row in list(pending.items())[:limit]:
        cand = row.get("candidate") or {}
        src = str(cand.get("source") or cid)[:48]
        cat = cand.get("category", "?")
        conf = cand.get("confidence", 0)
        lines.append(f"  · {cid[:8]}… {cat} conf={conf:.2f} — {src}")
    if len(pending) > limit:
        lines.append(f"  … 另有 {len(pending) - limit} 条")
    return lines


def format_pipeline_report(result: PipelineResult) -> str:
    s = result.summary()
    m = s["mining"]
    lines = [
        "⛏️ 经验挖掘 (D3-6)",
        f"候选: {m['total_candidates']} · 高置信: {m['high_confidence']} · 扫描源: {m['sources_scanned']}",
        f"审查: 通过 {s['approved']} · 待审 {s['pending']} · 拒绝 {s['rejected']}",
        f"入库: {s['ingested']} · 入队待审: {s['pending_saved']}",
    ]
    if m.get("errors"):
        lines.append(f"错误: {', '.join(m['errors'][:2])}")
    lines.extend(format_pending_lines(limit=5))
    return "\n".join(lines)


def ingest_to_experience_library(
    report: MiningReport,
    xlib_path: str,
    min_confidence: float = 0.7,
    auto_approve: bool = False,
) -> dict[str, int]:
    """Legacy API — delegates to review + ingest pipeline."""
    added = skipped = 0
    experiences: list[Any] = []
    for cand in report.candidates:
        if cand.confidence < min_confidence and not auto_approve:
            skipped += 1
            continue
        review = review_candidate(cand)
        if review.status != "approved" or review.experience is None:
            skipped += 1
            continue
        experiences.append(review.experience)
    counts = ingest_experiences(experiences, xlib_path=xlib_path)
    return {
        "candidates": len(report.candidates),
        "added": counts["added"],
        "skipped": skipped + counts["skipped"],
    }


__all__ = [
    "CandidateExperience",
    "MiningReport",
    "PipelineResult",
    "ReviewResult",
    "approve_pending",
    "candidate_to_experience",
    "experience_library_path",
    "feeds_path",
    "format_pending_lines",
    "format_pipeline_report",
    "ingest_experiences",
    "ingest_to_experience_library",
    "load_pending",
    "mine_changelog",
    "mine_feeds",
    "mine_recent_edits",
    "mine_workspace_patterns",
    "mining_enabled",
    "pending_path",
    "queue_pending",
    "review_candidate",
    "run_mining",
    "run_pipeline",
]
