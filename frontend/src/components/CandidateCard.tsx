import type { ManualCandidateCard as ManualCandidate } from "../api/types";
import { useImageSafetyMode } from "./ImageSafetyMode";

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
  const { imageSafetyModeEnabled } = useImageSafetyMode();
  const safetyLabel = imageSafetyModeEnabled
    ? `${candidate.title} 候选图片，安全模式已模糊，悬停、聚焦或轻点可临时查看`
    : `${candidate.title} 候选图片`;

  return (
    <article className={`candidate-card${selected ? " is-selected" : ""}`}>
      <div className="candidate-image">
        {candidate.image_url ? (
          <img
            alt={`${candidate.title} 候选图片`}
            aria-label={safetyLabel}
            className={`safety-image${imageSafetyModeEnabled ? " is-blurred" : ""}`}
            data-image-safety={imageSafetyModeEnabled ? "blurred" : "visible"}
            src={candidate.image_url}
            tabIndex={imageSafetyModeEnabled ? 0 : undefined}
            title={
              imageSafetyModeEnabled
                ? "安全模式已开启，悬停、聚焦或轻点图片可临时查看。"
                : "安全模式已关闭。"
            }
          />
        ) : (
          <span aria-label={`${candidate.title} 缺少图片`} role="img">
            无图片
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
            <dt>演员</dt>
            <dd>{candidate.actors.join(", ") || "未知"}</dd>
          </div>
          <div>
            <dt>制作方</dt>
            <dd>{candidate.studio || "未知"}</dd>
          </div>
          <div>
            <dt>系列</dt>
            <dd>{candidate.series || "无"}</dd>
          </div>
          <div>
            <dt>日期</dt>
            <dd>{candidate.release_date || "未知"}</dd>
          </div>
          <div>
            <dt>URL</dt>
            <dd>
              <a href={candidate.url}>{candidate.url}</a>
            </dd>
          </div>
        </dl>
        <div className="breakdown" aria-label="评分明细">
          {breakdown.length ? (
            breakdown.map(([key, value]) => (
              <span key={key}>
                {key}: {value}
              </span>
            ))
          ) : (
            <span>无明细</span>
          )}
        </div>
        <button type="button" onClick={() => onSelect(candidate)}>
          {selected ? "已选择" : "选择候选项"}
        </button>
      </div>
    </article>
  );
}
