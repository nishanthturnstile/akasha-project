"""Secret-safe EOSDA API Connect HTTP client."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

import httpx

from ...config import settings
from ...raster.errors import AkashaError, sanitize_error_value

logger = logging.getLogger("akasha.api.providers.eos")


class EosClient:
    """Small wrapper around EOSDA API Connect with sanitized error mapping."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.eos_api_key
        self.base_url = (base_url if base_url is not None else settings.eos_base_url).rstrip("/")
        timeout = timeout_seconds if timeout_seconds is not None else settings.eos_timeout_seconds
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)
        self._base_origin = _origin(self.base_url)

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expected_status: Iterable[int] = (200,),
    ) -> Any:
        if not self.api_key.strip():
            raise AkashaError(
                "PROVIDER_UNCONFIGURED",
                "EOS provider is not configured.",
                503,
                {"provider": "eos"},
            )

        safe_path = path.split("?", 1)[0]
        logger.info("EOS provider request: method=%s path=%s", method.upper(), safe_path)
        try:
            response = self._client.request(
                method,
                path,
                json=json,
                params=params,
                headers={"x-api-key": self.api_key},
            )
        except httpx.TimeoutException as exc:
            raise AkashaError(
                "PROVIDER_TIMEOUT",
                "EOS provider request timed out.",
                504,
                {"provider": "eos"},
            ) from exc
        except httpx.RequestError as exc:
            raise AkashaError(
                "PROVIDER_UPSTREAM_ERROR",
                "EOS provider is unavailable.",
                502,
                {"provider": "eos"},
            ) from exc

        if response.status_code in set(expected_status):
            if response.status_code == 204 or not response.content:
                return None
            try:
                return response.json()
            except ValueError as exc:
                raise AkashaError(
                    "PROVIDER_INVALID_RESPONSE",
                    "EOS provider returned an invalid response.",
                    502,
                    {"provider": "eos", "upstreamStatusCode": response.status_code},
                ) from exc

        raise self._error_from_response(response)

    def request_bytes(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        expected_status: Iterable[int] = (200,),
    ) -> tuple[bytes, str]:
        if not self.api_key.strip():
            raise AkashaError(
                "PROVIDER_UNCONFIGURED",
                "EOS provider is not configured.",
                503,
                {"provider": "eos"},
            )

        safe_path = path.split("?", 1)[0]
        logger.info("EOS provider bytes request: method=%s path=%s", method.upper(), safe_path)
        try:
            headers = {"Accept": "image/png,*/*"}
            if _origin(path) in {None, self._base_origin}:
                headers["x-api-key"] = self.api_key

            response = self._client.request(
                method,
                path,
                params=params,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise AkashaError(
                "PROVIDER_TIMEOUT",
                "EOS provider request timed out.",
                504,
                {"provider": "eos"},
            ) from exc
        except httpx.RequestError as exc:
            raise AkashaError(
                "PROVIDER_UPSTREAM_ERROR",
                "EOS provider is unavailable.",
                502,
                {"provider": "eos"},
            ) from exc

        if response.status_code in set(expected_status):
            return response.content, response.headers.get("Content-Type", "image/png")

        raise self._error_from_response(response)

    def _error_from_response(self, response: httpx.Response) -> AkashaError:
        retry_after = response.headers.get("retry-after")
        details: dict[str, Any] = {
            "provider": "eos",
            "upstreamStatusCode": response.status_code,
        }
        if retry_after and retry_after.isdigit():
            details["retryAfterSeconds"] = int(retry_after)
        if response.status_code == 429:
            return AkashaError(
                "PROVIDER_RATE_LIMITED",
                "EOS provider rate limit was reached.",
                429,
                details,
            )
        if response.status_code == 404:
            return AkashaError(
                "PROVIDER_NOT_FOUND",
                "EOS provider resource was not found.",
                404,
                details,
            )
        status = 502 if response.status_code >= 500 else 400
        return AkashaError(
            "PROVIDER_UPSTREAM_ERROR",
            "EOS provider request failed.",
            status,
            sanitize_error_value(details),
        )


def _origin(value: str) -> tuple[str, str, int | None] | None:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.hostname:
        return None
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port
