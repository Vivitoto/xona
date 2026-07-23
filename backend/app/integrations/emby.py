from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from backend.app.core.redaction import redact_payload
from backend.app.schemas.emby import EmbyLibrary, EmbyPathMapping


class EmbyError(RuntimeError):
    pass


class EmbyPathMappingError(ValueError):
    def __init__(self, message: str, diagnostics: dict[str, object]) -> None:
        super().__init__(f"{message}: {diagnostics!r}")
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class ResolvedEmbyPath:
    local_path: Path
    emby_path: str
    container_root: Path
    emby_root: str


class EmbyPathMapper:
    def __init__(self, mappings: list[EmbyPathMapping | dict[str, str]]) -> None:
        self._mappings = [
            mapping
            if isinstance(mapping, EmbyPathMapping)
            else EmbyPathMapping.model_validate(mapping)
            for mapping in mappings
        ]

    @property
    def mappings(self) -> list[EmbyPathMapping]:
        return list(self._mappings)

    def map_path(self, local_path: Path | str) -> ResolvedEmbyPath:
        path = Path(local_path).resolve(strict=False)
        for mapping in self._mappings:
            container_root = Path(mapping.container_root).resolve(strict=False)
            try:
                relative = path.relative_to(container_root)
            except ValueError:
                continue
            emby_root = mapping.emby_root.rstrip("/\\")
            emby_path = emby_root
            if relative.parts:
                emby_path = f"{emby_root}/{relative.as_posix()}"
            return ResolvedEmbyPath(
                local_path=path,
                emby_path=emby_path,
                container_root=container_root,
                emby_root=mapping.emby_root,
            )

        diagnostics = {
            "path": str(path),
            "configured_container_roots": [
                mapping.container_root for mapping in self._mappings
            ],
        }
        raise EmbyPathMappingError(
            "No Emby path mapping matched local path",
            redact_payload(diagnostics),
        )


class EmbyClient:
    def __init__(
        self,
        server_url: str,
        api_key: str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._api_key = api_key
        self._http_client = http_client or httpx.AsyncClient()
        self._owns_http_client = http_client is None

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> "EmbyClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def test_connection(self) -> dict[str, Any]:
        try:
            info = await self._request_json("GET", "/System/Info")
            libraries = await self.libraries()
        except EmbyError as exc:
            return {
                "ok": False,
                "authorized": "401" not in str(exc),
                "diagnostics": {"error": redact_payload(str(exc))},
            }
        return {
            "ok": True,
            "authorized": True,
            "server_version": _str_or_none(info.get("Version")),
            "server_name": _str_or_none(info.get("ServerName")),
            "libraries": libraries,
            "diagnostics": {},
        }

    async def libraries(self) -> list[EmbyLibrary]:
        payload = await self._request_json("GET", "/Library/VirtualFolders")
        if not isinstance(payload, list):
            raise EmbyError("Malformed Emby library response")
        libraries: list[EmbyLibrary] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = _str_or_none(item.get("Name")) or _str_or_none(item.get("name"))
            if not name:
                continue
            library_id = _str_or_none(item.get("ItemId")) or _str_or_none(item.get("Id"))
            locations = item.get("Locations") or item.get("locations") or []
            libraries.append(
                EmbyLibrary(
                    id=library_id,
                    name=name,
                    locations=[str(location) for location in locations],
                )
            )
        return libraries

    async def scan_library(self) -> None:
        await self._request("POST", "/Library/Refresh")

    async def find_item_by_path(self, emby_path: str) -> dict[str, Any] | None:
        payload = await self._request_json(
            "GET",
            "/Items",
            params={"Recursive": "true", "Path": emby_path, "Fields": "Path"},
        )
        items = payload.get("Items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            return None
        first = items[0]
        return first if isinstance(first, dict) else None

    async def refresh_item(self, item_id: str) -> None:
        await self._request(
            "POST",
            f"/Items/{item_id}/Refresh",
            params={
                "MetadataRefreshMode": "FullRefresh",
                "ImageRefreshMode": "FullRefresh",
                "ReplaceAllMetadata": "false",
                "ReplaceAllImages": "false",
            },
        )

    async def find_person(self, name: str) -> dict[str, Any] | None:
        payload = await self._request_json(
            "GET",
            "/Persons",
            params={"SearchTerm": name, "Limit": "1"},
        )
        items = payload.get("Items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            return None
        first = items[0]
        return first if isinstance(first, dict) else None

    async def upload_person_portrait(
        self,
        person_id: str,
        portrait_bytes: bytes,
        *,
        content_type: str,
    ) -> None:
        await self._request(
            "POST",
            f"/Items/{person_id}/Images/Primary",
            content=portrait_bytes,
            headers={"Content-Type": content_type},
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> Any:
        response = await self._request(method, path, params=params)
        try:
            return response.json()
        except ValueError as exc:
            raise EmbyError(
                f"Malformed Emby JSON response: {redact_payload(response.text[:200])}"
            ) from exc

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        request_params = dict(params or {})
        request_params["api_key"] = self._api_key
        url = f"{self._server_url}/{path.lstrip('/')}"
        try:
            response = await self._http_client.request(
                method,
                url,
                params=request_params,
                content=content,
                headers=headers,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            detail = {
                "url": str(exc.request.url),
                "status_code": exc.response.status_code,
                "body": exc.response.text[:200],
            }
            raise EmbyError(f"Emby request failed: {redact_payload(detail)!r}") from exc
        except httpx.HTTPError as exc:
            detail = {"url": url, "error": str(exc)}
            raise EmbyError(f"Emby request failed: {redact_payload(detail)!r}") from exc


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None
