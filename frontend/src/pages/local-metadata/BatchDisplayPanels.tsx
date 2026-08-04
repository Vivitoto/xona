import type { OrganizationMode } from "../../api/types";
import type {
  BatchDraftState,
  BatchDraftStatus,
  BatchOutputFilter,
  BatchOutputItem,
  BatchOutputLog,
  BatchOutputLogTone,
  BatchOutputState,
  BusyAction,
  CoverEditorSettings,
} from "./batchTypes";

const outputFilters: Array<{ value: BatchOutputFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "attention", label: "需处理" },
  { value: "ready", label: "可执行" },
  { value: "running", label: "处理中" },
  { value: "done", label: "已完成" },
];

export function BatchExecutionSummary({
  batchOutputItems,
  isDestructiveMode,
  selectedCount,
}: {
  batchOutputItems: BatchOutputItem[];
  isDestructiveMode: boolean;
  selectedCount: number;
}) {
  const stats = batchOutputStats(batchOutputItems);
  const failedCount = stats.failed + stats.executeFailed;
  return (
    <div className="batch-execution-summary" aria-label="批量执行摘要">
      <span>已选择 {selectedCount}</span>
      <span>可执行 {stats.executable}</span>
      <span>失败 {failedCount}</span>
      {isDestructiveMode ? (
        <strong>当前模式会改变原始文件位置或内容，执行前确认目标路径。</strong>
      ) : null}
    </div>
  );
}

export function BatchOutputSummary({
  batchOutputItems,
  busy,
}: {
  batchOutputItems: BatchOutputItem[];
  busy: BusyAction;
}) {
  const stats = batchOutputStats(batchOutputItems);
  return (
    <div className="batch-summary-panel">
      <p
        aria-label="批量生成摘要"
        aria-live="polite"
        className="status"
        role="status"
      >
        {batchOutputSummaryText({ batchOutputItems, busy })}
      </p>
      {batchOutputItems.length ? (
        <dl className="batch-summary-metrics" aria-label="批量生成统计">
          <div>
            <dt>总数</dt>
            <dd>{stats.total}</dd>
          </div>
          <div>
            <dt>等待</dt>
            <dd>{stats.pending}</dd>
          </div>
          <div>
            <dt>处理中</dt>
            <dd>{stats.running}</dd>
          </div>
          <div>
            <dt>预览可用</dt>
            <dd>{stats.succeeded}</dd>
          </div>
          <div>
            <dt>可执行</dt>
            <dd>{stats.executable}</dd>
          </div>
          <div>
            <dt>失败</dt>
            <dd>{stats.failed + stats.executeFailed}</dd>
          </div>
          <div>
            <dt>已执行</dt>
            <dd>{stats.executed}</dd>
          </div>
        </dl>
      ) : null}
    </div>
  );
}

export function BatchOutputFilterControls({
  filter,
  items,
  onChange,
}: {
  filter: BatchOutputFilter;
  items: BatchOutputItem[];
  onChange: (filter: BatchOutputFilter) => void;
}) {
  if (!items.length) {
    return null;
  }
  const statsByFilter = outputFilters.map((item) => ({
    ...item,
    count: filterBatchOutputItems(items, item.value).length,
  }));
  return (
    <div className="batch-output-filters" aria-label="批量预览筛选" role="group">
      {statsByFilter.map((item) => (
        <button
          aria-pressed={filter === item.value}
          className="secondary button-compact"
          key={item.value}
          type="button"
          onClick={() => onChange(item.value)}
        >
          {item.label}
          <span>{item.count}</span>
        </button>
      ))}
    </div>
  );
}

export function CompactBatchDraftTable({
  batchStatuses,
  visibleLimit,
}: {
  batchStatuses: BatchDraftStatus[];
  visibleLimit: number;
}) {
  const visibleItems = batchStatuses.slice(0, visibleLimit);
  const hiddenCount = Math.max(batchStatuses.length - visibleItems.length, 0);

  return (
    <div className="batch-compact-panel">
      <div className="row row-between batch-table-heading">
        <div>
          <h3>已生成的批量元数据</h3>
          <p className="muted">
            共 {batchStatuses.length} 个；当前只显示前 {visibleItems.length} 个，提交预览任务时仍包含全部已生成元数据。
          </p>
        </div>
        <span className="status-pill status-pill-neutral">待提交</span>
      </div>
      {hiddenCount ? (
        <p className="status batch-limit-note">
          为避免页面过长，已折叠 {hiddenCount} 个成功元数据条目。
        </p>
      ) : null}
      <div className="table-wrap batch-compact-table">
        <table>
          <caption>已生成的批量元数据</caption>
          <thead>
            <tr>
              <th>文件</th>
              <th>标题</th>
              <th>整理文件名</th>
              <th>封面</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.map((item) => (
              <tr key={item.path}>
                <td>
                  <strong title={item.filename}>{item.filename}</strong>
                  <small className="path-cell" title={item.path}>{item.path}</small>
                </td>
                <td>{item.draft.title}</td>
                <td className="path-cell" title={item.draft.organize_filename ?? undefined}>
                  {item.draft.organize_filename || "使用文件名模板"}
                </td>
                <td>{coverSettingsSummary(item.coverSettings)}</td>
                <td>
                  <span className={`status-pill ${batchStatusClass(item.status)}`}>
                    {batchStatusLabel(item.status)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function CompactBatchOutputTable({
  batchOutputItems,
  filter,
  visibleLimit,
}: {
  batchOutputItems: BatchOutputItem[];
  filter: BatchOutputFilter;
  visibleLimit: number;
}) {
  const filteredItems = filterBatchOutputItems(batchOutputItems, filter);
  const visibleItems = prioritizedBatchOutputItems(filteredItems).slice(
    0,
    visibleLimit,
  );
  const hiddenCount = Math.max(filteredItems.length - visibleItems.length, 0);

  return (
    <div
      aria-label="批量预览结果"
      className="batch-compact-panel batch-output-results"
      role="region"
    >
      <div className="row row-between batch-table-heading">
        <div>
          <h3>批量预览结果</h3>
          <p className="muted">
            优先显示失败、处理中和可执行条目；日志、封面和计划细节默认折叠。
          </p>
        </div>
        <span className="status-pill status-pill-neutral">
          显示 {visibleItems.length} / {filteredItems.length}
        </span>
      </div>
      {hiddenCount ? (
        <p className="status batch-limit-note">
          已隐藏 {hiddenCount} 个低优先级条目，避免 100+ 文件时页面过长；批量执行仍覆盖全部可执行计划。
        </p>
      ) : null}
      <div className="table-wrap batch-compact-table">
        <table>
          <caption>批量预览结果</caption>
          <thead>
            <tr>
              <th>文件</th>
              <th>标题 / 计划</th>
              <th>状态</th>
              <th>执行</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.length ? (
              visibleItems.map((item) => (
                <tr key={item.path}>
                  <td>
                    <strong title={item.filename}>{item.filename}</strong>
                    <small className="path-cell" title={item.path}>{item.path}</small>
                  </td>
                  <td>
                    <strong>{item.draft.title}</strong>
                    <small>
                      {item.planPreview
                        ? `计划 ${item.planPreview.plan_id}`
                        : item.draft.organize_filename || "等待计划"}
                    </small>
                  </td>
                  <td>
                    <span
                      className={`status-pill ${batchOutputStatusClass(item.status)}`}
                    >
                      {batchOutputStatusLabel(item.status)}
                    </span>
                    {item.error ? (
                      <p className="status error batch-output-error">
                        {shortBatchError(item.error)}
                      </p>
                    ) : null}
                  </td>
                  <td>{batchOutputExecutionLabel(item)}</td>
                  <td>
                    <BatchOutputDetails item={item} />
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5}>
                  <p className="muted">当前筛选没有批量预览条目。</p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function canExecuteBatchOutputItem(item: BatchOutputItem): boolean {
  return Boolean(
    item.planPreview &&
      item.planPreview.plan.mode !== "preview" &&
      !item.executeResult &&
      (item.status === "succeeded" || item.status === "execute_failed"),
  );
}

export function batchOutputStats(items: BatchOutputItem[]) {
  return {
    total: items.length,
    pending: items.filter((item) => item.status === "pending").length,
    running: items.filter(
      (item) => item.status === "running" || item.status === "executing",
    ).length,
    succeeded: items.filter(
      (item) =>
        item.status === "succeeded" ||
        item.status === "executing" ||
        item.status === "executed",
    ).length,
    executable: items.filter(canExecuteBatchOutputItem).length,
    failed: items.filter((item) => item.status === "failed").length,
    executed: items.filter((item) => item.status === "executed").length,
    executeFailed: items.filter((item) => item.status === "execute_failed").length,
  };
}

export function batchOutputStatusLabel(status: BatchOutputState): string {
  switch (status) {
    case "running":
      return "生成中";
    case "succeeded":
      return "已生成";
    case "failed":
      return "生成失败";
    case "executing":
      return "执行中";
    case "executed":
      return "已执行";
    case "execute_failed":
      return "执行失败";
    case "cancelled":
      return "已取消";
    case "pending":
    default:
      return "等待";
  }
}

function BatchOutputDetails({ item }: { item: BatchOutputItem }) {
  return (
    <details className="batch-output-disclosure">
      <summary>查看详情</summary>
      <div className="batch-output-details">
        <span>{item.planPreview ? "NFO 已生成" : "NFO 未生成"}</span>
        <span>
          {item.coverPreview ? `封面 ${item.coverPreview.poster.id}` : "封面未生成"}
        </span>
        <span>
          {item.planPreview ? `计划 ${item.planPreview.plan_id}` : "计划未生成"}
        </span>
        {item.planPreview ? (
          <span>目标 {item.planPreview.plan.target_directory}</span>
        ) : null}
        {item.coverPreview?.warnings.length ? (
          <span>{item.coverPreview.warnings.map(coverWarningLabel).join("；")}</span>
        ) : null}
      </div>
      <BatchOutputLogView logs={item.logs} />
    </details>
  );
}

function BatchOutputLogView({ logs }: { logs: BatchOutputLog[] }) {
  return (
    <div className="progress-log" aria-label="批量条目日志">
      {logs.length ? (
        <ol>
          {logs.map((entry, index) => (
            <li className={batchOutputLogClass(entry.tone)} key={index}>
              <span aria-hidden="true" />
              <p>{entry.message}</p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">等待处理。</p>
      )}
    </div>
  );
}

function batchOutputSummaryText({
  batchOutputItems,
  busy,
}: {
  batchOutputItems: BatchOutputItem[];
  busy: BusyAction;
}): string {
  if (!batchOutputItems.length) {
    return "批量预览摘要：等待生成 NFO、封面与整理预览。";
  }
  const stats = batchOutputStats(batchOutputItems);

  if (busy === "batch_generate" || busy === "batch_execute") {
    return `批量预览摘要：共 ${stats.total} 个，处理中 ${stats.running} 个，等待 ${stats.pending} 个，预览可用 ${stats.succeeded} 个，失败 ${stats.failed + stats.executeFailed} 个，可执行 ${stats.executable} 个。`;
  }
  return `批量预览摘要：共 ${stats.total} 个，预览可用 ${stats.succeeded} 个，失败 ${stats.failed} 个，可执行 ${stats.executable} 个，已执行 ${stats.executed} 个，执行失败 ${stats.executeFailed} 个。`;
}

function filterBatchOutputItems(
  items: BatchOutputItem[],
  filter: BatchOutputFilter,
): BatchOutputItem[] {
  switch (filter) {
    case "attention":
      return items.filter((item) =>
        ["failed", "execute_failed", "cancelled"].includes(item.status),
      );
    case "ready":
      return items.filter(canExecuteBatchOutputItem);
    case "running":
      return items.filter((item) =>
        ["pending", "running", "executing"].includes(item.status),
      );
    case "done":
      return items.filter((item) =>
        item.status === "executed" ||
        (item.status === "succeeded" && item.planPreview?.plan.mode === "preview"),
      );
    case "all":
    default:
      return items;
  }
}

function prioritizedBatchOutputItems(items: BatchOutputItem[]): BatchOutputItem[] {
  const priority: Record<BatchOutputState, number> = {
    failed: 0,
    execute_failed: 1,
    running: 2,
    executing: 3,
    succeeded: 4,
    pending: 5,
    cancelled: 6,
    executed: 7,
  };
  return [...items].sort((left, right) => {
    const leftPriority = priority[left.status];
    const rightPriority = priority[right.status];
    if (leftPriority !== rightPriority) {
      return leftPriority - rightPriority;
    }
    return left.filename.localeCompare(right.filename, "zh-Hans-CN");
  });
}

function batchOutputExecutionLabel(item: BatchOutputItem): string {
  if (item.executeResult) {
    return item.executeResult.state === "completed"
      ? "整理完成"
      : `状态 ${item.executeResult.state}`;
  }
  if (item.planPreview?.plan.mode === "preview") {
    return "仅预览";
  }
  if (canExecuteBatchOutputItem(item)) {
    return "可执行";
  }
  if (item.planPreview) {
    return "等待批量执行";
  }
  return "未生成计划";
}

function shortBatchError(message: string): string {
  return message.length > 96 ? `${message.slice(0, 96)}...` : message;
}

function batchStatusLabel(status: BatchDraftState): string {
  return status === "drafted" ? "已生成" : "已生成";
}

function batchStatusClass(status: BatchDraftState): string {
  return status === "drafted" ? "status-pill-success" : "status-pill-success";
}

function batchOutputStatusClass(status: BatchOutputState): string {
  switch (status) {
    case "succeeded":
    case "executed":
      return "status-pill-success";
    case "failed":
    case "execute_failed":
      return "status-pill-danger";
    case "running":
    case "executing":
      return "status-pill-neutral";
    case "pending":
    case "cancelled":
    default:
      return "status-pill-warning";
  }
}

function batchOutputLogClass(tone: BatchOutputLogTone): string {
  const suffix = tone === "neutral" ? "" : ` progress-log-line-${tone}`;
  return `progress-log-line${suffix}`;
}

function coverSettingsSummary(settings: CoverEditorSettings): string {
  const fallback = settings.allowSimilarFrameFallback
    ? `相似帧兜底 ${settings.similarFrameFallbackThreshold}`
    : "相似帧严格";
  return `${coverTemplateLabel(settings.template)} / ${posterFontLabel(
    settings.titleFontId,
  )} / ${settings.titleFontSize}px / ${settings.titleFillColor} -> ${
    settings.titleStrokeColor
  } / ${formatSignedNumber(
    settings.titleAngleDegrees,
  )} 度 / X ${formatSignedNumber(settings.titleOffsetX)} Y ${formatSignedNumber(
    settings.titleOffsetY,
  )} / ${fallback}`;
}

function coverWarningLabel(warning: string): string {
  if (warning === "similar_frames_fallback_used") {
    return "similar_frames_fallback_used：内容相近截图不足 9 张，已使用相似帧补足。";
  }
  return warning;
}

function coverTemplateLabel(template: string): string {
  switch (template) {
    case "simple_poster":
      return "Simple Poster";
    case "jav_classic_left_strip":
      return "JAV Classic";
    case "tangxin_vlog":
      return "TangXin Vlog";
    default:
      return template;
  }
}

function posterFontLabel(fontId: string): string {
  switch (fontId) {
    case "source_han_sans":
      return "思源黑体 / Source Han Sans";
    case "noto_sans_jp":
      return "Noto Sans JP";
    case "noto_sans_cjk_regular":
      return "Noto 黑体常规 / Noto Sans CJK";
    case "noto_serif_cjk":
      return "Noto 宋体 / Noto Serif CJK";
    case "noto_serif_cjk_bold":
      return "Noto 粗宋 / Noto Serif CJK Bold";
    case "dela_gothic_one":
      return "Dela Gothic One";
    case "bebas_neue":
      return "Bebas Neue";
    case "anton":
      return "Anton";
    case "smiley_sans":
      return "得意黑 / Smiley Sans";
    case "zcool_qingke_huangyou":
      return "站酷庆科黄油体";
    case "zcool_kuaile":
      return "站酷快乐体 / ZCOOL KuaiLe";
    case "lxgw_wenkai":
      return "霞鹜文楷 / LXGW WenKai";
    default:
      return fontId;
  }
}

function formatSignedNumber(value: number): string {
  const rounded = Number.isInteger(value) ? value : Number(value.toFixed(1));
  return rounded > 0 ? `+${rounded}` : String(rounded);
}

export function isDestructiveOrganizationMode(mode: OrganizationMode | string): boolean {
  return mode === "move" || mode === "in_place";
}
