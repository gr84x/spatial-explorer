#!/usr/bin/env python3
"""Generate a lightweight repository map for LLM-assisted workflows.

Outputs (relative to repo root by default):
- .codex/repo-map.json
- .codex/repo-map.md

The JSON format is intentionally small and stable for prompt injection.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}


TOP_LEVEL_DESCRIPTIONS = {
    "agents": "Agent configs and prompts",
    "activity": "Activity logs and reporting",
    "browser": "Browser automation",
    "cc": "Command-center related tooling",
    "config": "Configuration",
    "content": "Content tooling",
    "cron": "Cron/automation workflows",
    "dispatch": "Task dispatch and worker orchestration",
    "knowledge": "Workflow and knowledge base markdown",
    "llm": "LLM client and helpers",
    "notifications": "Notification integrations",
    "openclaw": "OpenClaw runtime integration",
    "qa": "Quality assurance tooling",
    "research": "Research helpers",
    "roadmap": "Task and roadmap management",
    "search": "Search integrations",
    "security": "Security checks/tools",
    "tests": "Test suite",
    "tools": "Misc tools",
    "validation": "Validation utilities",
}


@dataclass(frozen=True)
class RepoMap:
    version: int
    generated: str
    commit: str
    summary: str
    stack: list[str]
    structure: dict[str, str]
    key_files: list[dict[str, Any]]
    entry_points: list[str]
    test_command: str
    lint_command: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generated": self.generated,
            "commit": self.commit,
            "summary": self.summary,
            "stack": self.stack,
            "structure": self.structure,
            "key_files": self.key_files,
            "entry_points": self.entry_points,
            "test_command": self.test_command,
            "lint_command": self.lint_command,
        }


def _utc_now_iso() -> str:
    return dt.datetime.now(tz=dt.timezone.utc).replace(microsecond=0).isoformat()


def _run_git(repo_root: Path, args: list[str]) -> str | None:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception:
        return None
    return p.stdout.strip() or None


def get_commit_sha(repo_root: Path) -> str:
    sha = _run_git(repo_root, ["rev-parse", "HEAD"])
    return sha or "unknown"


def read_first_readme_line(repo_root: Path) -> str | None:
    for name in ("README.md", "README.txt", "README.rst", "readme.md"):
        p = repo_root / name
        if not p.exists():
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # Prefer the first markdown header, otherwise first non-empty line.
        for line in txt.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                return s.lstrip("# ").strip() or None
            return s
    return None


def infer_stack(repo_root: Path) -> list[str]:
    stack: set[str] = set()

    # Language signals
    if any(repo_root.rglob("*.py")):
        stack.add("python")
    if (repo_root / "package.json").exists() or any(repo_root.rglob("package.json")):
        stack.add("node")
    if any(repo_root.rglob("*.ts")):
        stack.add("typescript")
    if any(repo_root.rglob("*.go")):
        stack.add("go")

    # Framework signals (cheap heuristics)
    content = ""
    for p in (repo_root / "dispatch").glob("**/*.py") if (repo_root / "dispatch").exists() else []:
        try:
            content += p.read_text(encoding="utf-8", errors="ignore")[:4000] + "\n"
        except Exception:
            pass
        if len(content) > 20000:
            break

    if "fastapi" in content.lower():
        stack.add("fastapi")
    if "flask" in content.lower():
        stack.add("flask")

    return sorted(stack)


def describe_top_level(repo_root: Path) -> dict[str, str]:
    structure: dict[str, str] = {}
    for child in sorted(repo_root.iterdir()):
        if child.name.startswith("."):
            continue
        if child.name in DEFAULT_EXCLUDE_DIRS:
            continue
        if child.is_dir():
            desc = TOP_LEVEL_DESCRIPTIONS.get(child.name, "Module / scripts")
            structure[f"{child.name}/"] = desc
    return structure


def _is_text_file(path: Path) -> bool:
    # Avoid reading huge binaries; treat common text extensions as text.
    if path.suffix.lower() in {
        ".py",
        ".md",
        ".txt",
        ".json",
        ".toml",
        ".yml",
        ".yaml",
        ".ini",
        ".cfg",
        ".sh",
    }:
        return True
    # Otherwise, limit by size and attempt decode.
    try:
        return path.stat().st_size <= 512 * 1024
    except OSError:
        return False


def count_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


_MAIN_RE = re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]")


def find_entry_points(repo_root: Path, *, max_files: int = 25) -> list[str]:
    entry: list[str] = []

    # Common CLI/script file names first.
    preferred = [
        "main.py",
        "__main__.py",
        "cli.py",
        "app.py",
        "run.py",
        "server.py",
        "build_prompt_cli.py",
    ]

    for name in preferred:
        for p in repo_root.rglob(name):
            if any(part in DEFAULT_EXCLUDE_DIRS for part in p.parts):
                continue
            rel = p.relative_to(repo_root).as_posix()
            if rel not in entry:
                entry.append(rel)
            if len(entry) >= max_files:
                return entry

    # Generic: look for __main__ blocks.
    for p in repo_root.rglob("*.py"):
        if any(part in DEFAULT_EXCLUDE_DIRS for part in p.parts):
            continue
        if not _is_text_file(p):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if _MAIN_RE.search(txt):
            rel = p.relative_to(repo_root).as_posix()
            if rel not in entry:
                entry.append(rel)
        if len(entry) >= max_files:
            break

    return entry


def guess_purpose(path: str) -> str:
    # Focus on stable, small purposes.
    base = os.path.basename(path)
    if base in {"README.md", "README.txt", "README.rst"}:
        return "Project overview"
    if base.startswith("test_") or "/tests/" in f"/{path}/":
        return "Tests"
    if base.endswith("_cli.py") or base in {"cli.py", "__main__.py"}:
        return "CLI entry point"
    if base == "build_prompt_cli.py":
        return "Prompt builder CLI"
    if path.startswith("dispatch/"):
        return "Dispatch / orchestration"
    if path.startswith("cron/"):
        return "Cron automation"
    if path.startswith("knowledge/"):
        return "Knowledge/workflow docs"
    if path.startswith("tools/repo_map/"):
        return "Repo-map generator"
    return "Source file"


def select_key_files(repo_root: Path, entry_points: list[str]) -> list[dict[str, Any]]:
    candidates: list[Path] = []

    # README first (if present)
    for name in ("README.md", "README.txt", "README.rst"):
        p = repo_root / name
        if p.exists():
            candidates.append(p)
            break

    # Entry points are usually important.
    for rel in entry_points:
        p = repo_root / rel
        if p.exists():
            candidates.append(p)

    # Add some known likely important files if present.
    for rel in [
        "dispatch/prompt_builder.py",
        "dispatch/build_prompt_cli.py",
        "dispatch/worker_status.py",
        "dispatch/finalize_task.py",
        "tools/repo_map/generate.py",
    ]:
        p = repo_root / rel
        if p.exists():
            candidates.append(p)

    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for p in candidates:
        rel = p.relative_to(repo_root).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        out.append({"path": rel, "purpose": guess_purpose(rel), "lines": count_lines(p)})
        if len(out) >= 15:
            break
    return out


def infer_commands(repo_root: Path) -> tuple[str, str]:
    test_cmd = "pytest"
    if (repo_root / "tests").exists():
        test_cmd = "pytest -q"

    # Prefer ruff if there are python files; otherwise empty.
    lint_cmd = "ruff check ."
    if not any(repo_root.rglob("*.py")):
        lint_cmd = ""

    return test_cmd, lint_cmd


def build_repo_map(repo_root: Path) -> RepoMap:
    repo_root = repo_root.resolve()

    summary = read_first_readme_line(repo_root) or "Repository of automation tools and scripts"
    stack = infer_stack(repo_root)
    structure = describe_top_level(repo_root)
    entry_points = find_entry_points(repo_root)
    key_files = select_key_files(repo_root, entry_points)
    test_cmd, lint_cmd = infer_commands(repo_root)

    return RepoMap(
        version=1,
        generated=_utc_now_iso(),
        commit=get_commit_sha(repo_root),
        summary=summary,
        stack=stack,
        structure=structure,
        key_files=key_files,
        entry_points=entry_points,
        test_command=test_cmd,
        lint_command=lint_cmd,
    )


def render_markdown(m: RepoMap) -> str:
    lines: list[str] = []
    lines.append("# Repo Map")
    lines.append("")
    lines.append(f"Generated: `{m.generated}`")
    lines.append(f"Commit: `{m.commit}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(m.summary)
    lines.append("")

    lines.append("## Stack")
    lines.append("")
    lines.append(", ".join(m.stack) if m.stack else "(unknown)")
    lines.append("")

    lines.append("## Structure")
    lines.append("")
    for k, v in m.structure.items():
        lines.append(f"- `{k}` — {v}")
    lines.append("")

    lines.append("## Key files")
    lines.append("")
    lines.append("| Path | Purpose | Lines |")
    lines.append("| --- | --- | ---: |")
    for kf in m.key_files:
        lines.append(f"| `{kf['path']}` | {kf['purpose']} | {kf['lines']} |")
    lines.append("")

    lines.append("## Entry points")
    lines.append("")
    if m.entry_points:
        for ep in m.entry_points:
            lines.append(f"- `{ep}`")
    else:
        lines.append("(none detected)")
    lines.append("")

    lines.append("## Commands")
    lines.append("")
    lines.append(f"- Test: `{m.test_command}`")
    lines.append(f"- Lint: `{m.lint_command}`")
    lines.append("")

    return "\n".join(lines)


def write_outputs(repo_root: Path, out_dir: Path, m: RepoMap) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "repo-map.json"
    md_path = out_dir / "repo-map.md"

    json_path.write_text(json.dumps(m.to_dict(), indent=2, sort_keys=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(m) + "\n", encoding="utf-8")

    return md_path, json_path


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate .codex repo-map artifacts")
    p.add_argument("--root", type=Path, default=Path("."), help="Repo root (default: .)")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: <root>/.codex)",
    )
    return p.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root: Path = args.root
    out_dir: Path = args.out_dir if args.out_dir is not None else repo_root / ".codex"

    m = build_repo_map(repo_root)
    write_outputs(repo_root, out_dir, m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
