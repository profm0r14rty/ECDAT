"""FindingDetail widget: the master/detail pane's right-hand half.

Shows everything known about the highlighted finding — algorithm and risk,
location, the two independent weakness flags, why it matters, the Mosca
timeline, an urgency gauge, the recommended replacement, and the matched code
snippet.

Every value that originates from a scanned repository (file paths, snippets,
algorithm names, rationales) is attacker-controlled and therefore enters the
widget only as :class:`rich.text.Text` — never as a Rich markup string.
"""

from __future__ import annotations

from typing import Optional

from rich.style import Style
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ecdat.services.viewmodel import FindingVM
from ecdat.tui.widgets.mosca_timeline import MoscaTimeline
from ecdat.ui.render import risk_chip, smooth_bar
from ecdat.ui.theme import PALETTE, strip_control_chars

# The urgency gauge is normalised against this ceiling so a runaway ratio does
# not simply saturate: ratios at or above 1.5 render as a full bar.
_URGENCY_CEILING = 1.5

_PLACEHOLDER = "\u2014"


class FindingDetail(VerticalScroll):
    """Detail view for one :class:`~ecdat.services.viewmodel.FindingVM`.

    Renders a header (algorithm + risk chip), the location line, the two
    weakness flags, the rationale, a :class:`MoscaTimeline`, an urgency gauge,
    the recommendation, and — when present — the matched snippet highlighted
    with :class:`rich.syntax.Syntax`.

    Args:
        id: DOM id.
        classes: Additional CSS classes.
    """

    def __init__(
        self,
        *,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        cls = f"{classes} finding-detail" if classes else "finding-detail"
        super().__init__(id=id, classes=cls)
        self.finding: Optional[FindingVM] = None

    def compose(self) -> ComposeResult:
        """Compose the static sections once; values are filled in on update."""
        yield Static("", id="detail-header")
        yield Static("", id="detail-location")
        yield Static("", id="detail-flags")
        yield Static("", id="detail-why")
        yield MoscaTimeline(id="detail-mosca")
        yield Static("", id="detail-urgency")
        yield Static("", id="detail-recommendation")
        yield Static("", id="detail-snippet")

    def on_mount(self) -> None:
        """Render whatever finding was set before the child DOM existed.

        The parent pane may push a finding during its own ``on_mount``, which
        can run before this widget's children are queryable.  ``show_finding``
        stores the value unconditionally, so re-rendering here guarantees the
        detail catches up once the DOM is ready.
        """
        self._rebuild()

    # -- public API ---------------------------------------------------------

    def show_finding(self, finding: Optional[FindingVM]) -> None:
        """Render *finding*, or a friendly placeholder when it is ``None``."""
        self.finding = finding
        self._rebuild()

    def _rebuild(self) -> None:
        """Render the stored finding into the child statics."""
        finding = self.finding
        if finding is None:
            self._render_empty()
            return
        self._render_header(finding)
        self._render_location(finding)
        self._render_flags(finding)
        self._render_why(finding)
        self._render_mosca(finding)
        self._render_urgency(finding)
        self._render_recommendation(finding)
        self._render_snippet(finding)

    def location_text(self) -> str:
        """Return the ``file:line`` string for the current finding (or ``""``)."""
        if self.finding is None:
            return ""
        return f"{self.finding.file_path}:{self.finding.line}"

    def plain_text(self) -> str:
        """Concatenate every rendered section — used by tests and for search."""
        parts = []
        for widget in self.query(Static):
            rendered = widget.render()
            if isinstance(rendered, Syntax):
                parts.append(rendered.code)
                continue
            parts.append(getattr(rendered, "plain", str(rendered)))
        return "\n".join(parts)

    # -- sections -----------------------------------------------------------

    def _render_empty(self) -> None:
        self._set("detail-header", Text("No finding selected", style=Style(color=PALETTE.muted, italic=True)))
        self._set("detail-location", Text(""))
        self._set("detail-flags", Text(""))
        self._set("detail-why", Text(""))
        self._set("detail-urgency", Text(""))
        self._set("detail-recommendation", Text(""))
        self._set("detail-snippet", Text(""))
        mosca = self._mosca()
        if mosca is not None:
            mosca.set_values(None, None, None)

    def _render_header(self, f: FindingVM) -> None:
        header = Text()
        header.append(risk_chip(f.risk_level))
        header.append("  ")
        header.append(Text(strip_control_chars(f.algorithm), style="bold"))
        self._set("detail-header", header)

    def _render_location(self, f: FindingVM) -> None:
        location = Text()
        location.append(Text(strip_control_chars(f"{f.file_path}:{f.line}")))
        if f.language:
            location.append(
                strip_control_chars(f"   [{f.language}]"),
                style=Style(color=PALETTE.muted),
            )
        self._set("detail-location", location)

    def _render_flags(self, f: FindingVM) -> None:
        flags = Text()
        flags.append("Quantum-vulnerable: ", style=Style(color=PALETTE.muted))
        flags.append(
            Text(
                "yes" if f.quantum_vulnerable else "no",
                style=Style(
                    color=PALETTE.critical if f.quantum_vulnerable else PALETTE.safe,
                    bold=True,
                ),
            )
        )
        flags.append("\n")
        flags.append("Classically broken: ", style=Style(color=PALETTE.muted))
        flags.append(
            Text(
                "yes" if f.classically_broken else "no",
                style=Style(
                    color=PALETTE.critical if f.classically_broken else PALETTE.safe,
                    bold=True,
                ),
            )
        )
        self._set("detail-flags", flags)

    def _render_why(self, f: FindingVM) -> None:
        why = Text()
        why.append("Why it matters\n", style="bold")
        if f.rationale:
            why.append(Text(strip_control_chars(f.rationale)))
        else:
            why.append(Text(_PLACEHOLDER, style=Style(color=PALETTE.muted)))
        self._set("detail-why", why)

    def _render_mosca(self, f: FindingVM) -> None:
        mosca = self._mosca()
        if mosca is None:
            return
        mosca.set_values(f.mosca_x, f.mosca_y, f.mosca_z)

    def _render_urgency(self, f: FindingVM) -> None:
        fraction = min(f.urgency_ratio, _URGENCY_CEILING) / _URGENCY_CEILING
        gauge = Text()
        gauge.append("Urgency  ", style=Style(color=PALETTE.muted))
        gauge.append(self._fmt(f.urgency_ratio), style="bold")
        gauge.append("\n")
        gauge.append(smooth_bar(fraction, 40))
        self._set("detail-urgency", gauge)

    def _render_recommendation(self, f: FindingVM) -> None:
        rec = Text()
        rec.append("Recommended replacement\n", style="bold")
        if f.recommended:
            rec.append(
                Text(
                    strip_control_chars(f.recommended),
                    style=Style(color=PALETTE.accent, bold=True),
                )
            )
        else:
            rec.append(Text("No migration needed", style=Style(color=PALETTE.muted, italic=True)))
        rec.append("\n")
        rec.append("FIPS reference: ", style=Style(color=PALETTE.muted))
        if f.fips_reference:
            rec.append(Text(strip_control_chars(f.fips_reference)))
        else:
            rec.append(Text(_PLACEHOLDER, style=Style(color=PALETTE.muted)))
        rec.append(f"   Confidence: {f.confidence * 100:.0f}%", style=Style(color=PALETTE.muted))
        self._set("detail-recommendation", rec)

    def _render_snippet(self, f: FindingVM) -> None:
        widget = self.query_one("#detail-snippet", Static)
        if not f.snippet:
            widget.update(Text("No snippet captured", style=Style(color=PALETTE.muted, italic=True)))
            return
        snippet = strip_control_chars(f.snippet)
        try:
            syntax = Syntax(
                snippet,
                lexer=f.language or "text",
                theme="ansi_dark",
                word_wrap=True,
                background_color=PALETTE.surface,
            )
        except Exception:  # noqa: BLE001 - unknown lexer must never crash the pane
            syntax = Text(snippet)
        widget.update(syntax)

    # -- helpers ------------------------------------------------------------

    def _set(self, selector: str, renderable) -> None:  # noqa: ANN001
        """Update a child Static by id, tolerating a not-yet-ready DOM.

        *selector* is a bare id (``"detail-header"``); the leading ``#`` is
        added here — a bare word is parsed as a *type* selector by Textual and
        would silently match nothing.
        """
        try:
            widget = self.query_one(f"#{selector}", Static)
        except Exception:  # noqa: BLE001 - during mount the child may not exist yet
            return
        widget.update(renderable)

    def _mosca(self) -> Optional[MoscaTimeline]:
        """Return the timeline child, or ``None`` before the DOM is ready."""
        try:
            return self.query_one("#detail-mosca", MoscaTimeline)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _fmt(value: float) -> str:
        """Format a number without a trailing ``.0``."""
        return str(int(value)) if float(value).is_integer() else f"{value:.2f}"


__all__ = ["FindingDetail"]
