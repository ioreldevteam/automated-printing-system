# Industrial Automated Printing System
## Full Technical Implementation Plan

**Document Version:** 1.0  
**Date:** 2026-09-10  
**Target:** Desktop Python production printing application  
**Production Volume:** Approximately 3,000 units/day

---

## 1. Executive Summary

This project is a desktop-based industrial printing control system that automates a production labeling workflow.

The operator will:

1. Select a product.
2. Enter the required production quantity.
3. Request/obtain product serial numbers from an external API.
4. Select or use configured production printers.
5. Print the required product marking using an ANSER X Series printer integrated with a conveyor.
6. Print sticker labels using Zebra printers.
7. Monitor printer and production status in real time.
8. Pause production automatically when a printer or system failure occurs.
9. Resolve the failure.
10. Resume from the exact unfinished production point.
11. Maintain permanent production, printer, error, recovery, and audit logs.

The most important design principle is:

> **The local production database is the source of truth for production state.**

The application must never depend only on printer counters or an in-memory queue to determine where production stopped.

---

# 2. Project Goals

## 2.1 Primary Goals

- Automate production printing.
- Support product selection.
- Integrate with the product/serial-number API.
- Support ANSER X Series printing.
- Support Zebra sticker printing.
- Handle approximately 3,000 units per production day.
- Detect printer failures.
- Automatically pause when production cannot safely continue.
- Allow operator-controlled recovery.
- Continue from the exact stop point.
- Prevent duplicate or missing serial numbers.
- Maintain complete production history.
- Provide operator-friendly desktop UI.
- Support multiple printers.
- Provide reliable local operation even when the external API is temporarily unavailable.

## 2.2 Secondary Goals

- Printer health monitoring.
- Print retry management.
- Production reports.
- Operator authentication.
- Audit logging.
- Configuration management.
- Printer testing.
- Job recovery after application restart.
- Recovery after PC restart/power failure.
- Future barcode/camera verification.
- Future integration with PLC/industrial control systems.

---

# 3. Scope

## 3.1 In Scope

### Desktop Application

- Product selection
- Quantity input
- Production job creation
- Printer selection
- Production start/pause/resume/stop
- Real-time progress
- Printer monitoring
- Error display
- Recovery workflow
- Production history
- Logs
- Configuration

### API Integration

- Product retrieval
- Serial number allocation
- Production job communication
- API authentication
- Retry handling
- Timeout handling

### Printing

- ANSER X Series integration
- Zebra printer integration
- ZPL template management
- Sticker printing
- Print queue management
- Print retry

### Reliability

- Persistent production state
- Failure detection
- Automatic pause
- Recovery
- Crash recovery
- Duplicate prevention
- Audit trail

---

# 4. Out of Scope for Initial Version

The following should not be part of the first MVP unless required by the factory:

- Cloud dashboard
- Multi-site production management
- Complex ERP replacement
- Advanced computer vision
- Predictive maintenance
- AI-based printer failure prediction
- Remote production control
- Mobile application
- Full MES replacement

These can be added later.

---

# 5. High-Level Architecture

```text
                         EXTERNAL SYSTEM
                              |
                              v
                    +----------------------+
                    | Product / Serial API |
                    +----------+-----------+
                               |
                               | HTTPS
                               v
+----------------------------------------------------------------+
|                 PYTHON DESKTOP APPLICATION                     |
|                                                                |
|  +----------------------+       +----------------------------+ |
|  |      PySide6 UI      |       |   Production Controller    | |
|  +----------+-----------+       +-------------+--------------+ |
|             |                                 |                |
|             |                                 v                |
|             |                    +--------------------------+  |
|             |                    | State Machine / Job Mgmt |  |
|             |                    +------------+-------------+  |
|             |                                 |                |
|             |                 +---------------+--------------+ |
|             |                 |                              | |
|             v                 v                              v |
|      +-------------+   +--------------+              +---------+|
|      | Local DB    |   | Print Queue  |              | Monitor ||
|      | SQLite      |   | Manager      |              | Service ||
|      +-------------+   +------+-------+              +----+----+|
|                               |                           |     |
+-------------------------------|---------------------------|-----+
                                |                           |
                 +--------------+-------------+             |
                 |                            |             |
                 v                            v             v
          +--------------+              +-------------+  Status
          | ANSER X      |              | Zebra       |
          | Series       |              | Printer(s)  |
          +------+-------+              +------+------+ 
                 |                             |
                 v                             v
            Conveyor                   Sticker Labels
                 |                             |
                 +-------------+---------------+
                               |
                               v
                         Production Line
```

---

# 6. Core Architecture Principles

## 6.1 Database Is the Source of Truth

Never use:

- Python variables
- printer counters
- temporary files
- UI counters

as the authoritative production state.

Use the database.

Example:

```text
SN001485 -> COMPLETED
SN001486 -> COMPLETED
SN001487 -> PRINTING
SN001488 -> QUEUED
SN001489 -> QUEUED
```

If the application crashes, it can recover from this state.

---

# 7. Recommended Technology Stack

| Layer | Technology |
|---|---|
| Desktop UI | Python + PySide6 |
| Language | Python 3.12+ |
| Database | SQLite |
| ORM | SQLAlchemy |
| HTTP Client | httpx |
| Async Operations | asyncio where appropriate |
| Validation | Pydantic |
| Configuration | YAML |
| Logging | Python logging |
| Zebra | ZPL / TCP / Zebra developer technologies |
| Label Design | ZebraDesigner for Developers |
| ANSER | Vendor interface / SDK / network protocol / PLC |
| Testing | pytest |
| Packaging | PyInstaller |
| Database Migrations | Alembic |
| API Security | HTTPS + token authentication |
| Optional Verification | Barcode scanner / industrial camera |

---

# 8. Desktop Application Architecture

The application should use a layered architecture.

```text
app/
|
+-- ui/
|
+-- application/
|
+-- domain/
|
+-- infrastructure/
|
+-- printers/
|
+-- api/
|
+-- database/
|
+-- monitoring/
|
+-- logging/
|
+-- config/
|
+-- tests/
```

Do not put printer commands directly inside PySide6 button handlers.

---

# 9. Recommended Project Structure

```text
production_print_system/
|
+-- app/
|   |
|   +-- main.py
|   |
|   +-- ui/
|   |   +-- main_window.py
|   |   +-- dashboard.py
|   |   +-- production_view.py
|   |   +-- printer_view.py
|   |   +-- jobs_view.py
|   |   +-- history_view.py
|   |   +-- settings_view.py
|   |   +-- dialogs/
|   |       +-- error_dialog.py
|   |       +-- recovery_dialog.py
|   |       +-- printer_test_dialog.py
|   |
|   +-- application/
|   |   +-- production_service.py
|   |   +-- job_service.py
|   |   +-- recovery_service.py
|   |   +-- printer_service.py
|   |   +-- serial_service.py
|   |
|   +-- domain/
|   |   +-- models.py
|   |   +-- states.py
|   |   +-- events.py
|   |   +-- exceptions.py
|   |
|   +-- printers/
|   |   +-- base.py
|   |   +-- zebra.py
|   |   +-- anser.py
|   |   +-- printer_manager.py
|   |
|   +-- api/
|   |   +-- client.py
|   |   +-- auth.py
|   |   +-- serial_api.py
|   |   +-- product_api.py
|   |
|   +-- database/
|   |   +-- database.py
|   |   +-- models.py
|   |   +-- repositories.py
|   |   +-- migrations/
|   |
|   +-- monitoring/
|   |   +-- printer_monitor.py
|   |   +-- health_monitor.py
|   |   +-- network_monitor.py
|   |
|   +-- queue/
|   |   +-- print_queue.py
|   |   +-- queue_worker.py
|   |
|   +-- templates/
|   |   +-- zpl/
|   |
|   +-- config/
|   |   +-- loader.py
|   |
|   +-- logging/
|       +-- logger.py
|
+-- tests/
|
+-- resources/
|   +-- icons/
|   +-- templates/
|
+-- config.yaml
+-- requirements.txt
+-- production.db
+-- README.md
```

---

# 10. Main Production Workflow

```text
START
  |
  v
Operator Login
  |
  v
Select Product
  |
  v
Enter Quantity
  |
  v
Validate Product + Quantity
  |
  v
Create Production Job
  |
  v
Request Serial Numbers
  |
  v
Persist Serial Numbers Locally
  |
  v
Select / Load Printer Configuration
  |
  v
Test Printers
  |
  v
Start Production
  |
  v
Queue Production Units
  |
  v
ANSER Printing
  |
  v
ANSER Verification / Completion
  |
  v
Zebra Sticker Printing
  |
  v
Zebra Verification
  |
  v
Mark Unit COMPLETED
  |
  v
Next Unit
  |
  v
Quantity Reached?
  |
 YES
  |
  v
Complete Job
```

---

# 11. Production State Machine

The state machine is one of the most important components.

## 11.1 Job States

```text
CREATED
QUEUED
RUNNING
PAUSED
RECOVERING
STOPPING
STOPPED
COMPLETED
FAILED
CANCELLED
```

## 11.2 Unit States

```text
ALLOCATED
QUEUED
ANSER_PRINTING
ANSER_PRINTED
ZEBRA_PRINTING
ZEBRA_PRINTED
VERIFYING
COMPLETED
FAILED
RETRY_PENDING
UNKNOWN
```

## 11.3 State Example

```text
ALLOCATED
    |
    v
QUEUED
    |
    v
ANSER_PRINTING
    |
    v
ANSER_PRINTED
    |
    v
ZEBRA_PRINTING
    |
    v
ZEBRA_PRINTED
    |
    v
VERIFYING
    |
    v
COMPLETED
```

Failure:

```text
ANY PRINT STATE
      |
      v
    FAILED
      |
      v
RETRY_PENDING
      |
      v
RECOVERING
      |
      v
PRINTING
```

Uncertain result:

```text
PRINTING
   |
   v
UNKNOWN
   |
   v
RECONCILIATION
   |
   +---- VERIFIED PRINTED ----> COMPLETED
   |
   +---- NOT PRINTED ---------> RETRY
```

---

# 12. Production Unit Model

Every physical unit should have its own record.

Example:

```text
Production Unit
-------------------------
Job ID: JOB-001
Sequence: 1487
Serial: SN001487

ANSER:
  Status: PRINTED

Zebra:
  Status: PRINTING

Overall:
  ZEBRA_PRINTING
```

This provides exact recovery.

---

# 13. Database Design

## 13.1 Tables

Recommended initial tables:

```text
users
products
printers
printer_templates

production_jobs
production_units

serial_batches
print_attempts

printer_events
system_events
audit_logs

application_settings
```

---

# 14. `users`

```text
id
username
password_hash
role
active
created_at
last_login_at
```

Roles:

```text
ADMIN
SUPERVISOR
OPERATOR
MAINTENANCE
VIEWER
```

---

# 15. `products`

```text
id
external_product_id
product_code
product_name
description
active
created_at
updated_at
```

---

# 16. `printers`

```text
id
name
type
model
ip_address
port
enabled
location
configuration_json
created_at
updated_at
```

Example:

```text
ZEBRA-01
type = ZEBRA

ANSER-01
type = ANSER
```

---

# 17. `production_jobs`

```text
id
job_number
product_id

requested_quantity
allocated_quantity
completed_quantity
failed_quantity

status

current_sequence

started_at
paused_at
resumed_at
completed_at

created_by
created_at
updated_at
```

---

# 18. `production_units`

```text
id
job_id
sequence_number
serial_number

anser_status
anser_printed_at

zebra_status
zebra_printed_at

verification_status
verified_at

overall_status

attempt_count

created_at
updated_at
```

Important constraint:

```text
UNIQUE(job_id, sequence_number)
```

and, if serials are globally unique:

```text
UNIQUE(serial_number)
```

---

# 19. `print_attempts`

Every print attempt should be recorded.

```text
id
production_unit_id
printer_id
print_stage

attempt_number

request_payload_hash
status

error_code
error_message

started_at
completed_at
```

Example:

```text
SN001487
ZEBRA
attempt 1
FAILED
MEDIA_OUT
```

Then:

```text
SN001487
ZEBRA
attempt 2
SUCCESS
```

---

# 20. `printer_events`

```text
id
printer_id
event_type
status
error_code
message
created_at
```

Examples:

```text
ONLINE
OFFLINE
MEDIA_OUT
RIBBON_OUT
HEAD_OPEN
READY
PAUSED
ERROR
RECOVERED
```

---

# 21. `audit_logs`

Every important operator/system action should be logged.

```text
id
user_id
action
entity_type
entity_id
details
created_at
```

Examples:

```text
START_JOB
PAUSE_JOB
RESUME_JOB
STOP_JOB
RETRY_PRINT
RESET_PRINTER
CHANGE_CONFIGURATION
LOGIN
LOGOUT
```

---

# 22. Serial Number Management

The serial API integration must be designed for recovery.

Do not use:

```text
request 100 serials
print them
request another 100
```

without tracking the allocation.

Instead:

```text
Production Job
      |
      v
Serial Batch
      |
      v
Local Database
      |
      v
Production Units
```

Example:

```text
JOB-001

Serial Batch:
BATCH-001

Quantity:
3000

Serials:
SN000001
SN000002
...
SN003000
```

---

# 23. API Idempotency

The external API should ideally support a production job or batch ID.

Example:

```http
POST /production/jobs
```

Request:

```json
{
  "product_id": "PROD-001",
  "quantity": 3000,
  "client_job_id": "JOB-20260910-001"
}
```

Response:

```json
{
  "job_id": "JOB-20260910-001",
  "serial_batch_id": "BATCH-001",
  "quantity": 3000
}
```

If the client repeats the request with the same ID, the server should return the existing job rather than allocate duplicate serials.

If the API cannot support idempotency, the local application must carefully persist the API response before continuing.

---

# 24. Serial Buffering

Do not necessarily load all serials into Python memory.

Use:

```text
API
 |
 v
Local Database
 |
 v
Durable Queue
 |
 v
Printer
```

The application can maintain a configurable buffer:

```text
50
100
200
```

depending on the API and production speed.

---

# 25. Zebra Integration

Zebra should be isolated behind a printer interface.

```python
class Printer:

    def connect(self):
        ...

    def disconnect(self):
        ...

    def get_status(self):
        ...

    def print_label(self, data):
        ...

    def test_print(self):
        ...

    def pause(self):
        ...

    def resume(self):
        ...
```

Implementation:

```text
Printer
   |
   +-- ZebraPrinter
   |
   +-- AnserPrinter
```

The production controller should not need to know Zebra-specific commands.

---

# 26. Zebra Label Templates

Use ZebraDesigner for creating label templates.

The application should maintain versioned templates.

Example:

```text
templates/
|
+-- product_label_v1.zpl
+-- product_label_v2.zpl
+-- sticker_label_v1.zpl
```

A template can contain:

```text
PRODUCT_NAME
SERIAL_NUMBER
BATCH_NUMBER
DATE
EXPIRY_DATE
BARCODE
QR_CODE
```

Python supplies the values.

Example:

```python
label_data = {
    "PRODUCT_NAME": "Example Product",
    "SERIAL_NUMBER": "SN001487",
    "BATCH_NUMBER": "B20260910",
    "DATE": "2026-09-10"
}
```

## 26.1 Automatic Barcode/QR Generation (No Manual Placement)

The printer generates the barcode and QR code natively from the serial number — the operator never creates or places a barcode by hand, and the application never needs a separate barcode-image step for Zebra labels.

Example ZPL template:

```text
^XA
^FO50,50^A0N,30,30^FD{PRODUCT_NAME}^FS
^FO50,100^BY2
^BCN,80,Y,N,N^FD{SERIAL_NUMBER}^FS
^FO50,220^BQN,2,5^FDQA,{SERIAL_NUMBER}^FS
^XZ
```

- `^BC` renders a Code 128 barcode directly from the serial number text supplied in the following `^FD` field.
- `^BQ` renders a QR code the same way.
- The Python layer only substitutes `{PRODUCT_NAME}` and `{SERIAL_NUMBER}` into the template string before sending the finished ZPL over the socket. No image library, no manual layout step, no per-unit design work.

This is why templates are versioned as raw `.zpl` text files (Section 65) rather than as static images — the barcode data changes every unit, but the template itself does not.

## 26.2 Fallback: Raster/Bitmap Label Rendering

If a given printer's command language has no native barcode primitive (this must be confirmed for the ANSER X series — see Section 28), the label must instead be fully rendered as a bitmap in Python before sending:

```python
import qrcode
from barcode import Code128
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw

def build_label(serial_no: str, product_name: str) -> Image.Image:
    label = Image.new("1", (800, 400), 1)  # 1-bit monochrome, white background
    draw = ImageDraw.Draw(label)
    draw.text((20, 20), product_name, fill=0)

    barcode_img = Code128(serial_no, writer=ImageWriter()).render()
    label.paste(barcode_img.resize((400, 100)), (20, 80))

    qr_img = qrcode.make(serial_no).resize((150, 150))
    label.paste(qr_img, (450, 80))

    return label
```

The resulting bitmap is then sent using whichever raster/image-upload command the printer's protocol defines. This path is slower and heavier than Section 26.1, so it should only be used where native barcode commands are unavailable. Zebra should always use 26.1; ANSER falls back to 26.2 only if its documentation confirms it has no barcode primitive.

---

# 27. Zebra Communication

Depending on the selected Zebra model and production environment, use the appropriate Zebra-supported communication mechanism.

A common raw printing approach is TCP printing to the printer's print service, commonly port 9100.

The implementation should also support printer status monitoring through the capabilities exposed by the specific Zebra model.

Do not assume every Zebra model exposes exactly the same status features.

---

# 28. ANSER X1 Integration (Confirmed From Vendor Manual)

The ANSER X Series printer is the **X1**, a thermal inkjet coder (marks directly onto product, not a label applicator). Confirmed communication interfaces from the vendor user manual (v1.7):

```text
Ethernet (RJ-45) — TCP/IP, Modbus TCP, and "ANSER U2 Net protocol"
USB — appears as a virtual COM port (ttyACM0 / ttyUSB0 on Linux — confirmed Linux-compatible)
RS-232 — 8-pin M8 connector
Digital I/O — 1 input pin, 5 output pins (alarms, print start/stop)
```

Since your hardware supports both USB and Ethernet, **use Ethernet** — it's the interface the vendor documents for "remote control and monitoring," it's more reliable at 3,000 units/day than USB serial, and it fits a Linux server/PC setup with no driver installation.

## 28.1 Critical Architectural Difference From Zebra

This is the single most important thing to get right: **the X1 does not work like a per-job label printer.** You do not send a complete label per unit. Instead:

1. **One-time setup (not per print):** design a message template on the X1 touchscreen (or ANSER's Windows tool "Message Pro X") containing static text, a barcode/QR object, and a *Variable* object. The barcode object is linked to the Variable object as its data source. This is done once per label design, not once per unit.
2. **Per-unit (what your Python app actually does):** push the serial number into that Variable over the network. Two mechanisms, both over Ethernet:
   - **`0xCA` (Data Update):** overwrites the internal variable table. The value stays until overwritten again — the X1 will keep printing it repeatedly if triggered multiple times. Not suitable alone for unique-serial-per-unit printing.
   - **`0xCF` (Data Stream):** pushes into a FIFO buffer. Each value is consumed exactly once and removed after printing. **This is the correct command for your use case** — one serial number in, one physical print consumes it, in order.
3. **The physical print event is sensor-triggered, not software-triggered.** A photocell sensor on the conveyor detects the product and fires the actual print — the X1 handles this internally, without an explicit "print now" command from your app. Your app's job is to keep the `0xCF` FIFO buffer correctly loaded, one serial number ahead of the next product reaching the sensor.

Implication for your job manager: it is not "send job → wait for ack → done" per unit like Zebra. It's "push next serial into FIFO → later, confirm (via status/counter feedback) that a print consumed it → mark that unit completed in the database." The consumption confirmation is what closes the loop for your state machine (Section 11).

Field limits confirmed from the manual: each variable holds up to 100 bytes (UTF-8), and the FIFO buffer holds up to 250 bytes total — so keep serial numbers compact and push them one at a time rather than batching many into the buffer at once.

## 28.2 What's Still Missing: Exact Byte-Level Protocol

The public user manual names the commands (`0xCA`, `0xCF`, and related `0xCB`/`0xCC`) and describes their behavior, but does **not** publish the exact frame format (header/length/checksum bytes) needed to actually construct a socket packet. This is normally provided as a separate **"ANSER Net Protocol" / communication protocol specification** document by ANSER support, or accessible via **Modbus TCP register maps** since that protocol is also listed as supported. Action item for Milestone 1: request this document (or the Modbus register map, whichever ANSER support provides) directly from ANSER before writing the X1 driver — do not attempt to guess the frame structure.

## 28.3 Barcode/QR — Resolved

The X1 has a dedicated **Barcode object** in its message editor (confirmed: supports UPC-A and other types selectable in the UI), and a **Variable object** that can feed it. So the same principle from Section 26.1 applies: **no manual barcode placement, no bitmap rendering needed for ANSER.** Design the barcode once linked to a variable; your app only ever sends the serial number text. The Section 26.2 raster fallback is not needed for ANSER X1.

## 28.4 Failure Detection

The X1 exposes an **I/O Management** module (Section 3.5 of its manual) that can be configured to raise digital outputs on events including: print start/stop, low ink, ink empty, cartridge errors, Wi-Fi/USB/LAN disconnection. Two integration options:

- **Digital I/O wiring:** connect the X1's alarm output pins into the same failure-detection path used for other line stops (if the factory already wires alarms this way).
- **Network status polling:** poll status over the same Ethernet/Modbus TCP connection used for the `0xCF` data stream, rather than requiring separate physical wiring. This is simpler for a pure-software integration and is the recommended default — confirm exact status registers/fields against the protocol document in Section 28.2.

---

# 29. Conveyor Architecture (Revised for X1)

The X1 handles conveyor timing internally via its own **encoder and photocell sensor inputs** (configured directly on the controller — see its Production Line Setup) — a separate PLC is **not required** to trigger printing, since the X1 is designed to be the thing that watches the sensor and fires the print itself.

```text
Python Application  (pushes serial numbers via 0xCF over Ethernet)
        |
        v
   ANSER X1 Controller  (owns photocell/encoder, message templates, FIFO buffer)
        |
        v
   Conveyor + Photocell Sensor  (physically triggers each print)
        |
        v
     Product
```

A PLC only enters the picture if the factory's conveyor motor control is already PLC-managed for reasons unrelated to printing (line speed, other stations, safety interlocks) — in which case the X1 and the PLC operate side by side, not with the PLC mediating the print trigger.

---

# 30. Sensor Integration (Revised for X1)

The photocell sensor connects directly to the X1 controller (not to Python, and not necessarily to a PLC). Python's role is purely upstream: keep the FIFO buffer loaded with the next correct serial number before the corresponding product reaches the sensor.

```text
Product Sensor  →  ANSER X1 (built-in trigger + print)  →  Status/consumption feedback over Ethernet  →  Python (marks unit completed)
```

Confirm during Milestone 1 whether the X1's status feedback (via Modbus TCP or the Net protocol) reports each individual print/consumption event, or only aggregate counters — this determines exactly how granular your unit-level completion tracking can be.

---

# 31. Recommended Physical Workflow

```text
                    Production Line

Product
   |
   v
[Photocell Sensor — wired to X1]
   |
   v
[ANSER X1 — prints marking, consumes next FIFO serial]
   |
   v
[Zebra Station — Python sends ZPL label with same serial + barcode/QR]
   |
   v
Completed Product
```

Note the ordering dependency: Zebra's sticker (Section 26) is sent per-unit directly by Python and should use the **same serial number** just consumed by the X1, so both markings on a given unit match. If the actual factory process differs, adapt this flow — but keep this pairing principle.

---

# 32. Printer Manager

The printer manager maintains all configured printers.

```text
Printer Manager
|
+-- ANSER-01
|     |
|     +-- connection
|     +-- status
|     +-- health
|     +-- errors
|
+-- ZEBRA-01
|     |
|     +-- connection
|     +-- status
|     +-- health
|     +-- errors
|
+-- ZEBRA-02
```

---

# 33. Printer Health Monitoring

A background monitor should periodically check printers.

Example:

```text
Every 1 second:
    Check printer connectivity

Every 1-5 seconds:
    Check printer operational state

On error:
    Create printer event
    Pause affected production
```

Do not make the UI thread responsible for monitoring.

---

# 34. Printer Status Model

Normalize vendor-specific states into application states.

```text
ONLINE
READY
BUSY
PAUSED
MEDIA_OUT
RIBBON_OUT
HEAD_OPEN
ERROR
OFFLINE
UNKNOWN
```

For example:

```text
Zebra Vendor Status
        |
        v
Printer Adapter
        |
        v
Application Status
```

---

# 35. Automatic Failure Handling

Example:

```text
Zebra reports MEDIA_OUT
        |
        v
Printer Monitor detects it
        |
        v
Create Printer Event
        |
        v
Production Controller notified
        |
        v
Pause production
        |
        v
Persist PAUSED state
        |
        v
Notify operator
```

The system should stop issuing new print operations.

---

# 36. Failure Recovery

Operator sees:

```text
ZEBRA-01
MEDIA OUT

Production paused.

Current Serial:
SN001487

Completed:
1486 / 3000
```

Operator replaces media.

Then:

```text
[TEST PRINTER]
```

The system verifies:

```text
Connected
Ready
No active error
```

Then:

```text
[RESUME]
```

The system loads the unfinished unit:

```text
SN001487
```

and continues.

---

# 37. Never Automatically Retry Every Failure

Some failures are safe to retry.

Examples:

```text
Temporary network timeout
Printer busy
Transient communication error
```

Some failures require operator verification:

```text
Media out
Head open
Ink issue
Physical product jam
Unknown print result
```

Some failures should immediately stop the production line:

```text
Serial mismatch
Verification failure
Safety fault
Emergency stop
Repeated print failure
```

---

# 38. Retry Policy

Recommended configuration:

```yaml
printing:
  max_retries: 3

  retryable_errors:
    - TIMEOUT
    - CONNECTION_RESET
    - TEMPORARY_BUSY

  manual_recovery_errors:
    - MEDIA_OUT
    - RIBBON_OUT
    - HEAD_OPEN
    - UNKNOWN_PRINT_RESULT
```

After maximum retries:

```text
FAILED
```

and require operator action.

---

# 39. Critical Problem: Unknown Print Result

This scenario must be explicitly designed.

Example:

```text
Python sends SN001487
        |
        v
Printer prints
        |
        v
Network disconnects
        |
        v
Python does not receive confirmation
```

The application cannot safely assume:

```text
FAILED
```

because it may already have printed.

Therefore:

```text
UNKNOWN
```

should be a real state.

---

# 40. Reconciliation Process

For `UNKNOWN`:

```text
UNKNOWN
   |
   v
Check printer state
   |
   v
Check print counter / job state if available
   |
   v
Barcode/camera verification if available
   |
   +---- Printed ----> COMPLETED
   |
   +---- Not Printed -> RETRY
   |
   +---- Cannot Determine -> Operator Decision
```

This prevents accidental duplicate labels.

---

# 41. Barcode/Camera Verification

For high reliability, add verification.

Example:

```text
Expected:
SN001487

Scanner reads:
SN001487

Result:
MATCH
```

Mismatch:

```text
Expected:
SN001487

Scanner:
SN001486

Result:
MISMATCH
```

Then:

```text
STOP PRODUCTION
```

This should be considered strongly for a 3,000-unit/day production environment.

---

# 42. Duplicate Prevention

The database must enforce uniqueness.

Example:

```text
serial_number = SN001487
```

must not appear twice for production.

Use database constraints.

The application should also check:

```text
Has this serial already been completed?
```

before printing.

---

# 43. Exactly-Once vs At-Least-Once Printing

Physical printing systems are difficult to guarantee as exactly-once without verification.

The safer design is:

```text
At-least-once command delivery
+
persistent state
+
verification/reconciliation
```

Do not claim exactly-once physical printing unless the hardware/process can prove it.

---

# 44. Queue Architecture

Use a durable queue backed by SQLite.

```text
Production Units
      |
      v
Durable Queue
      |
      +----> ANSER Worker
      |
      +----> Zebra Worker
```

Each worker should process units independently.

---

# 45. Worker Architecture

```text
Main Application
       |
       v
Production Controller
       |
       +----------------+
       |                |
       v                v
ANSER Worker       Zebra Worker
       |                |
       v                v
ANSER Printer       Zebra Printer
```

Do not run blocking printer operations on the UI thread.

---

# 46. PySide6 Threading

The UI must remain responsive.

Use:

```text
PySide6
   |
   +-- Main UI Thread
   |
   +-- Printer Worker
   |
   +-- Monitoring Worker
   |
   +-- API Worker
```

Communication should use Qt signals/slots or a carefully designed async integration.

Never directly modify UI widgets from background threads.

---

# 47. Dashboard Design

Main dashboard:

```text
+------------------------------------------------------------+
|                PRODUCTION CONTROL                         |
+------------------------------------------------------------+
| Product: Chicken Rice 500g                                |
| Job: JOB-20260910-001                                     |
|                                                            |
| Quantity: 3000                                             |
|                                                            |
| Progress: ███████████████░░░░░ 1486 / 3000                |
|                                                            |
| Completed: 1486     Failed: 2     Remaining: 1514         |
+------------------------------------------------------------+
| ANSER X-01                    | ZEBRA-01                  |
|                              |                           |
| ● ONLINE                     | ● ONLINE                  |
| ● READY                      | ● READY                   |
| Conveyor: RUNNING            | Media: OK                 |
| Printed: 1486                | Printed: 1486             |
+------------------------------------------------------------+
| Current Serial: SN001487                                   |
+------------------------------------------------------------+
| [PAUSE]        [RESUME]        [STOP]                     |
+------------------------------------------------------------+
```

---

# 48. Printer Dashboard

```text
Printers

ANSER-X-01
---------------------
Status: READY
Connection: ONLINE
Conveyor: RUNNING
Fault: NONE

ZEBRA-01
---------------------
Status: READY
Connection: ONLINE
Media: OK
Ribbon: OK
Fault: NONE
```

Use clear visual states:

```text
READY
WARNING
ERROR
OFFLINE
```

---

# 49. Production Screen

Show:

```text
Job Number
Product
Requested Quantity
Allocated Quantity
Completed Quantity
Failed Quantity
Remaining Quantity
Current Serial
Elapsed Time
Estimated Remaining Time
Current Printer
Current Stage
```

Example:

```text
Current Stage:
ZEBRA PRINTING

Current Serial:
SN001487
```

---

# 50. Recovery Screen

When a fault occurs:

```text
+------------------------------------------------+
| PRODUCTION PAUSED                              |
+------------------------------------------------+
| Printer: ZEBRA-01                              |
| Error: MEDIA_OUT                               |
|                                                |
| Current Unit: SN001487                         |
| Completed: 1486 / 3000                        |
|                                                |
| Action Required:                               |
| Replace media and test printer.                |
|                                                |
| [TEST PRINTER]                                 |
| [RETRY CURRENT UNIT]                            |
| [RESUME]                                       |
| [CANCEL JOB]                                   |
+------------------------------------------------+
```

---

# 51. Operator Roles

## Operator

Can:

- Login
- Select product
- Create production job
- Start
- Pause
- Resume
- Retry
- View current errors
- View production history

## Supervisor

Can additionally:

- Cancel jobs
- Override selected recovery actions
- View reports
- Review audit logs

## Maintenance

Can:

- Test printers
- View diagnostics
- Reset printer connection
- View printer errors

## Admin

Can:

- Manage users
- Configure printers
- Configure API
- Configure templates
- Configure retry rules
- Change system settings

---

# 52. Job Lifecycle

```text
CREATED
  |
  v
SERIALS_ALLOCATED
  |
  v
READY
  |
  v
RUNNING
  |
  +----> PAUSED
  |         |
  |         v
  |      RECOVERING
  |         |
  |         v
  +------ RUNNING
  |
  v
COMPLETED
```

---

# 53. Application Startup Recovery

Every time the application starts:

```text
START
 |
 v
Load database
 |
 v
Find RUNNING jobs
 |
 v
Find PAUSED jobs
 |
 v
Find PRINTING / UNKNOWN units
 |
 v
Run reconciliation
 |
 v
Show recovery screen
 |
 v
Operator chooses:
   Resume
   Reconcile
   Stop
```

Do not automatically resume production after a power failure unless the physical system has been verified safe.

---

# 54. Power Failure Recovery

Example:

```text
Before power failure:

SN001485 COMPLETED
SN001486 COMPLETED
SN001487 PRINTING
SN001488 QUEUED
```

After restart:

```text
SN001485 COMPLETED
SN001486 COMPLETED
SN001487 UNKNOWN
SN001488 QUEUED
```

The system must inspect SN001487 before continuing.

---

# 55. Database Transaction Strategy

When marking a unit completed:

```text
BEGIN TRANSACTION

Update production unit
Update production job counters
Create audit event

COMMIT
```

Do not update the UI counter as the authoritative operation.

The UI should reflect database state.

---

# 56. Production Counters

Use database-derived counters:

```text
Requested = 3000
Completed = 1486
Failed = 2
Remaining = 1512
```

Do not manually increment counters without a database transaction.

---

# 57. Logging Architecture

Use three levels.

## Application Logs

Technical:

```text
INFO
WARNING
ERROR
DEBUG
```

## Production Logs

Business events:

```text
JOB_STARTED
UNIT_PRINTED
UNIT_VERIFIED
JOB_PAUSED
JOB_RESUMED
JOB_COMPLETED
```

## Audit Logs

Operator actions:

```text
USER_LOGIN
START_JOB
PAUSE_JOB
RETRY_UNIT
CANCEL_JOB
CHANGE_PRINTER_CONFIG
```

---

# 58. Log File Structure

```text
logs/
|
+-- application.log
+-- production.log
+-- printer.log
+-- error.log
```

Use log rotation.

Example:

```text
RotatingFileHandler
```

Keep an appropriate retention period based on operational requirements.

---

# 59. Error Codes

Create normalized error codes.

```text
API_001
API_TIMEOUT

PRINTER_001
PRINTER_OFFLINE

PRINTER_002
MEDIA_OUT

PRINTER_003
RIBBON_OUT

PRINTER_004
HEAD_OPEN

PRINT_001
PRINT_TIMEOUT

PRINT_002
UNKNOWN_PRINT_RESULT

VERIFY_001
SERIAL_MISMATCH

SYSTEM_001
DATABASE_ERROR
```

---

# 60. Error Handling Rules

Example:

```text
API timeout
    -> Retry
    -> If repeated, pause new serial allocation

Printer offline
    -> Pause affected printing

Media out
    -> Pause
    -> Operator recovery

Serial mismatch
    -> Immediate production stop
    -> Manual investigation

Database error
    -> Stop production
    -> Do not continue without persistence
```

---

# 61. Network Failure

The application has two separate network dependencies:

```text
External API
Printer Network
```

They should be handled independently.

If API is offline but enough serials are already stored locally:

```text
Continue production
```

If printer is offline:

```text
Pause printing
```

If database is unavailable:

```text
Stop production
```

---

# 62. API Retry Strategy

Use exponential backoff.

Example:

```text
Attempt 1 -> immediate
Attempt 2 -> 1 sec
Attempt 3 -> 2 sec
Attempt 4 -> 4 sec
Attempt 5 -> 8 sec
```

Add a maximum delay.

Never continuously hammer an unavailable API.

---

# 63. Configuration

Use external configuration.

Example:

```yaml
application:
  name: Production Print System
  environment: production

api:
  base_url: "https://example.com/api"
  timeout_seconds: 10
  retry_count: 3

database:
  path: "./data/production.db"

printing:
  max_retries: 3
  queue_size: 100

printers:

  anser:
    name: "ANSER-X-01"
    model: "ANSER X"
    address: "192.168.1.20"

  zebra:
    name: "ZEBRA-01"
    model: "ZD621"
    address: "192.168.1.30"
    port: 9100
```

Do not store secrets directly in source code.

---

# 64. Security

The application should support:

- User login
- Password hashing
- Role-based access
- API token protection
- HTTPS
- Audit logs
- Configuration permissions

Never store:

```text
plain-text passwords
API secrets in Git
```

---

# 65. Template Versioning

Every production job should record the template version.

Example:

```text
Zebra Template:
sticker_label_v3

Version:
3.0

Created:
2026-09-01
```

If the template changes later, old production jobs still show which template was used.

---

# 66. Printer Configuration Versioning

Production records should also capture:

```text
Printer ID
Printer model
Template version
Printer configuration version
```

This is useful for audits and troubleshooting.

---

# 67. Production Job Snapshot

When a job starts, store:

```text
Product
Product code
Quantity
Serial batch
ANSER printer
Zebra printer
Label template
Template version
Operator
Start time
```

This makes historical reconstruction possible.

---

# 68. Reporting

Initial reports:

## Daily Production

```text
Date
Product
Quantity Requested
Quantity Completed
Failed
Retries
Production Time
Downtime
```

## Printer Report

```text
Printer
Total Prints
Failures
Offline Duration
Media Errors
Average Recovery Time
```

## Operator Report

```text
Operator
Jobs Started
Jobs Completed
Recovery Actions
```

---

# 69. Performance Requirements

Target:

```text
Daily volume: 3,000+
```

The software should comfortably support:

```text
10,000+ units/day
```

from a database and queue perspective.

The limiting factors are likely:

- Printer speed
- Conveyor speed
- Label application speed
- API allocation rate
- Verification speed

rather than Python CPU performance.

---

# 70. Reliability Targets

Suggested engineering targets:

```text
No lost production records
No silent serial duplication
No silent printer failure
Recoverable application restart
Recoverable network interruption
Persistent error history
Persistent production history
```

For production deployment, define formal targets such as:

```text
RPO: 0 for committed local transactions
RTO: < 5 minutes for normal application recovery
```

The exact targets should be agreed with operations.

---

# 71. Monitoring Architecture

```text
Printer
   |
   v
Printer Monitor
   |
   v
Event Normalizer
   |
   +------> Database
   |
   +------> Production Controller
   |
   +------> UI
```

Example:

```text
Zebra MEDIA_OUT
      |
      v
Normalized Event:
MEDIA_OUT
      |
      v
Production Controller
      |
      v
PAUSE
```

---

# 72. Event-Driven Design

Important events:

```text
PRODUCT_SELECTED
JOB_CREATED
SERIALS_ALLOCATED

PRODUCTION_STARTED
PRODUCTION_PAUSED
PRODUCTION_RESUMED
PRODUCTION_STOPPED

PRINTER_CONNECTED
PRINTER_DISCONNECTED
PRINTER_ERROR
PRINTER_RECOVERED

UNIT_QUEUED
UNIT_PRINT_STARTED
UNIT_PRINT_COMPLETED
UNIT_VERIFICATION_FAILED
UNIT_COMPLETED

JOB_COMPLETED
```

This makes the system easier to extend.

---

# 73. Production Controller

The production controller is the central coordinator.

Responsibilities:

```text
- Load job
- Validate job
- Allocate serials
- Queue units
- Control production state
- Coordinate printers
- React to failures
- Manage retries
- Manage recovery
- Update database
```

It should not contain vendor-specific printer code.

---

# 74. Printer Adapter Pattern

Example:

```python
class BasePrinter:
    def connect(self):
        raise NotImplementedError

    def status(self):
        raise NotImplementedError

    def print(self, job):
        raise NotImplementedError
```

Then:

```python
class ZebraPrinter(BasePrinter):
    ...
```

and:

```python
class AnserPrinter(BasePrinter):
    ...
```

This allows future printers.

---

# 75. Test Printer Mode

Provide a dedicated printer test mode.

Example:

```text
Settings
   |
   v
Printer Test
   |
   +-- Test Connection
   +-- Read Status
   +-- Test Print
   +-- Test Error Detection
```

This should be usable without creating a production job.

---

# 76. Simulation Mode

Before connecting physical hardware, create:

```text
SimulationPrinter
```

Example:

```text
SimulationPrinter
    |
    +-- success
    +-- timeout
    +-- offline
    +-- media_out
    +-- unknown_result
```

This allows testing recovery logic safely.

---

# 77. Failure Simulation

The development system should be able to simulate:

```text
Printer disconnected
Printer timeout
Printer media out
Printer busy
API timeout
API unavailable
Database restart
Application crash
Power interruption
Verification mismatch
```

This is essential for testing.

---

# 78. Testing Strategy

## Unit Tests

Test:

- State transitions
- Serial allocation
- Retry logic
- Database repository
- Printer adapters
- Error mapping

## Integration Tests

Test:

- API + database
- Database + queue
- Printer + queue
- Recovery flow

## Hardware Tests

Test actual:

- Zebra
- ANSER
- Conveyor
- Sensors
- PLC
- Scanner/camera

---

# 79. Critical Test Cases

### Test 1

Print 1 unit successfully.

Expected:

```text
COMPLETED
```

### Test 2

Print 3,000 units successfully.

Expected:

```text
3000 COMPLETED
```

### Test 3

Printer disconnects at unit 1,487.

Expected:

```text
1,486 COMPLETED
1,487 PAUSED/UNKNOWN
```

### Test 4

Restart application.

Expected:

```text
Recovery screen
Current unit = 1,487
```

### Test 5

Printer recovers.

Expected:

```text
Resume from 1,487
```

### Test 6

Duplicate serial appears.

Expected:

```text
Production blocked
```

### Test 7

Verification mismatch.

Expected:

```text
Production stopped
```

### Test 8

API unavailable.

Expected:

```text
Existing local queue continues
New allocation pauses when buffer is exhausted
```

---

# 80. End-to-End Recovery Test

This should be one of the acceptance tests.

Start:

```text
Quantity = 3000
```

Stop printer at:

```text
SN001487
```

Application should show:

```text
Completed = 1486
Current = SN001487
Status = PAUSED
```

Turn printer back on.

Run:

```text
TEST PRINTER
```

Then:

```text
RESUME
```

Expected:

```text
SN001487
SN001488
SN001489
...
SN003000
```

No duplicate and no missing serial.

---

# 81. Application Packaging (Confirmed: Linux)

Target: **Linux desktop/industrial PC** (confirmed).

PyInstaller still works fine on Linux and produces a single-directory or single-file executable — no code changes needed versus the Windows path, just build on the target Linux distro (or a matching container) since PyInstaller bundles are not cross-platform.

Recommended production installation:

```text
/opt/production-print-system/
|
+-- production-print-system      (PyInstaller-built executable)
+-- config/
+-- data/                        (SQLite database lives here)
+-- logs/
+-- templates/                   (ZPL templates)
+-- backups/
```

Practical Linux-specific notes:

- Run as a dedicated service account, not root; grant it access to the printer device paths (serial/USB devices appear as `/dev/ttyUSB0`, `/dev/ttyACM0`, etc. — matches what the ANSER X1 manual confirms for its own USB virtual COM behavior).
- If auto-start on boot is wanted, use a `systemd` unit rather than a login-session autostart, so the app restarts automatically after a power failure — this directly supports Section 54 (Power Failure Recovery).
- No `.exe`/Windows-specific packaging concerns apply; drop any Windows-only steps from Milestone 10 (Section 3184).

---

# 82. Local Backup

The database is critical.

Create scheduled backups:

```text
data/
  production.db

backups/
  production_20260910.db
```

At minimum:

```text
Daily backup
```

Better:

```text
Periodic backup
+
Daily backup
```

Do not keep the only backup on the same physical disk if the production history is important.

---

# 83. Database Integrity

Use SQLite WAL mode where appropriate.

Recommended concepts:

```text
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
```

Use transactions for production-state changes.

Do not manually edit the production database.

---

# 84. Offline Operation

The system should distinguish:

```text
LOCAL OPERATION
```

from:

```text
EXTERNAL API CONNECTIVITY
```

For example:

```text
API: OFFLINE
Local serial buffer: 100
Printer: ONLINE
Production: RUNNING
```

Production can continue until the serial buffer is exhausted.

---

# 85. Safety

This is an industrial environment.

The software should not replace:

- Emergency stop systems
- Safety relays
- Machine guarding
- PLC safety logic
- Industrial interlocks

Python should coordinate production, not become the only safety mechanism.

---

# 86. Human-Machine Interaction

Operators should never have to understand:

```text
TCP
ZPL
API
database
```

The UI should say:

```text
Zebra Printer: Media Empty
```

rather than:

```text
TCP socket error 104
```

Technical details can be available in diagnostics.

---

# 87. Error Message Design

Bad:

```text
ConnectionResetError: [Errno 104]
```

Good:

```text
Zebra printer is not responding.

Check:
1. Printer power
2. Network connection
3. Printer status

Production has been paused safely.
```

---

# 88. Production State Recovery Rules

The recovery engine should determine:

```text
What was the last confirmed operation?
What is currently uncertain?
What can be safely retried?
What requires verification?
```

It should never simply do:

```text
last_sequence + 1
```

without considering uncertain operations.

---

# 89. Recommended Recovery Algorithm

```text
Application starts
       |
       v
Load active jobs
       |
       v
Find unfinished units
       |
       v
For each unfinished unit:
       |
       +-- COMPLETED?
       |       |
       |       +--> Ignore
       |
       +-- QUEUED?
       |       |
       |       +--> Requeue
       |
       +-- PRINTING?
       |       |
       |       +--> UNKNOWN
       |
       +-- UNKNOWN?
               |
               v
         Reconciliation
               |
        +------+------+
        |             |
     Printed       Not Printed
        |             |
        v             v
   COMPLETED        RETRY
```

---

# 90. Production Stop Points

The system should explicitly store stop points.

Example:

```text
Job:
JOB-001

Stop Point:
Sequence 1487

Reason:
ZEBRA_MEDIA_OUT

Time:
08:52:34

Status:
PAUSED
```

After recovery:

```text
Resume Point:
1487
```

---

# 91. Multiple Printers

The design should support:

```text
ANSER-01
ZEBRA-01
ZEBRA-02
ZEBRA-03
```

Each printer has:

```text
Type
Model
IP
Port
Template
Production Role
Enabled
```

A product can define its printer route.

---

# 92. Product Print Routing

Create a configuration such as:

```text
Product
   |
   +-- ANSER Template
   +-- ANSER Printer
   |
   +-- Zebra Template
   +-- Zebra Printer
```

Example:

```text
Product A
  ANSER-01
  ZEBRA-01

Product B
  ANSER-01
  ZEBRA-02
```

The operator should not need to manually select every printer every time if the product has a predefined route.

Allow supervisor override if required.

---

# 93. Product Configuration

Recommended:

```text
product_routes

id
product_id
anser_printer_id
zebra_printer_id

anser_template_id
zebra_template_id

active
```

This creates repeatable production recipes.

---

# 94. Production Recipe

A recipe can contain:

```text
Product
ANSER printer
ANSER configuration
Zebra printer
Zebra template
Quantity rules
Verification requirements
Retry policy
```

Example:

```text
RECIPE: PRODUCT-A-V2

ANSER:
  ANSER-01

Zebra:
  ZEBRA-01

Sticker:
  sticker_v3

Verification:
  REQUIRED
```

---

# 95. Operator Workflow

The ideal operator workflow should be very short:

```text
LOGIN
  |
  v
SELECT PRODUCT
  |
  v
ENTER QUANTITY
  |
  v
CONFIRM RECIPE
  |
  v
CHECK PRINTERS
  |
  v
START
  |
  v
MONITOR
```

During failure:

```text
ERROR
  |
  v
FIX HARDWARE
  |
  v
TEST
  |
  v
RESUME
```

---

# 96. Suggested Development Milestones

## Milestone 1: Requirements and Hardware Discovery

Deliverables:

- Exact Zebra model
- Exact ANSER model
- Communication methods
- Conveyor architecture
- PLC details
- Sensor details
- API documentation
- Label requirements
- Failure conditions

Do this first.

---

## Milestone 2: Database and State Machine

Build:

- SQLite
- SQLAlchemy
- Database models
- Job states
- Unit states
- Audit logs
- Recovery states

No physical printer required.

---

## Milestone 3: API Integration

Build:

- Authentication
- Product retrieval
- Serial allocation
- Retry
- Idempotency
- Local persistence

---

## Milestone 4: Zebra Integration

Build:

- Connection
- Status
- ZPL printing
- Template management
- Printer monitoring
- Failure detection

---

## Milestone 5: ANSER Integration

Build:

- Connection
- Print/trigger mechanism
- Conveyor integration
- Status
- Fault handling

This milestone depends heavily on the actual hardware interface.

---

## Milestone 6: Production Controller

Integrate:

```text
API
+
Database
+
Queue
+
ANSER
+
Zebra
+
Recovery
```

---

## Milestone 7: Desktop UI

Build:

- Dashboard
- Job screen
- Printer screen
- Recovery screen
- History
- Settings

---

## Milestone 8: Verification

Add:

- Barcode scanner
- Camera if required
- Serial verification
- Print verification

---

## Milestone 9: Stress Testing

Run:

```text
100 units
500 units
1000 units
3000 units
```

Test failures at different points.

---

## Milestone 10: Production Deployment

Prepare:

- Installer
- Database backup
- Configuration
- Printer setup
- Operator training
- Maintenance guide
- Recovery guide

---

# 97. MVP Definition

The first production-capable MVP should include:

```text
[✓] Product selection
[✓] Quantity
[✓] API serial allocation
[✓] Local database
[✓] Production job
[✓] Zebra printing
[✓] ANSER integration
[✓] Printer monitoring
[✓] Pause
[✓] Resume
[✓] Stop
[✓] Retry
[✓] Failure logging
[✓] Recovery
[✓] Crash recovery
[✓] Production history
[✓] Basic authentication
```

---

# 98. Version 2

Add:

```text
[ ] Barcode verification
[ ] Camera verification
[ ] Advanced reports
[ ] Multiple production lines
[ ] PostgreSQL
[ ] Central server
[ ] Remote monitoring
[ ] Printer analytics
[ ] Predictive maintenance
```

---

# 99. Key Risks

## Risk 1: ANSER interface unknown

Mitigation:

Get the exact model and communication documentation before implementation.

## Risk 2: Unknown physical print result

Mitigation:

Use verification or reconciliation.

## Risk 3: Duplicate serial

Mitigation:

Database uniqueness + API idempotency.

## Risk 4: PC crash

Mitigation:

Persistent state machine + recovery.

## Risk 5: Printer failure

Mitigation:

Background monitoring + automatic pause.

## Risk 6: Network failure

Mitigation:

Local durable queue + retry.

## Risk 7: Operator error

Mitigation:

Role-based permissions + confirmations + clear UI.

## Risk 8: Physical line timing

Mitigation:

Use PLC/sensors for real-time physical control.

---

# 100. Acceptance Criteria

The system should be accepted only if all of the following work.

### Production

- Operator can select a product.
- Operator can request a quantity.
- Serial numbers are allocated.
- Production starts.
- ANSER prints correctly.
- Zebra prints correctly.
- Completed quantity is accurate.

### Failure

- Printer disconnect is detected.
- Production pauses.
- Error is displayed.
- Error is logged.
- Operator can recover the printer.
- Production resumes correctly.

### Recovery

- Application can restart.
- Active job is detected.
- Unfinished units are identified.
- Unknown print results are reconciled.
- Production resumes from the correct point.

### Data

- No duplicate serial numbers.
- No silently lost units.
- Production history is persistent.
- Printer errors are persistent.
- Audit logs are persistent.

---

# 101. Recommended First Technical Prototype

Do not start with the entire application.

Build this first:

```text
Python
 |
 +-- SQLite
 |
 +-- Production Job
 |
 +-- One Serial API Mock
 |
 +-- Zebra Mock
 |
 +-- ANSER Mock
 |
 +-- State Machine
 |
 +-- Recovery
```

Run:

```text
3000 virtual units
```

Inject failures:

```text
Failure at:
100
500
1000
1487
2000
2999
```

Verify that the application always resumes correctly.

Then connect the real hardware.

---

# 102. Development Order

The recommended order is:

```text
1. Hardware/API requirements
          ↓
2. Database schema
          ↓
3. State machine
          ↓
4. Recovery engine
          ↓
5. Mock printers
          ↓
6. API integration
          ↓
7. Zebra integration
          ↓
8. ANSER integration
          ↓
9. Production controller
          ↓
10. Monitoring
          ↓
11. PySide6 UI
          ↓
12. Verification
          ↓
13. Stress testing
          ↓
14. Deployment
```

Do not reverse this and build the UI first.

---

# 103. Final Recommended Architecture

```text
                         +----------------------+
                         | Product / Serial API |
                         +----------+-----------+
                                    |
                                    v
+----------------------------------------------------------------+
|                        PYTHON APP                              |
|                                                                |
|  +-------------------+        +------------------------------+|
|  |     PySide6 UI    |<------>| Production Controller         ||
|  +-------------------+        |                              ||
|                               | State Machine                ||
|                               | Job Manager                  ||
|                               | Recovery Manager             ||
|                               +---------------+--------------+|
|                                               |
|                 +-----------------------------+----------------+
|                 |                             |                |
|                 v                             v                v
|        +----------------+          +----------------+  +----------+
|        | Serial Manager |          | Print Queue    |  | Monitor  |
|        +-------+--------+          +-------+--------+  +----+-----+
|                |                           |                |
|                v                           v                |
|        +------------------------------------------------+   |
|        |              SQLite Database                   |   |
|        +------------------------------------------------+   |
|                                                    |          |
+----------------------------------------------------|----------+
                                                     |
                                      +--------------+--------------+
                                      |                             |
                                      v                             v
                              +---------------+             +---------------+
                              | ANSER Adapter |             | Zebra Adapter |
                              +-------+-------+             +-------+-------+
                                      |                             |
                                      v                             v
                                ANSER X Series                 Zebra Printer
                                      |                             |
                                      v                             v
                                  Conveyor                    Sticker Label
                                      |                             |
                                      +-------------+---------------+
                                                    |
                                                    v
                                              Verification
                                                    |
                                                    v
                                               COMPLETED
```

---

# 104. Final Design Principle

The system should follow these five rules:

### Rule 1
**Every production unit has a unique database record.**

### Rule 2
**Every print attempt is logged.**

### Rule 3
**A printer failure automatically pauses the affected production flow.**

### Rule 4
**An uncertain print result is never blindly retried.**

### Rule 5
**Production resumes from the last safely verified point, not simply from the last counter value.**

---

# 105. Immediate Next Steps

**Confirmed as of this revision:**

1. ~~ANSER exact model~~ → **X1** (thermal inkjet coder, confirmed via vendor manual)
2. ~~ANSER communication method~~ → **USB or Ethernet available; Ethernet recommended** (TCP/IP, Modbus TCP, ANSER U2 Net protocol — see Section 28)
3. ~~Zebra exact model(s)~~ → **ZT230, ZM400, ZM600** (all standard ZPL-over-TCP-9100 capable Zebra models — Section 25/27 apply directly, no changes needed)
4. ~~Whether the application will run on Windows or Linux~~ → **Linux** (Section 81 updated accordingly)
15. ~~Product/serial API~~ → **fully customizable to this system** — design its contract to match Sections 22–24 (idempotent serial allocation, retry-safe) rather than adapting around a fixed external API.

**Still open — required before ANSER driver code is written (Milestone 1 blocker):**

1. **Exact `0xCA`/`0xCF` byte-level frame format** — not in the public user manual; request the "ANSER Net Protocol" specification or Modbus TCP register map directly from ANSER support (see Section 28.2).
2. **Number of Zebra printers** and which model is assigned to which label/line.
3. **Whether ANSER's status/consumption feedback is per-unit or only aggregate-counter** (Section 30) — determines completion-tracking granularity.
4. **Available product sensors** beyond the X1's own photocell (e.g., for the Zebra station, if verification is needed there too).
5. **Available barcode scanners/cameras**, if verification (Section 41) is wanted for MVP or deferred to v2.
6. **Example Zebra label** (current physical sticker layout) to translate into the ZPL template in Section 26.
7. **Physical production sequence** — confirm the ANSER-then-Zebra ordering assumed in Section 31 matches the real line.
8. **What constitutes a successful ANSER print vs. Zebra print** — exact status/field definitions for Section 35 (Automatic Failure Handling).
9. **All printer failure conditions operators currently handle manually** — informs the failure taxonomy in Section 59 (Error Codes).
10. **Whether one PC controls one production line or multiple lines.**

Do not begin ANSER driver code until item 1 above is in hand — everything else in Section 28 can be designed against it, but the actual socket implementation depends on the real frame format.

---

# 106. Conclusion

The recommended system is a **durable production orchestration application**, not simply a Python program that sends print commands.

The most important components are:

```text
PySide6
   +
Production Controller
   +
State Machine
   +
SQLite
   +
Durable Print Queue
   +
ANSER Adapter
   +
Zebra Adapter
   +
Printer Monitoring
   +
Failure Recovery
   +
Audit Logging
   +
Optional Verification
```

With this architecture, a production sequence such as:

```text
3000 units
```

can safely progress:

```text
SN000001
SN000002
...
SN001486
```

then stop because of a printer fault:

```text
PAUSED
Current = SN001487
Reason = MEDIA_OUT
```

and after the operator resolves the problem:

```text
TEST
  ↓
READY
  ↓
RESUME
  ↓
SN001487
SN001488
...
SN003000
  ↓
COMPLETED
```

The system therefore preserves the production point and provides a complete history of what happened, rather than relying on manual counting or restarting the entire batch.
