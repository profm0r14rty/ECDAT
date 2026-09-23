"""A teardown-safe variant of Textual's ``Header`` widget.

The only difference from :class:`textual.widgets.Header` is that the deferred
title-update coroutine also tolerates the header *widget itself* having been
detached before it runs.
"""

from __future__ import annotations

from textual.css.query import NoMatches
from textual.dom import NoScreen
from textual.events import Mount
from textual.widgets import Header
from textual.widgets._header import HeaderTitle


class SafeHeader(Header):
    """A :class:`~textual.widgets.Header` that survives being torn down
    while its title update is still pending.

    Textual's own ``Header._on_mount`` queues an async ``set_title`` callback
    on the header's *own* message pump for every watched title/subtitle
    change, but its guard only catches ``NoScreen`` — the header's *screen*
    going away.  When the header widget itself is detached before that
    deferred coroutine runs — a test tearing down a screen, or a real screen
    switch — the ``query_one(HeaderTitle)`` lookup instead raises
    :class:`~textual.css.query.NoMatches`, which upstream Textual leaves
    unguarded and surfaces out of ``App.run_test()`` as an intermittent
    ``NoMatches: No nodes match 'HeaderTitle' on Header()`` failure.

    This is a faithful copy of Textual's ``_on_mount`` (same four
    ``self.watch(...)`` registrations, same ``format_title()`` call) with
    exactly one change: ``NoMatches`` is added to the ``except`` clause.
    Everything else is inherited unchanged — the same ``DEFAULT_CSS``,
    ``_css_type_names``, reactives and bindings as ``Header`` itself.

    One subtlety: Textual dispatches an event handler for *every* class in the
    widget's MRO, so merely overriding ``_on_mount`` would let upstream
    ``Header._on_mount`` run anyway and register its unguarded ``set_title``
    watcher on the same instance.  ``event.prevent_default()`` is Textual's
    documented way to stop base-class handlers from being called; it is what
    makes this override the *only* ``_on_mount`` that runs.
    """

    def _on_mount(self, event: Mount) -> None:
        event.prevent_default()

        async def set_title() -> None:
            try:
                self.query_one(HeaderTitle).update(self.format_title())
            except (NoScreen, NoMatches):
                pass

        self.watch(self.app, "title", set_title)
        self.watch(self.app, "sub_title", set_title)
        self.watch(self.screen, "title", set_title)
        self.watch(self.screen, "sub_title", set_title)


__all__ = ["SafeHeader"]