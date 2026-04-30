"""Shared types for ``scripts/lib/`` check modules.

Each check returns a list of :class:`Finding` objects. Hooks aggregate
them and exit non-zero when any are present.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """A single rule violation."""

    path: str
    line: int
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"
