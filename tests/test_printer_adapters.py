import pytest

from app.printers.discovery import discover_cups_printers

from app.domain.models import LabelData
from app.domain.states import PrinterStatus
from app.printers.anser import _pack_serial_to_registers
from app.printers.base import PrinterError
from app.printers.simulation import SimulationPrinter
from app.printers.template_engine import render_template
from app.printers.zebra import ZebraPrinter


def test_pack_serial_to_registers_round_trip():
    registers = _pack_serial_to_registers("SN00001487", register_count=10)
    assert len(registers) == 10
    chars = []
    for reg in registers:
        hi = (reg >> 8) & 0xFF
        lo = reg & 0xFF
        chars.append(chr(hi))
        if lo:
            chars.append(chr(lo))
    recovered = "".join(chars).rstrip("\x00")
    assert recovered == "SN00001487"


def test_pack_serial_truncates_to_register_capacity():
    registers = _pack_serial_to_registers("X" * 50, register_count=4)
    assert len(registers) == 4  # 4 registers -> 8 chars max


def test_render_template_substitutes_all_fields():
    label = LabelData(product_name="Widget", serial_number="SN001", batch_number="B1", date="2026-09-14")
    rendered = render_template("{PRODUCT_NAME}|{SERIAL_NUMBER}|{BATCH_NUMBER}|{DATE}", label)
    assert rendered == "Widget|SN001|B1|2026-09-14"


def test_zebra_parse_host_status_ready():
    text = "\x02000,0,0,0208,000\x03\r\n\x0200000000,0,0,0,00000000,0\x03\r\n\x020,0,0,0000,0000,0,0,0,0\x03\r\n"
    info = ZebraPrinter._parse_host_status(text)
    assert info.status == PrinterStatus.READY


def test_zebra_parse_host_status_paper_out():
    text = "\x02000,1,0,0208,000\x03\r\n"
    info = ZebraPrinter._parse_host_status(text)
    assert info.status == PrinterStatus.MEDIA_OUT


def test_zebra_parse_host_status_empty_response():
    info = ZebraPrinter._parse_host_status("")
    assert info.status == PrinterStatus.UNKNOWN


def test_simulation_printer_one_shot_failure():
    printer = SimulationPrinter("SIM-1", role="ZEBRA")
    printer.connect()
    printer.inject_failure("media_out")
    with pytest.raises(PrinterError):
        printer.print_label("^XA^XZ", LabelData(product_name="P", serial_number="S1"))
    # one-shot: clears after firing
    printer.print_label("^XA^XZ", LabelData(product_name="P", serial_number="S2"))


def test_simulation_printer_failure_at_specific_call():
    printer = SimulationPrinter("SIM-2", role="ANSER")
    printer.connect()
    printer.inject_failure("offline", at_call=3)
    printer.push_serial("SN1")
    printer.connect()  # offline failure disconnects; reconnect for next calls
    printer.push_serial("SN2")
    with pytest.raises(PrinterError):
        printer.push_serial("SN3")
    assert printer.get_consumption_count() == 2


def test_discover_cups_printers_parses_usb_queue(monkeypatch):
    monkeypatch.setattr("app.printers.discovery.shutil.which", lambda _: "/usr/bin/lpstat")

    class Result:
        returncode = 0
        stdout = (
            "printer EPSON_LQ310 is idle. enabled since Tue 15 Sep 2026\n"
            "device for EPSON_LQ310: usb://EPSON/LQ-310?serial=ABC123\n"
        )

    monkeypatch.setattr("app.printers.discovery.subprocess.run", lambda *args, **kwargs: Result())
    printers = discover_cups_printers()

    assert printers[0].name == "EPSON_LQ310"
    assert printers[0].uri.startswith("usb://EPSON/LQ-310")
