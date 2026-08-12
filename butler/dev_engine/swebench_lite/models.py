from __future__ import annotations

import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SWEInstance:
    instance_id: str
    category: str
    repo_name: str
    issue_title: str
    issue_body: str
    files: dict[str, str]
    oracle_patch: dict[str, tuple[str, str]]
    test_code: str
    difficulty: str = "easy"
    tags: list[str] = field(default_factory=list)

    def setup_workspace(self, workspace: Path) -> None:
        for rel_path, content in self.files.items():
            fp = workspace / rel_path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(textwrap.dedent(content), encoding="utf-8")

    def apply_oracle(self, workspace: Path) -> None:
        for rel_path, (old, new) in self.oracle_patch.items():
            fp = workspace / rel_path
            text = fp.read_text(encoding="utf-8")
            fp.write_text(text.replace(old, new), encoding="utf-8")

    def verify(self, workspace: Path) -> bool:
        test_file = workspace / "_swe_test.py"
        test_file.write_text(self.test_code, encoding="utf-8")
        result = subprocess.run(
            ["python", "-m", "pytest", str(test_file), "-q", "--tb=short"],
            capture_output=True, text=True, cwd=str(workspace), timeout=30,
        )
        return result.returncode == 0
