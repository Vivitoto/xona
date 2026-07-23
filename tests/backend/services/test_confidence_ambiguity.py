from __future__ import annotations

from backend.app.schemas.matching import CandidateMetadata, MatchInput
from backend.app.services.matching import evaluate_candidates


INPUT = MatchInput(search_text="Sample Work Alpha", title="Sample Work Alpha")


def _candidate(source_id: str, title: str, *, complete: bool = True) -> CandidateMetadata:
    return CandidateMetadata(
        source_id=source_id,
        title=title,
        complete=complete,
        asset_ready=True,
    )


def test_no_candidates_requires_review() -> None:
    decision = evaluate_candidates(INPUT, [])

    assert decision.action == "review_required"
    assert decision.reasons == ["no_candidates"]


def test_exact_and_non_exact_ties_require_review() -> None:
    exact = evaluate_candidates(
        INPUT,
        [_candidate("one", "Sample Work Alpha"), _candidate("two", "Sample Work Alpha")],
    )
    fuzzy = evaluate_candidates(
        INPUT,
        [_candidate("one", "Sample Work Alfa"), _candidate("two", "Sample Work Alfa")],
        auto_threshold=50,
        required_lead=0,
    )

    assert exact.action == "review_required"
    assert "tie" in exact.reasons
    assert fuzzy.action == "review_required"
    assert "tie" in fuzzy.reasons


def test_insufficient_lead_requires_review() -> None:
    decision = evaluate_candidates(
        INPUT,
        [_candidate("one", "Sample Work Alpha"), _candidate("two", "Sample Work Alphb")],
        auto_threshold=50,
        required_lead=10,
    )

    assert decision.action == "review_required"
    assert "insufficient_lead" in decision.reasons
