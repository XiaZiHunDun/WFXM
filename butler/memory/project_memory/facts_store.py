from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from butler.io.safe_load import safe_load_json


class ProjectFactsStore:
    def __init__(self, facts_path: Path):
        self.path = Path(facts_path)
        self._facts: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        with self._lock:
            self._facts = safe_load_json(
                self.path, default={}, kind="memory_project_facts",
            )
            if not isinstance(self._facts, dict):
                self._facts = {}

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._facts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        from butler.memory.project_memory_ops import sync_facts_to_knowledge_db_safe
        sync_facts_to_knowledge_db_safe(self.path)

    def auto_extract(self, project_dir: Path) -> dict[str, Any]:
        root = Path(project_dir).resolve()
        facts: dict[str, Any] = {"extracted_at": time.time()}

        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            facts["build_system"] = "python"
            ptext = pyproject.read_text(encoding="utf-8", errors="replace").lower()
            if "fastapi" in ptext:
                facts.setdefault("frameworks", []).append("FastAPI")
            if "django" in ptext:
                facts.setdefault("frameworks", []).append("Django")
            if "flask" in ptext:
                facts.setdefault("frameworks", []).append("Flask")

        requirements = root / "requirements.txt"
        if requirements.exists():
            facts["build_system"] = facts.get("build_system", "python")
            deps = [
                ln.split("==")[0].split(">=")[0].strip()
                for ln in requirements.read_text(encoding="utf-8", errors="replace").splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            facts["python_dependencies"] = deps[:30]

        pkg_json = root / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
                facts["build_system"] = facts.get("build_system", "node")
                facts["node_dependencies"] = list(pkg.get("dependencies", {}).keys())[:30]
                deps = pkg.get("dependencies", {})
                if isinstance(deps, dict):
                    if "react" in deps:
                        facts.setdefault("frameworks", []).append("React")
                    if "vue" in deps:
                        facts.setdefault("frameworks", []).append("Vue")
                    if "next" in deps:
                        facts.setdefault("frameworks", []).append("Next.js")
            except (json.JSONDecodeError, OSError):
                pass

        go_mod = root / "go.mod"
        if go_mod.exists():
            facts["build_system"] = facts.get("build_system", "go")

        cargo = root / "Cargo.toml"
        if cargo.exists():
            facts["build_system"] = facts.get("build_system", "rust")

        top_dirs = sorted(
            [
                d.name
                for d in root.iterdir()
                if d.is_dir()
                and not d.name.startswith(".")
                and d.name
                not in ("node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build")
            ]
        )[:20]
        facts["directory_structure"] = top_dirs

        py_count = len(list(root.rglob("*.py")))
        js_count = len(list(root.rglob("*.js"))) + len(list(root.rglob("*.ts")))
        tsx_count = len(list(root.rglob("*.tsx")))
        facts["file_counts"] = {
            "python": py_count,
            "javascript_typescript": js_count + tsx_count,
        }

        with self._lock:
            self._facts = facts
            self._save_unlocked()
        return facts

    def refresh(self, project_dir: Path | None = None) -> dict[str, Any]:
        root = Path(project_dir or self.path.parent.parent.parent).resolve()
        return self.auto_extract(root)

    def format_for_prompt(self) -> str:
        with self._lock:
            facts = dict(self._facts)
        if not facts:
            return ""
        parts: list[str] = []
        if facts.get("build_system"):
            parts.append(f"Build: {facts['build_system']}")
        fw = facts.get("frameworks")
        if fw:
            uniq = []
            for x in fw:
                if x not in uniq:
                    uniq.append(x)
            parts.append(f"Frameworks: {', '.join(uniq)}")
        dirs = facts.get("directory_structure")
        if dirs:
            parts.append(f"Top-level dirs: {', '.join(dirs[:12])}")
        fc = facts.get("file_counts")
        if fc:
            parts.append(
                f"Approx file counts: py={fc.get('python', 0)}, js/ts/tsx={fc.get('javascript_typescript', 0)}"
            )
        return "\n".join(parts)