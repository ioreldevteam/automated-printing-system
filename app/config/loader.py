"""Typed configuration loading (Section 63). config.yaml holds non-secret
defaults; secrets (API tokens, DB credentials) should come from environment
variables referenced here, never hardcoded.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from app.domain.exceptions import ConfigurationError

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


class ApplicationConfig(BaseModel):
    name: str = "Industrial Automated Printing System"
    environment: str = "production"


class ApiConfig(BaseModel):
    # "local" uses api/serial_api.py's LocalSerialApiClient (a durable, idempotent
    # allocator backed by our own database — see Section 105 item 15: the
    # product/serial API is "fully customizable", so it is designed here rather
    # than guessed at). "remote" calls a real HTTP endpoint at base_url.
    mode: str = "local"
    base_url: str = ""
    token_env_var: str = "PRODUCTION_API_TOKEN"
    timeout_seconds: float = 10.0
    retry_count: int = 5
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 30.0

    @property
    def token(self) -> Optional[str]:
        return os.environ.get(self.token_env_var)


class DatabaseConfig(BaseModel):
    path: str = "./data/production.db"
    backup_dir: str = "./backups"


class PrintingConfig(BaseModel):
    max_retries: int = 3
    queue_size: int = 100
    serial_buffer_size: int = 100
    retryable_errors: list[str] = Field(
        default_factory=lambda: ["TIMEOUT", "CONNECTION_RESET", "TEMPORARY_BUSY"]
    )
    manual_recovery_errors: list[str] = Field(
        default_factory=lambda: ["MEDIA_OUT", "RIBBON_OUT", "HEAD_OPEN", "UNKNOWN_PRINT_RESULT"]
    )
    immediate_stop_errors: list[str] = Field(
        default_factory=lambda: ["SERIAL_MISMATCH", "SAFETY_FAULT", "EMERGENCY_STOP"]
    )


class AnserModbusConfig(BaseModel):
    """Register map for the ANSER X1 over Modbus TCP.

    Section 28.2 of the plan: the proprietary "ANSER U2 Net Protocol" frame
    format (0xCA/0xCF) is not published in the public manual. Modbus TCP is a
    standard, documented protocol the X1 also exposes (Section 28), so it is
    the connection method used here. The exact register addresses below are
    placeholders that MUST be confirmed against the ANSER-supplied Modbus
    register map before going live — see Section 105 item 1. They are
    deliberately left in config, not hardcoded, so that confirming them does
    not require a code change.
    """

    unit_id: int = 1
    # Holding register (FC16) the app writes the next serial number into.
    # The X1 is expected to treat this as its 0xCF-equivalent FIFO input.
    serial_fifo_register: int = 40001
    # How many 16-bit registers the serial value occupies (ASCII packed 2 chars/register).
    serial_register_length: int = 10
    # Holding/input register (FC3/FC4) reporting cumulative prints consumed from the FIFO.
    consumption_counter_register: int = 40101
    # Input register reporting the normalized fault/status code (see printers/anser.py).
    status_register: int = 40102
    # Coil (FC5) that pulses a test print when written True.
    test_print_coil: int = 1
    poll_interval_seconds: float = 1.0


class PrinterConfig(BaseModel):
    name: str
    type: str  # "ANSER" | "ZEBRA" | "CUPS" | "WINDOWS" | "SIMULATION"
    model: str = ""
    address: str = "127.0.0.1"
    port: int = 9100
    enabled: bool = True
    simulate: bool = False
    connect_timeout_seconds: float = 5.0
    anser_modbus: AnserModbusConfig = Field(default_factory=AnserModbusConfig)


class MonitoringConfig(BaseModel):
    poll_interval_seconds: float = 1.0
    status_poll_interval_seconds: float = 3.0


class LoggingConfig(BaseModel):
    directory: str = "./logs"
    level: str = "INFO"
    max_bytes: int = 10_485_760
    backup_count: int = 10


class SecurityConfig(BaseModel):
    bcrypt_rounds: int = 12
    session_timeout_minutes: int = 60


class AppConfig(BaseModel):
    application: ApplicationConfig = Field(default_factory=ApplicationConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    printing: PrintingConfig = Field(default_factory=PrintingConfig)
    printers: list[PrinterConfig] = Field(default_factory=list)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    def printer_by_name(self, name: str) -> Optional[PrinterConfig]:
        return next((p for p in self.printers if p.name == name), None)


def load_config(path: Path | str | None = None) -> AppConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    try:
        return AppConfig.model_validate(raw)
    except Exception as exc:  # pragma: no cover - defensive
        raise ConfigurationError(f"Invalid configuration: {exc}") from exc
