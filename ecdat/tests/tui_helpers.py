"""Shared helpers for the ECDAT TUI tests.

Pilot-driven tests need a way to wait for a condition that a timer will only
satisfy in a later frame; :func:`wait_until` polls the pilot without blocking
the event loop.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def wait_until(
    pilot,
    predicate: Callable[[], T],
    timeout: float = 10.0,
    interval: float = 0.05,
) -> T:
    """Poll *predicate* until it is truthy, or fail the test on timeout.

    The pilot is paused between polls so pending Textual messages and timer
    callbacks get a chance to run.

    Args:
        pilot: The Textual :class:`~textual.pilot.Pilot`.
        predicate: A zero-argument callable; its truthiness ends the wait.
        timeout: Maximum seconds to wait.
        interval: Seconds to pause between polls.

    Returns:
        The value returned by *predicate*.

    Raises:
        AssertionError: When *predicate* never becomes truthy in time.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        result = predicate()
        if result:
            return result
        if loop.time() >= deadline:
            raise AssertionError(f"timed out after {timeout}s waiting for condition")
        await pilot.pause(interval)


async def wait_for_text(pilot, widget, timeout: float = 10.0) -> str:
    """Wait until *widget* renders any non-empty text, and return it."""
    def current() -> str:
        rendered = widget.render()
        if hasattr(rendered, "plain"):
            return rendered.plain
        return str(rendered)

    return await wait_until(pilot, current, timeout=timeout)


__all__ = ["wait_until", "wait_for_text"]
