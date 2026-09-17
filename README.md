# Industrial Automated Printing System

A Linux desktop application for coordinating industrial production printing with an ANSER X1 coder and Zebra label printers.

The system is designed around durable production state: every production unit, print attempt, printer event, and recovery action will be persisted locally so a printer or application failure can be reconciled without relying on in-memory counters.

## Current Status

The core system described in the plan is implemented: database schema, job/unit state machine, durable queue workers, recovery/reconciliation engine, serial allocation (local + pluggable remote API), Zebra ZPL/TCP printing, an ANSER X1 adapter over Modbus TCP, printer health monitoring, audit/production/printer logging, role-based authentication, and a PySide6 desktop UI (dashboard, production control, printers, jobs, history, settings, recovery/error/printer-test dialogs).

Two things remain genuinely open, both hardware-dependent and called out in the plan itself (Section 105):

- **ANSER X1 Modbus register map** -- `config.yaml`'s `printers[].anser_modbus` addresses are placeholders. Confirm the real register map with ANSER support, update those addresses, and flip `simulate: false` for the ANSER printer.
- **Zebra printer IP/port** -- also a placeholder in `config.yaml`; flip `simulate: false` once real hardware is reachable.

Until both are confirmed, run with `simulate: true` (the default) against `SimulationPrinter`, which supports injecting the failure modes in Section 77 for testing recovery behavior safely.

The source of truth for the intended behavior is [industrial_printing_system_full_plan.md](industrial_printing_system_full_plan.md).

## Running

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
# or: python -m app.main
```

On first run this seeds a default `admin` / `admin` account (Section 64) -- you'll get a startup warning until it's changed via a real user-management flow. Add at least one product from the Settings tab before creating a production job; the product catalog starts empty (Section 15).

Run the test suite (includes a full end-to-end recovery test per Section 79/80 using `SimulationPrinter`, and a headless UI smoke test):

```bash
python -m pytest
```

## Database Migrations

`init_db()` creates any missing tables automatically (`Base.metadata.create_all`) so the app is usable standalone. Alembic is also wired up (`app/database/migrations/`) for evolving the schema later:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## Backups

`python -m app.database.backup` takes a consistent online backup (Section 82) using SQLite's backup API, safe to run while the app is live. See `deploy/production-print-system-backup.timer` for a systemd timer that runs it daily.

## Capabilities

- Product and quantity selection
- Idempotent serial-number allocation (local by default; a real API can be plugged in via `api.mode: remote`)
- SQLite-backed production jobs and unit-level recovery
- ANSER X1 integration over Modbus TCP
- Zebra ZPL printing over TCP
- Durable print queues and background printer monitoring
- Automatic pause on printer faults
- Recovery from unknown print results and application restarts (Section 39/40/89)
- Role-based access and audit logging
- Production and printer history/reports

## Repository Layout

```text
app/
	api/          External product and serial-number integration
	application/  Production and recovery services
	config/       Configuration loading
	database/     Database models and repositories
	domain/       Domain models and state transitions
	logging/      Application and production logging
	monitoring/   Printer and network monitoring
	printers/     ANSER and Zebra adapters
	queue/        Durable print queue and workers
	templates/    Runtime label templates
	ui/           PySide6 desktop interface
	main.py       Application entry point
resources/      Icons, images, and packaged templates
tests/          Automated tests
config.yaml     Local application configuration
requirements.txt Python dependencies
```

## Requirements

- Linux desktop or industrial PC for production deployment (see `deploy/`); development works on any OS with Python 3.11+
- ANSER X1 Modbus register map and Zebra printer network details before running against real hardware (see Current Status above)

## Configuration and Runtime Data

Keep machine-specific settings and secrets out of Git. Use `config.yaml` for non-secret defaults and local environment/config files for credentials and printer-specific values.

Runtime files should be stored outside the source tree where possible:

```text
data/       SQLite database
logs/       Rotating application and production logs
backups/    Database backups
```

These paths are ignored by Git. Never commit API tokens, passwords, production databases, or printer credentials.

## Not Yet Implemented

- Barcode/camera verification (Section 41, listed as Version 2 scope in Section 98)
- Packaging into a PyInstaller executable and the full deployment install (Section 81/Milestone 10) -- the `deploy/` systemd units assume that step

Physical safety systems, emergency stops, guarding, and PLC interlocks remain outside the Python application and must continue to be handled by the appropriate industrial controls.
