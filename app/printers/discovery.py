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

    CUPS normally exposes USB printers, including Epson LQ-310 queues, through
    ``lpstat``. Discovery is intentionally metadata-only; printing still uses
    an explicitly configured adapter.
    """
    lpstat = shutil.which("lpstat")
    if lpstat is None:
        return []
    try:
        result = subprocess.run(
            [lpstat, "-p", "-v"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []

    printers: dict[str, DiscoveredPrinter] = {}
    for line in result.stdout.splitlines():
        printer_match = re.match(r"printer (\S+) (.*)", line)
        if printer_match:
            name, _ = printer_match.groups()
            printers[name] = DiscoveredPrinter(name=name)
            continue
        device_match = re.match(r"device for (\S+): (\S+)", line)
        if device_match:
            name, uri = device_match.groups()
            existing = printers.get(name, DiscoveredPrinter(name=name))
            printers[name] = DiscoveredPrinter(
                name=existing.name, uri=uri, model=existing.model, source=existing.source
            )
    return list(printers.values())