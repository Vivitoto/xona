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
    return <p className="muted">尚无操作预览。</p>;
  }

  return (
    <section className="plan-view" aria-label="操作计划">
      {resolvedPlan ? (
        <div className="plan-summary">
          <span>计划 {resolvedPlan.plan_id}</span>
          <span>模式 {resolvedPlan.mode}</span>
          <span>目标 {resolvedPlan.target_directory}</span>
        </div>
      ) : null}

      <PlanList
        empty="无拒绝原因。"
        heading="拒绝原因"
        items={refusalReasons.map((reason) => ({ key: reason, label: reason }))}
      />
      <PlanList
        empty="无冲突。"
        heading="冲突"
        items={(resolvedPlan?.conflicts ?? []).map((conflict) => ({
          key: `${conflict.target_path}:${conflict.reason}`,
          label: `${conflict.target_path} - ${conflict.reason}`,
        }))}
      />
      <PlanList
        empty="无计划步骤。"
        heading="计划步骤"
        items={steps.map((step) => ({
          key: step.step_id,
          label: `${step.operation} ${step.source_path ?? ""} -> ${step.target_path}`,
        }))}
      />
      <PlanList
        empty="无目标路径。"
        heading="目标路径"
        items={steps.map((step) => ({
          key: `target:${step.step_id}`,
          label: step.target_path,
        }))}
      />
      <PlanList
        empty="无已缓存资源。"
        heading="已缓存资源"
        items={materializedAssets.map((asset, index) => ({
          key: `asset:${index}`,
          label: stringifyAsset(asset),
        }))}
      />
      <PlanList
        empty="无缺失资源。"
        heading="缺失资源"
        items={missingAssets.map((asset, index) => ({
          key: `missing:${index}`,
          label: stringifyAsset(asset),
        }))}
      />
      <PlanList
        empty="无 .actors 输出。"
        heading=".actors 输出"
        items={actorOutputs.map((step) => ({
          key: `actor:${step.step_id}`,
          label: step.target_path,
        }))}
      />
      <PlanList
        empty="无生成文件。"
        heading="生成文件"
        items={generatedFiles.map((step) => ({
          key: `generated:${step.step_id}`,
          label: step.target_path,
        }))}
      />
      <PlanList
        empty="无安全警告。"
        heading="安全警告"
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
