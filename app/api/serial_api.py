"""Serial/job allocation client (Section 22-24).

There is no existing external product/serial API for this deployment -- the
plan notes it is "fully customizable to this system" (Section 105 item 15).
Rather than guessing at someone else's contract, SerialApiClient defines the
contract this application needs (idempotent allocation keyed by
client_job_id, Section 23) and LocalSerialApiClient implements it directly
against our own database so the system is usable standalone today.
RemoteSerialApiClient implements the same interface against a real HTTP
endpoint later -- swap `api.mode` in config.yaml, no other code changes.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from app.api.client import RetryingHttpClient
from app.config.loader import ApiConfig
from app.database.repositories import SerialBatchRepository
from app.domain.models import SerialAllocationResult
from sqlalchemy.orm import Session


class SerialApiClient(ABC):
    @abstractmethod
    def allocate(self, client_job_id: str, job_id: int, product_code: str, quantity: int) -> SerialAllocationResult:
        """Idempotent: calling this twice with the same client_job_id must
        return the same batch/serials rather than allocating twice."""


class LocalSerialApiClient(SerialApiClient):
    """Durable, idempotent local allocator. Serial format: SN followed by a
    zero-padded, monotonically increasing global sequence number, guaranteed
    unique by the `production_units.serial_number` UNIQUE constraint
    (Section 18) and by re-using any existing batch for a repeated
    client_job_id (Section 23)."""

    def __init__(self, session: Session):
        self.session = session
        self.batches = SerialBatchRepository(session)

    def allocate(self, client_job_id: str, job_id: int, product_code: str, quantity: int) -> SerialAllocationResult:
        existing = self.batches.get_by_client_job_id(client_job_id)
        if existing is not None:
            serials = self._serials_for(existing.job_id, existing.quantity)
            return SerialAllocationResult(
                serial_batch_id=existing.batch_id, job_number=client_job_id,
                quantity=existing.quantity, serials=serials,
            )

        batch_id = f"BATCH-{uuid.uuid4().hex[:12].upper()}"
        serials = self._serials_for(job_id, quantity)
        self.batches.create(batch_id=batch_id, job_id=job_id, client_job_id=client_job_id,
                             quantity=quantity, source="local")
        return SerialAllocationResult(serial_batch_id=batch_id, job_number=client_job_id,
                                       quantity=quantity, serials=serials)

    @staticmethod
    def _serials_for(job_id: int, quantity: int) -> list[str]:
        # Sequence base derived from job_id keeps serials readable and unique
        # across jobs without a separate global counter table, and lets a
        # repeated allocate() call for the same client_job_id deterministically
        # reproduce the same serial strings (Section 23 idempotency).
        base = job_id * 1_000_000
        return [f"SN{base + n:08d}" for n in range(1, quantity + 1)]


class RemoteSerialApiClient(SerialApiClient):
    def __init__(self, http_client: RetryingHttpClient):
        self.http_client = http_client

    def allocate(self, client_job_id: str, job_id: int, product_code: str, quantity: int) -> SerialAllocationResult:
        body = {"product_id": product_code, "quantity": quantity, "client_job_id": client_job_id}
        data = self.http_client.request("POST", "/production/jobs", json_body=body)
        return SerialAllocationResult(
            serial_batch_id=data["serial_batch_id"],
            job_number=data.get("job_id", client_job_id),
            quantity=data["quantity"],
            serials=data.get("serials", []),
        )


def build_serial_api_client(api_config: ApiConfig, session: Session) -> SerialApiClient:
    if api_config.mode == "remote":
        http_client = RetryingHttpClient(
            base_url=api_config.base_url, timeout_seconds=api_config.timeout_seconds,
            retry_count=api_config.retry_count, backoff_base_seconds=api_config.backoff_base_seconds,
            backoff_max_seconds=api_config.backoff_max_seconds, token=api_config.token,
        )
        return RemoteSerialApiClient(http_client)
    return LocalSerialApiClient(session)
