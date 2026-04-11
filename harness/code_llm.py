"""Code LLM — OpenAI-compatible client + SEARCH/REPLACE parser."""

import re
from typing import Optional

from openai import OpenAI, APIConnectionError, APITimeoutError, AuthenticationError


# SEARCH/REPLACE regex — lenient: 6-8 chevrons, case-insensitive.
_SEARCH_RE = re.compile(
    r"^<{6,8}\s*SEARCH\s*\n(.*?)\n={6,8}\s*\n(.*?)\n>{6,8}\s*REPLACE\s*$",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

MODEL = "gemini-2.5-flash"

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Timeout for hosted LLM requests (seconds).
REQUEST_TIMEOUT = 120.0

SYSTEM_PROMPT = """\
You are a senior coding assistant embedded in a voice-driven IDE called Voice Harness.
The user speaks a request. You receive the request plus the contents of the currently open file.

Rules:
1. If the user asks for a code change, respond with one or more SEARCH/REPLACE blocks.
   Format:
   <<<<<<< SEARCH
   exact lines to find
   =======
   replacement lines
   >>>>>>> REPLACE

2. Before or after the SEARCH/REPLACE blocks, give a SHORT spoken explanation (1-3 sentences).
   This text will be read aloud via TTS — keep it conversational, not technical.
3. If the user asks a question (no code change), just answer in plain speech.
4. Never wrap SEARCH/REPLACE blocks inside a fenced code block.
5. SEARCH blocks must match the existing file EXACTLY — same whitespace, same indentation.
"""


# Context budget: Gemini 2.5 Pro supports 1M tokens; allow ~100k chars of file context.
_MAX_CONTEXT_CHARS = 100_000


def chat(
    query: str,
    context: Optional[str] = None,
    repo_map: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """Send a user query (+ file context) to the hosted LLM and return the response."""
    if not api_key:
        raise RuntimeError("No API key configured")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    user_parts = []
    if context:
        truncated = context[:_MAX_CONTEXT_CHARS]
        if len(context) > _MAX_CONTEXT_CHARS:
            truncated += "\n... (truncated)"
        user_parts.append(f"## Currently open file\n```\n{truncated}\n```\n")
    if repo_map:
        user_parts.append(f"## Repository map\n{repo_map}\n")
    user_parts.append(f"## User request\n{query}")

    messages.append({"role": "user", "content": "\n".join(user_parts)})

    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            timeout=REQUEST_TIMEOUT,
        )
    except AuthenticationError as exc:
        raise RuntimeError(f"Invalid API key: {exc}") from exc
    except (APIConnectionError, APITimeoutError) as exc:
        raise RuntimeError(f"LLM unavailable: {exc}") from exc
    return response.choices[0].message.content


def parse_search_replace(text: str) -> list[dict]:
    """Extract SEARCH/REPLACE blocks from LLM output.

    Returns list of {"search": str, "replace": str} dicts.
    """
    # Strip any enclosing fenced code block before parsing.
    stripped = re.sub(r"^```\w*\n", "", text).rstrip("`").rstrip()
    results = []
    for m in _SEARCH_RE.finditer(stripped):
        results.append({"search": m.group(1), "replace": m.group(2)})
    return results


def extract_prose(text: str) -> str:
    """Return the non-SEARCH/REPLACE prose from an LLM response (for TTS)."""
    prose = _SEARCH_RE.sub("", text).strip()
    # Collapse multiple blank lines.
    return re.sub(r"\n{3,}", "\n\n", prose)
