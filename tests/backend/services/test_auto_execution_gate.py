from __future__ import annotations

from backend.app.schemas.matching import CandidateMetadata, ExecutionSafety, MatchInput
from backend.app.services.matching import can_auto_execute, manual_selection_gate


INPUT = MatchInput(search_text="ABC-123 Sample Work Alpha", identifier="ABC-123", title="Sample Work Alpha")
STRONG = CandidateMetadata(
    source_id="XC-001",
    title="Sample Work Alpha",
    identifiers=["ABC-123"],
    complete=True,
    asset_ready=True,
    unique_detail=True,
)


def test_strong_candidate_auto_approves_only_when_safe_and_complete() -> None:
    decision = can_auto_execute(INPUT, [STRONG], ExecutionSafety())

    assert decision.action == "auto_approved"
    assert decision.selected.source_id == "XC-001"
    assert decision.score.total >= 92


def test_auto_execute_lists_safety_refusal_reasons() -> None:
    unsafe = ExecutionSafety(
        unsafe_path=True,
        file_conflict=True,
        unresolved_multipart=True,
        strict_assets_missing=True,
    )
    incomplete = STRONG.model_copy(update={"complete": False, "asset_ready": False, "unique_detail": False})

    decision = can_auto_execute(INPUT, [incomplete], unsafe)

    assert decision.action == "review_required"
    for reason in [
        "unsafe_path",
        "file_conflict",
        "unresolved_multipart",
        "strict_assets_missing",
        "incomplete_metadata",
        "missing_strict_assets",
        "non_unique_detail",
    ]:
        assert reason in decision.reasons


def test_manual_selection_bypasses_confidence_but_not_safety() -> None:
    weak = CandidateMetadata(source_id="XC-002", title="Different", complete=True, asset_ready=True)

    allowed = manual_selection_gate(weak, ExecutionSafety())
    refused = manual_selection_gate(
        weak,
        ExecutionSafety(file_conflict=True, strict_assets_missing=True),
    )

    assert allowed.action == "manual_approved"
    assert refused.action == "review_required"
    assert refused.reasons == ["file_conflict", "strict_assets_missing"]
