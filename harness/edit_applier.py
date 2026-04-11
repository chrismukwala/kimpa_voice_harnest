"""Edit applier — apply SEARCH/REPLACE blocks to file content with security gates."""

import os
import difflib
from dataclasses import dataclass, field
from typing import List

# Minimum similarity ratio for fuzzy matching (ADR-005: ~0.85 threshold).
_FUZZY_THRESHOLD = 0.85


@dataclass
class EditResult:
    """Outcome of applying edits to file content."""
    success: bool
    content: str
    errors: List[str] = field(default_factory=list)
    used_fuzzy: bool = False


def validate_path(path: str, project_root: str) -> str:
    """Validate a file path is safe to edit.

    Raises ValueError if the path is absolute, empty, or attempts traversal.
    Returns the sanitized path on success.
    """
    if not path or not path.strip():
        raise ValueError("File path is empty")

    # Normalize separators for cross-platform checks.
    normalized = path.replace("\\", "/")

    # Reject absolute paths.
    if os.path.isabs(path) or normalized.startswith("/"):
        raise ValueError(f"Refusing absolute path: {path}")

    # Reject path traversal.
    parts = normalized.split("/")
    if ".." in parts:
        raise ValueError(f"Path traversal detected: {path}")

    return path


def _fuzzy_find_and_replace(content: str, search: str, replace: str) -> str | None:
    """Try to find a fuzzy match for *search* in *content* and apply the replacement.

    Uses difflib SequenceMatcher.  Returns the modified content on success,
    or None if no sufficiently similar block is found.
    """
    search_lines = search.splitlines(keepends=True)
    content_lines = content.splitlines(keepends=True)
    n = len(search_lines)

    if n == 0:
        return None

    best_ratio = 0.0
    best_start = -1
    search_text = "".join(search_lines)

    for i in range(len(content_lines) - n + 1):
        candidate_text = "".join(content_lines[i:i + n])
        ratio = difflib.SequenceMatcher(
            None, search_text, candidate_text
        ).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = i

    if best_ratio >= _FUZZY_THRESHOLD and best_start >= 0:
        replace_lines = replace.splitlines(keepends=True)
        new_lines = content_lines[:best_start] + replace_lines + content_lines[best_start + n:]
        return "".join(new_lines)

    return None


def apply_edits(content: str, edits: list[dict]) -> EditResult:
    """Apply a list of SEARCH/REPLACE edits to file content.

    Each edit is {"search": str, "replace": str}.
    Tries exact match first, then fuzzy fallback.

    Returns an EditResult with the modified content and any errors.
    """
    if not edits:
        return EditResult(success=True, content=content)

    modified = content
    errors: list[str] = []
    used_fuzzy = False

    for i, edit in enumerate(edits):
        search = edit["search"]
        replace = edit["replace"]

        # Try exact match first.
        if search in modified:
            modified = modified.replace(search, replace, 1)
            continue

        # Fuzzy fallback.
        fuzzy_result = _fuzzy_find_and_replace(modified, search, replace)
        if fuzzy_result is not None:
            modified = fuzzy_result
            used_fuzzy = True
            continue

        errors.append(f"Block {i + 1}: no match found for SEARCH text")

    if errors:
        return EditResult(success=False, content=content, errors=errors)

    return EditResult(success=True, content=modified, used_fuzzy=used_fuzzy)
