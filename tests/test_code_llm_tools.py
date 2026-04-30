"""Tests for code_llm.chat_with_tools — multi-turn tool-calling loop."""

from unittest.mock import MagicMock, patch

import pytest

from harness import code_llm


class _FakeToolCall:
    def __init__(self, call_id, name, args_json):
        self.id = call_id
        self.type = "function"
        self.function = MagicMock(name=name, arguments=args_json)
        self.function.name = name
        self.function.arguments = args_json


def _make_message(content=None, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    msg.role = "assistant"
    return msg


def _make_completion(message, finish_reason="stop"):
    completion = MagicMock()
    completion.choices = [MagicMock(message=message, finish_reason=finish_reason)]
    return completion


class TestChatWithTools:
    def test_no_tool_call_returns_final_text(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _make_completion(
            _make_message(content="just an answer"),
            finish_reason="stop",
        )

        with patch("harness.code_llm.OpenAI", return_value=client):
            result = code_llm.chat_with_tools(
                "hi",
                api_key="k",
                tool_dispatcher=lambda name, args: "should not be called",
            )
        assert result == "just an answer"

    def test_single_tool_call_loop_dispatches_and_returns_final(self):
        client = MagicMock()

        first = _make_completion(
            _make_message(
                content=None,
                tool_calls=[_FakeToolCall("c1", "read_file", '{"path": "a.py"}')],
            ),
            finish_reason="tool_calls",
        )
        second = _make_completion(
            _make_message(content="done after tool"),
            finish_reason="stop",
        )
        client.chat.completions.create.side_effect = [first, second]

        dispatched = []

        def dispatcher(name, args):
            dispatched.append((name, args))
            return "file content"

        with patch("harness.code_llm.OpenAI", return_value=client):
            result = code_llm.chat_with_tools(
                "do thing",
                api_key="k",
                tool_dispatcher=dispatcher,
            )
        assert result == "done after tool"
        assert dispatched == [("read_file", {"path": "a.py"})]

    def test_progress_callback_invoked_per_tool_call(self):
        client = MagicMock()
        first = _make_completion(
            _make_message(
                tool_calls=[_FakeToolCall("c1", "list_dir", '{"path": "."}')],
            ),
            finish_reason="tool_calls",
        )
        second = _make_completion(_make_message(content="ok"), finish_reason="stop")
        client.chat.completions.create.side_effect = [first, second]

        progress = []

        with patch("harness.code_llm.OpenAI", return_value=client):
            code_llm.chat_with_tools(
                "x",
                api_key="k",
                tool_dispatcher=lambda n, a: "[]",
                progress_cb=lambda name, args: progress.append((name, args)),
            )
        assert progress == [("list_dir", {"path": "."})]

    def test_max_iterations_guard_prevents_runaway(self):
        client = MagicMock()
        loop = _make_completion(
            _make_message(
                tool_calls=[_FakeToolCall("c", "list_dir", '{"path": "."}')],
            ),
            finish_reason="tool_calls",
        )
        client.chat.completions.create.return_value = loop

        with patch("harness.code_llm.OpenAI", return_value=client):
            with pytest.raises(RuntimeError, match="max"):
                code_llm.chat_with_tools(
                    "x",
                    api_key="k",
                    tool_dispatcher=lambda n, a: "[]",
                    max_iterations=3,
                )

    def test_no_api_key_raises(self):
        with pytest.raises(RuntimeError, match="API key"):
            code_llm.chat_with_tools("x", api_key=None, tool_dispatcher=lambda *a: "")
