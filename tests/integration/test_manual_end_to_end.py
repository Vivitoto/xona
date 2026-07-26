from __future__ import annotations

from backend.app.db.models import OperationPlan, OperationStep

from conftest import (
    ACTOR_BYTES,
    MEDIA_BYTES,
    POSTER_BYTES,
    ORIGIN,
    MediaLayout,
    api_client,
    app_with_mocks,
    assert_disposable_database_paths,
    happy_xchina,
    run,
    sha256_file,
)


def test_manual_preview_mode_does_not_change_media(
    media_layout: MediaLayout,
    settings_for_layout,
) -> None:
    xchina = happy_xchina()
    settings = settings_for_layout()
    app = app_with_mocks(settings, xchina=xchina)
    before_stat = media_layout.media_file.stat()
    before_hash = sha256_file(media_layout.media_file)

    async def scenario() -> dict:
        async with api_client(app) as client:
            scan = await client.post(
                "/api/manual/scan",
                json={"directory": str(media_layout.source)},
                headers={"Origin": ORIGIN},
            )
            assert scan.status_code == 200, scan.text
            job_id = scan.json()["jobs"][0]["job_id"]

            search = await client.post(
                "/api/manual/search",
                json={
                    "job_id": job_id,
                    "filename": media_layout.media_file.name,
                    "normalized_query": "Sample Work Alpha",
                },
                headers={"Origin": ORIGIN},
            )
            assert search.status_code == 200, search.text
            candidate_id = search.json()["candidates"][0]["candidate_id"]

            selected = await client.post(
                f"/api/manual/jobs/{job_id}/select-candidate",
                json={"candidate_id": candidate_id, "strict_assets": True},
                headers={"Origin": ORIGIN},
            )
            assert selected.status_code == 200, selected.text

            preview = await client.post(
                f"/api/manual/jobs/{job_id}/preview",
                json={
                    "destination_root": str(media_layout.output),
                    "mode": "preview",
                    "folder_templates": ["{studio}", "{title}"],
                    "filename_template": "{xchina_id} - {title}",
                    "asset_policy": "lenient",
                },
                headers={"Origin": ORIGIN},
            )
            assert preview.status_code == 200, preview.text
            plan_id = preview.json()["plan_id"]

            executed = await client.post(
                f"/api/manual/plans/{plan_id}/execute",
                json={"approved": True, "plan_version": 1},
                headers={"Origin": ORIGIN},
            )
            assert executed.status_code == 200, executed.text
            job = await client.get(f"/api/manual/jobs/{job_id}")
            return {"preview": preview.json(), "execute": executed.json(), "job": job.json()}

    result = run(scenario())

    assert result["execute"]["state"] == "completed"
    assert result["job"]["state"] == "completed"
    assert media_layout.media_file.read_bytes() == MEDIA_BYTES
    assert media_layout.media_file.stat().st_size == before_stat.st_size
    assert media_layout.media_file.stat().st_mtime_ns == before_stat.st_mtime_ns
    assert sha256_file(media_layout.media_file) == before_hash
    assert not (
        media_layout.output / "Studio One" / "Sample Work Alpha" / "XC-001 - Sample Work Alpha.mkv"
    ).exists()
    assert all(step["operation"] == "preview" for step in result["preview"]["plan"]["steps"])
    assert_disposable_database_paths(app, media_layout.root)


def test_manual_copy_mode_writes_media_metadata_assets_and_journal(
    media_layout: MediaLayout,
    settings_for_layout,
) -> None:
    xchina = happy_xchina()
    app = app_with_mocks(settings_for_layout(), xchina=xchina)

    async def scenario() -> int:
        async with api_client(app) as client:
            scan = await client.post(
                "/api/manual/scan",
                json={"directory": str(media_layout.source)},
                headers={"Origin": ORIGIN},
            )
            assert scan.status_code == 200, scan.text
            job_id = scan.json()["jobs"][0]["job_id"]
            search = await client.post(
                "/api/manual/search",
                json={
                    "job_id": job_id,
                    "filename": media_layout.media_file.name,
                    "normalized_query": "Sample Work Alpha",
                },
                headers={"Origin": ORIGIN},
            )
            assert search.status_code == 200, search.text
            candidate_id = search.json()["candidates"][0]["candidate_id"]
            selected = await client.post(
                f"/api/manual/jobs/{job_id}/select-candidate",
                json={"candidate_id": candidate_id, "strict_assets": True},
                headers={"Origin": ORIGIN},
            )
            assert selected.status_code == 200, selected.text
            preview = await client.post(
                f"/api/manual/jobs/{job_id}/preview",
                json={
                    "destination_root": str(media_layout.output),
                    "mode": "copy",
                    "folder_templates": ["{studio}", "{title}"],
                    "filename_template": "{xchina_id} - {title}",
                    "asset_policy": "lenient",
                },
                headers={"Origin": ORIGIN},
            )
            assert preview.status_code == 200, preview.text
            executed = await client.post(
                f"/api/manual/plans/{preview.json()['plan_id']}/execute",
                json={"approved": True, "plan_version": 1},
                headers={"Origin": ORIGIN},
            )
            assert executed.status_code == 200, executed.text
            assert executed.json()["state"] == "completed"
            return job_id

    job_id = run(scenario())
    target_dir = media_layout.output / "Studio One" / "Sample Work Alpha"
    target_media = target_dir / "XC-001 - Sample Work Alpha.mkv"
    target_nfo = target_dir / "XC-001 - Sample Work Alpha.nfo"

    assert media_layout.media_file.read_bytes() == MEDIA_BYTES
    assert target_media.read_bytes() == MEDIA_BYTES
    assert target_nfo.read_text(encoding="utf-8").find("Sample Work Alpha") >= 0
    assert not (target_dir / "xchina-normalized.json").exists()
    assert (target_dir / "poster.jpg").read_bytes() == POSTER_BYTES
    assert not (target_dir / "fanart.jpg").exists()
    assert (target_dir / ".actors" / "Actor One.jpg").read_bytes() == ACTOR_BYTES
    assert xchina.detail_fetches == []

    with app.state.sessionmaker() as session:
        plan = session.query(OperationPlan).filter_by(job_id=job_id).one()
        assert plan.status == "completed"
        media_step = (
            session.query(OperationStep)
            .filter_by(
                operation_plan_id=plan.id,
                operation="copy",
                source_path=str(media_layout.media_file),
            )
            .one()
        )
        assert media_step.status == "completed"
        completed = media_step.step_json["journal"][-1]
        assert completed["observed_size_bytes"] == len(MEDIA_BYTES)
        assert completed["observed_mtime_ns"] == target_media.stat().st_mtime_ns
        assert completed["observed_sha256"] == sha256_file(target_media)

    assert_disposable_database_paths(app, media_layout.root)
