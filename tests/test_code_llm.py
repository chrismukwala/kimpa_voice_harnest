"""Tests for harness/code_llm.py — SEARCH/REPLACE parser + prose extractor."""

from unittest.mock import patch, MagicMock

import pytest

from harness.code_llm import parse_search_replace, extract_prose, chat, SYSTEM_PROMPT, MODEL


# =====================================================================
# parse_search_replace
# =====================================================================

class TestParseSearchReplace:
    """Verify the SEARCH/REPLACE regex parser handles all expected formats."""

    def test_single_block(self):
        text = (
            "Here is the fix.\n"
            "<<<<<<< SEARCH\n"
            "old line\n"
            "=======\n"
            "new line\n"
            ">>>>>>> REPLACE"
        )
        result = parse_search_replace(text)
        assert len(result) == 1
        assert result[0]["search"] == "old line"
        assert result[0]["replace"] == "new line"

    def test_multiple_blocks(self):
        text = (
            "<<<<<<< SEARCH\n"
            "first old\n"
            "=======\n"
            "first new\n"
            ">>>>>>> REPLACE\n"
            "\n"
            "<<<<<<< SEARCH\n"
            "second old\n"
            "=======\n"
            "second new\n"
            ">>>>>>> REPLACE"
        )
        result = parse_search_replace(text)
        assert len(result) == 2
        assert result[0]["search"] == "first old"
        assert result[1]["search"] == "second old"

    def test_multiline_search_and_replace(self):
        text = (
            "<<<<<<< SEARCH\n"
            "line one\n"
            "line two\n"
            "line three\n"
            "=======\n"
            "replaced one\n"
            "replaced two\n"
            ">>>>>>> REPLACE"
        )
        result = parse_search_replace(text)
        assert len(result) == 1
        assert "line two" in result[0]["search"]
        assert "replaced two" in result[0]["replace"]

    def test_eight_chevrons(self):
        """Parser should accept 6-8 chevrons (lenient regex)."""
        text = (
            "<<<<<<<< SEARCH\n"
            "old\n"
            "========\n"
            "new\n"
            ">>>>>>>> REPLACE"
        )
        result = parse_search_replace(text)
        assert len(result) == 1

    def test_six_chevrons(self):
        text = (
            "<<<<<< SEARCH\n"
            "old\n"
            "======\n"
            "new\n"
            ">>>>>> REPLACE"
        )
        result = parse_search_replace(text)
        assert len(result) == 1

    def test_case_insensitive(self):
        text = (
            "<<<<<<< search\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> replace"
        )
        result = parse_search_replace(text)
        assert len(result) == 1

    def test_strips_fenced_code_block(self):
        text = (
            "```python\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> REPLACE\n"
            "```"
        )
        result = parse_search_replace(text)
        assert len(result) == 1

    def test_no_blocks_returns_empty_list(self):
        text = "Just some plain text with no edit blocks."
        result = parse_search_replace(text)
        assert result == []

    def test_empty_replace_block(self):
        """Deleting lines — replace is empty."""
        text = (
            "<<<<<<< SEARCH\n"
            "delete this line\n"
            "=======\n"
            "\n"
            ">>>>>>> REPLACE"
        )
        result = parse_search_replace(text)
        assert len(result) == 1
        assert result[0]["search"] == "delete this line"

    def test_five_chevrons_rejected(self):
        """Fewer than 6 chevrons should NOT match."""
        text = (
            "<<<<< SEARCH\n"
            "old\n"
            "=====\n"
            "new\n"
            ">>>>> REPLACE"
        )
        result = parse_search_replace(text)
        assert result == []


# =====================================================================
# extract_prose
# =====================================================================

class TestExtractProse:
    """Verify prose extraction strips SEARCH/REPLACE blocks, keeps spoken text."""

    def test_prose_only(self):
        text = "I added a docstring to the function."
        result = extract_prose(text)
        assert result == text

    def test_strips_single_block(self):
        text = (
            "I fixed the bug.\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> REPLACE\n"
            "That should do it."
        )
        result = extract_prose(text)
        assert "old" not in result
        assert "I fixed the bug." in result
        assert "That should do it." in result

    def test_strips_multiple_blocks(self):
        text = (
            "Two changes:\n"
            "<<<<<<< SEARCH\n"
            "old_alpha\n"
            "=======\n"
            "new_beta\n"
            ">>>>>>> REPLACE\n"
            "And also:\n"
            "<<<<<<< SEARCH\n"
            "old_gamma\n"
            "=======\n"
            "new_delta\n"
            ">>>>>>> REPLACE"
        )
        result = extract_prose(text)
        assert "Two changes:" in result
        assert "And also:" in result
        assert "old_alpha" not in result
        assert "old_gamma" not in result

    def test_collapses_excessive_blank_lines(self):
        text = "Line one.\n\n\n\n\nLine two."
        result = extract_prose(text)
        assert "\n\n\n" not in result

    def test_empty_string(self):
        assert extract_prose("") == ""


# =====================================================================
# chat (mocked Ollama)
# =====================================================================

class TestChat:
    """Verify chat() builds correct messages and calls the OpenAI-compatible API properly."""

    def _mock_response(self, content="Hello!"):
        """Build a mock ChatCompletion response."""
        msg = MagicMock()
        msg.content = content
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    @patch("harness.code_llm.OpenAI")
    def test_basic_query_no_context(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_response("Hello!")

        result = chat("say hello", api_key="test-key")

        assert result == "Hello!"
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == MODEL
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        assert "say hello" in messages[1]["content"]

    @patch("harness.code_llm.OpenAI")
    def test_query_with_context(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_response("Done.")

        result = chat("fix the bug", context="def foo(): pass", api_key="test-key")

        user_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "def foo(): pass" in user_msg
        assert "fix the bug" in user_msg

    @patch("harness.code_llm.OpenAI")
    def test_query_with_repo_map(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_response("OK.")

        chat("add tests", repo_map="src/main.py: class App", api_key="test-key")

        user_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "src/main.py: class App" in user_msg

    @patch("harness.code_llm.OpenAI")
    def test_api_key_passed_to_client(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_response("OK.")

        chat("test", api_key="my-secret-key")

        from harness.code_llm import BASE_URL
        MockOpenAI.assert_called_once_with(api_key="my-secret-key", base_url=BASE_URL)

    @patch("harness.code_llm.OpenAI")
    def test_timeout_is_set(self, MockOpenAI):
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_response("OK.")

        from harness.code_llm import REQUEST_TIMEOUT
        chat("test", api_key="test-key")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["timeout"] == REQUEST_TIMEOUT

    def test_no_api_key_raises_runtime(self):
        """Missing API key should raise RuntimeError immediately."""
        with pytest.raises(RuntimeError, match="No API key configured"):
            chat("test")

    def test_none_api_key_raises_runtime(self):
        with pytest.raises(RuntimeError, match="No API key configured"):
            chat("test", api_key=None)

    @patch("harness.code_llm.OpenAI")
    def test_auth_error_raises_runtime(self, MockOpenAI):
        from openai import AuthenticationError
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.headers = {}
        err = AuthenticationError(
            message="invalid key",
            response=mock_resp,
            body=None,
        )
        mock_client.chat.completions.create.side_effect = err

        with pytest.raises(RuntimeError, match="Invalid API key"):
            chat("test", api_key="bad-key")

    @patch("harness.code_llm.OpenAI")
    def test_connection_error_raises_runtime(self, MockOpenAI):
        from openai import APIConnectionError
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )

        with pytest.raises(RuntimeError, match="LLM unavailable"):
            chat("test", api_key="test-key")

    @patch("harness.code_llm.OpenAI")
    def test_timeout_error_raises_runtime(self, MockOpenAI):
        from openai import APITimeoutError
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APITimeoutError(
            request=MagicMock()
        )

        with pytest.raises(RuntimeError, match="LLM unavailable"):
            chat("test", api_key="test-key")

    @patch("harness.code_llm.OpenAI")
    def test_context_truncated_when_oversized(self, MockOpenAI):
        """Context longer than _MAX_CONTEXT_CHARS is truncated."""
        from harness.code_llm import _MAX_CONTEXT_CHARS

        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_response("OK.")

        big_context = "x" * (_MAX_CONTEXT_CHARS + 5000)
        chat("query", context=big_context, api_key="test-key")

        user_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "... (truncated)" in user_msg
        assert len(user_msg) < len(big_context)

    @patch("harness.code_llm.OpenAI")
    def test_context_not_truncated_when_small(self, MockOpenAI):
        """Context within budget is passed through unmodified."""
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._mock_response("OK.")

        small_context = "def foo(): pass"
        chat("query", context=small_context, api_key="test-key")

        user_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "... (truncated)" not in user_msg
        assert "def foo(): pass" in user_msg
