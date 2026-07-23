import { useEffect, useState } from "react";

import { ApiError, apiFetch } from "../api/client";
import type {
  HistoryPlanRead,
  HistoryPlansResponse,
  OperationPlan,
  RollbackResponse,
} from "../api/types";
import { Section } from "../components/FormField";
import { OperationPlanView } from "../components/OperationPlanView";

export function HistoryRollbackPage() {
  const [plans, setPlans] = useState<HistoryPlanRead[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function loadHistory() {
    setError("");
    try {
      const response = await apiFetch<HistoryPlansResponse>("/api/history/plans");
      setPlans(response.plans);
      setSelectedPlanId((current) => current ?? response.plans[0]?.plan_id ?? null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载历史记录");
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

  return (
    <div className="page-stack">
      <Section title="历史/回滚">
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
            {plans.length ? (
              plans.map((plan) => (
                <tr key={plan.plan_id}>
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
                  <td>{plan.status}</td>
                  <td>{plan.verification_status}</td>
                  <td>{plan.target_paths.join(", ")}</td>
                  <td>
                    <button type="button" onClick={() => rollback(plan.plan_id)}>
                      回滚
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7}>暂无操作历史。</td>
              </tr>
            )}
          </tbody>
        </table>
        {selectedPlan ? (
          <OperationPlanView plan={historyPlanToOperationPlan(selectedPlan)} />
        ) : null}
        {status ? <p className="status">{status}</p> : null}
        {error ? <p className="status error">{error}</p> : null}
      </Section>
    </div>
  );
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
