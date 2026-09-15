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
