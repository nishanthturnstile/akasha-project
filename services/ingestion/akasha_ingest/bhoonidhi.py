"""Bhoonidhi API client and manifest helpers for ResourceSat ingestion.

The production worker runs from the whitelisted staging VM. This module keeps
the network boundary small and fakeable so search/download behavior can be
tested without live Bhoonidhi credentials.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import config

RESOURCESAT_LISS3_SOURCE_ID = "resourcesat-2a-liss3-boa"
RESOURCESAT_LISS3_BHOONIDHI_COLLECTION = "ResourceSat-2A_LISS3_BOA"
RESOURCESAT_AWIFS_SOURCE_ID = "resourcesat-2a-awifs-boa"
RESOURCESAT_AWIFS_BHOONIDHI_COLLECTION = "ResourceSat-2A_AWIFS_BOA"
EOS04_SAR_SOURCE_ID = "eos-04-sar-mrs-l2b"
EOS04_SAR_BHOONIDHI_COLLECTION = "EOS-04_SAR-MRS_L2B"
NISAR_GCOV_SOURCE_ID = "nisar-ssar-beta-gcov"
NISAR_GCOV_BHOONIDHI_COLLECTION = "NISAR_SSAR-Beta_GCOV"
EOS06_CONTEXT_SOURCE_ID = "eos-06-ocm-lac-ndvi-8day-360m"
EOS06_CONTEXT_BHOONIDHI_COLLECTION = "EOS-06_OCM-LAC_NDVI_8day_360m"

SOURCE_COLLECTIONS: dict[str, str] = {
    RESOURCESAT_LISS3_SOURCE_ID: RESOURCESAT_LISS3_BHOONIDHI_COLLECTION,
    RESOURCESAT_AWIFS_SOURCE_ID: RESOURCESAT_AWIFS_BHOONIDHI_COLLECTION,
    EOS04_SAR_SOURCE_ID: EOS04_SAR_BHOONIDHI_COLLECTION,
    NISAR_GCOV_SOURCE_ID: NISAR_GCOV_BHOONIDHI_COLLECTION,
    EOS06_CONTEXT_SOURCE_ID: EOS06_CONTEXT_BHOONIDHI_COLLECTION,
}

RETRYABLE_SEARCH_STATUS = {429, 500, 502, 503, 504}
RETRYABLE_DOWNLOAD_STATUS = {412, 500, 502, 503, 504}
AUTH_RETRY_STATUS = {401}


class BhoonidhiError(RuntimeError):
    """Base Bhoonidhi client error."""


class BhoonidhiAuthError(BhoonidhiError):
    """Authentication/session failure."""


class BhoonidhiDownloadUnavailable(BhoonidhiError):
    """Product is not currently downloadable."""


@dataclass
class TokenSession:
    access_token: str
    refresh_token: str | None
    expires_at: float

    def is_fresh(self, now: float, skew_seconds: int = 60) -> bool:
        return bool(self.access_token) and now < (self.expires_at - skew_seconds)


def source_collection(source_id: str) -> str:
    try:
        return SOURCE_COLLECTIONS[source_id]
    except KeyError as exc:
        raise ValueError(f"unsupported Bhoonidhi source: {source_id}") from exc


def utc_now() -> datetime:
    return datetime.now(UTC)


def lookback_datetime_range(days: int, now: datetime | None = None) -> str:
    end = now or utc_now()
    start = end - timedelta(days=int(days))
    return f"{start:%Y-%m-%dT00:00:00Z}/{end:%Y-%m-%dT23:59:59Z}"


def _feature_aoi(feature: dict[str, Any], fallback_id: str) -> dict[str, Any]:
    props = dict(feature.get("properties")) if isinstance(feature.get("properties"), dict) else {}
    for key in ("compositeGridCrs", "composite_grid_crs", "akasha:composite_grid_crs"):
        if key in feature and key not in props:
            props[key] = feature[key]
    return {
        "id": props.get("id") or fallback_id,
        "name": props.get("name") or props.get("id") or fallback_id,
        "bbox": feature.get("bbox"),
        "geometry": feature.get("geometry"),
        "properties": props,
    }


def _load_aoi_file(path: Path, *, aoi_id: str | None = None) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("type") == "Feature":
        aoi = _feature_aoi(doc, path.stem)
        if aoi_id and aoi_id != aoi.get("id"):
            raise ValueError(f"AOI '{aoi_id}' not found; loaded '{aoi.get('id')}'")
        return aoi
    if doc.get("type") == "FeatureCollection":
        features = [item for item in doc.get("features", []) if isinstance(item, dict)]
        aois = [
            _feature_aoi(feature, f"{path.stem}-{index + 1}")
            for index, feature in enumerate(features)
        ]
        if aoi_id:
            match = next((item for item in aois if item.get("id") == aoi_id), None)
            if match:
                return match
            available = ", ".join(str(item.get("id")) for item in aois)
            raise ValueError(f"AOI '{aoi_id}' not found in {path}; available: {available}")
        if len(aois) == 1:
            return aois[0]
        raise ValueError(f"{path} contains multiple AOIs; pass --aoi to select one.")
    props = dict(doc.get("properties", {})) if isinstance(doc.get("properties"), dict) else {}
    for key in ("compositeGridCrs", "composite_grid_crs", "akasha:composite_grid_crs"):
        if key in doc and key not in props:
            props[key] = doc[key]
    aoi = {
        "id": doc.get("id") or path.stem,
        "name": doc.get("name") or doc.get("id") or path.stem,
        "bbox": doc.get("bbox"),
        "geometry": doc.get("geometry") if isinstance(doc, dict) else None,
        "properties": props,
    }
    if aoi_id and aoi_id != aoi.get("id"):
        raise ValueError(f"AOI '{aoi_id}' not found; loaded '{aoi.get('id')}'")
    return aoi


def _aoi_file_candidates(directory: Path, aoi_id: str) -> list[Path]:
    return [
        directory / f"{aoi_id}.geojson",
        directory / f"{aoi_id}-aoi.geojson",
        directory / f"{aoi_id}.json",
    ]


def load_aoi(
    path: str | Path | None = None,
    *,
    aoi_id: str | None = None,
    aoi_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Load one AOI from a file, FeatureCollection, or AOI directory."""
    if path:
        aoi_path = Path(path)
        if aoi_path.is_dir():
            if not aoi_id:
                raise ValueError(f"{aoi_path} is an AOI directory; pass --aoi to select one.")
            for candidate in _aoi_file_candidates(aoi_path, aoi_id):
                if candidate.is_file():
                    return _load_aoi_file(candidate, aoi_id=aoi_id)
            raise ValueError(f"AOI '{aoi_id}' not found under {aoi_path}")
        return _load_aoi_file(aoi_path, aoi_id=aoi_id)

    configured_dir = (
        Path(aoi_dir or config.AOI_CONFIG_DIR) if (aoi_dir or config.AOI_CONFIG_DIR) else None
    )
    if configured_dir and aoi_id:
        for candidate in _aoi_file_candidates(configured_dir, aoi_id):
            if candidate.is_file():
                return _load_aoi_file(candidate, aoi_id=aoi_id)

    return _load_aoi_file(Path(config.AOI_CONFIG_PATH), aoi_id=aoi_id)


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _parse_error_body(exc: urllib.error.HTTPError) -> dict[str, Any]:
    try:
        raw = exc.read()
        if raw:
            parsed = json.loads(raw.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {"body": parsed}
    except Exception:  # noqa: BLE001
        pass
    return {}


class BhoonidhiClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        user_id: str | None = None,
        password: str | None = None,
        opener: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
        max_retries: int = 3,
    ) -> None:
        self.base_url = (base_url or config.BHOONIDHI_API_BASE).rstrip("/")
        self.user_id = user_id if user_id is not None else config.BHOONIDHI_USER_ID
        self.password = password if password is not None else config.BHOONIDHI_PASSWORD
        self.opener = opener or urllib.request.build_opener()
        self.sleep = sleep
        self.now = now
        self.max_retries = max_retries
        self.session: TokenSession | None = None

    def token(self) -> str:
        if self.session and self.session.is_fresh(self.now()):
            return self.session.access_token
        if self.session and self.session.refresh_token:
            try:
                return self._refresh_token()
            except (BhoonidhiAuthError, urllib.error.HTTPError) as exc:
                if isinstance(exc, urllib.error.HTTPError) and exc.code not in {401, 403}:
                    raise
                stale_session = self.session
                if stale_session is not None:
                    self._logout_session(stale_session, ignore_errors=True)
                self.session = None
        return self._password_token()

    def _password_token(self) -> str:
        if not self.user_id or not self.password:
            raise BhoonidhiAuthError("Bhoonidhi credentials are not configured.")
        try:
            data = self._request_json(
                "POST",
                "/auth/token",
                {
                    "userId": self.user_id,
                    "password": self.password,
                    "grant_type": "password",
                },
                auth=False,
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and self.session:
                self.logout(ignore_errors=True)
                data = self._request_json(
                    "POST",
                    "/auth/token",
                    {
                        "userId": self.user_id,
                        "password": self.password,
                        "grant_type": "password",
                    },
                    auth=False,
                )
            elif exc.code == 403:
                raise BhoonidhiAuthError(
                    "Bhoonidhi auth rejected the session; max active sessions may be reached."
                ) from exc
            else:
                raise
        return self._store_token(data)

    def _refresh_token(self) -> str:
        assert self.session is not None
        data = self._request_json(
            "POST",
            "/auth/token",
            {"refresh_token": self.session.refresh_token, "grant_type": "refresh_token"},
            auth=False,
        )
        return self._store_token(data)

    def _store_token(self, data: dict[str, Any]) -> str:
        token = str(data.get("access_token") or "")
        if not token:
            raise BhoonidhiAuthError("Bhoonidhi auth response did not include access_token.")
        expires_in = int(data.get("expires_in") or 1200)
        self.session = TokenSession(
            access_token=token,
            refresh_token=data.get("refresh_token"),
            expires_at=self.now() + max(expires_in, 1),
        )
        return token

    def logout(self, *, ignore_errors: bool = False) -> None:
        try:
            if self.session:
                self._logout_session(self.session, ignore_errors=ignore_errors)
        except Exception:  # noqa: BLE001
            if not ignore_errors:
                raise
        finally:
            self.session = None

    def _logout_session(self, session: TokenSession, *, ignore_errors: bool) -> None:
        try:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {session.access_token}",
            }
            req = self._request(
                "/auth/logout",
                method="POST",
                body=_json_bytes({}),
                headers=headers,
                auth=False,
            )
            with self.opener.open(req, timeout=30) as resp:
                resp.read()
        except Exception:  # noqa: BLE001
            if not ignore_errors:
                raise

    def search(
        self,
        *,
        collection: str,
        datetime_range: str,
        intersects: dict[str, Any],
        limit: int = 100,
        sortby: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        payload = {
            "collections": [collection],
            "datetime": datetime_range,
            "intersects": intersects,
            "filter": {"op": "eq", "args": [{"property": "Online"}, "Y"]},
            "filter-lang": "cql2-json",
            "limit": min(max(int(limit), 1), 500),
            "sortby": sortby or [{"field": "datetime", "direction": "desc"}],
        }
        data = self._retry_json("POST", "/data/search", payload, RETRYABLE_SEARCH_STATUS)
        features = _features(data)
        while True:
            next_link = _next_link(data)
            if not next_link:
                break
            delay = _search_page_delay_seconds()
            if delay > 0:
                self.sleep(delay)
            data = self._retry_link_json(next_link, RETRYABLE_SEARCH_STATUS)
            features.extend(_features(data))
        return features

    def download_product(
        self,
        *,
        product_id: str,
        collection: str,
        destination: Path,
        chunk_size: int = 1024 * 1024,
    ) -> dict[str, Any]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and destination.stat().st_size > 0:
            return {
                "status": "exists",
                "path": destination.as_posix(),
                "bytes": destination.stat().st_size,
            }

        part_path = destination.with_suffix(destination.suffix + ".part")
        params = urllib.parse.urlencode({"id": product_id, "collection": collection})
        for attempt in range(self.max_retries + 1):
            try:
                req = self._request(f"/download?{params}", method="GET", auth=True)
                with self.opener.open(req, timeout=120) as resp:
                    total = 0
                    with part_path.open("wb") as fh:
                        while True:
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            fh.write(chunk)
                            total += len(chunk)
                part_path.replace(destination)
                return {"status": "downloaded", "path": destination.as_posix(), "bytes": total}
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise BhoonidhiDownloadUnavailable(
                        f"Bhoonidhi product is not online: {product_id}"
                    ) from exc
                if (
                    exc.code not in RETRYABLE_DOWNLOAD_STATUS
                    and exc.code not in AUTH_RETRY_STATUS
                ) or attempt >= self.max_retries:
                    raise
                if exc.code in AUTH_RETRY_STATUS:
                    self.session = None
                self.sleep(_backoff_seconds(attempt, exc.code))
        raise BhoonidhiDownloadUnavailable(f"Bhoonidhi product download failed: {product_id}")

    def _retry_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        retry_statuses: set[int],
    ) -> dict[str, Any]:
        url = urllib.parse.urljoin(self.base_url + "/", path.lstrip("/"))
        return self._retry_url_json(method, url, payload, retry_statuses)

    def _retry_link_json(
        self,
        link: dict[str, Any],
        retry_statuses: set[int],
    ) -> dict[str, Any]:
        href = str(link.get("href") or "")
        if not href:
            raise BhoonidhiError("Bhoonidhi next link is missing href.")
        method = str(link.get("method") or "GET").upper()
        body = link.get("body") if isinstance(link.get("body"), dict) else None
        url = urllib.parse.urljoin(self.base_url + "/", href)
        return self._retry_url_json(method, url, body, retry_statuses)

    def _retry_url_json(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        retry_statuses: set[int],
    ) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                return self._request_json_url(method, url, payload, auth=True)
            except urllib.error.HTTPError as exc:
                detail = _parse_error_body(exc)
                if _is_search_no_results(url, exc.code, detail):
                    return {"features": []}
                if (
                    exc.code not in retry_statuses
                    and exc.code not in AUTH_RETRY_STATUS
                ) or attempt >= self.max_retries:
                    raise BhoonidhiError(
                        f"Bhoonidhi request failed with HTTP {exc.code}: {detail or exc.reason}"
                    ) from exc
                if exc.code in AUTH_RETRY_STATUS:
                    self.session = None
                self.sleep(_backoff_seconds(attempt, exc.code))
        raise BhoonidhiError("Bhoonidhi request failed after retries.")

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        *,
        auth: bool,
    ) -> dict[str, Any]:
        url = urllib.parse.urljoin(self.base_url + "/", path.lstrip("/"))
        return self._request_json_url(method, url, payload, auth=auth)

    def _request_json_url(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        *,
        auth: bool,
    ) -> dict[str, Any]:
        body = _json_bytes(payload) if payload is not None else None
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = self._request_url(url, method=method, body=body, headers=headers, auth=auth)
        with self.opener.open(req, timeout=30) as resp:
            raw = resp.read()
        if not raw:
            return {}
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {"value": parsed}

    def _request(
        self,
        path: str,
        *,
        method: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        auth: bool,
    ) -> urllib.request.Request:
        url = urllib.parse.urljoin(self.base_url + "/", path.lstrip("/"))
        return self._request_url(url, method=method, body=body, headers=headers, auth=auth)

    def _request_url(
        self,
        url: str,
        *,
        method: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        auth: bool,
    ) -> urllib.request.Request:
        req_headers = dict(headers or {})
        if auth:
            req_headers["Authorization"] = f"Bearer {self.token()}"
        return urllib.request.Request(url, data=body, headers=req_headers, method=method)


def _backoff_seconds(attempt: int, status_code: int) -> float:
    base = 10.0 if status_code in {412, 429} else 2.0
    return min(base * (2**attempt), 120.0)


def _search_page_delay_seconds() -> float:
    try:
        rps = float(config.BHOONIDHI_SEARCH_RPS)
    except ValueError:
        return 0.0
    return 1.0 / rps if rps > 0 else 0.0


def _features(data: dict[str, Any]) -> list[dict[str, Any]]:
    features = data.get("features") if isinstance(data, dict) else []
    return [feature for feature in features if isinstance(feature, dict)]


def _next_link(data: dict[str, Any]) -> dict[str, Any] | None:
    links = data.get("links") if isinstance(data, dict) else []
    if not isinstance(links, list):
        return None
    return next(
        (
            link
            for link in links
            if isinstance(link, dict)
            and str(link.get("rel") or "").lower() == "next"
            and link.get("href")
        ),
        None,
    )


def _is_search_no_results(url: str, status_code: int, detail: dict[str, Any]) -> bool:
    if status_code != 404:
        return False
    if urllib.parse.urlparse(url).path.rstrip("/") != "/data/search":
        return False
    haystack = " ".join(str(detail.get(key, "")) for key in ("ErrorCode", "Description"))
    return "no results" in haystack.lower()


def _bbox_intersection(a: list[float], b: list[float]) -> list[float] | None:
    minx = max(float(a[0]), float(b[0]))
    miny = max(float(a[1]), float(b[1]))
    maxx = min(float(a[2]), float(b[2]))
    maxy = min(float(a[3]), float(b[3]))
    if minx >= maxx or miny >= maxy:
        return None
    return [minx, miny, maxx, maxy]


def _normalise_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        west, south_or_north, east, north_or_south = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    south = min(south_or_north, north_or_south)
    north = max(south_or_north, north_or_south)
    if west >= east:
        return None
    return [west, south, east, north]


def _bbox_area(bbox: list[float] | None) -> float:
    if not bbox:
        return 0.0
    return max(float(bbox[2]) - float(bbox[0]), 0.0) * max(float(bbox[3]) - float(bbox[1]), 0.0)


def candidate_from_item(item: dict[str, Any], aoi_bbox: list[float] | None) -> dict[str, Any]:
    raw_props = item.get("properties")
    props: dict[str, Any] = raw_props if isinstance(raw_props, dict) else {}
    bbox = _normalise_bbox(item.get("bbox") or props.get("bbox") or props.get("BoundingBox"))
    overlap_bbox = _bbox_intersection(bbox, aoi_bbox) if bbox and aoi_bbox else None
    item_id = str(item.get("id") or props.get("id") or "")
    return {
        "item_id": item_id,
        "collection": item.get("collection") or props.get("collection"),
        "datetime": props.get("datetime") or item.get("datetime"),
        "online": props.get("Online") or props.get("online"),
        "bbox": bbox,
        "overlap_bbox": overlap_bbox,
        "overlap_area": _bbox_area(overlap_bbox),
        "properties": props,
        "download_status": "pending",
    }


def _is_online(candidate: dict[str, Any]) -> bool:
    value = candidate.get("online")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().upper() == "Y"


def build_search_manifest(
    *,
    source_id: str,
    collection: str,
    aoi: dict[str, Any],
    datetime_range: str,
    items: list[dict[str, Any]],
    created_at: datetime | None = None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for item in items:
        candidate = candidate_from_item(item, aoi.get("bbox"))
        if candidate["overlap_area"] > 0 and _is_online(candidate):
            candidates.append(candidate)
    selected_ids = [candidate["item_id"] for candidate in candidates if candidate["item_id"]]
    return {
        "type": "bhoonidhi_search_manifest",
        "version": 1,
        "created": (created_at or utc_now()).isoformat().replace("+00:00", "Z"),
        "source_id": source_id,
        "collection": collection,
        "aoi": {"id": aoi.get("id"), "name": aoi.get("name"), "bbox": aoi.get("bbox")},
        "search": {"datetime": datetime_range, "filter": "Online=Y"},
        "selection": {"selected_product_ids": selected_ids},
        "candidates": candidates,
    }


def write_manifest(manifest: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path
