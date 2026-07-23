from __future__ import annotations

from backend.app.schemas.matching import CandidateMetadata, MatchInput
from backend.app.services.matching import score_candidate


def test_score_candidate_exposes_weighted_breakdown() -> None:
    match_input = MatchInput(
        search_text="ABC-123 Sample Work Alpha",
        identifier="ABC-123",
        title="Sample Work Alpha",
        actors=["Actor One"],
        studio="Studio Example",
        release_date="2026-01-15",
        parent_hint="Series Example",
    )
    candidate = CandidateMetadata(
        source_id="XC-001",
        title="Sample Work Alpha",
        original_title="Original Sample Alpha",
        identifiers=["ABC-123"],
        actors=["Actor One"],
        studio="Studio Example",
        series="Series Example",
        release_date="2026-01-15",
        complete=True,
        asset_ready=True,
    )

    score = score_candidate(match_input, candidate)

    assert score.total == 100
    assert score.breakdown["identifier"] > 0
    assert score.breakdown["title"] > 0
    assert score.breakdown["actors"] > 0
    assert score.breakdown["asset_readiness"] > 0
