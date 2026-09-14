# Industrial Automated Printing System

A Linux desktop application for coordinating industrial production printing with an ANSER X1 coder and Zebra label printers.

The system is designed around durable production state: every production unit, print attempt, printer event, and recovery action will be persisted locally so a printer or application failure can be reconciled without relying on in-memory counters.

## Current Status

This repository is at the initial project setup stage. The package layout and technical implementation plan are present, but the production controller, database schema, printer adapters, UI, and API integration still need to be implemented.

The source of truth for the intended behavior is [industrial_printing_system_full_plan.md](industrial_printing_system_full_plan.md).

## Planned Capabilities

- Product and quantity selection
- Idempotent serial-number allocation through a configurable API
- SQLite-backed production jobs and unit-level recovery
- ANSER X1 integration over Ethernet
- Zebra ZPL printing over TCP
- Durable print queues and background printer monitoring
- Automatic pause on printer faults
- Recovery from unknown print results and application restarts
- Role-based access and audit logging
- Production and printer history

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

- Linux desktop or industrial PC
- Python 3.12 or newer
- Access to the product/serial API when API allocation is required
- ANSER X1 and Zebra printer network details for hardware integration

The ANSER protocol specification or Modbus TCP register map is required before implementing the X1 network driver. The public user manual does not define the complete byte-level frame format.

## Development Setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Once the application entry point and dependencies are implemented, start the desktop application with:

```bash
python -m app.main
```

Run the test suite with:

```bash
pytest
```

At the current setup stage these commands may have no runnable application or tests yet.

## Configuration and Runtime Data

Keep machine-specific settings and secrets out of Git. Use `config.yaml` for non-secret defaults and local environment/config files for credentials and printer-specific values.

Runtime files should be stored outside the source tree where possible:

```text
data/       SQLite database
logs/       Rotating application and production logs
backups/    Database backups
```

These paths are ignored by Git. Never commit API tokens, passwords, production databases, or printer credentials.

## Implementation Order

1. Confirm API, printer, sensor, and verification requirements.
2. Build the SQLite schema and production/unit state machine.
3. Implement recovery and reconciliation logic.
4. Add mock printers and failure simulation.
5. Integrate the serial API, Zebra printers, and ANSER X1.
6. Add the production controller and monitoring services.
7. Build the PySide6 UI, verification workflow, and deployment packaging.

Physical safety systems, emergency stops, guarding, and PLC interlocks remain outside the Python application and must continue to be handled by the appropriate industrial controls.
