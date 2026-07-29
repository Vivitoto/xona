from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.local_metadata import (
    LocalFrameRequest,
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
from backend.app.services.local_metadata import (
    LocalMetadataError,
    LocalMetadataService,
    clean_local_title,
    clean_organize_filename,
    local_metadata_record,
    _percentage_times,
)


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
        tags=["local-generated", "unmatched"],
    )

    record = local_metadata_record(draft)

    assert [actor.name for actor in record.actors] == ["Actor One", "Actor Two"]

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
    assert record.technical is not None
    assert record.technical.width == 3840
    assert record.technical.height == 2160
    assert record.technical.video_codec == "hevc"


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
    cache_dir = settings.config_dir / "cache" / "local_metadata" / "synthetic"
    poster = _synthetic_frame(cache_dir / "poster.jpg", (40, 84, 126), size=(1000, 1500))
    fanart = _synthetic_frame(cache_dir / "fanart.jpg", (48, 112, 76), size=(1920, 1080))
    thumb = _synthetic_frame(cache_dir / "thumb.jpg", (98, 88, 156), size=(1920, 1080))
    frame1 = _synthetic_frame(cache_dir / "frames" / "frame-1.jpg", (126, 72, 52))
    frame2 = _synthetic_frame(cache_dir / "frames" / "frame-2.jpg", (48, 112, 76))
    frame3 = _synthetic_frame(cache_dir / "frames" / "frame-3.jpg", (190, 120, 40))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    try:
        with get_sessionmaker(engine)() as session:
            service = LocalMetadataService(settings, session)
            response = service.preview_plan(
                LocalPlanPreviewRequest(
                    metadata=LocalMetadataDraft(
                        video_path=video,
                        title="Unmatched Work",
                        plot="Local draft.",
                        tags=["local-generated", "unmatched"],
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
                        tags=["local-generated", "unmatched"],
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
    cache_dir = settings.config_dir / "cache" / "local_metadata" / "synthetic"
    frame = _synthetic_frame(cache_dir / "frames" / "frame-1.jpg", (126, 72, 52))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    try:
        with get_sessionmaker(engine)() as session:
            service = LocalMetadataService(settings, session)
            with pytest.raises(LocalMetadataError) as exc_info:
                service.preview_plan(
                    LocalPlanPreviewRequest(
                        metadata=LocalMetadataDraft(
                            video_path=video,
                            title="Unmatched Work",
                            plot="Local draft.",
                            tags=["local-generated", "unmatched"],
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
                        tags=["local-generated", "unmatched"],
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
                        tags=["local-generated", "unmatched"],
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
