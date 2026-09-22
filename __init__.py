"""Jina backend plugin — user plugin, auto-loaded when enabled."""

from __future__ import annotations

from .provider import JinaProvider


def register(ctx) -> None:
    """Plugin entry point — called once at load time."""
    ctx.register_web_search_provider(JinaProvider())
