from app.domain.states import (
    JobStatus,
    UnitStatus,
    can_transition_job,
    can_transition_unit,
)


def test_job_valid_transitions():
    assert can_transition_job(JobStatus.CREATED, JobStatus.SERIALS_ALLOCATED)
    assert can_transition_job(JobStatus.RUNNING, JobStatus.PAUSED)
    assert can_transition_job(JobStatus.PAUSED, JobStatus.RUNNING)
    assert can_transition_job(JobStatus.RUNNING, JobStatus.COMPLETED)


def test_job_invalid_transitions():
    assert not can_transition_job(JobStatus.COMPLETED, JobStatus.RUNNING)
    assert not can_transition_job(JobStatus.CREATED, JobStatus.RUNNING)
    assert not can_transition_job(JobStatus.CANCELLED, JobStatus.RUNNING)


def test_unit_valid_transitions():
    assert can_transition_unit(UnitStatus.QUEUED, UnitStatus.ANSER_PRINTING)
    assert can_transition_unit(UnitStatus.ANSER_PRINTING, UnitStatus.UNKNOWN)
    assert can_transition_unit(UnitStatus.UNKNOWN, UnitStatus.COMPLETED)
    assert can_transition_unit(UnitStatus.ZEBRA_PRINTED, UnitStatus.COMPLETED)


def test_unit_invalid_transitions():
    assert not can_transition_unit(UnitStatus.COMPLETED, UnitStatus.QUEUED)
    assert not can_transition_unit(UnitStatus.ALLOCATED, UnitStatus.COMPLETED)
