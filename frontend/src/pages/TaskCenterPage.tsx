import { useEffect, useMemo, useState } from "react";
import { FileSearch, ListChecks } from "lucide-react";

import { ApiError, apiFetch } from "../api/client";
import type {
  OrganizeRecordRead,
  OrganizeRecordsResponse,
  OrganizeRollbackResponse,
} from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { FormField, Section } from "../components/FormField";
import { LoadingSkeleton } from "../components/LoadingSkeleton";
import { OperationPlanView } from "../components/OperationPlanView";
import { codeLabel } from "../components/ProgressLog";

const RERUN_VIDEO_PATH_KEY = "xona-rerun-video-path";

type StatusFilter = "all" | "completed" | "failed" | "rollbackable" | "rolled_back" | "modified";
type ModeFilter = "all" | "move" | "copy" | "in_place" | "hardlink" | "symlink";
type MetadataFilter = "all" | "nfo" | "cover" | "missing_nfo" | "missing_cover" | "actors";

type LimitOption = 50 | 100 | 500;

const statusFilters: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "全部状态" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
  { value: "rollbackable", label: "可回滚" },
  { value: "rolled_back", label: "已回滚" },
  { value: "modified", label: "有外部变更" },
];

const modeFilters: Array<{ value: ModeFilter; label: string }> = [
  { value: "all", label: "全部方式" },
  { value: "move", label: "移动" },
  { value: "copy", label: "复制" },
  { value: "in_place", label: "原地整理" },
  { value: "hardlink", label: "硬链接" },
  { value: "symlink", label: "软链接" },
];

const metadataFilters: Array<{ value: MetadataFilter; label: string }> = [
  { value: "all", label: "全部元数据" },
  { value: "nfo", label: "已生成 NFO" },
  { value: "cover", label: "已生成封面" },
  { value: "missing_nfo", label: "缺少 NFO" },
  { value: "missing_cover", label: "缺少封面" },
  { value: "actors", label: "已生成演员" },
];

export function TaskCenterPage({ onRerun }: { onRerun?: (path: string) => void } = {}) {
  const [records, setRecords] = useState<OrganizeRecordRead[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<OrganizeRecordRead | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [modeFilter, setModeFilter] = useState<ModeFilter>("all");
  const [metadataFilter, setMetadataFilter] = useState<MetadataFilter>("all");
  const [limit, setLimit] = useState<LimitOption>(50);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (search.trim()) {
      params.set("q", search.trim());
    }
    if (statusFilter !== "all") {
      params.set("status", statusFilter);
    }
    if (modeFilter !== "all") {
      params.set("mode", modeFilter);
    }
    if (metadataFilter !== "all") {
      params.set("metadata", metadataFilter);
    }
    return params.toString();
  }, [limit, metadataFilter, modeFilter, search, statusFilter]);

  async function loadRecords() {
    setError("");
    setLoading(true);
    try {
      const response = await apiFetch<OrganizeRecordsResponse>(`/api/organize-records?${query}`);
      const nextRecords = Array.isArray(response.records) ? response.records : [];
      setRecords(nextRecords);
      setSelectedRecord((current) => {
        if (current && nextRecords.some((record) => record.record_id === current.record_id)) {
          return current;
        }
        return nextRecords[0] ?? null;
      });
      setStatus("整理记录已刷新");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载整理记录");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadRecords();
  }, [query]);

  async function selectRecord(record: OrganizeRecordRead) {
    setSelectedRecord(record);
    setDetailLoading(true);
    setError("");
    try {
      const detail = await apiFetch<OrganizeRecordRead>(`/api/organize-records/${record.record_id}`);
      setSelectedRecord(detail);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载整理记录详情");
    } finally {
      setDetailLoading(false);
    }
  }

  async function rollback(record: OrganizeRecordRead) {
    setError("");
    setStatus("");
    try {
      const response = await apiFetch<OrganizeRollbackResponse>(
        `/api/organize-records/${record.record_id}/rollback`,
        { method: "POST" },
      );
      setStatus(`回滚完成；已反转 ${response.reversed_steps.length} 个步骤`);
      await loadRecords();
    } catch (exc) {
      if (exc instanceof ApiError && isRollbackRefusal(exc.detail)) {
        setError(`回滚被拒绝：${exc.detail.detail.reason}`);
      } else {
        setError(exc instanceof Error ? exc.message : "回滚失败");
      }
    }
  }

  function rerun(record: OrganizeRecordRead) {
    if (!record.rerun_path) {
      setError("没有可重新整理的视频路径，请重新扫描目录。");
      return;
    }
    window.localStorage.setItem(RERUN_VIDEO_PATH_KEY, record.rerun_path);
    setStatus(`已准备重新整理：${record.rerun_path}`);
    onRerun?.(record.rerun_path);
  }

  const completedCount = records.filter((record) => record.status === "completed").length;
  const rollbackableCount = records.filter((record) => record.can_rollback).length;
  const modifiedCount = records.filter((record) => record.verification_status === "externally_modified").length;

  return (
    <div className="page-stack organize-records-page">
      <div className="metric-grid">
        <div className="metric metric-primary">
          <span>整理记录</span>
          <strong>{loading ? "-" : records.length}</strong>
          <small>最近 {limit} 条</small>
        </div>
        <div className="metric metric-success">
          <span>已完成</span>
          <strong>{loading ? "-" : completedCount}</strong>
          <small>完成整理</small>
        </div>
        <div className="metric metric-warning">
          <span>可回滚 / 外部变更</span>
          <strong>{loading ? "-" : `${rollbackableCount}/${modifiedCount}`}</strong>
          <small>安全操作提示</small>
        </div>
      </div>

      <Section title="整理记录">
        <div className="section-toolbar organize-record-filters">
          <FormField label="搜索">
            <input
              placeholder="名称、路径、#序号、plan ID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </FormField>
          <FormField label="状态">
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
              {statusFilters.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </FormField>
          <FormField label="整理方式">
            <select value={modeFilter} onChange={(event) => setModeFilter(event.target.value as ModeFilter)}>
              {modeFilters.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </FormField>
          <FormField label="元数据">
            <select value={metadataFilter} onChange={(event) => setMetadataFilter(event.target.value as MetadataFilter)}>
              {metadataFilters.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </FormField>
          <FormField label="范围">
            <select value={limit} onChange={(event) => setLimit(Number(event.target.value) as LimitOption)}>
              <option value={50}>最近 50</option>
              <option value={100}>最近 100</option>
              <option value={500}>最近 500</option>
            </select>
          </FormField>
          <button disabled={loading} type="button" onClick={loadRecords}>刷新</button>
        </div>

        {loading ? (
          <LoadingSkeleton rows={5} title="正在加载整理记录" variant="table" />
        ) : records.length ? (
          <div className="table-wrap">
            <table>
              <caption>整理记录</caption>
              <thead>
                <tr>
                  <th>序号</th>
                  <th>名称</th>
                  <th>状态</th>
                  <th>方式</th>
                  <th>元数据</th>
                  <th>原始路径</th>
                  <th>当前路径</th>
                  <th>时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr className={record.record_id === selectedRecord?.record_id ? "is-selected-row" : undefined} key={record.record_id}>
                    <td><button className="link-button" type="button" onClick={() => selectRecord(record)}>{record.display_index}</button></td>
                    <td>
                      <div className="record-title-cell">
                        <strong>{record.name}</strong>
                        {record.short_plan_id ? <small>{record.short_plan_id}</small> : null}
                      </div>
                    </td>
                    <td><span className={`status-pill ${statusTone(record.status, record.verification_status)}`}>{recordStatusLabel(record)}</span></td>
                    <td>{modeLabel(record.mode)}</td>
                    <td><MetadataFlags flags={record.metadata} /></td>
                    <td><PathCell path={record.source_path} /></td>
                    <td><PathCell path={record.target_path} /></td>
                    <td>{formatDate(record.created_at)}</td>
                    <td>
                      <div className="button-row">
                        <button className="secondary" type="button" onClick={() => selectRecord(record)}>查看</button>
                        <button disabled={!record.can_rerun} type="button" onClick={() => rerun(record)}>重新整理</button>
                        <button disabled={!record.can_rollback} type="button" onClick={() => rollback(record)}>回滚</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            actions={[{ label: "刷新记录", onClick: loadRecords }]}
            description="整理完成后会显示名称、路径、元数据生成情况和回滚入口。"
            icon={ListChecks}
            title="暂无整理记录"
          />
        )}
      </Section>

      <Section title="记录详情">
        {selectedRecord ? (
          <>
            <dl className="metadata-list compact history-summary">
              <div><dt>序号</dt><dd>{selectedRecord.display_index}</dd></div>
              <div><dt>名称</dt><dd>{selectedRecord.name}</dd></div>
              <div><dt>完整 plan ID</dt><dd>{selectedRecord.plan_id ? <code>{selectedRecord.plan_id}</code> : "无"}</dd></div>
              <div><dt>源路径</dt><dd><PathCell path={selectedRecord.source_path} /></dd></div>
              <div><dt>当前路径</dt><dd><PathCell path={selectedRecord.target_path} /></dd></div>
              <div><dt>校验</dt><dd>{verificationLabel(selectedRecord.verification_status)}</dd></div>
              <div><dt>重新整理路径</dt><dd><PathCell path={selectedRecord.rerun_path} /></dd></div>
            </dl>
            <div className="button-row">
              <button disabled={!selectedRecord.can_rerun} type="button" onClick={() => rerun(selectedRecord)}>重新整理</button>
              <button disabled={!selectedRecord.can_rollback} type="button" onClick={() => rollback(selectedRecord)}>回滚</button>
            </div>
            {detailLoading ? <LoadingSkeleton rows={3} title="正在加载记录详情" /> : null}
            {selectedRecord.plan ? <OperationPlanView plan={selectedRecord.plan} /> : null}
          </>
        ) : (
          <EmptyState description="从整理记录列表选择一条记录。" icon={FileSearch} title="还没有选择记录" />
        )}
      </Section>

      {status ? <p className="status floating-status">{status}</p> : null}
      {error ? <p className="status error floating-status" role="alert">{error}</p> : null}
    </div>
  );
}

function MetadataFlags({ flags }: { flags: OrganizeRecordRead["metadata"] }) {
  const items = [
    ["NFO", flags.nfo],
    ["Poster", flags.poster],
    ["Fanart", flags.fanart],
    ["Thumb", flags.thumb],
    ["Backdrop", flags.backdrop],
    ["演员", flags.actors],
  ] as const;
  return (
    <div className="metadata-flags">
      {items.map(([label, enabled]) => (
        <span className={`status-pill ${enabled ? "status-pill-success" : "status-pill-neutral"}`} key={label}>{label}</span>
      ))}
    </div>
  );
}

function PathCell({ path }: { path: string | null }) {
  if (!path) {
    return <span className="muted">无</span>;
  }
  return <code className="path-cell" title={path}>{path}</code>;
}

function recordStatusLabel(record: OrganizeRecordRead): string {
  if (record.status === "externally_modified" || record.verification_status === "externally_modified") {
    return "目标被修改";
  }
  return codeLabel(record.status);
}

function verificationLabel(status: string): string {
  if (status === "verified") return "已校验";
  if (status === "externally_modified") return "目标被外部修改";
  if (status === "partial") return "部分完成";
  if (status === "pending") return "目标缺失";
  return status;
}

function modeLabel(mode: string | null): string {
  if (mode === "move") return "移动";
  if (mode === "copy") return "复制";
  if (mode === "in_place") return "原地整理";
  if (mode === "hardlink") return "硬链接";
  if (mode === "symlink") return "软链接";
  if (mode === "preview") return "预览";
  return mode ?? "未知";
}

function statusTone(status: string, verification: string): string {
  if (status === "failed" || status === "rollback_failed") return "status-pill-danger";
  if (status === "rolled_back") return "status-pill-neutral";
  if (verification === "externally_modified" || verification === "partial" || verification === "pending") return "status-pill-warning";
  if (status === "completed") return "status-pill-success";
  return "status-pill-neutral";
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function isRollbackRefusal(detail: unknown): detail is { detail: { error: string; reason: string } } {
  if (!detail || typeof detail !== "object" || !("detail" in detail)) {
    return false;
  }
  const body = detail.detail;
  if (!body || typeof body !== "object" || !("reason" in body)) {
    return false;
  }
  return typeof body.reason === "string";
}
