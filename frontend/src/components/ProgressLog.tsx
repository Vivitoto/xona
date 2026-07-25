import { useEffect, useRef } from "react";

import type { JobEventRead } from "../api/types";
import { redactText } from "../utils/redaction";

export type ProgressLogTone =
  | "neutral"
  | "active"
  | "success"
  | "warning"
  | "danger";

export interface ProgressLogLine {
  id: string;
  label: string;
  tone?: ProgressLogTone;
}

export function ProgressLog({
  ariaLabel = "进度日志",
  emptyLabel = "暂无进度。",
  lines,
}: {
  ariaLabel?: string;
  emptyLabel?: string;
  lines: ProgressLogLine[];
}) {
  const visibleLines = lines.slice(-12);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const element = logRef.current;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }, [visibleLines.length]);

  return (
    <div aria-label={ariaLabel} className="progress-log" ref={logRef} role="log">
      {visibleLines.length ? (
        <ol>
          {visibleLines.map((line) => (
            <li
              className={`progress-log-line progress-log-line-${line.tone ?? "neutral"}`}
              key={line.id}
            >
              <span aria-hidden="true" />
              <p>{line.label}</p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">{emptyLabel}</p>
      )}
    </div>
  );
}

export function jobEventsToProgressLines(
  events: JobEventRead[],
  currentState?: string | null,
): ProgressLogLine[] {
  const sorted = [...events].sort((left, right) => left.id - right.id);
  const lines = sorted.map((event) => ({
    id: `event-${event.id}`,
    label: eventLabel(event),
    tone: toneForState(event.to_state),
  }));

  if (!lines.length && currentState) {
    return [
      {
        id: `state-${currentState}`,
        label: stateLabel(currentState),
        tone: toneForState(currentState),
      },
    ];
  }

  return lines;
}

export function stateLabel(state: string): string {
  return stateLabels[state] ?? "任务状态更新";
}

export function codeLabel(code: string): string {
  const normalized = code.split(":", 1)[0] ?? code;
  return codeLabels[code] ?? codeLabels[normalized] ?? "未分类问题";
}

export function toneForState(state: string): ProgressLogTone {
  if (["completed"].includes(state)) {
    return "success";
  }
  if (["failed", "cancelled", "local_complete_emby_failed"].includes(state)) {
    return "danger";
  }
  if (["review_required", "rolled_back"].includes(state)) {
    return "warning";
  }
  if (
    [
      "searching",
      "scraping",
      "materializing_assets",
      "planning",
      "ready",
      "executing",
      "notifying_emby",
    ].includes(state)
  ) {
    return "active";
  }
  return "neutral";
}

function eventLabel(event: JobEventRead): string {
  const details = compactPayloadDetail(event.payload);
  return details
    ? `${stateLabel(event.to_state)}：${details}`
    : stateLabel(event.to_state);
}

function compactPayloadDetail(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  const reason = stringValue(payload.reason);
  const errorCode = stringValue(payload.error_code);
  const planId = stringValue(payload.plan_id);
  const retryScope = stringValue(payload.retry_scope);
  const attempts = numberValue(payload.attempts);
  const candidateId = numberValue(payload.candidate_id);

  if (reason) {
    parts.push(`原因：${codeLabel(redactText(reason))}`);
  }
  if (errorCode) {
    parts.push(`错误：${codeLabel(redactText(errorCode))}`);
  }
  if (planId) {
    parts.push(`计划：${redactText(planId)}`);
  }
  if (retryScope) {
    parts.push(`重试：${codeLabel(redactText(retryScope))}`);
  }
  if (typeof attempts === "number") {
    parts.push(`第 ${attempts} 次尝试`);
  }
  if (typeof candidateId === "number") {
    parts.push(`候选 ${candidateId}`);
  }

  return parts.slice(0, 2).join("，");
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

const stateLabels: Record<string, string> = {
  created: "已创建任务",
  scanned: "扫描完成",
  discovered: "扫描到新文件",
  waiting_stable: "等待文件稳定",
  searching: "搜索候选",
  review_required: "等待人工复核",
  matched: "匹配候选完成",
  scraping: "获取详情",
  materializing_assets: "缓存素材",
  planning: "规划整理",
  previewed: "安全计划完成",
  ready: "准备执行",
  executing: "执行整理",
  notifying_emby: "通知 Emby",
  completed: "整理完成",
  local_complete_emby_failed: "本地整理完成，Emby 通知失败",
  failed: "整理失败",
  cancelled: "已取消",
  rolled_back: "已回滚",
};

const codeLabels: Record<string, string> = {
  cache_integrity_failed: "缓存校验失败",
  confidence_below_threshold: "置信度低于阈值",
  content_type_not_allowed: "资源类型不符",
  destination_collision: "目标文件已存在",
  download_too_large: "资源文件过大",
  empty_download: "下载内容为空",
  file_conflict: "文件冲突",
  incomplete_metadata: "元数据不完整",
  insufficient_lead: "候选优势不足",
  local: "本地整理",
  missing_source_url: "缺少资源地址",
  missing_strict_assets: "必需资源缺失",
  network_timeout: "网络超时",
  no_candidates: "未找到候选",
  outside_storage_root: "超出媒体目录",
  plan_approval_required: "需要确认计划",
  plan_not_executable: "计划不可执行",
  plan_version_mismatch: "计划版本不一致",
  search_adapter_unconfigured: "搜索服务未配置",
  scraper_unconfigured: "刮削服务未配置",
  source_integrity_mismatch: "源文件校验失败",
  strict_asset_materialization_failed: "必需资源处理失败",
  strict_assets_missing: "必需资源缺失",
  symlink_ancestor: "路径存在符号链接风险",
  target_exists: "目标文件已存在",
  target_integrity_mismatch: "目标文件校验失败",
  tie: "候选结果并列",
  unresolved_multipart: "多段视频需确认",
  unsafe_path: "路径不安全",
};
