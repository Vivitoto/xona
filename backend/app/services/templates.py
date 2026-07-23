from __future__ import annotations

import string
from pathlib import Path

from backend.app.schemas.templates import TemplateContext, TemplatePreview
from backend.app.services.normalization import sanitize_path_component


SUPPORTED_VARIABLES = {
    "number",
    "title",
    "original_title",
    "studio",
    "series",
    "year",
    "release_date",
    "actors",
    "first_actor",
    "source_filename",
    "xchina_id",
}


def preview_template(
    *,
    folder_templates: list[str],
    filename_template: str,
    context: TemplateContext,
) -> TemplatePreview:
    values = _context_values(context)
    validation_errors = [
        f"unknown_variable:{name}"
        for name in sorted(_unknown_variables([*folder_templates, filename_template]))
    ]
    warnings: list[str] = []
    if validation_errors:
        return TemplatePreview(
            folder_path=None,
            filename=None,
            validation_errors=validation_errors,
            warnings=warnings,
        )

    folders: list[str] = []
    for template in folder_templates:
        rendered = _render(template, values)
        component = sanitize_path_component(rendered)
        if component == "untitled":
            warnings.append("empty_folder_component")
        if len(component) >= 180:
            warnings.append("truncated_folder_component")
        folders.append(component)

    filename = sanitize_path_component(_render(filename_template, values))
    if filename == "untitled":
        validation_errors.append("empty_filename")
        filename_value = None
    else:
        filename_value = filename
    if len(filename) >= 180:
        warnings.append("truncated_filename")

    return TemplatePreview(
        folder_path=str(Path(*folders)) if folders else "",
        filename=filename_value,
        validation_errors=validation_errors,
        warnings=warnings,
    )


def _context_values(context: TemplateContext) -> dict[str, str]:
    release_date = context.release_date or ""
    return {
        "number": context.number or context.xchina_id or "",
        "title": context.title or "",
        "original_title": context.original_title or context.title or "",
        "studio": context.studio or "",
        "series": context.series or "",
        "year": release_date[:4] if len(release_date) >= 4 else "",
        "release_date": release_date,
        "actors": ", ".join(context.actors),
        "first_actor": context.actors[0] if context.actors else "",
        "source_filename": Path(context.source_filename or "").name,
        "xchina_id": context.xchina_id or context.number or "",
    }


def _unknown_variables(templates: list[str]) -> set[str]:
    formatter = string.Formatter()
    unknown: set[str] = set()
    for template in templates:
        for _literal, field_name, _format_spec, _conversion in formatter.parse(template):
            if field_name and field_name not in SUPPORTED_VARIABLES:
                unknown.add(field_name)
    return unknown


def _render(template: str, values: dict[str, str]) -> str:
    return template.format_map(values)
