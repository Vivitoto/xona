import type { ManualPreviewResponse, OperationPlan } from "../api/types";

export function OperationPlanView({
  plan,
  preview,
  refusalReasons = [],
}: {
  plan?: OperationPlan | null;
  preview?: ManualPreviewResponse | null;
  refusalReasons?: string[];
}) {
  const resolvedPlan = plan ?? preview?.plan ?? null;
  const materializedAssets =
    preview?.materialized_assets ?? assetObjects(resolvedPlan?.materialized_asset_cache_paths);
  const missingAssets = preview?.missing_assets ?? [];
  const steps = resolvedPlan?.steps ?? [];
  const actorOutputs = steps.filter(
    (step) =>
      step.actor_output ||
      step.category === "actor_output" ||
      step.target_path.includes("/.actors/"),
  );
  const generatedFiles = steps.filter(
    (step) => step.generated_artifact || step.operation === "write_generated",
  );

  if (!resolvedPlan && !refusalReasons.length) {
    return <p className="muted">No operation preview yet.</p>;
  }

  return (
    <section className="plan-view" aria-label="Operation plan">
      {resolvedPlan ? (
        <div className="plan-summary">
          <span>Plan {resolvedPlan.plan_id}</span>
          <span>Mode {resolvedPlan.mode}</span>
          <span>Target {resolvedPlan.target_directory}</span>
        </div>
      ) : null}

      <PlanList
        empty="No refusal reasons."
        heading="Refusal reasons"
        items={refusalReasons.map((reason) => ({ key: reason, label: reason }))}
      />
      <PlanList
        empty="No conflicts."
        heading="Conflicts"
        items={(resolvedPlan?.conflicts ?? []).map((conflict) => ({
          key: `${conflict.target_path}:${conflict.reason}`,
          label: `${conflict.target_path} - ${conflict.reason}`,
        }))}
      />
      <PlanList
        empty="No planned steps."
        heading="Planned steps"
        items={steps.map((step) => ({
          key: step.step_id,
          label: `${step.operation} ${step.source_path ?? ""} -> ${step.target_path}`,
        }))}
      />
      <PlanList
        empty="No target paths."
        heading="Target paths"
        items={steps.map((step) => ({
          key: `target:${step.step_id}`,
          label: step.target_path,
        }))}
      />
      <PlanList
        empty="No materialized assets."
        heading="Materialized assets"
        items={materializedAssets.map((asset, index) => ({
          key: `asset:${index}`,
          label: stringifyAsset(asset),
        }))}
      />
      <PlanList
        empty="No missing assets."
        heading="Missing assets"
        items={missingAssets.map((asset, index) => ({
          key: `missing:${index}`,
          label: stringifyAsset(asset),
        }))}
      />
      <PlanList
        empty="No .actors outputs."
        heading=".actors outputs"
        items={actorOutputs.map((step) => ({
          key: `actor:${step.step_id}`,
          label: step.target_path,
        }))}
      />
      <PlanList
        empty="No generated files."
        heading="Generated files"
        items={generatedFiles.map((step) => ({
          key: `generated:${step.step_id}`,
          label: step.target_path,
        }))}
      />
      <PlanList
        empty="No safety warnings."
        heading="Safety warnings"
        items={(resolvedPlan?.safety_warnings ?? []).map((warning) => ({
          key: `${warning.code}:${warning.path ?? ""}`,
          label: `${warning.code}: ${warning.message}${warning.path ? ` (${warning.path})` : ""}`,
        }))}
      />
    </section>
  );
}

function PlanList({
  heading,
  items,
  empty,
}: {
  heading: string;
  items: { key: string; label: string }[];
  empty: string;
}) {
  return (
    <div className="plan-list">
      <h3>{heading}</h3>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item.key}>{item.label}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">{empty}</p>
      )}
    </div>
  );
}

function assetObjects(paths: string[] | undefined): Record<string, unknown>[] {
  return (paths ?? []).map((path) => ({ path }));
}

function stringifyAsset(asset: Record<string, unknown>): string {
  const pathLike =
    asset.path ??
    asset.cache_path ??
    asset.target_path ??
    asset.destination_path ??
    asset.url ??
    asset.kind;
  return typeof pathLike === "string" ? pathLike : JSON.stringify(asset);
}
