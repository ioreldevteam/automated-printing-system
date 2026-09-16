"""Printer adapter interface (Section 25/74). The production controller only
ever talks to this interface -- vendor-specific commands never leak upward.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import LabelData, PrinterStatusInfo


class PrinterError(Exception):
    """Raised by adapters for connection/protocol failures. print_label /
    push_serial may also raise this with an `uncertain=True` flag when the
    physical result could not be confirmed (Section 39)."""

    def __init__(self, message: str, error_code: str = "PRINT_001", uncertain: bool = False):
        super().__init__(message)
        self.error_code = error_code
        self.uncertain = uncertain


class BasePrinter(ABC):
    name: str

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def get_status(self) -> PrinterStatusInfo: ...

    @abstractmethod
    def test_print(self) -> bool: ...

    def pause(self) -> None:  # pragma: no cover - optional per vendor
        pass

    def resume(self) -> None:  # pragma: no cover - optional per vendor
        pass

    # --- optional batch-printing support -------------------------------
    # Adapters that talk to a real desktop OS print queue (Windows/CUPS)
    # override these so a whole job's worth of labels goes out as ONE print
    # job / one OS-level submission instead of one submission per label --
    # see WindowsPrinter/CupsPrinter for why that matters (Section: each
    # separate submission can surface its own OS/driver print prompt, which
    # is exactly what an operator does NOT want to click through once per
    # unit when printing a batch of N). Adapters that don't override these
    # (ANSER, Zebra, Simulation) print immediately as before -- batching
    # doesn't apply to a raw socket/FIFO push.
    def supports_batch_printing(self) -> bool:
        return False

    def flush_batch(self) -> None:  # pragma: no cover - no-op unless overridden
        """Send any buffered labels as a single print job. Safe to call even
        when nothing is buffered."""
        return None
