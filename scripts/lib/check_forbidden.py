"""Forbidden-pattern check (Phase H1).

Mechanically enforces the prose rules already documented in
``AGENTS.md`` and ``.github/copilot-instructions.md``. Each rule is
keyed off a regex and may be scoped to specific path prefixes.

Lines containing ``# pragma: allow forbidden`` are skipped to support
intentional examples in tests and docs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from _finding import Finding


ALLOWLIST_PRAGMA = "pragma: allow forbidden"

# Files that may legitimately contain forbidden patterns as data
# (this module's own pattern table, the test suite, the plan docs).
PATH_ALLOWLIST: frozenset[str] = frozenset({
    "scripts/lib/check_forbidden.py",
    "tests/test_hooks.py",
    "docs/PLAN_HARNESS_ENGINEERING.md",
})

_BINARY_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".pdf", ".zip",
    ".tgz", ".tar", ".gz", ".whl", ".so", ".dll", ".pyd", ".pyc",
    ".wav", ".mp3", ".ogg", ".bin", ".gguf", ".ggml", ".pt", ".onnx",
})


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern[str]
    message: str
    # Path prefixes (relative, forward-slashed) the rule applies to.
    # ``None`` means "all files".
    scope: Optional[Sequence[str]] = None
    # Suffixes to apply to. ``None`` means "all suffixes".
    suffixes: Optional[Sequence[str]] = None


RULES: List[Rule] = [
    Rule(
        # Bare ``except:`` clause. Matches the start of the line so we
        # do not flag ``except Exception:`` or comments.
        pattern=re.compile(r"^\s*except\s*:\s*(?:#.*)?$"),
        message="bare except: forbidden — catch a specific exception",
        suffixes=(".py",),
    ),
    Rule(
        # ``compute_type="float16"`` is banned by AGENTS.md (must be
        # ``int8_float16`` for the 12 GB VRAM budget).
        pattern=re.compile(r"""compute_type\s*=\s*["']float16["']"""),
        message='compute_type="float16" forbidden — use "int8_float16"',
        suffixes=(".py",),
    ),
    Rule(
        # ``file://`` URLs in UI code break Monaco Web Workers.
        pattern=re.compile(r"file://"),
        message="file:// URL forbidden in UI — Monaco must use localhost HTTP",
        scope=("ui/", "phase0_poc/"),
        suffixes=(".py",),
    ),
    Rule(
        # ``git add .`` / ``git add -A`` violates the staging rule in
        # the contributor guide.
        # Trailing context is "end of word" for ``-A``/``--all``,
        # or end-of-token for ``.``. ``\b`` doesn't anchor against ``.``,
        # so use a lookahead for whitespace/end/punctuation instead.
        pattern=re.compile(r"\bgit\s+add\s+(?:\.|-A|--all)(?=$|[\s`'\"])"),
        message="`git add .` / `git add -A` forbidden — stage specific files",
    ),
    Rule(
        # ``print(`` in production code — use logging instead. Scoped
        # to ``harness/`` and ``ui/``; ``tools/`` and ``scripts/`` are
        # CLI utilities and may print freely.
        pattern=re.compile(r"^\s*print\("),
        message="print() forbidden in harness/ and ui/ — use logging",
        scope=("harness/", "ui/"),
        suffixes=(".py",),
    ),
]


def _rule_applies(rule: Rule, path: str) -> bool:
    if rule.scope is not None and not any(path.startswith(p) for p in rule.scope):
        return False
    if rule.suffixes is not None and not any(path.endswith(s) for s in rule.suffixes):
        return False
    return True


def scan_text(path: str, text: str) -> List[Finding]:
    """Scan ``text`` (the contents of ``path``) for forbidden patterns."""
    norm = path.replace("\\", "/")
    if norm in PATH_ALLOWLIST:
        return []

    applicable = [r for r in RULES if _rule_applies(r, norm)]
    if not applicable:
        return []

    findings: List[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOWLIST_PRAGMA in line:
            continue
        for rule in applicable:
            if rule.pattern.search(line):
                findings.append(Finding(path=norm, line=lineno, message=rule.message))
    return findings


def scan_paths(paths: Iterable[Path], repo_root: Path) -> List[Finding]:
    out: List[Finding] = []
    for rel in paths:
        full = repo_root / rel
        if full.suffix.lower() in _BINARY_SUFFIXES:
            continue
        if not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.extend(scan_text(str(rel).replace("\\", "/"), text))
    return out
