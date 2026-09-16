import pytest

from app.printers import discovery
from app.printers.discovery import (
    DiscoveredPrinter,
    discover_cups_printers,
    discover_network_devices,
    discover_printers,
    ensure_cups_queue,
)

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


def test_discover_cups_printers_falls_back_to_system_queue_for_network_printers(monkeypatch):
    monkeypatch.setattr("app.printers.discovery.shutil.which", lambda _: "/usr/bin/lpstat")

    class PrimaryResult:
        returncode = 1
        stdout = ""
        stderr = ""

    class FallbackResult:
        returncode = 0
        stdout = (
            "system default destination: WIFI_PRINTER\n"
            "device for WIFI_PRINTER: ipp://192.168.1.42/ipp/printer\n"
        )

    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[1:3] == ["-p", "-v"]:
            return PrimaryResult()
        if args[1:3] == ["-s", "-v"]:
            return FallbackResult()
        return FallbackResult()

    monkeypatch.setattr("app.printers.discovery.subprocess.run", fake_run)
    printers = discover_cups_printers()

    assert [args for args in calls if args[:2] == ["/usr/bin/lpstat", "-p"]] == [["/usr/bin/lpstat", "-p", "-v"]]
    assert printers[0].name == "WIFI_PRINTER"
    assert printers[0].uri.startswith("ipp://192.168.1.42")


def test_discover_network_devices_finds_wifi_printer_not_yet_installed(monkeypatch):
    """A Wi-Fi MFP that was never added as a CUPS queue (so lpstat can't see
    it) must still be found via lpinfo's dnssd/Bonjour backend -- this is the
    "PS3 on MFP13901874" case: a driverless network printer advertised over
    mDNS with a friendly name that includes spaces."""
    monkeypatch.setattr("app.printers.discovery.shutil.which", lambda _: "/usr/bin/lpinfo")

    class Result:
        returncode = 0
        stdout = (
            "network socket\n"
            "network http\n"
            "network ipp\n"
            "network ipps\n"
            "network lpd\n"
            "direct usb://EPSON/WF-3620%20Series?serial=XYZ\n"
            "network dnssd://PS3%20on%20MFP13901874._ipp._tcp.local./?uuid=abc-123\n"
        )
        stderr = ""

    monkeypatch.setattr("app.printers.discovery.subprocess.run", lambda *a, **k: Result())
    printers = discover_network_devices()

    assert len(printers) == 1
    found = printers[0]
    assert found.name == "PS3_on_MFP13901874"
    assert found.uri.startswith("dnssd://PS3%20on%20MFP13901874")
    assert found.source == "NETWORK"


def test_discover_network_devices_returns_empty_without_lpinfo(monkeypatch):
    monkeypatch.setattr("app.printers.discovery.shutil.which", lambda _: None)
    assert discover_network_devices() == []


def test_discover_printers_skips_already_installed_and_provisions_new(monkeypatch):
    """discover_printers() should not duplicate a printer lpstat already
    knows about, but should auto-create a CUPS queue (via lpadmin) for a
    Wi-Fi printer that's only visible through lpinfo."""

    def fake_which(cmd):
        return f"/usr/bin/{cmd}"

    monkeypatch.setattr("app.printers.discovery.shutil.which", fake_which)

    lpstat_result_type = type("R", (), {
        "returncode": 0,
        "stdout": (
            "printer ZEBRA_01 is idle. enabled since Tue 15 Sep 2026\n"
            "device for ZEBRA_01: socket://192.168.1.30:9100\n"
        ),
        "stderr": "",
    })
    lpinfo_result_type = type("R", (), {
        "returncode": 0,
        "stdout": (
            "network dnssd://ZEBRA_01._ipp._tcp.local./?uuid=already-installed\n"
            "network dnssd://PS3%20on%20MFP13901874._ipp._tcp.local./?uuid=new-printer\n"
        ),
        "stderr": "",
    })

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0].endswith("lpstat"):
            return lpstat_result_type()
        if command[0].endswith("lpinfo"):
            return lpinfo_result_type()
        if command[0].endswith("lpadmin"):
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        if command[0].endswith("avahi-browse"):
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        raise AssertionError(f"unexpected command {command}")

    monkeypatch.setattr("app.printers.discovery.subprocess.run", fake_run)
    printers = discover_printers()

    names = {p.name for p in printers}
    assert names == {"ZEBRA_01", "PS3_on_MFP13901874"}

    lpadmin_calls = [c for c in calls if c[0].endswith("lpadmin")]
    assert len(lpadmin_calls) == 1
    assert "PS3_on_MFP13901874" in lpadmin_calls[0]
    assert "-m" in lpadmin_calls[0] and "everywhere" in lpadmin_calls[0]


def test_ensure_cups_queue_returns_false_without_lpadmin(monkeypatch):
    monkeypatch.setattr("app.printers.discovery.shutil.which", lambda _: None)
    printer = DiscoveredPrinter(name="PS3_on_MFP13901874", uri="dnssd://PS3%20on%20MFP13901874._ipp._tcp.local./")
    assert ensure_cups_queue(printer) is False


def test_discover_windows_printers_parses_get_printer_json(monkeypatch):
    """Windows names Wi-Fi/WSD-discovered MFPs "<Driver> on <Host>" (e.g.
    "PS3 on MFP13901874") and lists them immediately via Get-Printer once
    they're connected -- no CUPS-style manual queue involved."""
    monkeypatch.setattr("app.printers.discovery.shutil.which",
                         lambda cmd: "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
                         if "powershell" in cmd else None)

    class Result:
        returncode = 0
        stdout = (
            '[{"Name":"PS3 on MFP13901874","DriverName":"Microsoft IPP Class Driver",'
            '"PortName":"192.168.1.55"},'
            '{"Name":"Microsoft Print to PDF","DriverName":"Microsoft Print To PDF",'
            '"PortName":"PORTPROMPT:"}]'
        )
        stderr = ""

    monkeypatch.setattr("app.printers.discovery.subprocess.run", lambda *a, **k: Result())
    printers = discovery.discover_windows_printers()

    names = {p.name for p in printers}
    assert "PS3 on MFP13901874" in names
    ps3 = next(p for p in printers if p.name == "PS3 on MFP13901874")
    assert ps3.uri == "192.168.1.55"
    assert ps3.source == "WINDOWS"


def test_discover_windows_printers_handles_single_object_json(monkeypatch):
    """ConvertTo-Json returns a bare object (not an array) when there's only
    one printer -- must not crash on that shape."""
    monkeypatch.setattr("app.printers.discovery.shutil.which", lambda cmd: "/usr/bin/powershell")

    class Result:
        returncode = 0
        stdout = '{"Name":"PS3 on MFP13901874","DriverName":"IPP","PortName":"192.168.1.55"}'
        stderr = ""

    monkeypatch.setattr("app.printers.discovery.subprocess.run", lambda *a, **k: Result())
    printers = discovery.discover_windows_printers()
    assert len(printers) == 1
    assert printers[0].name == "PS3 on MFP13901874"


def test_discover_windows_printers_returns_empty_without_powershell(monkeypatch):
    monkeypatch.setattr("app.printers.discovery.shutil.which", lambda cmd: None)
    assert discovery.discover_windows_printers() == []


def test_discover_printers_routes_to_windows_when_platform_is_windows(monkeypatch):
    monkeypatch.setattr("app.printers.discovery.is_windows", lambda: True)
    monkeypatch.setattr("app.printers.discovery.discover_windows_printers",
                         lambda: [DiscoveredPrinter(name="PS3 on MFP13901874", uri="192.168.1.55",
                                                     source="WINDOWS")])
    printers = discover_printers()
    assert [p.name for p in printers] == ["PS3 on MFP13901874"]


def test_windows_printer_connect_and_status(monkeypatch):
    from app.printers.windows import WindowsPrinter
    monkeypatch.setattr("app.printers.windows._powershell_executable", lambda: "/usr/bin/powershell")

    class OkResult:
        returncode = 0
        stdout = "Normal"
        stderr = ""

    monkeypatch.setattr("app.printers.windows.subprocess.run", lambda *a, **k: OkResult())
    printer = WindowsPrinter(name="PS3 on MFP13901874", port_name="192.168.1.55")
    printer.connect()  # should not raise
    status = printer.get_status()
    assert status.connected is True


def test_windows_printer_registered_via_printer_manager(monkeypatch):
    """A printer discovered with source="WINDOWS" must be built as a
    WindowsPrinter (not CupsPrinter), since CUPS doesn't exist on Windows."""
    from app.printers.printer_manager import PrinterManager
    from app.printers.windows import WindowsPrinter

    manager = PrinterManager()
    added = manager.register_discovered(
        [DiscoveredPrinter(name="PS3 on MFP13901874", uri="192.168.1.55", source="WINDOWS")]
    )
    assert added == ["PS3 on MFP13901874"]
    assert isinstance(manager.get("PS3 on MFP13901874"), WindowsPrinter)
