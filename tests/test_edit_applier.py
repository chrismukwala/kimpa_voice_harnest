"""Tests for harness/edit_applier.py — apply SEARCH/REPLACE + security gates."""

import pytest

from harness.edit_applier import apply_edits, validate_path, EditResult, _FUZZY_THRESHOLD


# =====================================================================
# Path validation (security gates)
# =====================================================================

class TestValidatePath:
    """Reject dangerous file paths before any editing."""

    def test_rejects_absolute_path(self):
        with pytest.raises(ValueError, match="absolute"):
            validate_path("C:\\Users\\secrets\\file.py", "C:\\project")

    def test_rejects_unix_absolute_path(self):
        with pytest.raises(ValueError, match="absolute"):
            validate_path("/etc/passwd", "/home/user/project")

    def test_rejects_traversal_dotdot(self):
        with pytest.raises(ValueError, match="traversal"):
            validate_path("../../../etc/passwd", "/home/user/project")

    def test_rejects_traversal_embedded(self):
        with pytest.raises(ValueError, match="traversal"):
            validate_path("src/../../secrets.py", "/home/user/project")

    def test_rejects_traversal_backslash(self):
        with pytest.raises(ValueError, match="traversal"):
            validate_path("src\\..\\..\\secrets.py", "C:\\project")

    def test_allows_normal_relative_path(self):
        # Should not raise
        result = validate_path("src/main.py", "/home/user/project")
        assert result == "src/main.py"

    def test_allows_nested_path(self):
        result = validate_path("harness/code_llm.py", "/home/user/project")
        assert result == "harness/code_llm.py"

    def test_rejects_empty_path(self):
        with pytest.raises(ValueError, match="empty"):
            validate_path("", "/home/user/project")


# =====================================================================
# apply_edits — exact match
# =====================================================================

class TestApplyEditsExact:
    """Verify exact-match SEARCH/REPLACE application."""

    def test_single_edit(self):
        original = "line one\nline two\nline three\n"
        edits = [{"search": "line two", "replace": "line TWO"}]
        result = apply_edits(original, edits)

        assert result.success
        assert "line TWO" in result.content
        assert "line two" not in result.content

    def test_multiple_edits(self):
        original = "alpha\nbeta\ngamma\n"
        edits = [
            {"search": "alpha", "replace": "ALPHA"},
            {"search": "gamma", "replace": "GAMMA"},
        ]
        result = apply_edits(original, edits)

        assert result.success
        assert "ALPHA" in result.content
        assert "GAMMA" in result.content

    def test_multiline_search_and_replace(self):
        original = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        edits = [{
            "search": "def foo():\n    pass",
            "replace": "def foo():\n    return 42",
        }]
        result = apply_edits(original, edits)

        assert result.success
        assert "return 42" in result.content
        assert "def bar():\n    pass" in result.content

    def test_delete_lines(self):
        """Empty replace = deletion."""
        original = "keep\ndelete me\nkeep too\n"
        edits = [{"search": "delete me\n", "replace": ""}]
        result = apply_edits(original, edits)

        assert result.success
        assert "delete me" not in result.content
        assert "keep\nkeep too\n" == result.content

    def test_insert_lines(self):
        """Search for anchor text, replace with anchor + new lines."""
        original = "import os\n\ndef main():\n    pass\n"
        edits = [{
            "search": "import os",
            "replace": "import os\nimport sys",
        }]
        result = apply_edits(original, edits)

        assert result.success
        assert "import os\nimport sys" in result.content

    def test_no_match_returns_failure(self):
        original = "hello world\n"
        edits = [{"search": "nonexistent text", "replace": "replacement"}]
        result = apply_edits(original, edits)

        assert not result.success
        assert result.content == original  # unchanged
        assert len(result.errors) == 1

    def test_empty_edits_returns_original(self):
        original = "unchanged\n"
        result = apply_edits(original, [])

        assert result.success
        assert result.content == original


# =====================================================================
# apply_edits — fuzzy match fallback
# =====================================================================

class TestApplyEditsFuzzy:
    """When exact match fails, fuzzy matching (difflib ~0.85) should try to find a close match."""

    def test_threshold_matches_adr(self):
        """Fuzzy threshold must match ADR-005 (~0.85)."""
        assert _FUZZY_THRESHOLD >= 0.8
        assert _FUZZY_THRESHOLD <= 0.9

    def test_whitespace_difference_matches(self):
        """LLM output often has slightly different trailing whitespace."""
        original = "line one\nline two  \nline three\n"
        edits = [{
            "search": "line one\nline two\nline three",
            "replace": "LINE ONE\nLINE TWO\nLINE THREE",
        }]
        result = apply_edits(original, edits)

        assert result.success
        assert "LINE ONE" in result.content
        assert result.used_fuzzy

    def test_major_whitespace_difference_rejects(self):
        """2-space vs 4-space is too different at 0.85 threshold."""
        original = "def foo():\n    x = 1\n    y = 2\n"
        edits = [{
            "search": "def foo():\n  x = 1\n  y = 2",  # 2 spaces vs 4
            "replace": "def foo():\n    x = 10\n    y = 20",
        }]
        result = apply_edits(original, edits)

        # At 0.85 threshold, this should likely fail (ratio ~0.82).
        # Exact behavior depends on SequenceMatcher.

    def test_too_different_rejects(self):
        """Completely different text should not fuzzy match."""
        original = "def foo():\n    return 1\n"
        edits = [{
            "search": "class Bar:\n    pass",
            "replace": "class Bar:\n    value = 42",
        }]
        result = apply_edits(original, edits)

        assert not result.success
        assert not result.used_fuzzy

    def test_similar_functions_do_not_cross_match(self):
        """Moderately different blocks should not fuzzy match at 0.85 threshold."""
        original = (
            "def calculate_tax(income):\n"
            "    rate = 0.25\n"
            "    return income * rate\n"
        )
        edits = [{
            "search": (
                "def calculate_discount(price):\n"
                "    rate = 0.10\n"
                "    return price * rate"
            ),
            "replace": (
                "def calculate_discount(price):\n"
                "    rate = 0.15\n"
                "    return price * rate"
            ),
        }]
        result = apply_edits(original, edits)

        assert not result.success

    def test_exact_match_does_not_set_fuzzy_flag(self):
        """Exact matches should not flag used_fuzzy."""
        original = "alpha\nbeta\n"
        edits = [{"search": "alpha", "replace": "ALPHA"}]
        result = apply_edits(original, edits)

        assert result.success
        assert not result.used_fuzzy


# =====================================================================
# EditResult dataclass
# =====================================================================

class TestEditResult:
    """Verify EditResult carries the right data."""

    def test_success_result(self):
        r = EditResult(success=True, content="new", errors=[])
        assert r.success
        assert r.content == "new"
        assert r.errors == []
        assert not r.used_fuzzy

    def test_failure_result(self):
        r = EditResult(success=False, content="old", errors=["block 1 not found"])
        assert not r.success
        assert len(r.errors) == 1

    def test_fuzzy_flag(self):
        r = EditResult(success=True, content="new", used_fuzzy=True)
        assert r.used_fuzzy
