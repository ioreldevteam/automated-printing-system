"""Best-effort discovery of printers installed in the host print system."""
from __future__ import annotations

import re
import shutil
import subprocess
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