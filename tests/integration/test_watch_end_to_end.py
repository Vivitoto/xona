from __future__ import annotations

from pathlib import Path

from backend.app.db.models import OperationStep

from conftest import (
    MEDIA_BYTES,
    ORIGIN,
    MediaLayout,
    MockEmby,
    MockXChina,
    api_client,
    app_with_mocks,
    assert_disposable_database_paths,
    happy_detail,
    happy_xchina,
    result_for_detail,
    run,
    run_worker_until_state,
    sha256_file,
)


def test_watch_monitor_auto_flow_materializes_plans_executes_and_completes(
    media_layout: MediaLayout,
    settings_for_layout,
) -> None:
    xchina = happy_xchina()
    app = app_with_mocks(
        settings_for_layout(monitor_enabled=True),
        xchina=xchina,
        emby=MockEmby(),
    )

    async def scenario() -> dict:
        async with api_client(app) as client:
            created = await client.post(
                "/api/watch-rules",
                json={
                    "source_directory": str(media_layout.source),
                    "destination_directory": str(media_layout.output),
                    "realtime": True,
                    "stability_seconds": 0,
                    "stable_check_count": 1,
                    "organization_mode": "copy",
                    "folder_templates": ["{studio}", "{title}"],
                    "filename_template": "{xchina_id} - {title}",
                    "asset_policy": "strict",
                    "include_patterns": ["*.mkv"],
                    "emby_options": {"enabled": False},
                },
                headers={"Origin": ORIGIN},
            )
            assert created.status_code == 201, created.text
            rule_id = created.json()["rule_id"]

            assert app.state.monitor.handle_event(media_layout.media_file, rule_id=rule_id) == []
            jobs = app.state.monitor.handle_event(media_layout.media_file, rule_id=rule_id)
            assert len(jobs) == 1
            job_id = jobs[0].id

            return await run_worker_until_state(
                app,
                client,
                job_id,
                {"completed", "review_required", "failed", "local_complete_emby_failed"},
            )

    job = run(scenario())

    assert job["state"] == "completed"
    assert job["payload"]["auto"]["score"]["total"] >= 92
    assert job["payload"]["auto"]["score"]["lead"] >= 10
    target = media_layout.output / "Studio One" / "Sample Work Alpha" / "XC-001 - Sample Work Alpha.mkv"
    assert target.read_bytes() == MEDIA_BYTES
    assert (target.parent / "poster.jpg").is_file()
    assert (target.parent / ".actors" / "Actor One.jpg").is_file()
    assert_disposable_database_paths(app, media_layout.root)


def test_watch_auto_review_gates(
    tmp_path: Path,
    settings_for_layout,
) -> None:
    cases = [
        (
            "low_confidence",
            "Sample.Work.Alpha.mkv",
            MockXChina(
                results=[
                    result_for_detail(
                        happy_detail(source_id="XC-100", title="Unrelated Work"),
                        title="Unrelated Work",
                    )
                ],
                details={},
                assets={},
            ),
            "threshold_not_met",
            92,
        ),
        (
            "exact_tie",
            "Sample.Work.Alpha.mkv",
            _xchina_for_results(
                [
                    ("XC-201", "Sample Work Alpha"),
                    ("XC-202", "Sample Work Alpha"),
                ]
            ),
            "tie",
            50,
        ),
        (
            "incomplete_metadata",
            "XC-001.Sample.Work.Alpha.mkv",
            _xchina_for_detail(happy_detail(complete=False)),
            "incomplete_metadata",
            92,
        ),
        (
            "insufficient_lead",
            "Sample.Work.Alpha.mkv",
            _xchina_for_results(
                [
                    ("XC-301", "Sample Work Alpha"),
                    ("XC-302", "Sample Work Alpha Extended"),
                ]
            ),
            "insufficient_lead",
            50,
        ),
    ]

    for name, filename, xchina, expected_reason, threshold in cases:
        source = tmp_path / name / "source"
        output = tmp_path / name / "output"
        config = tmp_path / name / "config"
        source.mkdir(parents=True)
        output.mkdir()
        media_file = source / filename
        media_file.write_bytes(MEDIA_BYTES)
        root = tmp_path / name
        app = app_with_mocks(
            settings_for_layout(
                config_dir=config,
                storage_roots=(root,),
                monitor_enabled=True,
            ),
            xchina=xchina,
        )

        async def scenario() -> dict:
            async with api_client(app) as client:
                created = await client.post(
                    "/api/watch-rules",
                    json={
                        "source_directory": str(source),
                        "destination_directory": str(output),
                        "realtime": True,
                        "stability_seconds": 0,
                        "stable_check_count": 1,
                        "organization_mode": "copy",
                        "folder_templates": ["{studio}", "{title}"],
                        "filename_template": "{xchina_id} - {title}",
                        "asset_policy": "strict",
                        "include_patterns": ["*.mkv"],
                        "confidence_threshold": threshold,
                    },
                    headers={"Origin": ORIGIN},
                )
                assert created.status_code == 201, created.text
                rule_id = created.json()["rule_id"]
                app.state.monitor.handle_event(media_file, rule_id=rule_id)
                jobs = app.state.monitor.handle_event(media_file, rule_id=rule_id)
                return await run_worker_until_state(
                    app,
                    client,
                    jobs[0].id,
                    {"review_required", "completed", "failed"},
                )

        job = run(scenario())
        assert job["state"] == "review_required"
        assert expected_reason in job["gate_reasons"]
        assert not any(path.is_file() for path in output.rglob("*"))
        assert_disposable_database_paths(app, root)


def test_emby_failure_is_retryable_without_reexecuting_local_files(
    media_layout: MediaLayout,
    settings_for_layout,
) -> None:
    xchina = happy_xchina()
    emby = MockEmby(fail_next_refresh=True)
    app = app_with_mocks(
        settings_for_layout(monitor_enabled=True),
        xchina=xchina,
        emby=emby,
    )

    async def scenario() -> tuple[dict, dict, int]:
        async with api_client(app) as client:
            created = await client.post(
                "/api/watch-rules",
                json={
                    "source_directory": str(media_layout.source),
                    "destination_directory": str(media_layout.output),
                    "realtime": True,
                    "stability_seconds": 0,
                    "stable_check_count": 1,
                    "organization_mode": "copy",
                    "folder_templates": ["{studio}", "{title}"],
                    "filename_template": "{xchina_id} - {title}",
                    "asset_policy": "strict",
                    "include_patterns": ["*.mkv"],
                    "emby_options": {
                        "enabled": True,
                        "path_mappings": [
                            {
                                "container_root": str(media_layout.output),
                                "emby_root": "/visible",
                            }
                        ],
                    },
                },
                headers={"Origin": ORIGIN},
            )
            assert created.status_code == 201, created.text
            rule_id = created.json()["rule_id"]
            app.state.monitor.handle_event(media_layout.media_file, rule_id=rule_id)
            jobs = app.state.monitor.handle_event(media_layout.media_file, rule_id=rule_id)
            job_id = jobs[0].id

            failed = await run_worker_until_state(
                app,
                client,
                job_id,
                {"local_complete_emby_failed", "completed", "review_required", "failed"},
            )
            retry = await client.post(
                f"/api/jobs/{job_id}/retry-emby",
                headers={"Origin": ORIGIN},
            )
            assert retry.status_code == 200, retry.text
            completed = await run_worker_until_state(
                app,
                client,
                job_id,
                {"completed", "local_complete_emby_failed", "failed"},
            )
            return failed, completed, job_id

    failed, completed, job_id = run(scenario())
    target = media_layout.output / "Studio One" / "Sample Work Alpha" / "XC-001 - Sample Work Alpha.mkv"
    before_hash = sha256_file(target)
    before_mtime = target.stat().st_mtime_ns

    assert failed["state"] == "local_complete_emby_failed"
    assert failed["payload"]["local_operations_complete"] is True
    assert completed["state"] == "completed"
    assert before_hash == sha256_file(target)
    assert before_mtime == target.stat().st_mtime_ns
    assert emby.scan_calls == 2
    assert emby.refreshed_item_ids == ["emby-item-1"]

    with app.state.sessionmaker() as session:
        local_journal_lengths = [
            len(step.step_json.get("journal") or [])
            for step in session.query(OperationStep)
            .join(OperationStep.plan)
            .filter_by(job_id=job_id)
            .all()
        ]
    assert all(length == 2 for length in local_journal_lengths)
    assert_disposable_database_paths(app, media_layout.root)


def _xchina_for_detail(detail) -> MockXChina:
    return MockXChina(
        results=[result_for_detail(detail)],
        details={detail.source_url: detail},
        assets={
            "https://images.example.test/poster.jpg": (b"poster", "image/jpeg"),
            "https://images.example.test/fanart.jpg": (b"fanart", "image/jpeg"),
            "https://images.example.test/actor-one.jpg": (b"actor", "image/jpeg"),
        },
    )


def _xchina_for_results(rows: list[tuple[str, str]]) -> MockXChina:
    details = [
        happy_detail(source_id=source_id, title=title)
        for source_id, title in rows
    ]
    return MockXChina(
        results=[result_for_detail(detail) for detail in details],
        details={detail.source_url: detail for detail in details},
        assets={
            "https://images.example.test/poster.jpg": (b"poster", "image/jpeg"),
            "https://images.example.test/fanart.jpg": (b"fanart", "image/jpeg"),
            "https://images.example.test/actor-one.jpg": (b"actor", "image/jpeg"),
        },
    )
