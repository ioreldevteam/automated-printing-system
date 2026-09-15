"""ANSER X1 adapter (Section 28).

Why Modbus TCP instead of the proprietary "ANSER U2 Net Protocol": the public
X1 user manual names the 0xCA (Data Update) / 0xCF (Data Stream / FIFO) frame
commands but does not publish the byte-level frame format (header/length/
checksum) -- Section 28.2 / Section 105 item 1 flags this as an open item that
must come from ANSER support before that protocol can be implemented safely.
Modbus TCP is listed by the same manual as a supported Ethernet interface and
is a standard, publicly documented protocol, so it is used here as "a
suitable method to connect to the printer" now, without guessing at an
undocumented proprietary frame layout.

What is NOT yet confirmed (Section 105 item 1/3) is the exact ANSER Modbus
*register map* -- which register is the FIFO input, which reports the
consumption counter, and the fault code encoding. Those addresses live in
config.yaml (`printers[].anser_modbus`) so they can be corrected the moment
ANSER support provides the real map, without a code change. Until then this
adapter should be run with `simulate: true` against SimulationPrinter, or
against ANSER's own Modbus test/simulation tooling if available.

Behavioural model implemented here follows Section 28.1: push_serial() writes
the next serial into the configured FIFO input register (the Modbus
equivalent of 0xCF) -- the X1's own photocell sensor fires the physical
print, not this adapter. get_consumption_count() polls a counter register so
the caller (queue_worker.AnserWorker) can detect when a pushed serial has
actually been consumed/printed and mark that unit COMPLETED, per the
push-then-confirm design in Section 28.1's closing paragraph.
"""
from __future__ import annotations

from app.config.loader import AnserModbusConfig
from app.domain.models import PrinterStatusInfo
from app.domain.states import PrinterStatus
from app.printers.base import BasePrinter, PrinterError

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:  # pragma: no cover - pymodbus is a hard dependency at runtime
    ModbusTcpClient = None  # type: ignore[assignment,misc]


# Fault code -> normalized PrinterStatus. Placeholder mapping (Section 105
# item 1): confirm real values against the ANSER register map, then adjust
# this dict -- nothing else in the adapter needs to change.
STATUS_CODE_MAP: dict[int, PrinterStatus] = {
    0: PrinterStatus.READY,
    1: PrinterStatus.BUSY,
    2: PrinterStatus.MEDIA_OUT,   # placeholder: likely "ink/cartridge empty" on the X1
    3: PrinterStatus.ERROR,
    4: PrinterStatus.OFFLINE,
}


def _pack_serial_to_registers(serial: str, register_count: int) -> list[int]:
    """Pack an ASCII serial number two characters per 16-bit register, the
    common convention for ASCII-in-holding-registers. Field limit per the
    manual: variables hold up to 100 bytes; register_count is configured
    accordingly (Section 28.1)."""
    max_chars = register_count * 2
    padded = serial.ljust(max_chars, "\x00")[:max_chars]
    registers = []
    for i in range(0, max_chars, 2):
        hi = ord(padded[i])
        lo = ord(padded[i + 1]) if i + 1 < len(padded) else 0
        registers.append((hi << 8) | lo)
    return registers


class AnserPrinter(BasePrinter):
    def __init__(self, name: str, address: str, port: int, modbus_config: AnserModbusConfig,
                 connect_timeout: float = 5.0):
        if ModbusTcpClient is None:  # pragma: no cover
            raise PrinterError("pymodbus is not installed", error_code="SYSTEM_003")
        self.name = name
        self.address = address
        self.port = port
        self.cfg = modbus_config
        self._client = ModbusTcpClient(address, port=port, timeout=connect_timeout)

    def connect(self) -> None:
        if not self._client.connect():
            raise PrinterError(f"Cannot reach ANSER X1 {self.name} at {self.address}:{self.port} over Modbus TCP",
                                error_code="PRINTER_001")

    def disconnect(self) -> None:
        self._client.close()

    def _ensure_connected(self) -> None:
        if not self._client.connected:
            self.connect()

    def push_serial(self, serial: str) -> None:
        """Write the next serial into the FIFO input register (Modbus
        equivalent of the X1's 0xCF Data Stream command, Section 28.1)."""
        self._ensure_connected()
        registers = _pack_serial_to_registers(serial, self.cfg.serial_register_length)
        try:
            result = self._client.write_registers(
                self.cfg.serial_fifo_register, registers, device_id=self.cfg.unit_id
            )
        except Exception as exc:  # pymodbus raises ModbusException subclasses / socket errors
            raise PrinterError(f"ANSER serial push failed for {self.name}: {exc}", error_code="PRINT_002",
                                uncertain=True) from exc
        if result is None or result.isError():
            raise PrinterError(f"ANSER {self.name} rejected serial write: {result}", error_code="PRINT_002",
                                uncertain=True)

    def get_consumption_count(self) -> int:
        """Poll the cumulative FIFO-consumed counter. If the X1 only exposes
        an aggregate counter (Section 105 item 3, still unconfirmed), unit-
        level completion tracking compares this counter's delta against how
        many serials were pushed, not per-unit acknowledgements."""
        self._ensure_connected()
        try:
            result = self._client.read_holding_registers(
                self.cfg.consumption_counter_register, count=1, device_id=self.cfg.unit_id
            )
        except Exception as exc:
            raise PrinterError(f"ANSER counter read failed for {self.name}: {exc}", error_code="PRINT_001") from exc
        if result is None or result.isError():
            raise PrinterError(f"ANSER {self.name} counter read error: {result}", error_code="PRINT_001")
        return result.registers[0]

    def get_status(self) -> PrinterStatusInfo:
        try:
            self._ensure_connected()
            result = self._client.read_holding_registers(
                self.cfg.status_register, count=1, device_id=self.cfg.unit_id
            )
        except Exception as exc:
            return PrinterStatusInfo(status=PrinterStatus.OFFLINE, connected=False, detail=str(exc))
        if result is None or result.isError():
            return PrinterStatusInfo(status=PrinterStatus.UNKNOWN, connected=True, detail=str(result))
        code = result.registers[0]
        status = STATUS_CODE_MAP.get(code, PrinterStatus.UNKNOWN)
        return PrinterStatusInfo(status=status, connected=True, raw_state=str(code))

    def test_print(self) -> bool:
        self._ensure_connected()
        try:
            result = self._client.write_coil(self.cfg.test_print_coil, True, device_id=self.cfg.unit_id)
        except Exception:
            return False
        return result is not None and not result.isError()
