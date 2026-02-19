from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.repo_map.generate import build_repo_map, render_markdown, write_outputs


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.check_output(["git", *args], cwd=str(cwd))
    return out.decode("utf-8").strip()


class RepoMapGenerateTests(unittest.TestCase):
    def test_generate_outputs_and_schema(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git not available")

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _git(repo, "init")
            _git(repo, "config", "user.email", "repo-map-test@example.com")
            _git(repo, "config", "user.name", "Repo Map Test")

            (repo / "README.md").write_text("# Demo Repo\n", encoding="utf-8")
            (repo / "main.py").write_text("print('hi')\n", encoding="utf-8")
            (repo / "tools").mkdir(parents=True, exist_ok=True)
            (repo / "tools" / "example_tool.py").write_text("def ok():\n    return True\n", encoding="utf-8")

            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "init", "--no-gpg-sign")

            m = build_repo_map(repo)
            md = render_markdown(m)
            self.assertIn("# Repo Map", md)
            self.assertTrue(m.generated)

            out_dir = repo / ".codex"
            md_path, json_path = write_outputs(repo, out_dir, m)
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())

            data = json.loads(json_path.read_text(encoding="utf-8"))
            for k in [
                "version",
                "generated",
                "commit",
                "summary",
                "stack",
                "structure",
                "key_files",
                "entry_points",
                "test_command",
                "lint_command",
            ]:
                self.assertIn(k, data)
