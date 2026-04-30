"""Auto-generated module index for AGENTS.md (Phase H3.1).

Walks the project's source directories, extracts the first line of each
module-level docstring, and renders a Markdown block bounded by the
``<!-- AUTO:modules -->`` / ``<!-- /AUTO:modules -->`` markers in
``AGENTS.md``. Running this script keeps the layout block in sync with
the codebase without manual edits.

Usage::

    python scripts/lib/generate_docs.py            # rewrite AGENTS.md
    python scripts/lib/generate_docs.py --check    # exit 1 if drifted
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


AUTO_BEGIN = "<!-- AUTO:modules -->"
AUTO_END = "<!-- /AUTO:modules -->"

# Top-level directories scanned for the auto module index. Order is the
# order they appear in the rendered table.
DEFAULT_DIRS: Tuple[str, ...] = (
    "harness",
    "ui",
    "tools",
    "scripts",
    "setup",
    "phase0_poc",
    "tests",
)


def summarize_module(path: Path) -> str:
    """Return the first non-empty line of ``path``'s module docstring.

    Returns an empty string if the file has no docstring, is empty, or
    fails to parse. Never raises.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not text.strip():
        return ""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    doc = ast.get_docstring(tree)
    if not doc:
        return ""
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def walk_modules(
    repo_root: Path, dirs: Sequence[str]
) -> List[Tuple[str, str]]:
    """Return ``(relpath, summary)`` tuples for every ``.py`` under ``dirs``.

    ``__init__.py`` files and anything inside ``__pycache__`` are skipped.
    Results are sorted by relpath for deterministic output.
    """
    results: List[Tuple[str, str]] = []
    for d in dirs:
        base = repo_root / d
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if path.name == "__init__.py":
                continue
            rel = path.relative_to(repo_root).as_posix()
            results.append((rel, summarize_module(path)))
    results.sort(key=lambda item: item[0])
    return results


def render_modules_block(entries: Iterable[Tuple[str, str]]) -> str:
    """Render the AUTO:modules block as Markdown.

    Groups entries by their top-level directory; each group gets a
    ``### dir/`` sub-heading followed by a two-column table.
    """
    grouped: dict[str, List[Tuple[str, str]]] = {}
    order: List[str] = []
    for rel, summary in entries:
        top = rel.split("/", 1)[0] + "/"
        if top not in grouped:
            grouped[top] = []
            order.append(top)
        grouped[top].append((rel, summary))

    lines: List[str] = [AUTO_BEGIN, ""]
    for top in order:
        lines.append(f"### {top}")
        lines.append("")
        lines.append("| Module | Summary |")
        lines.append("|---|---|")
        for rel, summary in grouped[top]:
            safe = summary.replace("|", "\\|") if summary else "_(no docstring)_"
            lines.append(f"| `{rel}` | {safe} |")
        lines.append("")
    lines.append(AUTO_END)
    return "\n".join(lines)


def update_between_markers(source: str, new_block: str) -> str:
    """Replace the AUTO:modules block in ``source`` with ``new_block``.

    ``new_block`` must itself be wrapped in :data:`AUTO_BEGIN` /
    :data:`AUTO_END`. Raises ``ValueError`` if ``source`` does not contain
    the marker pair.
    """
    begin = source.find(AUTO_BEGIN)
    end = source.find(AUTO_END)
    if begin == -1 or end == -1 or end < begin:
        raise ValueError("AUTO:modules markers not found in source")
    end_full = end + len(AUTO_END)
    return source[:begin] + new_block + source[end_full:]


def regenerate_agents_md(
    repo_root: Path,
    source: Optional[str] = None,
    dirs: Sequence[str] = DEFAULT_DIRS,
) -> str:
    """Return ``AGENTS.md`` content with a freshly rendered AUTO block.

    If ``source`` is ``None`` the current on-disk ``AGENTS.md`` is read.
    The function is pure — it does not write to disk.
    """
    agents_path = repo_root / "AGENTS.md"
    if source is None:
        source = agents_path.read_text(encoding="utf-8")
    entries = walk_modules(repo_root, dirs)
    block = render_modules_block(entries)
    return update_between_markers(source, block)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if AGENTS.md is out of date instead of rewriting it",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root (default: parent of scripts/)",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root
    agents_path = repo_root / "AGENTS.md"
    current = agents_path.read_text(encoding="utf-8")
    updated = regenerate_agents_md(repo_root, source=current)

    if args.check:
        if current != updated:
            print(
                "[generate_docs] AGENTS.md is out of date; "
                "run: python scripts/lib/generate_docs.py"
            )
            return 1
        print("[generate_docs] AGENTS.md is up to date")
        return 0

    if current == updated:
        print("[generate_docs] AGENTS.md already up to date")
        return 0
    agents_path.write_text(updated, encoding="utf-8")
    print(f"[generate_docs] rewrote {agents_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
