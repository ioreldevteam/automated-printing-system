"""Domain-level exceptions. Error codes match Section 59 of the plan."""
from __future__ import annotations


class ProductionError(Exception):
    """Base class for all domain errors. Carries a normalized error code."""

    code = "SYSTEM_000"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class InvalidStateTransition(ProductionError):
    code = "SYSTEM_002"


class DuplicateSerialError(ProductionError):
    code = "VERIFY_002"


class SerialMismatchError(ProductionError):
    code = "VERIFY_001"


class SerialAllocationError(ProductionError):
    code = "API_002"


class ApiTimeoutError(ProductionError):
    code = "API_001"


class ApiUnavailableError(ProductionError):
    code = "API_003"


class PrinterOfflineError(ProductionError):
    code = "PRINTER_001"


class MediaOutError(ProductionError):
    code = "PRINTER_002"


class RibbonOutError(ProductionError):
    code = "PRINTER_003"


class HeadOpenError(ProductionError):
    code = "PRINTER_004"


class PrintTimeoutError(ProductionError):
    code = "PRINT_001"


class UnknownPrintResultError(ProductionError):
    code = "PRINT_002"


class DatabaseError(ProductionError):
    code = "SYSTEM_001"


class AuthenticationError(ProductionError):
    code = "AUTH_001"


class PermissionDeniedError(ProductionError):
    code = "AUTH_002"


class ConfigurationError(ProductionError):
    code = "SYSTEM_003"
