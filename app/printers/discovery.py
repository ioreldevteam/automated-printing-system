"""Best-effort discovery of printers installed in the host print system."""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import urllib.parse
from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveredPrinter:
    name: str
    uri: str = ""
    model: str = ""
    source: str = "CUPS"


def discover_cups_printers() -> list[DiscoveredPrinter]:
    """Return printers known to CUPS without failing application startup.

    CUPS exposes both USB and network/Wi‑Fi printers through ``lpstat``. Some
    setups return a minimal `lpstat -p -v` output while others use a default
    destination summary; we accept both forms and treat them as valid CUPS
    printers. Discovery is intentionally metadata-only; printing still uses an
    explicitly configured adapter.
    """
    lpstat = shutil.which("lpstat")
    if lpstat is None:
        return []

    commands = [
        [lpstat, "-p", "-v"],
        [lpstat, "-s", "-v"],
    ]

    printers: dict[str, DiscoveredPrinter] = {}
    for command in commands:
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0 and result.returncode != 1:
            continue

        for line in result.stdout.splitlines():
            if not line.strip():
                continue

            printer_match = re.match(r"printer\s+(\S+)\s+.*", line)
            if printer_match:
                name = printer_match.group(1)
                printers.setdefault(name, DiscoveredPrinter(name=name))
                continue

            default_match = re.match(r"system default destination:\s*(\S+)", line)
            if default_match:
                name = default_match.group(1)
                printers.setdefault(name, DiscoveredPrinter(name=name))
                continue

            device_match = re.match(r"device for\s+(\S+):\s*(.+)$", line)
            if device_match:
                name, uri = device_match.groups()
                existing = printers.get(name, DiscoveredPrinter(name=name))
                source = "USB" if uri.lower().startswith("usb://") else "NETWORK"
                printers[name] = DiscoveredPrinter(
                    name=existing.name,
                    uri=uri.strip(),
                    model=existing.model,
                    source=source,
                )

    return list(printers.values())


def _sanitize_queue_name(name: str) -> str:
    """CUPS queue names may only contain letters, digits, '_', '-', '.'.
    Bonjour/mDNS advertised names (e.g. "PS3 on MFP13901874") contain spaces
    and can't be used as-is with ``lpadmin -p``."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "NETWORK_PRINTER"


def _friendly_name_from_dnssd_uri(uri: str) -> str:
    """A ``dnssd://`` device URI encodes the printer's Bonjour/mDNS service
    name as the URL host, e.g.::

        dnssd://PS3%20on%20MFP13901874._ipp._tcp.local./?uuid=...

    which advertises a Wi-Fi-connected printer as "PS3 on MFP13901874" (PS3 =
    PostScript level 3 support; the second half is the device's own
    model/serial string). This pulls the human-readable name back out.
    """
    parsed = urllib.parse.urlparse(uri)
    host = urllib.parse.unquote(parsed.netloc or parsed.path)
    host = re.sub(r"\._ipps?\._tcp\.local\.?.*$", "", host)
    host = host.rstrip("./")
    return host or uri


def discover_network_devices() -> list[DiscoveredPrinter]:
    """Discover printers CUPS's backends can see on the network (Wi-Fi or
    Ethernet, via DNS-SD/Bonjour/AirPrint) that do NOT yet have a local CUPS
    queue configured.

    This is the piece ``discover_cups_printers()`` (which only reads
    ``lpstat``, i.e. *already installed* queues) misses: a printer that is
    simply present on the Wi-Fi network but was never "added" through
    Settings/system-config-printer is invisible to lpstat even though CUPS's
    ``lpinfo`` backends already know about it.
    """
    lpinfo = shutil.which("lpinfo")
    if lpinfo is None:
        return []
    try:
        result = subprocess.run([lpinfo, "-v"], check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode not in (0, 1):
        return []

    discovered: list[DiscoveredPrinter] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        device_class, uri = parts
        # "network"/"dnssd" cover Wi-Fi and Ethernet printers; skip local
        # buses (usb/serial/parallel/beh) and bare backend-name placeholders
        # (e.g. "network socket" with no "://" is just an available backend,
        # not an actual discovered device).
        if device_class not in ("network", "dnssd") or "://" not in uri:
            continue
        scheme = uri.split("://", 1)[0].lower()

        if scheme == "dnssd":
            name = _friendly_name_from_dnssd_uri(uri)
        elif scheme in ("ipp", "ipps", "socket", "lpd", "http", "https"):
            name = urllib.parse.urlparse(uri).hostname or uri
        else:
            continue
        discovered.append(DiscoveredPrinter(name=_sanitize_queue_name(name), uri=uri, source="NETWORK"))
    return discovered


def discover_avahi_printers() -> list[DiscoveredPrinter]:
    """Fallback Wi-Fi/network discovery via ``avahi-browse`` (raw mDNS/Bonjour)
    for hosts where CUPS's own dnssd backend or the ``cups-browsed`` service
    isn't running/picking things up, even though the printer is genuinely
    broadcasting on the network. Complements discover_network_devices().
    """
    avahi_browse = shutil.which("avahi-browse")
    if avahi_browse is None:
        return []

    discovered: dict[str, DiscoveredPrinter] = {}
    for service_type in ("_ipp._tcp", "_ipps._tcp", "_printer._tcp"):
        try:
            result = subprocess.run(
                [avahi_browse, "-r", "-p", "-t", service_type],
                check=False, capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            if not line.startswith("="):
                continue
            fields = line.split(";")
            if len(fields) < 9:
                continue
            name = fields[3].strip()
            host = fields[6].strip()
            address = fields[7].strip()
            port = fields[8].strip() or "631"
            if not name:
                continue
            uri = f"ipp://{address or host}:{port}/ipp/print"
            discovered.setdefault(name, DiscoveredPrinter(name=_sanitize_queue_name(name), uri=uri,
                                                            source="NETWORK"))
    return list(discovered.values())


def ensure_cups_queue(printer: DiscoveredPrinter) -> bool:
    """Provision a real CUPS queue for a printer found only via
    ``discover_network_devices()``/``discover_avahi_printers()`` so it
    becomes actually printable (``lp -d <name>``), not just visible. Uses
    driverless IPP Everywhere (``lpadmin -m everywhere``), which is what
    modern Wi-Fi/AirPrint-class MFPs -- including ones that advertise
    PostScript level 3 ("PS3") support -- use instead of a vendor driver.
    Returns True on success; failures (missing ``lpadmin``, insufficient
    privilege, printer offline) are swallowed so discovery never crashes the
    app -- the printer still shows up as DETECTED either way.
    """
    lpadmin = shutil.which("lpadmin")
    if lpadmin is None or not printer.uri:
        return False
    try:
        result = subprocess.run(
            [lpadmin, "-p", printer.name, "-E", "-v", printer.uri, "-m", "everywhere"],
            check=False, capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def discover_printers() -> list[DiscoveredPrinter]:
    """Full host printer discovery. On Windows this queries the built-in
    printer subsystem directly (there is no CUPS); on Linux/macOS it combines
    already-installed CUPS queues (USB and network) with Wi-Fi/network
    printers CUPS can see but hasn't installed yet (via lpinfo, with an
    avahi-browse fallback), auto-provisioning the latter so they're
    immediately usable, not just listed.
    """
    if is_windows():
        return discover_windows_printers()

    installed = discover_cups_printers()
    known_names = {p.name for p in installed}

    network_only: list[DiscoveredPrinter] = []
    for printer in discover_network_devices() + discover_avahi_printers():
        if printer.name in known_names:
            continue
        ensure_cups_queue(printer)
        network_only.append(printer)
        known_names.add(printer.name)

    return installed + network_only


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def _powershell_executable() -> str | None:
    for candidate in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def discover_windows_printers() -> list[DiscoveredPrinter]:
    """Enumerate printers Windows already knows about (Settings > Printers &
    scanners / Devices and Printers), via the built-in ``Get-Printer``
    PowerShell cmdlet -- no CUPS, no extra dependency.

    This is what finds a Wi-Fi/network MFP like "PS3 on MFP13901874": Windows
    auto-installs Wi-Fi/WSD/Bonjour printers under exactly that
    "<Driver> on <Host>" name once you've connected to them via Settings, and
    `Get-Printer` lists it immediately -- no CUPS-style manual queue needed.
    """
    powershell = _powershell_executable()
    if powershell is None:
        return []

    command = [
        powershell, "-NoProfile", "-NonInteractive", "-Command",
        "Get-Printer | Select-Object Name, DriverName, PortName | ConvertTo-Json -Compress",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []

    output = result.stdout.strip()
    if not output:
        return []
    try:
        data = json.loads(output)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]

    discovered: list[DiscoveredPrinter] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("Name") or "").strip()
        if not name:
            continue
        driver = (entry.get("DriverName") or "").strip()
        port = (entry.get("PortName") or "").strip()
        # Windows printer names may contain spaces (e.g. "PS3 on
        # MFP13901874") and are used as-is by Get-Printer/Out-Printer -- do
        # NOT run these through _sanitize_queue_name, which is only needed
        # for CUPS's stricter -p queue-name rules.
        discovered.append(DiscoveredPrinter(name=name, uri=port, model=driver, source="WINDOWS"))
    return discovered