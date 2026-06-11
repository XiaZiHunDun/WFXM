"""Coding knowledge T01–T10 advisory benchmark (CK1–CK10).

Each case supplies violating and compliant code snippets; passes when the
theorem checker flags the violation and accepts the compliant variant.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from butler.dev_engine.coding_knowledge import THEOREM_CHECKERS


@dataclass
class CKCase:
    case_id: str
    theorem_id: str
    description: str
    bad_code: str
    good_code: str


@dataclass
class CKResult:
    case_id: str
    theorem_id: str
    description: str
    passed: bool
    bad_ok: bool
    good_ok: bool
    bad_message: str = ""
    good_message: str = ""
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "theorem_id": self.theorem_id,
            "description": self.description,
            "passed": self.passed,
            "bad_ok": self.bad_ok,
            "good_ok": self.good_ok,
            "bad_message": self.bad_message,
            "good_message": self.good_message,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


@dataclass
class CKReport:
    results: list[CKResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


CK_CASES: list[CKCase] = [
    CKCase(
        "CK_T01_nondeterministic",
        "T01",
        "random() breaks determinism",
        "import random\ndef f():\n    return random.randint(0, 9)\n",
        "def f(x):\n    return x * 2\n",
    ),
    CKCase(
        "CK_T02_mixed_returns",
        "T02",
        "inconsistent return types",
        "def f(x):\n    if x:\n        return 1\n    return 'no'\n",
        "def f(x):\n    return 1 if x else 0\n",
    ),
    CKCase(
        "CK_T03_eval",
        "T03",
        "eval() bypasses type safety",
        "def load(s):\n    return eval(s)\n",
        "def load(s):\n    return int(s)\n",
    ),
    CKCase(
        "CK_T04_infinite_loop",
        "T04",
        "while True without break",
        "def spin():\n    while True:\n        pass\n",
        "def spin(n):\n    for _ in range(n):\n        pass\n",
    ),
    CKCase(
        "CK_T05_global_mutation",
        "T05",
        "global keyword mutates shared state",
        "state = 0\ndef bump():\n    global state\n    state += 1\n",
        "def bump(state):\n    return state + 1\n",
    ),
    CKCase(
        "CK_T06_bare_except",
        "T06",
        "bare except swallows errors",
        "def parse(t):\n    try:\n        return int(t)\n    except:\n        pass\n",
        "def parse(t):\n    try:\n        return int(t)\n    except ValueError:\n        raise\n",
    ),
    CKCase(
        "CK_T07_non_idempotent",
        "T07",
        "append mutates caller list",
        "def ingest(bucket, x):\n    bucket.append(x)\n    return bucket\n",
        "def ingest(bucket, x):\n    return bucket + [x]\n",
    ),
    CKCase(
        "CK_T08_unclosed_resource",
        "T08",
        "file opened without context manager",
        "def read_all(path):\n    f = open(path)\n    return f.read()\n",
        "def read_all(path):\n    with open(path) as f:\n        return f.read()\n",
    ),
    CKCase(
        "CK_T09_http_no_status",
        "T09",
        "HTTP request without status check",
        "import requests\n\ndef fetch(url):\n    return requests.get(url).json()\n",
        "import requests\n\ndef fetch(url):\n    r = requests.get(url)\n"
        "    r.raise_for_status()\n    return r.json()\n",
    ),
    CKCase(
        "CK_T10_unvalidated_input",
        "T10",
        "external input without validation",
        "def load():\n    return input()\n",
        "def load():\n    raw = input().strip()\n    if not raw.isdigit():\n        raise ValueError('bad input')\n    return int(raw)\n",
    ),
]


def _check_case(case: CKCase) -> CKResult:
    checker = THEOREM_CHECKERS.get(case.theorem_id)
    if checker is None:
        return CKResult(
            case_id=case.case_id,
            theorem_id=case.theorem_id,
            description=case.description,
            passed=False,
            bad_ok=False,
            good_ok=False,
            bad_message="checker missing",
        )
    t0 = time.time()
    bad = checker(case.bad_code)
    good = checker(case.good_code)
    bad_ok = not bad.passed
    good_ok = good.passed
    return CKResult(
        case_id=case.case_id,
        theorem_id=case.theorem_id,
        description=case.description,
        passed=bad_ok and good_ok,
        bad_ok=bad_ok,
        good_ok=good_ok,
        bad_message=bad.detail,
        good_message=good.detail,
        elapsed_ms=(time.time() - t0) * 1000,
    )


def run_coding_knowledge_benchmark(
    cases: list[CKCase] | None = None,
) -> CKReport:
    report = CKReport()
    for case in cases or CK_CASES:
        report.results.append(_check_case(case))
    return report


__all__ = [
    "CK_CASES",
    "CKCase",
    "CKReport",
    "CKResult",
    "run_coding_knowledge_benchmark",
]
