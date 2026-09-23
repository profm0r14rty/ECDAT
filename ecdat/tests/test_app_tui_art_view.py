"""Tests for :class:`~ecdat.tui.widgets.art_view.ArtView` with motion off.

ArtView previously drew synchronously at mount, before Textual had resolved
``content_size``, and — with animations off — never re-rendered, so the widget
stayed blank.  These Pilot tests pin the deferred-draw and resize-redraw
behaviour that fixes it.

Everything runs headless with ``ECDAT_ANIM=0`` so the static path is
deterministic; the host repo's autouse fixture keeps ``ECDAT_HOME`` in a tmp
directory.
"""

from __future__ import annotations

import os

import pytest
from textual.app import App, ComposeResult

from ecdat.tui.widgets.art_view import ArtView

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_helpers import wait_until  # noqa: E402


class _ArtApp(App[None]):
    """Minimal host that lays a single ArtView out at full size."""

    CSS = "ArtView { width: 100%; height: 100%; }"

    def __init__(self, kind: str) -> None:
        super().__init__()
        self._kind = kind

    def compose(self) -> ComposeResult:
        yield ArtView(self._kind, id="art")


def _plain(widget: ArtView) -> str:
    rendered = widget.render()
    return getattr(rendered, "plain", str(rendered))


@pytest.mark.asyncio
async def test_globe_renders_static_frame_when_anim_off() -> None:
    os.environ["ECDAT_ANIM"] = "0"
    app = _ArtApp("globe")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        view = app.query_one("#art", ArtView)
        text = await wait_until(pilot, lambda: _plain(view) if _plain(view).strip() else "")
        assert len(text.replace("\n", "").strip()) > 0


@pytest.mark.asyncio
async def test_torus_renders_static_frame_when_anim_off() -> None:
    os.environ["ECDAT_ANIM"] = "0"
    app = _ArtApp("torus")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        view = app.query_one("#art", ArtView)
        text = await wait_until(pilot, lambda: _plain(view) if _plain(view).strip() else "")
        assert len(text.replace("\n", "").strip()) > 0


@pytest.mark.asyncio
async def test_static_frame_renders_after_resize() -> None:
    os.environ["ECDAT_ANIM"] = "0"
    app = _ArtApp("globe")
    async with app.run_test(size=(8, 4)) as pilot:
        await pilot.pause()
        view = app.query_one("#art", ArtView)
        # Too small for the globe: the static draw is necessarily blank here.
        assert _plain(view).strip() == ""

        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        text = await wait_until(pilot, lambda: _plain(view) if _plain(view).strip() else "")
        assert len(text.replace("\n", "").strip()) > 0
