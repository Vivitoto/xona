from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from backend.app.integrations.emby import EmbyClient, EmbyPathMapper


def test_emby_path_mapper_uses_ordered_container_roots_and_safe_diagnostics(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    child = root / "movies"
    child.mkdir(parents=True)
    mapper = EmbyPathMapper(
        [
            {"container_root": str(child), "emby_root": "/visible/movies"},
            {"container_root": str(root), "emby_root": "/visible"},
        ]
    )

    mapped = mapper.map_path(child / "Sample" / "movie.mkv")

    assert mapped.emby_path == "/visible/movies/Sample/movie.mkv"
    with pytest.raises(Exception) as exc_info:
        mapper.map_path(tmp_path / "outside" / "movie.mkv")
    rendered = repr(exc_info.value)
    assert "configured_container_roots" in rendered
    assert "api_key" not in rendered


def test_emby_client_connection_scan_lookup_refresh_and_portrait_upload() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        assert request.url.params["api_key"] == "secret-key"
        if request.url.path == "/System/Info":
            return httpx.Response(200, json={"Version": "4.8.0", "ServerName": "Emby"})
        if request.url.path == "/Library/VirtualFolders":
            return httpx.Response(
                200,
                json=[{"Name": "Movies", "ItemId": "lib-1", "Locations": ["/visible"]}],
            )
        if request.url.path == "/Library/Refresh":
            return httpx.Response(204)
        if request.url.path == "/Items":
            assert request.url.params["Path"] == "/visible/movie.mkv"
            return httpx.Response(200, json={"Items": [{"Id": "item-1"}]})
        if request.url.path == "/Items/item-1/Refresh":
            return httpx.Response(204)
        if request.url.path == "/Persons":
            return httpx.Response(200, json={"Items": [{"Id": "person-1"}]})
        if request.url.path == "/Items/person-1/Images/Primary":
            assert request.headers["content-type"] == "image/jpeg"
            assert request.content == b"portrait"
            return httpx.Response(204)
        return httpx.Response(404)

    async def run() -> dict[str, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = EmbyClient("http://emby.test", "secret-key", http_client=http)
            connection = await client.test_connection()
            await client.scan_library()
            item = await client.find_item_by_path("/visible/movie.mkv")
            await client.refresh_item("item-1")
            person = await client.find_person("Actor One")
            await client.upload_person_portrait(
                "person-1",
                b"portrait",
                content_type="image/jpeg",
            )
            return {"connection": connection, "item": item, "person": person}

    result = asyncio.run(run())

    assert result["connection"]["ok"] is True
    assert result["connection"]["server_version"] == "4.8.0"
    assert result["item"]["Id"] == "item-1"
    assert result["person"]["Id"] == "person-1"
    assert ("POST", "/Library/Refresh") in calls
