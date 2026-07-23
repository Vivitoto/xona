import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import type { BrowseResponse, ScanNowResponse, WatchRule, WatchRuleList } from "../api/types";
import { Section } from "../components/FormField";
import {
  WatchRuleDraft,
  WatchRuleEditor,
  emptyWatchRuleDraft,
} from "../components/WatchRuleEditor";

export function AutomaticMonitorsPage() {
  const [rules, setRules] = useState<WatchRule[]>([]);
  const [draft, setDraft] = useState<WatchRuleDraft>(emptyWatchRuleDraft);
  const [browse, setBrowse] = useState<BrowseResponse | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const updateDraft = useCallback((nextDraft: WatchRuleDraft) => {
    setDraft(nextDraft);
  }, []);

  async function loadRules() {
    setError("");
    try {
      const response = await apiFetch<WatchRuleList>("/api/watch-rules");
      setRules(response.rules);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load watch rules");
    }
  }

  useEffect(() => {
    void loadRules();
  }, []);

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
      setStatus(`Watch rule ${response.rule_id} saved`);
      await loadRules();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to save watch rule");
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
        `Scan queued for ${response.rule_id}: ${response.enqueued_jobs.join(", ") || "no jobs"}`,
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to scan watch rule");
    }
  }

  async function browseStorageRoots() {
    setError("");
    try {
      setBrowse(await apiFetch<BrowseResponse>("/api/storage-roots/browse?root_id=1"));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to browse storage roots");
    }
  }

  return (
    <div className="page-stack">
      <Section title="Automatic Monitors">
        <WatchRuleEditor
          draft={draft}
          onBrowse={browseStorageRoots}
          onChange={updateDraft}
          onSubmit={saveRule}
        />
        {browse ? (
          <ul className="dense-list" aria-label="Storage root browse entries">
            {browse.entries.map((entry) => (
              <li key={entry.path}>{entry.name}</li>
            ))}
          </ul>
        ) : null}
      </Section>
      <Section title="Watch Rules">
        <table>
          <caption>Automatic monitor rules</caption>
          <thead>
            <tr>
              <th>Rule</th>
              <th>Source</th>
              <th>Destination</th>
              <th>Mode</th>
              <th>Enabled</th>
              <th>Actions</th>
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
                  <td>{rule.enabled ? "Yes" : "No"}</td>
                  <td>
                    <div className="button-row">
                      <button type="button" onClick={() => setDraft({ ...rule })}>
                        Edit
                      </button>
                      <button type="button" onClick={() => scanNow(rule.rule_id)}>
                        Scan now
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6}>No watch rules configured.</td>
              </tr>
            )}
          </tbody>
        </table>
        {status ? <p className="status">{status}</p> : null}
        {error ? <p className="status error">{error}</p> : null}
      </Section>
    </div>
  );
}
