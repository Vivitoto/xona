from __future__ import annotations

from backend.app.schemas.templates import TemplateContext
from backend.app.services.templates import preview_template


def _context() -> TemplateContext:
    return TemplateContext(
        number="XC-001",
        title="Bad/Title",
        original_title="Original Title",
        studio="CON",
        series="Series: Example",
        release_date="2026-01-15",
        actors=["Actor One", "Actor/Two"],
        source_filename="source-file.mkv",
        xchina_id="XC-001",
    )


def test_renders_supported_variables_and_sanitizes_components() -> None:
    preview = preview_template(
        folder_templates=["{studio}", "{series}"],
        filename_template="{number} - {title} ({year}) - {first_actor}.mkv",
        context=_context(),
    )

    assert preview.validation_errors == []
    assert preview.folder_path == "CON_/Series_ Example"
    assert preview.filename == "XC-001 - Bad_Title (2026) - Actor One.mkv"


def test_actors_source_filename_release_date_and_xchina_id_variables() -> None:
    preview = preview_template(
        folder_templates=["{actors}"],
        filename_template="{xchina_id} - {original_title} - {release_date} - {source_filename}",
        context=_context(),
    )

    assert preview.folder_path == "Actor One, Actor_Two"
    assert preview.filename == "XC-001 - Original Title - 2026-01-15 - source-file.mkv"


def test_unknown_variables_return_validation_errors() -> None:
    preview = preview_template(
        folder_templates=["{studio}"],
        filename_template="{unknown} - {title}.mkv",
        context=_context(),
    )

    assert preview.validation_errors == ["unknown_variable:unknown"]
    assert preview.filename is None


def test_templates_do_not_create_nested_paths_inside_single_component() -> None:
    preview = preview_template(
        folder_templates=["{studio}/{series}"],
        filename_template="../{title}\0.mkv",
        context=_context(),
    )

    assert preview.validation_errors == []
    assert preview.folder_path == "CON_Series_ Example"
    assert preview.filename == "Bad_Title.mkv"
