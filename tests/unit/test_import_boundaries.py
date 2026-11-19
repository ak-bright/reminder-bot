"""Enforce the architecture rule: core/ and ai/ never import channels/ or telegram.

We read each source file's imports with the `ast` module (without running the code).
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "reminderbot"
FORBIDDEN = ("reminderbot.channels", "telegram")


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def python_files(*packages: str) -> list[Path]:
    files = []
    for package in packages:
        folder = SRC / package
        if folder.exists():  # ai/ doesn't exist until M4
            files.extend(folder.rglob("*.py"))
    return files


@pytest.mark.parametrize("path", python_files("core", "ai"), ids=lambda p: p.name)
def test_core_and_ai_do_not_import_channels(path):
    for module in imported_modules(path):
        assert not module.startswith(FORBIDDEN), f"{path.name} imports {module}"


def test_channel_agnostic_files_do_not_import_telegram():
    for name in ("base.py", "router.py"):
        for module in imported_modules(SRC / "channels" / name):
            assert not module.startswith("telegram"), f"{name} imports {module}"


@pytest.mark.parametrize("path", python_files("scheduler"), ids=lambda p: p.name)
def test_scheduler_does_not_import_telegram(path):
    # The scheduler sends through the Channel interface, so it works for WhatsApp too.
    for module in imported_modules(path):
        assert not module.startswith(("telegram", "reminderbot.channels.telegram"))
