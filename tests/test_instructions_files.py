"""Structural tests for `.github/instructions/*.instructions.md` (Phase H2).

Path-scoped instruction files must:
- exist for the five scopes the plan calls out,
- carry YAML frontmatter with both ``description`` and ``applyTo`` keys,
- stay short (≤60 body lines after the frontmatter), per the plan budget.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTRUCTIONS_DIR = REPO_ROOT / ".github" / "instructions"

REQUIRED_FILES = (
    "python-correctness.instructions.md",
    "tdd.instructions.md",
    "audio-stack.instructions.md",
    "qt-webengine.instructions.md",
    "coordinator-contract.instructions.md",
    "tests.instructions.md",
)

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)", re.DOTALL)


def _split_frontmatter(text: str) -> tuple[str, str]:
    match = FRONTMATTER_RE.match(text)
    assert match, "instruction file must start with YAML frontmatter delimited by '---'"
    return match.group(1), match.group(2)


@pytest.mark.parametrize("name", REQUIRED_FILES)
def test_instruction_file_exists(name: str) -> None:
    path = INSTRUCTIONS_DIR / name
    assert path.is_file(), f"missing instruction file: {path}"


@pytest.mark.parametrize("name", REQUIRED_FILES)
def test_instruction_file_has_required_frontmatter(name: str) -> None:
    text = (INSTRUCTIONS_DIR / name).read_text(encoding="utf-8")
    front, _body = _split_frontmatter(text)
    assert re.search(r"^description:\s*['\"].+['\"]\s*$", front, re.MULTILINE), (
        f"{name}: frontmatter missing quoted 'description'"
    )
    assert re.search(r"^applyTo:\s*['\"].+['\"]\s*$", front, re.MULTILINE), (
        f"{name}: frontmatter missing quoted 'applyTo'"
    )


@pytest.mark.parametrize("name", REQUIRED_FILES)
def test_instruction_body_within_budget(name: str) -> None:
    text = (INSTRUCTIONS_DIR / name).read_text(encoding="utf-8")
    _front, body = _split_frontmatter(text)
    body_lines = [ln for ln in body.splitlines() if ln.strip()]
    assert len(body_lines) <= 60, (
        f"{name}: body has {len(body_lines)} non-blank lines (budget 60)"
    )
