"""Tests for doc-generation + drift-detector libraries (Phase H3).

Covers ``scripts/lib/generate_docs.py`` (auto-generated module index in
``AGENTS.md``) and ``scripts/lib/validate_docs.py`` (drift warning when
``harness/*.py`` is changed without a matching ``docs/PROGRESS.md`` note).
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_LIB_DIR = _REPO_ROOT / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))


# --- generate_docs ---------------------------------------------------------

class TestSummarizeModule:
    def test_returns_first_docstring_line(self, tmp_path: Path):
        import generate_docs

        f = tmp_path / "m.py"
        f.write_text(
            '"""First summary line.\n\nMore prose below.\n"""\n', encoding="utf-8"
        )
        assert generate_docs.summarize_module(f) == "First summary line."

    def test_returns_empty_when_no_docstring(self, tmp_path: Path):
        import generate_docs

        f = tmp_path / "m.py"
        f.write_text("x = 1\n", encoding="utf-8")
        assert generate_docs.summarize_module(f) == ""

    def test_handles_single_line_docstring(self, tmp_path: Path):
        import generate_docs

        f = tmp_path / "m.py"
        f.write_text('"""Quick summary."""\n', encoding="utf-8")
        assert generate_docs.summarize_module(f) == "Quick summary."

    def test_skips_dunder_init_when_empty(self, tmp_path: Path):
        import generate_docs

        f = tmp_path / "__init__.py"
        f.write_text("", encoding="utf-8")
        # An empty __init__.py should produce an empty summary, not crash.
        assert generate_docs.summarize_module(f) == ""


class TestWalkModules:
    def test_collects_existing_harness_modules(self):
        import generate_docs

        entries = generate_docs.walk_modules(
            _REPO_ROOT, ["harness"]
        )
        rels = {rel for rel, _ in entries}
        # H3.1 explicitly calls out these as currently missing from the layout.
        assert "harness/edit_applier.py" in rels
        assert "harness/git_ops.py" in rels
        assert "harness/llm_tools.py" in rels
        assert "harness/model_manager.py" in rels
        assert "harness/repo_map.py" in rels

    def test_results_are_sorted(self):
        import generate_docs

        entries = generate_docs.walk_modules(_REPO_ROOT, ["harness"])
        rels = [rel for rel, _ in entries]
        assert rels == sorted(rels)

    def test_excludes_pycache_and_dunders(self):
        import generate_docs

        entries = generate_docs.walk_modules(_REPO_ROOT, ["harness"])
        rels = [rel for rel, _ in entries]
        assert not any("__pycache__" in r for r in rels)
        assert not any(r.endswith("__init__.py") for r in rels)


class TestRenderModulesBlock:
    def test_block_contains_markers_and_entries(self):
        import generate_docs

        block = generate_docs.render_modules_block([
            ("harness/foo.py", "Foo summary."),
            ("ui/bar.py", "Bar summary."),
        ])
        assert generate_docs.AUTO_BEGIN in block
        assert generate_docs.AUTO_END in block
        assert "harness/foo.py" in block
        assert "Foo summary." in block
        assert "ui/bar.py" in block

    def test_block_groups_by_top_level_dir(self):
        import generate_docs

        block = generate_docs.render_modules_block([
            ("harness/foo.py", "Foo."),
            ("ui/bar.py", "Bar."),
        ])
        # Each top-level dir gets a sub-heading.
        assert "harness/" in block
        assert "ui/" in block
        # Foo entry should appear after the harness/ heading and before ui/.
        h_idx = block.index("harness/")
        u_idx = block.index("ui/")
        foo_idx = block.index("harness/foo.py")
        bar_idx = block.index("ui/bar.py")
        assert h_idx < foo_idx < u_idx < bar_idx


class TestUpdateBetweenMarkers:
    def test_replaces_only_block_content(self):
        import generate_docs

        original = textwrap.dedent(
            f"""\
            # Title

            Before.

            {generate_docs.AUTO_BEGIN}
            old content
            {generate_docs.AUTO_END}

            After.
            """
        )
        new_block = (
            f"{generate_docs.AUTO_BEGIN}\nnew content\n{generate_docs.AUTO_END}"
        )
        out = generate_docs.update_between_markers(original, new_block)
        assert "old content" not in out
        assert "new content" in out
        assert "Before." in out
        assert "After." in out

    def test_raises_when_markers_missing(self):
        import generate_docs

        with pytest.raises(ValueError):
            generate_docs.update_between_markers(
                "no markers here", f"{generate_docs.AUTO_BEGIN}\n{generate_docs.AUTO_END}"
            )


class TestRegenerateIdempotent:
    def test_running_twice_produces_same_output(self):
        import generate_docs

        first = generate_docs.regenerate_agents_md(_REPO_ROOT)
        # Re-render against the just-produced content.
        second = generate_docs.regenerate_agents_md(_REPO_ROOT, source=first)
        assert first == second


class TestAgentsMdHasMarkers:
    def test_agents_md_contains_auto_markers(self):
        import generate_docs

        agents = (_REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert generate_docs.AUTO_BEGIN in agents
        assert generate_docs.AUTO_END in agents


# --- validate_docs ---------------------------------------------------------

class TestValidateDocsDrift:
    def test_warns_when_harness_changed_without_progress(self):
        import validate_docs

        msg = validate_docs.drift_warning(
            [Path("harness/coordinator.py")]
        )
        assert msg is not None
        assert "PROGRESS.md" in msg

    def test_silent_when_progress_also_staged(self):
        import validate_docs

        msg = validate_docs.drift_warning(
            [Path("harness/coordinator.py"), Path("docs/PROGRESS.md")]
        )
        assert msg is None

    def test_silent_for_non_harness_changes(self):
        import validate_docs

        msg = validate_docs.drift_warning([Path("ui/ai_panel.py")])
        assert msg is None

    def test_handles_windows_paths(self):
        import validate_docs

        msg = validate_docs.drift_warning([Path("harness\\coordinator.py")])
        assert msg is not None
