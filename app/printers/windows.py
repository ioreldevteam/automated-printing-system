"""Windows printer adapter -- the Windows-host counterpart to CupsPrinter.

CUPS doesn't exist on Windows, so printers there (including Wi-Fi/WSD/Bonjour
MFPs that Windows names "<Driver> on <Host>", e.g. "PS3 on MFP13901874") are
driven through the built-in ``Get-Printer`` / ``Out-Printer`` PowerShell
cmdlets instead. This avoids an extra dependency (e.g. pywin32) purely for
discovery/status/raw text output. As with CupsPrinter's raw ``lp -o raw``,
this is a best-effort text/raw pipeline suited to label/receipt content, not
a full graphics/driver pipeline.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from app.domain.models import LabelData, PrinterStatusInfo
from app.domain.states import PrinterStatus
from app.printers.base import BasePrinter, PrinterError


def _powershell_executable() -> str | None:
    for candidate in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


class WindowsPrinter(BasePrinter):
    def __init__(self, name: str, port_name: str = "", connect_timeout: float = 5.0):
        self.name = name
        self.port_name = port_name
        self.connect_timeout = connect_timeout
        # Labels are buffered here instead of being sent to Windows one at a
        # time (see flush_batch): sending N separate Out-Printer jobs means
        # the operator can see up to N separate print prompts/spooler jobs
        # for a single batch. Buffering and sending once as one job means
        # one click starts the job and every page in that job's quantity
        # comes out together.
        self._pending_documents: list[str] = []

    def _escaped_name(self) -> str:
        # Single-quote escaping for PowerShell: '' inside a '...' literal.
        return self.name.replace("'", "''")

    def _run_powershell(self, script: str) -> subprocess.CompletedProcess[str]:
        executable = _powershell_executable()
        if executable is None:
            raise PrinterError("PowerShell is not available to talk to Windows printers",
                                error_code="PRINTER_001")
        try:
            return subprocess.run(
                [executable, "-NoProfile", "-NonInteractive", "-Command", script],
                check=False, capture_output=True, text=True, timeout=self.connect_timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PrinterError(f"Windows print command failed for {self.name}: {exc}",
                                error_code="PRINTER_001") from exc

    def connect(self) -> None:
        result = self._run_powershell(f"Get-Printer -Name '{self._escaped_name()}' | Out-Null")
        if result.returncode != 0:
            raise PrinterError(
                result.stderr.strip() or f"Windows printer '{self.name}' is unavailable",
                error_code="PRINTER_001",
            )

    def disconnect(self) -> None:
        pass

    def get_status(self) -> PrinterStatusInfo:
        script = f"Get-Printer -Name '{self._escaped_name()}' | Select-Object -ExpandProperty PrinterStatus"
        try:
            result = self._run_powershell(script)
        except PrinterError as exc:
            return PrinterStatusInfo(status=PrinterStatus.OFFLINE, connected=False, detail=str(exc))
        if result.returncode != 0:
            return PrinterStatusInfo(status=PrinterStatus.OFFLINE, connected=False,
                                     detail=result.stderr.strip() or "Windows printer unavailable")
        raw = result.stdout.strip()
        lowered = raw.lower()
        if "offline" in lowered or "error" in lowered:
            status = PrinterStatus.OFFLINE
        elif "printing" in lowered or "busy" in lowered:
            status = PrinterStatus.BUSY
        elif "paperout" in lowered or "no paper" in lowered:
            status = PrinterStatus.MEDIA_OUT
        elif "paused" in lowered:
            status = PrinterStatus.PAUSED
        else:
            status = PrinterStatus.READY
        return PrinterStatusInfo(status=status, connected=True, raw_state=raw, detail=raw or "Normal")

    @staticmethod
    def _render_document(label: LabelData) -> str:
        return (
            f"PRODUCT: {label.product_name}\n"
            f"SERIAL: {label.serial_number}\n"
            f"BATCH: {label.batch_number}\n"
            f"DATE: {label.date}\n"
            "\f"  # form feed: force a page eject after this label so a
                  # batch of N labels comes out as N pages, not merged onto
                  # one page/strip -- see the matching note in cups.py.
        )

    def print_label(self, template: str, label: LabelData) -> None:
        """Buffer this label rather than sending it to Windows immediately.
        Call flush_batch() once the whole quantity is ready (or is done
        printing) to actually submit it as one print job."""
        del template
        self._pending_documents.append(self._render_document(label))

    def supports_batch_printing(self) -> bool:
        return True

    def flush_batch(self) -> None:
        if not self._pending_documents:
            return
        document = "".join(self._pending_documents)
        handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        try:
            handle.write(document)
            handle.close()
            script = (
                f"Get-Content -Raw '{handle.name}' | Out-Printer -Name '{self._escaped_name()}'"
            )
            result = self._run_powershell(script)
        finally:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
        if result.returncode != 0:
            # Keep the buffered documents so the caller can retry the whole
            # batch instead of losing labels that never actually printed.
            raise PrinterError(
                result.stderr.strip() or f"Windows print failed for '{self.name}'",
                error_code="PRINT_002", uncertain=True,
            )
        self._pending_documents.clear()

    def test_print(self) -> bool:
        # A test print must happen immediately, not sit in the batch buffer
        # behind whatever a real job has queued -- so it prints its own
        # single-label document straight away rather than going through
        # print_label()/flush_batch().
        test_label = LabelData(product_name="TEST", serial_number="TEST0000", batch_number="TEST")
        document = self._render_document(test_label)
        handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        try:
            handle.write(document)
            handle.close()
            script = f"Get-Content -Raw '{handle.name}' | Out-Printer -Name '{self._escaped_name()}'"
            result = self._run_powershell(script)
        finally:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
        return result.returncode == 0
