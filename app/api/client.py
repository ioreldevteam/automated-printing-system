"""Shared HTTP client with exponential backoff retry (Section 62)."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from app.domain.exceptions import ApiTimeoutError, ApiUnavailableError

logger = logging.getLogger("application")


class RetryingHttpClient:
    def __init__(self, base_url: str, timeout_seconds: float, retry_count: int,
                 backoff_base_seconds: float, backoff_max_seconds: float,
                 token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _backoff_delay(self, attempt: int) -> float:
        # attempt 1 -> immediate, attempt 2 -> base, attempt 3 -> 2*base, ...
        if attempt <= 1:
            return 0.0
        delay = self.backoff_base_seconds * (2 ** (attempt - 2))
        return min(delay, self.backoff_max_seconds)

    def request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(1, self.retry_count + 1):
            delay = self._backoff_delay(attempt)
            if delay:
                time.sleep(delay)
            try:
                with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                    response = client.request(method, path, json=json_body, headers=self._headers())
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning("API timeout on attempt %s/%s for %s %s", attempt, self.retry_count, method, path)
                continue
            except httpx.HTTPStatusError as exc:
                if 500 <= exc.response.status_code < 600:
                    last_exc = exc
                    logger.warning("API server error %s on attempt %s/%s for %s %s",
                                    exc.response.status_code, attempt, self.retry_count, method, path)
                    continue
                raise ApiUnavailableError(f"API request failed ({exc.response.status_code}): {exc}") from exc
            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning("API connection error on attempt %s/%s for %s %s: %s",
                                attempt, self.retry_count, method, path, exc)
                continue

        if isinstance(last_exc, httpx.TimeoutException):
            raise ApiTimeoutError(f"API timed out after {self.retry_count} attempts: {last_exc}") from last_exc
        raise ApiUnavailableError(f"API unavailable after {self.retry_count} attempts: {last_exc}") from last_exc
