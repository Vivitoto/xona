from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.local_metadata import (
    LocalBatchCoverSettings,
    LocalCoverPreviewRequest,
    LocalFrameRequest,
    LocalMetadataBatchCreateItem,
    LocalMetadataBatchCreateRequest,
    LocalMetadataBatchOptions,
    LocalMetadataDraft,
    LocalPlanPreviewRequest,
    LocalVideoTechnicalInfo,
)
from backend.app.services.cover_templates import (
    FANART_SIZE,
    POSTER_SIZE,
    CoverTemplateError,
    generate_cover_previews,
)
from backend.app.services import local_metadata as local_metadata_module
from backend.app.services.local_metadata import (
    LocalMetadataError,
    LocalMetadataService,
    clean_local_title,
    clean_organize_filename,
    local_metadata_record,
    _percentage_times,
    _video_cache_dir_for_asset_path,
)
from backend.app.services.local_metadata_batches import (
    LocalMetadataBatchManager,
    LocalMetadataBatchService,
    recalculate_batch_counts,
)
from backend.app.services.nfo import render_movie_nfo


def test_clean_local_title_uses_existing_filename_normalizer() -> None:
    assert (
        clean_local_title("site-prefix ABC123 [1080p WEB-DL] Nice.Title.4K.mkv")
        == "ABC123 Nice Title"
    )
    assert clean_local_title("TangXin.Vlog_EP01_1080p.mp4") == "TangXin Vlog_EP01"
    assert (
        clean_local_title("Nana_taipei【轻熟女教】老师4顽徒驯服 老师用肉体调教问题学生_4K.mkv")
        == "Nana_taipei【轻熟女教】老师4顽徒驯服 老师用肉体调教问题学生"
    )


def test_clean_organize_filename_sanitizes_user_stem() -> None:
    assert clean_organize_filename("../Custom:Name.mp4", source_suffix=".mp4") == "Custom_Name"
    assert clean_organize_filename("   ") is None


def test_local_metadata_draft_tags_default_empty() -> None:
    draft = LocalMetadataDraft(
        video_path=Path("/media/incoming/Local.Work.mp4"),
        title="Local Work",
    )

    assert draft.tags == []


def test_cover_templates_generate_poster_and_fanart_smoke(tmp_path: Path) -> None:
    frame_paths = [
        _synthetic_frame(tmp_path / f"frame-{index}.jpg", color)
        for index, color in enumerate(_nine_colors(), start=1)
    ]

    for template in ("simple_poster", "jav_classic_left_strip", "tangxin_vlog"):
        generated = generate_cover_previews(
            title="Local Work Title",
            template=template,
            frame_paths=frame_paths,
            output_dir=tmp_path / template,
        )

        assert generated.poster_path.is_file()
        assert generated.fanart_path.is_file()
        assert generated.thumb_path.is_file()
        with Image.open(generated.poster_path) as poster:
            assert poster.size == POSTER_SIZE
        with Image.open(generated.fanart_path) as fanart:
            assert fanart.size == FANART_SIZE
        with Image.open(generated.thumb_path) as thumb:
            assert thumb.size == FANART_SIZE


def test_cover_templates_render_thumb_as_three_by_three_collage_from_nine_frames(
    tmp_path: Path,
) -> None:
    colors = _nine_colors()
    frame_paths = [
        _solid_frame(tmp_path / f"solid-{index}.jpg", color)
        for index, color in enumerate(colors, start=1)
    ]

    generated = generate_cover_previews(
        title="Local Work Title",
        template="simple_poster",
        frame_paths=frame_paths,
        output_dir=tmp_path / "collage",
    )

    with Image.open(generated.thumb_path) as thumb:
        assert thumb.size == FANART_SIZE
        tile_width = FANART_SIZE[0] // 3
        tile_height = FANART_SIZE[1] // 3
        sampled = [
            thumb.getpixel(
                (
                    (index % 3) * tile_width + tile_width // 2,
                    (index // 3) * tile_height + tile_height // 2,
                )
            )
            for index in range(9)
        ]

    assert all(_near_color(pixel, color) for pixel, color in zip(sampled, colors))


def test_cover_templates_refuse_thumb_when_fewer_than_nine_distinct_frames(
    tmp_path: Path,
) -> None:
    colors = [
        (226, 32, 44),
        (30, 198, 82),
        (36, 78, 224),
        (235, 180, 40),
    ]
    frame_paths = [
        _solid_frame(tmp_path / f"solid-{index}.jpg", color)
        for index, color in enumerate(colors, start=1)
    ]

    with pytest.raises(CoverTemplateError, match="nine_distinct_frames_required:4"):
        generate_cover_previews(
            title="Local Work Title",
            template="simple_poster",
            frame_paths=frame_paths,
            output_dir=tmp_path / "collage",
        )


def test_cover_templates_render_fanart_as_promotional_art_not_thumb_grid(
    tmp_path: Path,
) -> None:
    colors = _nine_colors()
    frame_paths = [
        _solid_frame(tmp_path / f"solid-{index}.jpg", color)
        for index, color in enumerate(colors, start=1)
    ]

    generated = generate_cover_previews(
        title="Local Work Title",
        template="simple_poster",
        frame_paths=frame_paths,
        output_dir=tmp_path / "fanart",
    )

    with Image.open(generated.fanart_path) as fanart, Image.open(generated.thumb_path) as thumb:
        assert fanart.size == FANART_SIZE
        assert fanart.tobytes() != thumb.tobytes()
        assert _near_color(fanart.getpixel((FANART_SIZE[0] - 120, 120)), colors[0])
        assert not _near_color(fanart.getpixel((FANART_SIZE[0] // 6, FANART_SIZE[1] // 6)), colors[0])


def test_local_frame_request_defaults_to_nine_evenly_spaced_screenshots() -> None:
    request = LocalFrameRequest(video_path=Path("/media/source.mp4"))

    assert request.frame_count == 9
    assert request.percentages == []
    assert _percentage_times(request.percentages, 100.0, frame_count=request.frame_count) == [
        10.0,
        20.0,
        30.0,
        40.0,
        50.0,
        60.0,
        70.0,
        80.0,
        90.0,
    ]


def test_generate_frames_uses_known_duration_without_reprobing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "media"
    root.mkdir()
    video = root / "Known.Duration.mp4"
    video.write_bytes(b"synthetic-video")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    observed_times: list[float] = []

    def fail_probe(path: Path) -> LocalVideoTechnicalInfo:
        raise AssertionError(f"unexpected probe for {path}")

    def fake_extract(
        video_path: Path,
        *,
        output_dir: Path,
        times_seconds: list[float],
    ) -> list[tuple[Path, float]]:
        observed_times.extend(times_seconds)
        return [
            (_solid_frame(Path(output_dir) / f"frame-{index:02d}.jpg", color), time)
            for index, (time, color) in enumerate(
                zip(times_seconds, _nine_colors(), strict=True),
                start=1,
            )
        ]

    monkeypatch.setattr(local_metadata_module, "probe_video", fail_probe)
    monkeypatch.setattr(local_metadata_module, "extract_video_frames", fake_extract)

    try:
        with get_sessionmaker(engine)() as session:
            response = LocalMetadataService(settings, session).generate_frames(
                LocalFrameRequest(
                    video_path=video,
                    frame_count=9,
                    duration_seconds=90,
                )
            )

        assert [frame.time_seconds for frame in response.frames] == observed_times
        assert observed_times == _percentage_times([], 90, frame_count=9)
    finally:
        engine.dispose()


def test_generate_frames_reuses_cached_frames_without_extracting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "media"
    root.mkdir()
    video = root / "Cached.Frames.mp4"
    video.write_bytes(b"synthetic-video")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)

    def fail_probe(path: Path) -> LocalVideoTechnicalInfo:
        raise AssertionError(f"unexpected probe for {path}")

    def fail_extract(
        video_path: Path,
        *,
        output_dir: Path,
        times_seconds: list[float],
    ) -> list[tuple[Path, float]]:
        raise AssertionError("unexpected frame extraction")

    monkeypatch.setattr(local_metadata_module, "probe_video", fail_probe)
    monkeypatch.setattr(local_metadata_module, "extract_video_frames", fail_extract)

    try:
        with get_sessionmaker(engine)() as session:
            service = LocalMetadataService(settings, session)
            frame_dir = service._cache_dir_for_video(video) / "frames"
            for index, color in enumerate(_nine_colors(), start=1):
                _solid_frame(frame_dir / f"frame-{index:02d}.jpg", color)

            response = service.generate_frames(
                LocalFrameRequest(
                    video_path=video,
                    frame_count=9,
                    duration_seconds=90,
                )
            )

        assert len(response.frames) == 9
        assert response.frames[0].id.endswith("frames/frame-01.jpg")
        assert [frame.time_seconds for frame in response.frames] == _percentage_times(
            [],
            90,
            frame_count=9,
        )
    finally:
        engine.dispose()


def test_cover_preview_rejects_frames_from_another_video_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "media"
    root.mkdir()
    first_video = root / "First.Scene.mp4"
    second_video = root / "Second.Scene.mp4"
    first_video.write_bytes(b"first-video")
    second_video.write_bytes(b"second-video")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)

    def fail_probe(path: Path) -> LocalVideoTechnicalInfo:
        raise AssertionError(f"unexpected probe for {path}")

    def fake_extract(
        video_path: Path,
        *,
        output_dir: Path,
        times_seconds: list[float],
    ) -> list[tuple[Path, float]]:
        return [
            (_solid_frame(Path(output_dir) / f"frame-{index:02d}.jpg", color), time)
            for index, (time, color) in enumerate(
                zip(times_seconds, _nine_colors(), strict=True),
                start=1,
            )
        ]

    monkeypatch.setattr(local_metadata_module, "probe_video", fail_probe)
    monkeypatch.setattr(local_metadata_module, "extract_video_frames", fake_extract)

    try:
        with get_sessionmaker(engine)() as session:
            service = LocalMetadataService(settings, session)
            first_frames = service.generate_frames(
                LocalFrameRequest(
                    video_path=first_video,
                    frame_count=9,
                    duration_seconds=90,
                )
            )

            with pytest.raises(LocalMetadataError) as exc_info:
                service.cover_preview(
                    LocalCoverPreviewRequest(
                        video_path=second_video,
                        title="Second Scene",
                        selected_frame_ids=[frame.id for frame in first_frames.frames],
                    )
                )

        assert exc_info.value.code == "frame_ref_mismatch"
        assert exc_info.value.status_code == 409
    finally:
        engine.dispose()


def test_local_metadata_batch_manager_recovers_interrupted_batches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "media"
    destination = root / "organized"
    root.mkdir()
    destination.mkdir()
    first_video = root / "Interrupted.Preview.mp4"
    second_video = root / "Interrupted.Execute.mp4"
    first_video.write_bytes(b"synthetic-video")
    second_video.write_bytes(b"synthetic-video")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)

    try:
        session_factory = get_sessionmaker(engine)
        with session_factory() as session:
            batch = LocalMetadataBatchService(session).create_batch(
                LocalMetadataBatchCreateRequest(
                    options=LocalMetadataBatchOptions(
                        destination_root=destination,
                        mode="move",
                    ),
                    items=[
                        LocalMetadataBatchCreateItem(
                            video_path=first_video,
                            filename=first_video.name,
                            metadata=LocalMetadataDraft(
                                video_path=first_video,
                                title="Interrupted Preview",
                            ),
                            cover_settings=LocalBatchCoverSettings(),
                        ),
                        LocalMetadataBatchCreateItem(
                            video_path=second_video,
                            filename=second_video.name,
                            metadata=LocalMetadataDraft(
                                video_path=second_video,
                                title="Interrupted Execute",
                            ),
                            cover_settings=LocalBatchCoverSettings(),
                        ),
                    ],
                )
            )
            batch_id = batch.batch_id
            batch.status = "running"
            batch.items[0].status = "running"
            batch.items[1].status = "executing"
            batch.items[1].plan_id = "plan-interrupted"
            recalculate_batch_counts(batch)
            session.commit()

        manager = LocalMetadataBatchManager(session_factory, settings=settings)
        restarted_preview_batches: list[str] = []
        monkeypatch.setattr(manager, "start_preview", restarted_preview_batches.append)

        manager.recover_interrupted_batches()

        with session_factory() as session:
            recovered = LocalMetadataBatchService(session).get_batch(batch_id)
            assert recovered.status == "queued"
            assert recovered.pending_count == 1
            assert recovered.execute_failed_count == 1
            assert recovered.items[0].status == "pending"
            assert recovered.items[0].error is None
            assert recovered.items[0].logs_json[-1]["message"] == "服务重启后已恢复为等待处理"
            assert recovered.items[1].status == "execute_failed"
            assert recovered.items[1].error == "服务重启时整理执行中断；请检查目标文件后手动重试。"

        assert restarted_preview_batches == [batch_id]
    finally:
        engine.dispose()


def test_local_metadata_record_maps_draft_actors_to_nfo_and_template_context(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = root / "organized"
    incoming.mkdir(parents=True)
    destination.mkdir()
    video = incoming / "Actor.Work.mp4"
    video.write_bytes(b"synthetic-video")
    draft = LocalMetadataDraft(
        video_path=video,
        title="Actor Work",
        plot="Local draft.",
        actors=[" Actor One ", "Actor Two", "Actor One", ""],
        tags=["Manual Tag"],
    )

    record = local_metadata_record(draft)

    assert [actor.name for actor in record.actors] == ["Actor One", "Actor Two"]
    assert record.tags == ["Manual Tag"]

    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    try:
        with get_sessionmaker(engine)() as session:
            response = LocalMetadataService(settings, session).preview_plan(
                LocalPlanPreviewRequest(
                    metadata=draft,
                    destination_root=destination,
                    mode="preview",
                    folder_templates=["{first_actor}", "{actors}", "{title}"],
                    filename_template="{first_actor} - {title}",
                )
            )

            assert response.plan["target_directory"].endswith(
                "Actor One/Actor One, Actor Two/Actor Work"
            )
            assert "<name>Actor One</name>" in response.nfo_xml
            assert "<name>Actor Two</name>" in response.nfo_xml
            assert response.metadata["actors"][0]["name"] == "Actor One"
    finally:
        engine.dispose()


def test_local_metadata_record_adds_resolution_actor_and_studio_labels() -> None:
    draft = LocalMetadataDraft(
        video_path=Path("/media/incoming/Local.Work.mp4"),
        title="Local Work",
        studio=" 糖心Vlog ",
        actors=[" 星野兔 ", "星野兔", ""],
        technical=LocalVideoTechnicalInfo(
            path=Path("/media/incoming/Local.Work.mp4"),
            size_bytes=123,
            duration_seconds=2880,
            width=3840,
            height=2160,
            video_codec="hevc",
            audio_codec="aac",
            bit_rate=12000000,
            fps=59.94,
        ),
    )

    record = local_metadata_record(draft)

    assert record.labels == ["4K", "星野兔", "糖心Vlog"]
    assert record.tags == []
    assert record.genres == []
    assert record.technical is not None
    assert record.technical.width == 3840
    assert record.technical.height == 2160
    assert record.technical.video_codec == "hevc"


def test_local_metadata_record_expands_nfo_tag_and_genre_variables() -> None:
    draft = LocalMetadataDraft(
        video_path=Path("/media/incoming/Local.Work.mp4"),
        title="Local Work",
        studio=" Studio Local ",
        actors=[" Actor One ", "Actor Two", "Actor One"],
        tags=["{actors}", "{studio}", "{resolution}"],
        genres=["{actors}", "{studio}", "{resolution}"],
        technical=LocalVideoTechnicalInfo(
            path=Path("/media/incoming/Local.Work.mp4"),
            size_bytes=123,
            duration_seconds=2880,
            width=1920,
            height=1080,
            video_codec="h264",
            audio_codec="aac",
            bit_rate=5000000,
            fps=29.97,
        ),
    )

    record = local_metadata_record(draft)
    xml_text = render_movie_nfo(record).decode("utf-8")

    assert record.tags == ["Actor One", "Actor Two", "片商: Studio Local", "1080p"]
    assert record.genres == ["Actor One", "Actor Two", "片商: Studio Local", "1080p"]
    assert "<tag>Actor One</tag>" in xml_text
    assert "<tag>Actor Two</tag>" in xml_text
    assert "<tag>片商: Studio Local</tag>" in xml_text
    assert "<tag>1080p</tag>" in xml_text
    assert "<genre>Actor One</genre>" in xml_text
    assert "<genre>Actor Two</genre>" in xml_text
    assert "<genre>片商: Studio Local</genre>" in xml_text
    assert "<genre>1080p</genre>" in xml_text


def test_local_metadata_record_preserves_explicit_draft_tags_for_nfo() -> None:
    draft = LocalMetadataDraft(
        video_path=Path("/media/incoming/Local.Work.mp4"),
        title="Local Work",
        studio="Studio Local",
        actors=["Actor One"],
        tags=[" Explicit Tag ", "Actor One", "Explicit Tag"],
        genres=[" Manual Genre ", "Manual Genre"],
        technical=LocalVideoTechnicalInfo(
            path=Path("/media/incoming/Local.Work.mp4"),
            size_bytes=123,
            duration_seconds=2880,
            width=1920,
            height=1080,
            video_codec="h264",
            audio_codec="aac",
            bit_rate=5000000,
            fps=29.97,
        ),
    )

    record = local_metadata_record(draft)
    xml_text = render_movie_nfo(record).decode("utf-8")

    assert record.tags == ["Explicit Tag", "Actor One"]
    assert record.genres == ["Manual Genre"]
    assert "<tag>Explicit Tag</tag>" in xml_text
    assert "<tag>Actor One</tag>" in xml_text
    assert "<genre>Manual Genre</genre>" in xml_text
    assert "<tag>片商: Studio Local</tag>" not in xml_text
    assert "<tag>1080p</tag>" not in xml_text
    assert "<genre>片商: Studio Local</genre>" not in xml_text
    assert "<genre>1080p</genre>" not in xml_text


def test_local_plan_preview_includes_nfo_and_cached_generated_images(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = root / "organized"
    incoming.mkdir(parents=True)
    destination.mkdir()
    video = incoming / "Unmatched.Work.mp4"
    video.write_bytes(b"synthetic-video")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    try:
        with get_sessionmaker(engine)() as session:
            service = LocalMetadataService(settings, session)
            cache_dir = service._cache_dir_for_video(video)
            poster = _synthetic_frame(cache_dir / "covers" / "poster.jpg", (40, 84, 126), size=(1000, 1500))
            fanart = _synthetic_frame(cache_dir / "covers" / "fanart.jpg", (48, 112, 76), size=(1920, 1080))
            thumb = _synthetic_frame(cache_dir / "covers" / "thumb.jpg", (98, 88, 156), size=(1920, 1080))
            frame1 = _synthetic_frame(cache_dir / "frames" / "frame-1.jpg", (126, 72, 52))
            frame2 = _synthetic_frame(cache_dir / "frames" / "frame-2.jpg", (48, 112, 76))
            frame3 = _synthetic_frame(cache_dir / "frames" / "frame-3.jpg", (190, 120, 40))
            response = service.preview_plan(
                LocalPlanPreviewRequest(
                    metadata=LocalMetadataDraft(
                        video_path=video,
                        title="Unmatched Work",
                        plot="Local draft.",
                    ),
                    destination_root=destination,
                    mode="preview",
                    folder_templates=["Local", "{title}"],
                    filename_template="{title}",
                    poster_ref=str(poster.relative_to(settings.config_dir / "cache" / "local_metadata")),
                    fanart_ref=str(fanart.relative_to(settings.config_dir / "cache" / "local_metadata")),
                    thumb_ref=str(thumb.relative_to(settings.config_dir / "cache" / "local_metadata")),
                    selected_frame_ids=[
                        str(frame1.relative_to(settings.config_dir / "cache" / "local_metadata")),
                        str(frame2.relative_to(settings.config_dir / "cache" / "local_metadata")),
                        str(frame3.relative_to(settings.config_dir / "cache" / "local_metadata")),
                    ],
                    extra_backdrop_count=3,
                )
            )

            assert response.plan_id.startswith("plan_")
            assert len(response.materialized_assets) == 6
            steps = response.plan["steps"]
            assert any(step["category"] == "media" for step in steps)
            assert any(step["category"] == "asset" and step["target_path"].endswith("poster.jpg") for step in steps)
            assert any(step["category"] == "asset" and step["target_path"].endswith("fanart.jpg") for step in steps)
            assert any(step["category"] == "asset" and step["target_path"].endswith("thumb.jpg") for step in steps)
            assert any(step["category"] == "asset" and step["target_path"].endswith("backdrop.jpg") for step in steps)
            assert any(step["category"] == "asset" and step["target_path"].endswith("backdrop1.jpg") for step in steps)
            assert any(step["category"] == "asset" and step["target_path"].endswith("backdrop2.jpg") for step in steps)
            assert not any(step["category"] == "asset" and step["target_path"].endswith("backdrop3.jpg") for step in steps)
            assert any(
                step["category"] == "generated_artifact"
                and step["target_path"].endswith("Unmatched Work.nfo")
                for step in steps
            )
            assert not (destination / ".xona-cache").exists()
            for asset in response.materialized_assets:
                assert settings.config_dir / "cache" / "local_metadata" in Path(
                    asset["cache_path"]
                ).parents
            assert "<title>Unmatched Work</title>" in response.nfo_xml
    finally:
        engine.dispose()


def test_local_plan_preview_uses_organize_filename_for_media_and_nfo_not_xml_title(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = root / "organized"
    incoming.mkdir(parents=True)
    destination.mkdir()
    video = incoming / "Metadata.Title.mp4"
    video.write_bytes(b"synthetic-video")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    try:
        with get_sessionmaker(engine)() as session:
            service = LocalMetadataService(settings, session)
            response = service.preview_plan(
                LocalPlanPreviewRequest(
                    metadata=LocalMetadataDraft(
                        video_path=video,
                        title="Metadata Title",
                        organize_filename="Custom.Name.mp4",
                        plot="Local draft.",
                    ),
                    destination_root=destination,
                    mode="preview",
                    folder_templates=["Local", "{title}"],
                    filename_template="{unknown_filename_variable}",
                )
            )

            steps = response.plan["steps"]
            media_targets = [
                step["target_path"]
                for step in steps
                if step["category"] == "media"
            ]
            generated_targets = [
                step["target_path"]
                for step in steps
                if step["category"] == "generated_artifact"
            ]

            assert response.plan["target_directory"].endswith("Local/Metadata Title")
            assert media_targets == [
                str(destination / "Local" / "Metadata Title" / "Custom.Name.mp4")
            ]
            assert generated_targets == [
                str(destination / "Local" / "Metadata Title" / "Custom.Name.nfo")
            ]
            assert "<title>Metadata Title</title>" in response.nfo_xml
            assert "<title>Custom.Name</title>" not in response.nfo_xml
    finally:
        engine.dispose()


def test_local_plan_preview_refuses_existing_backdrop_output(tmp_path: Path) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = root / "organized"
    target_dir = destination / "Local" / "Unmatched Work"
    incoming.mkdir(parents=True)
    target_dir.mkdir(parents=True)
    video = incoming / "Unmatched.Work.mp4"
    video.write_bytes(b"synthetic-video")
    (target_dir / "backdrop.jpg").write_bytes(b"existing-backdrop")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    try:
        with get_sessionmaker(engine)() as session:
            service = LocalMetadataService(settings, session)
            cache_dir = service._cache_dir_for_video(video)
            frame = _synthetic_frame(cache_dir / "frames" / "frame-1.jpg", (126, 72, 52))
            with pytest.raises(LocalMetadataError) as exc_info:
                service.preview_plan(
                    LocalPlanPreviewRequest(
                        metadata=LocalMetadataDraft(
                            video_path=video,
                            title="Unmatched Work",
                            plot="Local draft.",
                        ),
                        destination_root=destination,
                        mode="preview",
                        folder_templates=["Local", "{title}"],
                        filename_template="{title}",
                        selected_frame_ids=[
                            str(frame.relative_to(settings.config_dir / "cache" / "local_metadata"))
                        ],
                        extra_backdrop_count=1,
                    )
                )

            assert exc_info.value.code == "destination_collision"
            assert "target_exists" in exc_info.value.reasons
    finally:
        engine.dispose()


def test_local_execute_plan_runs_current_non_preview_plan(tmp_path: Path) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = root / "organized"
    incoming.mkdir(parents=True)
    destination.mkdir()
    video = incoming / "Executable.Work.mp4"
    video.write_bytes(b"synthetic-video")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    try:
        with get_sessionmaker(engine)() as session:
            service = LocalMetadataService(settings, session)
            preview = service.preview_plan(
                LocalPlanPreviewRequest(
                    metadata=LocalMetadataDraft(
                        video_path=video,
                        title="Executable Work",
                        organize_filename="Executable Output",
                        plot="Local draft.",
                    ),
                    destination_root=destination,
                    mode="copy",
                    folder_templates=["Local", "{title}"],
                    filename_template="{title}",
                )
            )

            result = service.execute_plan(
                preview.plan_id,
                approved=True,
                plan_version=preview.plan["version"],
            )

            assert result.state == "completed"
            assert (destination / "Local" / "Executable Work" / "Executable Output.mp4").read_bytes() == b"synthetic-video"
            assert (destination / "Local" / "Executable Work" / "Executable Output.nfo").is_file()

        with get_sessionmaker(engine)() as session:
            service = LocalMetadataService(settings, session)
            preview = service.preview_plan(
                LocalPlanPreviewRequest(
                    metadata=LocalMetadataDraft(
                        video_path=video,
                        title="Preview Only Work",
                        plot="Local draft.",
                    ),
                    destination_root=destination,
                    mode="preview",
                    folder_templates=["Preview", "{title}"],
                    filename_template="{title}",
                )
            )

            with pytest.raises(LocalMetadataError) as exc_info:
                service.execute_plan(
                    preview.plan_id,
                    approved=True,
                    plan_version=preview.plan["version"],
                )

            assert exc_info.value.code == "plan_not_executable:preview_mode"
    finally:
        engine.dispose()


def test_local_plan_cache_cleanup_requires_completed_plan_and_removes_video_cache_dir(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = root / "organized"
    incoming.mkdir(parents=True)
    destination.mkdir()
    video = incoming / "Cache.Cleanup.Work.mp4"
    video.write_bytes(b"synthetic-video")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    try:
        with get_sessionmaker(engine)() as session:
            service = LocalMetadataService(settings, session)
            cache_dir = service._cache_dir_for_video(video)
            poster = _synthetic_frame(
                cache_dir / "covers" / "poster.jpg",
                (40, 84, 126),
                size=(1000, 1500),
            )
            fanart = _synthetic_frame(
                cache_dir / "covers" / "fanart.jpg",
                (48, 112, 76),
                size=(1920, 1080),
            )
            thumb = _synthetic_frame(
                cache_dir / "covers" / "thumb.jpg",
                (98, 88, 156),
                size=(1920, 1080),
            )
            frame = _synthetic_frame(cache_dir / "frames" / "frame-1.jpg", (126, 72, 52))
            cache_root = settings.config_dir / "cache" / "local_metadata"
            preview = service.preview_plan(
                LocalPlanPreviewRequest(
                    metadata=LocalMetadataDraft(
                        video_path=video,
                        title="Cache Cleanup Work",
                        plot="Local draft.",
                    ),
                    destination_root=destination,
                    mode="copy",
                    folder_templates=["Local", "{title}"],
                    filename_template="{title}",
                    poster_ref=str(poster.relative_to(cache_root)),
                    fanart_ref=str(fanart.relative_to(cache_root)),
                    thumb_ref=str(thumb.relative_to(cache_root)),
                    selected_frame_ids=[str(frame.relative_to(cache_root))],
                    extra_backdrop_count=1,
                )
            )

            with pytest.raises(LocalMetadataError) as exc_info:
                service.cleanup_plan_cache(
                    preview.plan_id,
                    plan_version=preview.plan["version"],
                )

            assert exc_info.value.code == "plan_not_completed"
            assert cache_dir.is_dir()

            service.execute_plan(
                preview.plan_id,
                approved=True,
                plan_version=preview.plan["version"],
            )
            result = service.cleanup_plan_cache(
                preview.plan_id,
                plan_version=preview.plan["version"],
            )

            assert result.deleted_directories == 1
            assert result.deleted_files == 4
            assert result.cache_dirs == [cache_dir]
            assert result.warnings == []
            assert not cache_dir.exists()
            assert (settings.config_dir / "cache" / "local_metadata").is_dir()
            assert (
                destination / "Local" / "Cache Cleanup Work" / "poster.jpg"
            ).is_file()
            assert (
                destination / "Local" / "Cache Cleanup Work" / "backdrop.jpg"
            ).is_file()
    finally:
        engine.dispose()


def test_local_metadata_cache_dir_resolution_only_accepts_video_cache_shape(
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "cache" / "local_metadata"
    key = "ab" + ("0" * 62)

    assert _video_cache_dir_for_asset_path(
        cache_root / "ab" / key / "covers" / "poster.jpg",
        root=cache_root,
    ) == cache_root / "ab" / key
    assert _video_cache_dir_for_asset_path(
        cache_root / "manual" / "poster.jpg",
        root=cache_root,
    ) is None
    assert _video_cache_dir_for_asset_path(
        cache_root / "ab" / key,
        root=cache_root,
    ) is None
    assert _video_cache_dir_for_asset_path(
        tmp_path / "outside" / "ab" / key / "covers" / "poster.jpg",
        root=cache_root,
    ) is None


def _synthetic_frame(
    path: Path,
    color: tuple[int, int, int],
    *,
    size: tuple[int, int] = (1280, 720),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, size[0] - 40, size[1] - 40), outline=(255, 255, 255), width=8)
    draw.line((0, 0, size[0], size[1]), fill=(255, 255, 255), width=5)
    image.save(path, "JPEG")
    return path


def _solid_frame(path: Path, color: tuple[int, int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), color)
    image.save(path, "JPEG", quality=95)
    return path


def _nine_colors() -> list[tuple[int, int, int]]:
    return [
        (226, 32, 44),
        (30, 198, 82),
        (36, 78, 224),
        (235, 180, 40),
        (165, 78, 224),
        (32, 178, 190),
        (242, 92, 148),
        (70, 150, 68),
        (55, 55, 62),
    ]


def _near_color(
    observed: tuple[int, int, int],
    expected: tuple[int, int, int],
    *,
    tolerance: int = 24,
) -> bool:
    return all(abs(channel - target) <= tolerance for channel, target in zip(observed, expected))
