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
      setError(exc instanceof Error ? exc.message : "Unable to load history");
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
        `Rollback ${response.status}; reversed ${response.reversed_steps.length} step(s)`,
      );
      await loadHistory();
    } catch (exc) {
      if (exc instanceof ApiError && isRollbackRefusal(exc.detail)) {
        setError(`Rollback refused: ${exc.detail.detail.reason}`);
      } else {
        setError(exc instanceof Error ? exc.message : "Rollback failed");
      }
    }
  }

  const selectedPlan = plans.find((plan) => plan.plan_id === selectedPlanId) ?? null;

  return (
    <div className="page-stack">
      <Section title="History/Rollback">
        <table>
          <caption>Operation history</caption>
          <thead>
            <tr>
              <th>Plan</th>
              <th>Job</th>
              <th>Mode</th>
              <th>Status</th>
              <th>Verification</th>
              <th>Targets</th>
              <th>Action</th>
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
                  <td>{plan.job_id ?? "Manual"}</td>
                  <td>{plan.mode}</td>
                  <td>{plan.status}</td>
                  <td>{plan.verification_status}</td>
                  <td>{plan.target_paths.join(", ")}</td>
                  <td>
                    <button type="button" onClick={() => rollback(plan.plan_id)}>
                      Rollback
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7}>No operation history.</td>
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
