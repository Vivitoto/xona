import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import type {
  JobListResponse,
  JobSummaryRead,
  ScanNowResponse,
  WatchRule,
  WatchRuleList,
} from "../api/types";
import { Section } from "../components/FormField";
import { Tabs, type TabItem } from "../components/Tabs";
import {
  WatchRuleDraft,
  WatchRuleEditor,
  emptyWatchRuleDraft,
} from "../components/WatchRuleEditor";

type MonitorTab = "rules" | "queue";

const monitorTabs: readonly TabItem<MonitorTab>[] = [
  { id: "rules", label: "监控规则" },
  { id: "queue", label: "任务队列" },
];

export function AutomaticMonitorsPage() {
  const [activeTab, setActiveTab] = useState<MonitorTab>("rules");
  const [rules, setRules] = useState<WatchRule[]>([]);
  const [reviewJobs, setReviewJobs] = useState<JobSummaryRead[]>([]);
  const [draft, setDraft] = useState<WatchRuleDraft>(emptyWatchRuleDraft);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const updateDraft = useCallback((nextDraft: WatchRuleDraft) => {
    setDraft(nextDraft);
  }, []);

  async function loadRules() {
    setError("");
    try {
      const response = await apiFetch<WatchRuleList>("/api/watch-rules");
      setRules(Array.isArray(response.rules) ? response.rules : []);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载监控规则");
    }
  }

  async function loadReviewItems() {
    setError("");
    try {
      const response = await apiFetch<JobListResponse>(
        "/api/jobs?state=review_required",
      );
      setReviewJobs(Array.isArray(response.jobs) ? response.jobs : []);
    } catch (exc) {
      setError(
        exc instanceof Error ? exc.message : "无法加载需复核任务",
      );
    }
  }

  useEffect(() => {
    void loadRules();
  }, []);

  useEffect(() => {
    if (activeTab === "queue") {
      void loadReviewItems();
    }
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
          organization_mode: draft.organization_mode,
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
      await loadReviewItems();
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
                        <td>{rule.organization_mode}</td>
                        <td>{rule.enabled ? "是" : "否"}</td>
                        <td>
                          <div className="button-row">
                            <button
                              type="button"
                              onClick={() => setDraft({ ...rule })}
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
          <Section title="任务队列">
            <table>
              <caption>监控器需复核任务</caption>
              <thead>
                <tr>
                  <th>任务</th>
                  <th>规则</th>
                  <th>标识</th>
                  <th>原因</th>
                  <th>候选项</th>
                </tr>
              </thead>
              <tbody>
                {reviewJobs.length ? (
                  reviewJobs.map((job) => (
                    <tr key={job.id}>
                      <td>{job.id}</td>
                      <td>{job.rule_id ?? "手动"}</td>
                      <td>{job.media_identity}</td>
                      <td>{job.gate_reasons.join(", ") || "需要复核"}</td>
                      <td>{candidateTitle(job.selected_candidate)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5}>没有需复核的监控项目。</td>
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
