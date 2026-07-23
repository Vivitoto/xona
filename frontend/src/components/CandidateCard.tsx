import type { ManualCandidateCard as ManualCandidate } from "../api/types";

export function CandidateCard({
  candidate,
  selected,
  onSelect,
}: {
  candidate: ManualCandidate;
  selected: boolean;
  onSelect: (candidate: ManualCandidate) => void;
}) {
  const breakdown = Object.entries(candidate.score_breakdown);

  return (
    <article className={`candidate-card${selected ? " is-selected" : ""}`}>
      <div className="candidate-image">
        {candidate.image_url ? (
          <img alt="" src={candidate.image_url} />
        ) : (
          <span aria-label={`${candidate.title} image missing`} role="img">
            No image
          </span>
        )}
      </div>
      <div className="candidate-body">
        <div className="row row-between">
          <h3>{candidate.title}</h3>
          <strong className="score">{candidate.confidence_score}</strong>
        </div>
        <dl className="metadata-list compact">
          <div>
            <dt>Actors</dt>
            <dd>{candidate.actors.join(", ") || "Unknown"}</dd>
          </div>
          <div>
            <dt>Studio</dt>
            <dd>{candidate.studio || "Unknown"}</dd>
          </div>
          <div>
            <dt>Series</dt>
            <dd>{candidate.series || "None"}</dd>
          </div>
          <div>
            <dt>Date</dt>
            <dd>{candidate.release_date || "Unknown"}</dd>
          </div>
          <div>
            <dt>URL</dt>
            <dd>
              <a href={candidate.url}>{candidate.url}</a>
            </dd>
          </div>
        </dl>
        <div className="breakdown" aria-label="Score breakdown">
          {breakdown.length ? (
            breakdown.map(([key, value]) => (
              <span key={key}>
                {key}: {value}
              </span>
            ))
          ) : (
            <span>No breakdown</span>
          )}
        </div>
        <button type="button" onClick={() => onSelect(candidate)}>
          {selected ? "Selected" : "Select candidate"}
        </button>
      </div>
    </article>
  );
}
