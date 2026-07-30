import { useEffect, useState } from "react";
import { FileSearch, History } from "lucide-react";

import { ApiError, apiFetch } from "../api/client";
import type {
  HistoryPlanRead,
  HistoryPlansResponse,
  OperationPlan,
  RollbackResponse,
} from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { Section } from "../components/FormField";
import { LoadingSkeleton } from "../components/LoadingSkeleton";
import { OperationPlanView } from "../components/OperationPlanView";

export function HistoryRollbackPage() {
  const [plans, setPlans] = useState<HistoryPlanRead[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadHistory() {
    setError("");
    setLoading(true);
    try {
      const response = await apiFetch<HistoryPlansResponse>("/api/history/plans?limit=50");
      const nextPlans = Array.isArray(response.plans) ? response.plans : [];
      setPlans(nextPlans);
      setSelectedPlanId((current) => current ?? nextPlans[0]?.plan_id ?? null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载历史记录");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadHistory();
  }, []);

  async function rollback(planId: string) {
    setStatus("");
    setError("");
    try {
      const response = await apiFetch<RollbackResponse>(
        `/api/plans/${planId}/rollback`,
        { method: "POST" },
      );
      setStatus(
        `回滚 ${response.status}；已反转 ${response.reversed_steps.length} 个步骤`,
      );
      await loadHistory();
    } catch (exc) {
      if (exc instanceof ApiError && isRollbackRefusal(exc.detail)) {
        setError(`回滚被拒绝：${exc.detail.detail.reason}`);
      } else {
        setError(exc instanceof Error ? exc.message : "回滚失败");
      }
    }
  }

  const selectedPlan = plans.find((plan) => plan.plan_id === selectedPlanId) ?? null;
  const completedCount = plans.filter((plan) => plan.status === "completed").length;
  const modifiedCount = plans.filter((plan) =>
    plan.verification_status.includes("modified"),
  ).length;
  const targetCount = plans.reduce((sum, plan) => sum + plan.target_paths.length, 0);

  return (
    <div className="page-stack">
      <div className="metric-grid">
        <div className="metric metric-primary">
          <span>历史计划</span>
          <strong>{loading ? "-" : plans.length}</strong>
          <small>操作计划</small>
        </div>
        <div className="metric metric-success">
          <span>完成记录</span>
          <strong>{loading ? "-" : completedCount}</strong>
          <small>已完成</small>
        </div>
        <div className="metric metric-warning">
          <span>外部变更</span>
          <strong>{loading ? "-" : modifiedCount}</strong>
          <small>目标被修改</small>
        </div>
      </div>

      <Section title="操作历史">
        <div className="section-toolbar">
          <button disabled={loading} type="button" onClick={loadHistory}>
            刷新历史
          </button>
        </div>

        {loading ? (
          <LoadingSkeleton rows={4} title="正在加载历史记录" variant="table" />
        ) : plans.length ? (
          <div className="table-wrap">
            <table>
              <caption>操作历史</caption>
              <thead>
                <tr>
                  <th>计划</th>
                  <th>任务</th>
                  <th>模式</th>
                  <th>状态</th>
                  <th>校验</th>
                  <th>目标</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {plans.map((plan) => (
                  <tr
                    className={plan.plan_id === selectedPlanId ? "is-selected-row" : undefined}
                    key={plan.plan_id}
                  >
                    <td>
                      <button
                        className="link-button"
                        type="button"
                        onClick={() => setSelectedPlanId(plan.plan_id)}
                      >
                        {plan.plan_id}
                      </button>
                    </td>
                    <td>{plan.job_id ?? "手动"}</td>
                    <td>{plan.mode}</td>
                    <td>
                      <span className={`status-pill ${statusTone(plan.status)}`}>
                        {plan.status}
                      </span>
                    </td>
                    <td>
                      <span className={`status-pill ${verificationTone(plan.verification_status)}`}>
                        {plan.verification_status}
                      </span>
                    </td>
                    <td>
                      <TargetList paths={plan.target_paths} />
                    </td>
                    <td>
                      <div className="button-row">
                        <button
                          className="secondary"
                          type="button"
                          onClick={() => setSelectedPlanId(plan.plan_id)}
                        >
                          查看
                        </button>
                        <button type="button" onClick={() => rollback(plan.plan_id)}>
                          回滚
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            actions={[{ label: "刷新历史", onClick: loadHistory }]}
            description="操作计划会显示在这里。"
            icon={History}
            title="暂无操作历史"
          />
        )}
      </Section>

      <Section title="选中计划预览">
        {selectedPlan ? (
          <>
            <dl className="metadata-list compact history-summary">
              <div>
                <dt>计划</dt>
                <dd>
                  <code>{selectedPlan.plan_id}</code>
                </dd>
              </div>
              <div>
                <dt>状态</dt>
                <dd>{selectedPlan.status}</dd>
              </div>
              <div>
                <dt>目标路径</dt>
                <dd>{targetCountLabel(selectedPlan.target_paths.length)}</dd>
              </div>
            </dl>
            <OperationPlanView plan={historyPlanToOperationPlan(selectedPlan)} />
          </>
        ) : (
          <EmptyState
            description="从历史列表选择一个计划。"
            icon={FileSearch}
            title="还没有选择计划"
          />
        )}
      </Section>

      {status ? <p className="status floating-status">{status}</p> : null}
      {error ? (
        <p className="status error floating-status" role="alert">
          {error}
        </p>
      ) : null}
      {!loading && plans.length ? <p className="muted">共 {targetCount} 个目标路径。</p> : null}
    </div>
  );
}

function TargetList({ paths }: { paths: string[] }) {
  if (!paths.length) {
    return <span className="muted">无目标路径</span>;
  }
  return (
    <ul className="target-list">
      {paths.slice(0, 3).map((path) => (
        <li key={path}>{path}</li>
      ))}
      {paths.length > 3 ? <li>另有 {paths.length - 3} 个目标路径</li> : null}
    </ul>
  );
}

function targetCountLabel(count: number): string {
  return count ? `${count} 个目标路径` : "无目标路径";
}

function statusTone(status: string): string {
  if (status === "completed") {
    return "status-pill-success";
  }
  if (["failed", "rollback_failed"].includes(status)) {
    return "status-pill-danger";
  }
  return "status-pill-neutral";
}

function verificationTone(status: string): string {
  if (status.includes("modified") || status.includes("refused")) {
    return "status-pill-warning";
  }
  if (status.includes("verified") || status === "ok") {
    return "status-pill-success";
  }
  return "status-pill-neutral";
}

function historyPlanToOperationPlan(plan: HistoryPlanRead): OperationPlan {
  return {
    plan_id: plan.plan_id,
    version: 1,
    job_id: plan.job_id,
    mode: plan.mode,
    destination_root: "",
    target_directory: plan.target_paths[0] ?? "",
    source_snapshot: [],
    materialized_asset_cache_paths: [],
    steps: plan.target_paths.map((targetPath, index) => ({
      step_id: `${plan.plan_id}:${index}`,
      operation: "history",
      category: "media",
      source_path: null,
      target_path: targetPath,
      temp_parent_path: "",
      expected_size_bytes: null,
      mtime_ns: null,
      sha256: null,
      sidecar: false,
      materialized_asset: false,
      generated_artifact: false,
      actor_output: targetPath.includes("/.actors/"),
      destructive: false,
      allow_existing_generated_replacement: false,
      metadata: {},
    })),
    conflicts: [],
    safety_warnings: [],
    created_at: plan.created_at,
  };
}

function isRollbackRefusal(
  detail: unknown,
): detail is { detail: { error: string; reason: string } } {
  if (!detail || typeof detail !== "object" || !("detail" in detail)) {
    return false;
  }
  const body = detail.detail;
  if (!body || typeof body !== "object" || !("reason" in body)) {
    return false;
  }
  return typeof body.reason === "string";
}
