"""Live scan screen — the animated progress view while the scanner runs.

Layout:
    - ``Header`` / ``Footer``.
    - ``#scan-title`` — the scan target.
    - Left: ``ArtView("torus")`` + ``#scan-counters``.
    - Right: stage rows (``#scan-stages``), a ``ProgressBar``, and a ``RichLog``.
    - ``#scan-error`` panel hidden until an error occurs.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from rich.panel import Panel
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, ProgressBar, RichLog, Static

from ecdat.services import demo
from ecdat.services import scanner
from ecdat.services.scanner import ScanError, ScanOutcome
from ecdat.services.settings import load_settings
from ecdat.tui.screens.home import HomeScreen
from ecdat.tui.widgets.art_view import ArtView
from ecdat.ui import motion
from ecdat.ui.theme import PALETTE, strip_control_chars
from ecdat_core.progress import ScanCancelled, ScanProgress

MAX_UPDATES_PER_SECOND = 20

STAGE_ORDER = ("clone", "ingest", "detect", "assess", "recommend", "assemble")

_COMPLETE_FLASH_S = 0.5
_SCRAMBLE_ALPHABET = "0123456789ABCDEF#$%&@"
_BRAILLE_SPINNER = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"
_ASCII_SPINNER = "|/-\\"
_SPINNER_FPS = 8.0


class ScanScreen(Screen[None]):
    """Animated live scan screen with stage tracking, progress bar, and the torus.

    The scan runs in a background thread.  Progress events are throttled and
    pushed onto the main thread via ``call_from_thread``.  Cancellation signals
    the worker through a :class:`threading.Event`; the worker catches
    :class:`~ecdat_core.progress.ScanCancelled` and returns to Home.
    """

    BINDINGS = [
        Binding("escape", "cancel_scan", "Cancel"),
        Binding("r", "retry", "Retry"),
        Binding("b", "back_home", "Back"),
    ]

    def __init__(
        self,
        target: str,
        label: Optional[str] = None,
        *,
        demo: bool = False,
    ) -> None:
        super().__init__()
        self._target = target
        self._label = label
        self._demo = demo

        self._cancel = threading.Event()
        self._errored = False
        self._started = False
        self._started_at = time.monotonic()
        self._files_current = 0
        self._files_total = 0
        self._findings = 0
        self._ui_updates = 0

        self._stage_status: dict[str, str] = {s: "pending" for s in STAGE_ORDER}
        self._stage_entered_at: dict[str, float] = {}

        self._last_event_time = 0.0
        self._last_sent_stage = ""

        self._spinner_frame = 0
        self._spinner_timer: Optional[object] = None

    # -- composition --------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="scan-title")
        with Horizontal(classes="scan-body"):
            with Vertical(id="scan-left"):
                yield ArtView("torus", id="scan-torus")
                yield Static("", id="scan-counters")
            with Vertical(id="scan-right"):
                with Vertical(id="scan-stages"):
                    for name in STAGE_ORDER:
                        yield Static("", id=f"stage-{name}")
                yield ProgressBar(id="scan-progress", total=None)
                yield RichLog(id="scan-log", max_lines=200, markup=False)
        yield Static("", id="scan-error")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#scan-title", Static).update(
            Text(strip_control_chars(f"Scanning {self._label or self._target}"))
        )

        self.query_one("#scan-error", Static).display = False

        if not self._demo:
            try:
                target = scanner.classify_target(self._target)
            except ScanError as exc:
                self._errored = True
                self._show_error(exc)
                return
            is_local = target.kind == "local"
        else:
            is_local = True

        if is_local:
            self.query_one("#stage-clone", Static).display = False

        self._spinner_timer = self.set_interval(
            1.0 / _SPINNER_FPS, self._tick_spinner
        )
        self._run_scan()

    def on_unmount(self) -> None:
        """Stop timers so a screen swap never leaves work running."""
        self._stop_spinner()
        self._cancel.set()

    def _stop_spinner(self) -> None:
        """Stop the stage-spinner timer, if running."""
        timer = self._spinner_timer
        if timer is not None:
            timer.stop()
            self._spinner_timer = None

    # -- spinner timer ------------------------------------------------------

    def _tick_spinner(self) -> None:
        self._spinner_frame += 1
        self._render_stages()

    # -- stage rendering ----------------------------------------------------

    @property
    def _animations(self) -> bool:
        return motion.animations_enabled(load_settings().reduce_motion)

    def _render_stages(self) -> None:
        for name in STAGE_ORDER:
            status = self._stage_status.get(name, "pending")
            label = scanner.STAGE_LABELS.get(name, name)
            self._render_stage_row(name, label, status)

    def _render_stage_row(self, name: str, label: str, status: str) -> None:
        widget = self.query_one(f"#stage-{name}", Static)
        frame = self._spinner_frame

        if status == "pending":
            indicator = Text("\u25cb", style=PALETTE.muted)
            label_text = Text(label, style=PALETTE.muted)
            widget.update(Text.assemble(indicator, " ", label_text))
        elif status == "active":
            encoding = getattr(self.app.console, "encoding", "") or ""
            if encoding.lower().startswith("utf"):
                spinner_char = _BRAILLE_SPINNER[frame % len(_BRAILLE_SPINNER)]
            else:
                spinner_char = _ASCII_SPINNER[frame % len(_ASCII_SPINNER)]
            indicator = Text(spinner_char, style=f"bold {PALETTE.accent}")

            if self._animations:
                entered = self._stage_entered_at.get(name, 0.0)
                elapsed = time.monotonic() - entered if entered > 0 else 0.0
                progress = min(elapsed / 0.4, 1.0)
                revealed = motion.scramble(label, progress, frame, alphabet=_SCRAMBLE_ALPHABET)
            else:
                revealed = label

            label_text = Text(revealed, style=f"bold {PALETTE.accent}")
            widget.update(Text.assemble(indicator, " ", label_text))
        else:  # done
            indicator = Text("\u2713", style=f"bold {PALETTE.accent}")
            label_text = Text(label, style=PALETTE.accent)
            widget.update(Text.assemble(indicator, " ", label_text))

    # -- worker -------------------------------------------------------------

    @work(thread=True, exclusive=True)
    def _run_scan(self) -> None:
        """Execute the scan in a background thread.

        The progress callback throttles delivery: only stage changes,
        terminal/final events, or no sooner than
        ``1 / MAX_UPDATES_PER_SECOND`` seconds trigger a UI push.
        """
        self._started = True
        self._started_at = time.monotonic()

        def _cb(ev: ScanProgress) -> None:
            self._deliver_or_raise(ev)

        target = self._target
        label = self._label
        outcome = None

        try:
            if self._demo:
                with demo.demo_project() as path:
                    target = str(path)
                    label = "demo project"
                    outcome = self._scan(target, label, _cb)
            else:
                outcome = self._scan(target, label, _cb)
        except ScanCancelled:
            self.app.call_from_thread(self._switch_home)
            return
        except ScanError as exc:
            if self._cancel.is_set():
                self.app.call_from_thread(self._switch_home)
                return
            self.app.call_from_thread(self._show_error, exc)
            return

        self.app.call_from_thread(self._on_scan_complete, outcome)

    def _scan(self, target: str, label: Optional[str], callback) -> ScanOutcome:
        return scanner.perform_scan(
            scanner.classify_target(target),
            label=label,
            on_progress=callback,
        )

    def _deliver_or_raise(self, ev: ScanProgress) -> None:
        """Push *ev* to the UI within the throttle budget, or raise on cancel.

        Runs on the worker thread.  Raises
        :class:`~ecdat_core.progress.ScanCancelled` as soon as
        :attr:`_cancel` is set, which is how Esc aborts the running scan.
        """
        if self._cancel.is_set():
            raise ScanCancelled(progress=ev)
        now = time.monotonic()
        stage_changed = ev.stage != self._last_sent_stage
        is_final = ev.stage in ("assemble", "done")
        enough_time = now - self._last_event_time >= 1.0 / MAX_UPDATES_PER_SECOND
        if stage_changed or is_final or enough_time:
            self._last_event_time = now
            self._last_sent_stage = ev.stage
            self.app.call_from_thread(self._apply_progress, ev)

    # -- callbacks from worker thread ---------------------------------------

    def _apply_progress(self, ev: object) -> None:
        """Apply a throttled progress event to the UI (main-thread)."""
        if not isinstance(ev, ScanProgress) or not self.is_mounted:
            return
        self._ui_updates += 1
        stage: str = ev.stage

        if stage in ("done", "assemble"):
            for name in STAGE_ORDER:
                self._stage_status[name] = "done"
        else:
            try:
                idx = STAGE_ORDER.index(stage)
            except ValueError:
                idx = -1
            for i, name in enumerate(STAGE_ORDER):
                if i < idx:
                    self._stage_status[name] = "done"
                elif i == idx:
                    if self._stage_status.get(name) != "active":
                        self._stage_status[name] = "active"
                        self._stage_entered_at[name] = time.monotonic()
                else:
                    self._stage_status[name] = "pending"

        self._files_current = ev.current
        if ev.total is not None:
            self._files_total = ev.total
        self._findings = ev.detections

        pb = self.query_one("#scan-progress", ProgressBar)
        if stage == "detect" and ev.total is not None and ev.total > 0:
            pb.total = ev.total
            pb.update(progress=min(ev.current, ev.total))
        else:
            pb.total = None

        elapsed = time.monotonic() - self._started_at
        counters = Text()
        counters.append("Files ", style=PALETTE.muted)
        counters.append(str(ev.current), style="bold")
        counters.append(
            f"/{ev.total or '?'} \u00b7 Findings {ev.detections} \u00b7 {elapsed:.1f}s",
            style=PALETTE.muted,
        )
        self.query_one("#scan-counters", Static).update(counters)

        if ev.message:
            self.query_one("#scan-log", RichLog).write(strip_control_chars(ev.message))

        self._render_stages()

    def _on_scan_complete(self, outcome: object) -> None:
        """Flash success, then transition to the ResultsScreen."""
        if not isinstance(outcome, ScanOutcome) or not self.is_mounted:
            return
        self._stop_spinner()
        for name in STAGE_ORDER:
            self._stage_status[name] = "done"
        self._render_stages()
        self.query_one("#scan-title", Static).update(
            Text("\u2714 Scan complete", style=f"bold {PALETTE.safe}")
        )
        self.set_timer(_COMPLETE_FLASH_S, lambda: self._open_results(outcome))

    def _open_results(self, outcome: ScanOutcome) -> None:
        if self._cancel.is_set() or not self.is_mounted:
            return
        from ecdat.tui.screens.results import ResultsScreen

        self.app.switch_screen(ResultsScreen(outcome))

    def _show_error(self, error: object) -> None:
        """Display the error panel (main-thread)."""
        if not isinstance(error, ScanError) or not self.is_mounted:
            return
        self._errored = True
        self._stop_spinner()

        content = Text()
        content.append(strip_control_chars(error.user_message), style="bold")
        if error.hint:
            content.append("\n\n")
            content.append(Text(strip_control_chars(error.hint), style="dim"))

        panel = Panel(content, title="Scan Error", border_style=PALETTE.critical)
        error_widget = self.query_one("#scan-error", Static)
        error_widget.update(panel)
        error_widget.display = True

        self.query_one("#scan-torus", ArtView).pause()

    def _switch_home(self) -> None:
        """Transition back to the Home screen, guarding against double-switch."""
        self._stop_spinner()
        if not self.is_mounted:
            return
        if type(self.app.screen) is not HomeScreen:
            self.app.switch_screen(HomeScreen())

    # -- actions ------------------------------------------------------------

    def action_cancel_scan(self) -> None:
        """Cancel the running scan and return Home."""
        if self._errored:
            self.action_back_home()
            return
        if self._cancel.is_set():
            return
        self._cancel.set()
        title = Text("Cancelling\u2026", style=f"italic {PALETTE.muted}")
        self.query_one("#scan-title", Static).update(title)

    def action_retry(self) -> None:
        """Re-run the scan after an error."""
        if not self._errored:
            return
        self._errored = False
        error_widget = self.query_one("#scan-error", Static)
        error_widget.display = False
        error_widget.update("")

        self._stage_status = {s: "pending" for s in STAGE_ORDER}
        self._stage_entered_at.clear()
        self._files_current = 0
        self._files_total = 0
        self._findings = 0
        self._ui_updates = 0
        self._last_event_time = 0.0
        self._last_sent_stage = ""
        self._cancel.clear()

        self.query_one("#scan-torus", ArtView).resume()

        self._spinner_frame = 0
        self._spinner_timer = self.set_interval(1.0 / _SPINNER_FPS, self._tick_spinner)
        self.query_one("#scan-log", RichLog).clear()
        self._run_scan()

    def action_back_home(self) -> None:
        """Return to the Home screen."""
        self._cancel.set()
        self._stop_spinner()
        self.app.switch_screen(HomeScreen())