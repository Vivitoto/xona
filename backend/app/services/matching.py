from __future__ import annotations

import re
from difflib import SequenceMatcher

from backend.app.schemas.matching import (
    CandidateMetadata,
    ExecutionSafety,
    MatchDecision,
    MatchInput,
    ScoreResult,
)

try:  # pragma: no cover - exercised only when optional dependency is installed.
    from rapidfuzz import fuzz
except ModuleNotFoundError:  # pragma: no cover - local fallback is covered instead.
    fuzz = None


DEFAULT_AUTO_THRESHOLD = 92
DEFAULT_REQUIRED_LEAD = 10


def score_candidate(match_input: MatchInput, candidate: CandidateMetadata) -> ScoreResult:
    breakdown = {
        "identifier": _identifier_score(match_input, candidate),
        "title": round(_title_ratio(match_input, candidate) * 45),
        "token_coverage": round(
            _token_coverage(match_input.title or match_input.search_text, candidate.title)
            * 10
        ),
        "studio": 4 if _same(match_input.studio, candidate.studio) else 0,
        "series_parent": 3 if _same(match_input.parent_hint, candidate.series) else 0,
        "actors": round(_actor_overlap(match_input.actors, candidate.actors) * 4),
        "date": 2 if _same(match_input.release_date, candidate.release_date) else 0,
        "asset_readiness": 7 if candidate.asset_ready else 0,
    }
    return ScoreResult(
        candidate=candidate,
        total=max(0, min(100, sum(breakdown.values()))),
        breakdown=breakdown,
    )


def evaluate_candidates(
    match_input: MatchInput,
    candidates: list[CandidateMetadata],
    *,
    auto_threshold: int = DEFAULT_AUTO_THRESHOLD,
    required_lead: int = DEFAULT_REQUIRED_LEAD,
) -> MatchDecision:
    if not candidates:
        return MatchDecision(action="review_required", reasons=["no_candidates"])

    scores = _rank(match_input, candidates)
    top = scores[0]
    reasons: list[str] = []
    if len(scores) > 1:
        lead = top.total - scores[1].total
        if lead == 0:
            reasons.append("tie")
        elif lead < required_lead:
            reasons.append("insufficient_lead")
    if top.total < auto_threshold:
        reasons.append("threshold_not_met")

    if reasons:
        return MatchDecision(
            action="review_required",
            reasons=_dedupe(reasons),
            selected=top.candidate,
            score=top,
        )
    return MatchDecision(action="auto_approved", selected=top.candidate, score=top)


def can_auto_execute(
    match_input: MatchInput,
    candidates: list[CandidateMetadata],
    safety: ExecutionSafety,
    *,
    auto_threshold: int = DEFAULT_AUTO_THRESHOLD,
    required_lead: int = DEFAULT_REQUIRED_LEAD,
) -> MatchDecision:
    decision = evaluate_candidates(
        match_input,
        candidates,
        auto_threshold=auto_threshold,
        required_lead=required_lead,
    )
    if decision.selected is None:
        return decision

    reasons = list(decision.reasons)
    reasons.extend(_safety_reasons(safety))
    reasons.extend(_candidate_safety_reasons(decision.selected))
    if decision.score is not None and decision.score.total < auto_threshold:
        reasons.append("threshold_not_met")

    if reasons:
        return MatchDecision(
            action="review_required",
            reasons=_dedupe(reasons),
            selected=decision.selected,
            score=decision.score,
        )
    return MatchDecision(
        action="auto_approved",
        selected=decision.selected,
        score=decision.score,
    )


def manual_selection_gate(
    candidate: CandidateMetadata,
    safety: ExecutionSafety,
) -> MatchDecision:
    reasons = [reason for reason in _safety_reasons(safety)]
    reasons.extend(_candidate_safety_reasons(candidate))
    if reasons:
        return MatchDecision(
            action="review_required",
            reasons=_dedupe(reasons),
            selected=candidate,
        )
    return MatchDecision(action="manual_approved", selected=candidate)


def _rank(match_input: MatchInput, candidates: list[CandidateMetadata]) -> list[ScoreResult]:
    return sorted(
        (score_candidate(match_input, candidate) for candidate in candidates),
        key=lambda score: (score.total, score.candidate.source_id),
        reverse=True,
    )


def _identifier_score(match_input: MatchInput, candidate: CandidateMetadata) -> int:
    if not match_input.identifier:
        return 0
    identifiers = {_normalize_identifier(value) for value in candidate.identifiers}
    return 30 if _normalize_identifier(match_input.identifier) in identifiers else 0


def _title_ratio(match_input: MatchInput, candidate: CandidateMetadata) -> float:
    needle = match_input.title or match_input.search_text
    titles = [candidate.title, candidate.original_title, *candidate.aliases]
    return max((_similarity(needle, title) for title in titles if title), default=0.0)


def _similarity(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if fuzz is not None:
        return fuzz.token_set_ratio(left_norm, right_norm) / 100
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _token_coverage(left: str, right: str) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def _actor_overlap(left: list[str], right: list[str]) -> float:
    if not left:
        return 0.0
    right_normalized = {_normalize_text(actor) for actor in right}
    matches = sum(1 for actor in left if _normalize_text(actor) in right_normalized)
    return matches / len(left)


def _candidate_safety_reasons(candidate: CandidateMetadata) -> list[str]:
    reasons: list[str] = []
    if not candidate.unique_detail:
        reasons.append("non_unique_detail")
    if not candidate.complete:
        reasons.append("incomplete_metadata")
    if not candidate.asset_ready:
        reasons.append("missing_strict_assets")
    return reasons


def _safety_reasons(safety: ExecutionSafety) -> list[str]:
    reasons: list[str] = []
    if safety.unsafe_path:
        reasons.append("unsafe_path")
    if safety.file_conflict:
        reasons.append("file_conflict")
    if safety.unresolved_multipart:
        reasons.append("unresolved_multipart")
    if safety.strict_assets_missing:
        reasons.append("strict_assets_missing")
    return reasons


def _same(left: str | None, right: str | None) -> bool:
    return bool(left and right and _normalize_text(left) == _normalize_text(right))


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _normalize_text(value: str) -> str:
    return " ".join(_tokens(value))


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _dedupe(reasons: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        unique.append(reason)
    return unique
