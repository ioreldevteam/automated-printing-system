"""Enumerations and valid state transitions for production jobs, units, and printers.

Section 11 of industrial_printing_system_full_plan.md defines these state machines.
The database is the source of truth; these enums and transition maps are the
single place that decides whether a transition is legal.
"""
from __future__ import annotations

import enum


class JobStatus(str, enum.Enum):
    CREATED = "CREATED"
    SERIALS_ALLOCATED = "SERIALS_ALLOCATED"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    RECOVERING = "RECOVERING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


JOB_TERMINAL_STATES = {JobStatus.COMPLETED, JobStatus.STOPPED, JobStatus.FAILED, JobStatus.CANCELLED}

JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.CREATED: {JobStatus.SERIALS_ALLOCATED, JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.SERIALS_ALLOCATED: {JobStatus.READY, JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.READY: {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {JobStatus.PAUSED, JobStatus.STOPPING, JobStatus.COMPLETED, JobStatus.FAILED},
    JobStatus.PAUSED: {JobStatus.RECOVERING, JobStatus.RUNNING, JobStatus.STOPPING, JobStatus.CANCELLED},
    JobStatus.RECOVERING: {JobStatus.RUNNING, JobStatus.PAUSED, JobStatus.STOPPING, JobStatus.FAILED},
    JobStatus.STOPPING: {JobStatus.STOPPED},
    JobStatus.STOPPED: set(),
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELLED: set(),
}


def can_transition_job(current: JobStatus, target: JobStatus) -> bool:
    return target in JOB_TRANSITIONS.get(current, set())


class UnitStatus(str, enum.Enum):
    ALLOCATED = "ALLOCATED"
    QUEUED = "QUEUED"
    ANSER_PRINTING = "ANSER_PRINTING"
    ANSER_PRINTED = "ANSER_PRINTED"
    ZEBRA_PRINTING = "ZEBRA_PRINTING"
    ZEBRA_PRINTED = "ZEBRA_PRINTED"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"
    UNKNOWN = "UNKNOWN"


UNIT_TERMINAL_STATES = {UnitStatus.COMPLETED}

# Any in-flight ("PRINTING") unit status becomes UNKNOWN on an ungraceful restart
# (Section 53/89) because the physical print result cannot be trusted.
UNIT_IN_FLIGHT_STATES = {UnitStatus.ANSER_PRINTING, UnitStatus.ZEBRA_PRINTING, UnitStatus.VERIFYING}

UNIT_TRANSITIONS: dict[UnitStatus, set[UnitStatus]] = {
    UnitStatus.ALLOCATED: {UnitStatus.QUEUED, UnitStatus.FAILED},
    UnitStatus.QUEUED: {UnitStatus.ANSER_PRINTING, UnitStatus.FAILED, UnitStatus.RETRY_PENDING},
    UnitStatus.ANSER_PRINTING: {UnitStatus.ANSER_PRINTED, UnitStatus.UNKNOWN, UnitStatus.FAILED},
    UnitStatus.ANSER_PRINTED: {UnitStatus.ZEBRA_PRINTING, UnitStatus.FAILED, UnitStatus.RETRY_PENDING},
    UnitStatus.ZEBRA_PRINTING: {UnitStatus.ZEBRA_PRINTED, UnitStatus.UNKNOWN, UnitStatus.FAILED},
    UnitStatus.ZEBRA_PRINTED: {UnitStatus.VERIFYING, UnitStatus.COMPLETED, UnitStatus.FAILED},
    UnitStatus.VERIFYING: {UnitStatus.COMPLETED, UnitStatus.FAILED, UnitStatus.UNKNOWN},
    UnitStatus.COMPLETED: set(),
    UnitStatus.FAILED: {UnitStatus.RETRY_PENDING},
    UnitStatus.RETRY_PENDING: {UnitStatus.QUEUED, UnitStatus.ANSER_PRINTING, UnitStatus.ZEBRA_PRINTING, UnitStatus.FAILED},
    UnitStatus.UNKNOWN: {UnitStatus.COMPLETED, UnitStatus.RETRY_PENDING, UnitStatus.FAILED, UnitStatus.QUEUED},
}


def can_transition_unit(current: UnitStatus, target: UnitStatus) -> bool:
    return target in UNIT_TRANSITIONS.get(current, set())


class PrinterStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    READY = "READY"
    BUSY = "BUSY"
    PAUSED = "PAUSED"
    MEDIA_OUT = "MEDIA_OUT"
    RIBBON_OUT = "RIBBON_OUT"
    HEAD_OPEN = "HEAD_OPEN"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


# Section 37: failures that are safe to retry automatically vs. require an
# operator to physically intervene vs. must stop the line immediately.
RETRYABLE_PRINTER_STATES = {PrinterStatus.BUSY}
MANUAL_RECOVERY_PRINTER_STATES = {
    PrinterStatus.MEDIA_OUT,
    PrinterStatus.RIBBON_OUT,
    PrinterStatus.HEAD_OPEN,
    PrinterStatus.OFFLINE,
    PrinterStatus.ERROR,
}


class PrintStage(str, enum.Enum):
    ANSER = "ANSER"
    ZEBRA = "ZEBRA"


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"
    OPERATOR = "OPERATOR"
    MAINTENANCE = "MAINTENANCE"
    VIEWER = "VIEWER"


# Section 51: coarse capability map used by the UI/services to gate actions.
ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.OPERATOR: {
        "login", "select_product", "create_job", "start_job", "pause_job",
        "resume_job", "retry_unit", "view_errors", "view_history",
    },
    Role.SUPERVISOR: {
        "login", "select_product", "create_job", "start_job", "pause_job",
        "resume_job", "retry_unit", "view_errors", "view_history",
        "cancel_job", "override_recovery", "view_reports", "view_audit_logs",
    },
    Role.MAINTENANCE: {
        "login", "test_printer", "view_diagnostics", "reset_printer", "view_errors",
    },
    Role.ADMIN: {
        "login", "manage_users", "manage_products", "configure_printers", "configure_api",
        "configure_templates", "configure_retry_rules", "change_settings",
        "select_product", "create_job", "start_job", "pause_job", "resume_job",
        "retry_unit", "view_errors", "view_history", "cancel_job",
        "override_recovery", "view_reports", "view_audit_logs", "test_printer",
        "view_diagnostics", "reset_printer",
    },
    Role.VIEWER: {"login", "view_history", "view_errors"},
}


def role_can(role: Role, action: str) -> bool:
    return action in ROLE_PERMISSIONS.get(role, set())
