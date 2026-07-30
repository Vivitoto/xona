import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../api/client";
import type {
  AppSettings,
  JobEventRead,
  JobEventsResponse,
  JobListResponse,
  JobSummaryRead,
  ScanNowResponse,
  WatchRule,
  WatchRuleList,
} from "../api/types";
import { Section } from "../components/FormField";
import {
  ProgressLog,
  codeLabel,
  jobEventsToProgressLines,
} from "../components/ProgressLog";
import { Tabs, type TabItem } from "../components/Tabs";
import {
  WatchRuleDraft,
  WatchRuleEditor,
  emptyWatchRuleDraft,
} from "../components/WatchRuleEditor";
import { normalizeSettings } from "./settings/settingsForm";

type MonitorTab = "rules" | "queue";

const monitorTabs: readonly TabItem<MonitorTab>[] = [
  { id: "rules", label: "监控规则" },
  { id: "queue", label: "任务队列" },
];

export function AutomaticMonitorsPage() {
  const [activeTab, setActiveTab] = useState<MonitorTab>("rules");
  const [rules, setRules] = useState<WatchRule[]>([]);
  const [automaticJobs, setAutomaticJobs] = useState<JobSummaryRead[]>([]);
  const [queueEvents, setQueueEvents] = useState<Record<number, JobEventRead[]>>({});
  const [queueEventErrors, setQueueEventErrors] = useState<Record<number, string>>({});
  const [draft, setDraft] = useState<WatchRuleDraft>(emptyWatchRuleDraft);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const draftTouched = useRef(false);

  const updateDraft = useCallback((nextDraft: WatchRuleDraft) => {
    draftTouched.current = true;
    setDraft(nextDraft);
  }, []);

  async function loadSettingsDefaults() {
    try {
      const response = await apiFetch<AppSettings>("/api/settings");
      const normalized = normalizeSettings(response);
      setDraft((current) => {
        if (draftTouched.current || current.rule_id) {
          return current;
        }
        return applyOrganizationDefaults(current, normalized);
      });
    } catch {
      return;
    }
  }

  async function loadRules() {
    setError("");
    try {
      const response = await apiFetch<WatchRuleList>("/api/watch-rules");
      setRules(Array.isArray(response.rules) ? response.rules : []);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载监控规则");
    }
  }

  async function loadAutomaticJobs() {
    setError("");
    try {
      const response = await apiFetch<JobListResponse>("/api/jobs?manual=false&limit=50");
      const jobs = Array.isArray(response.jobs) ? response.jobs : [];
      setAutomaticJobs(jobs);
      await loadQueueEvents(jobs);
    } catch (exc) {
      setError(
        exc instanceof Error ? exc.message : "无法加载自动整理任务",
      );
    }
  }

  async function loadQueueEvents(jobs: JobSummaryRead[]) {
    const nextEvents: Record<number, JobEventRead[]> = {};
    const nextErrors: Record<number, string> = {};

    await Promise.all(
      jobs.map(async (job) => {
        try {
          const response = await apiFetch<JobEventsResponse>(
            `/api/jobs/${job.id}/events`,
          );
          nextEvents[job.id] = Array.isArray(response.events) ? response.events : [];
        } catch (exc) {
          nextEvents[job.id] = [];
          nextErrors[job.id] = exc instanceof Error ? exc.message : "无法加载任务事件";
        }
      }),
    );

    setQueueEvents(nextEvents);
    setQueueEventErrors(nextErrors);
  }

  useEffect(() => {
    void loadSettingsDefaults();
    void loadRules();
  }, []);

  useEffect(() => {
    if (activeTab === "queue") {
      void loadAutomaticJobs();
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab !== "queue") {
      return;
    }
    const refreshTimer = window.setInterval(() => {
      void loadAutomaticJobs();
    }, 5000);
    return () => window.clearInterval(refreshTimer);
  }, [activeTab]);

  async function saveRule() {
    setError("");
    try {
      const path = draft.rule_id ? `/api/watch-rules/${draft.rule_id}` : "/api/watch-rules";
      const response = await apiFetch<WatchRule>(path, {
        method: draft.rule_id ? "PUT" : "POST",
        body: {
          source_directory: draft.source_directory,
          destination_directory: draft.destination_directory,
          recursive: draft.recursive,
          realtime: draft.realtime,
          polling_interval_seconds: draft.polling_interval_seconds,
          stability_seconds: draft.stability_seconds,
          stable_check_count: draft.stable_check_count,
          organization_mode: organizationModeOrCopy(draft.organization_mode),
          folder_templates: draft.folder_templates,
          filename_template: draft.filename_template,
          asset_policy: draft.asset_policy,
          emby_options: draft.emby_options,
          metadata_options: draft.metadata_options,
          include_patterns: draft.include_patterns,
          exclude_patterns: draft.exclude_patterns,
          excluded_destination_prefixes: draft.excluded_destination_prefixes,
          confidence_threshold: draft.confidence_threshold,
          enabled: draft.enabled,
        },
      });
      setDraft({ ...response });
      setStatus(`监控规则 ${response.rule_id} 已保存`);
      await loadRules();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法保存监控规则");
    }
  }

  async function scanNow(ruleId: string) {
    setError("");
    try {
      const response = await apiFetch<ScanNowResponse>(
        `/api/watch-rules/${ruleId}/scan-now`,
        { method: "POST" },
      );
      setStatus(
        `已为 ${response.rule_id} 加入扫描队列：${response.enqueued_jobs.join(", ") || "无任务"}`,
      );
      await loadAutomaticJobs();
      setActiveTab("queue");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法扫描监控规则");
    }
  }

  return (
    <div className="page-stack">
      <Tabs
        activeTab={activeTab}
        ariaLabel="自动监控视图"
        tabs={monitorTabs}
        onChange={setActiveTab}
      />
      <div className="tab-panel" role="tabpanel">
        {activeTab === "rules" ? (
          <>
            <Section title="自动监控">
              <WatchRuleEditor
                draft={draft}
                onChange={updateDraft}
                onSubmit={saveRule}
              />
            </Section>
            <Section title="监控规则">
              <table>
                <caption>自动监控规则</caption>
                <thead>
                  <tr>
                    <th>规则</th>
                    <th>源目录</th>
                    <th>目标目录</th>
                    <th>模式</th>
                    <th>启用</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.length ? (
                    rules.map((rule) => (
                      <tr key={rule.rule_id}>
                        <td>{rule.rule_id}</td>
                        <td>{rule.source_directory}</td>
                        <td>{rule.destination_directory}</td>
                        <td>{organizationModeLabel(rule.organization_mode)}</td>
                        <td>{rule.enabled ? "是" : "否"}</td>
                        <td>
                          <div className="button-row">
                            <button
                              type="button"
                              onClick={() => {
                                draftTouched.current = true;
                                setDraft({
                                  ...rule,
                                  organization_mode: organizationModeOrCopy(
                                    rule.organization_mode,
                                  ),
                                });
                              }}
                            >
                              编辑
                            </button>
                            <button
                              type="button"
                              onClick={() => scanNow(rule.rule_id)}
                            >
                              立即扫描
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6}>尚未配置监控规则。</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </Section>
          </>
        ) : (
          <Section title="自动整理任务">
            <table>
              <caption>自动整理任务进度</caption>
              <thead>
                <tr>
                  <th>任务</th>
                  <th>规则</th>
                  <th>标识</th>
                  <th>原因</th>
                  <th>候选项</th>
                  <th>进度</th>
                </tr>
              </thead>
              <tbody>
                {automaticJobs.length ? (
                  automaticJobs.map((job) => (
                    <tr key={job.id}>
                      <td>{job.id}</td>
                      <td>{job.rule_id ?? "手动"}</td>
                      <td>{job.media_identity}</td>
                      <td>{gateReasonLabel(job)}</td>
                      <td>{candidateTitle(job.selected_candidate)}</td>
                      <td className="queue-progress-cell">
                        <ProgressLog
                          ariaLabel={`任务 ${job.id} 进度日志`}
                          emptyLabel={queueEventErrors[job.id] || "暂无进度事件。"}
                          lines={jobEventsToProgressLines(
                            queueEvents[job.id] ?? [],
                            job.state,
                          )}
                        />
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6}>没有自动整理任务。</td>
                  </tr>
                )}
              </tbody>
            </table>
          </Section>
        )}
      </div>
      {status ? <p className="status">{status}</p> : null}
      {error ? <p className="status error">{error}</p> : null}
    </div>
  );
}

function candidateTitle(candidate: Record<string, unknown> | null): string {
  if (!candidate) {
    return "无候选项";
  }
  return typeof candidate.title === "string" ? candidate.title : "已选择候选项";
}

function gateReasonLabel(job: JobSummaryRead): string {
  if (job.gate_reasons.length) {
    return job.gate_reasons.map(codeLabel).join("，");
  }
  return job.state === "review_required" ? "需要复核" : "—";
}

function applyOrganizationDefaults(
  draft: WatchRuleDraft,
  settings: AppSettings,
): WatchRuleDraft {
  const defaults = settings.organization_defaults;
  const folderTemplates = defaults.folder_templates.length
    ? defaults.folder_templates
    : settings.naming.folder_templates;
  return {
    ...draft,
    destination_directory: defaults.destination_directory ?? draft.destination_directory,
    organization_mode: organizationModeOrCopy(defaults.organization_mode),
    folder_templates: folderTemplates.length ? folderTemplates : draft.folder_templates,
    filename_template:
      defaults.filename_template ||
      settings.naming.filename_template ||
      draft.filename_template,
    asset_policy:
      defaults.asset_policy ||
      settings.metadata_assets.asset_policy ||
      draft.asset_policy,
    metadata_options: {
      ...draft.metadata_options,
      include_source_snapshot: defaults.include_source_snapshot,
    },
  };
}

function organizationModeOrCopy(mode: WatchRuleDraft["organization_mode"]): WatchRuleDraft["organization_mode"] {
  return mode === "preview" ? "copy" : mode;
}

function organizationModeLabel(mode: WatchRuleDraft["organization_mode"]): string {
  switch (organizationModeOrCopy(mode)) {
    case "copy":
      return "复制";
    case "move":
      return "移动";
    case "hardlink":
      return "硬链接";
    case "symlink":
      return "符号链接";
    case "in_place":
      return "原地处理";
    case "preview":
      return "复制";
    default:
      return String(mode);
  }
}
