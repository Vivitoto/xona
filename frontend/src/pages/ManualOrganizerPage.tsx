import { FormEvent, useState } from "react";

import { apiFetch } from "../api/client";
import type {
  BrowseResponse,
  ManualCandidateCard as ManualCandidate,
  ManualExecutePlanResponse,
  ManualJobSummary,
  ManualPreviewResponse,
  ManualScanResponse,
  ManualSearchResponse,
  OrganizationMode,
} from "../api/types";
import { CandidateCard } from "../components/CandidateCard";
import { CheckboxField, FormField, Section } from "../components/FormField";
import { OperationPlanView } from "../components/OperationPlanView";
import { linesToList, listToLines } from "./settings/settingsForm";

const safetyLabels = [
  ["file_conflict", "Collision refusal"],
  ["unresolved_multipart", "Unresolved multipart"],
  ["incomplete_metadata", "Incomplete metadata"],
  ["unsafe_path", "Unsafe paths"],
  ["strict_assets_missing", "Strict asset failures"],
] as const;

type SafetyKey = (typeof safetyLabels)[number][0];

export function ManualOrganizerPage() {
  const [directory, setDirectory] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [ignorePatterns, setIgnorePatterns] = useState("");
  const [browseRootId, setBrowseRootId] = useState("1");
  const [browsePath, setBrowsePath] = useState("");
  const [browse, setBrowse] = useState<BrowseResponse | null>(null);
  const [jobs, setJobs] = useState<ManualJobSummary[]>([]);
  const [jobId, setJobId] = useState("");
  const [filename, setFilename] = useState("");
  const [normalizedQuery, setNormalizedQuery] = useState("");
  const [candidates, setCandidates] = useState<ManualCandidate[]>([]);
  const [selected, setSelected] = useState<ManualCandidate | null>(null);
  const [detailUrl, setDetailUrl] = useState("");
  const [strictAssets, setStrictAssets] = useState(false);
  const [safety, setSafety] = useState<Record<SafetyKey, boolean>>({
    file_conflict: false,
    unresolved_multipart: false,
    incomplete_metadata: false,
    unsafe_path: false,
    strict_assets_missing: false,
  });
  const [refusalReasons, setRefusalReasons] = useState<string[]>([]);
  const [destinationRoot, setDestinationRoot] = useState("");
  const [mode, setMode] = useState<OrganizationMode>("copy");
  const [folderTemplates, setFolderTemplates] = useState("{studio}\n{title}");
  const [filenameTemplate, setFilenameTemplate] = useState("{xchina_id} - {title}");
  const [assetPolicy, setAssetPolicy] = useState("strict");
  const [includeSourceSnapshot, setIncludeSourceSnapshot] = useState(false);
  const [preview, setPreview] = useState<ManualPreviewResponse | null>(null);
  const [executeResult, setExecuteResult] =
    useState<ManualExecutePlanResponse | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function browseSource() {
    setError("");
    const query = new URLSearchParams({
      root_id: browseRootId,
      path: browsePath,
    });
    try {
      setBrowse(await apiFetch<BrowseResponse>(`/api/storage-roots/browse?${query}`));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Browse failed");
    }
  }

  async function scan(event?: FormEvent) {
    event?.preventDefault();
    setStatus("Scanning");
    setError("");
    try {
      const response = await apiFetch<ManualScanResponse>("/api/manual/scan", {
        method: "POST",
        body: {
          directory,
          recursive,
          ignore_patterns: linesToList(ignorePatterns),
        },
      });
      setJobs(response.jobs);
      if (response.jobs[0]) {
        setJobId(String(response.jobs[0].job_id));
      }
      setStatus(`Scanned ${response.scanned_count} item(s)`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Scan failed");
    }
  }

  async function search(jobOverride?: number) {
    setStatus("Searching");
    setError("");
    try {
      const response = await apiFetch<ManualSearchResponse>("/api/manual/search", {
        method: "POST",
        body: {
          job_id: jobOverride ?? numericJobId(),
          filename: filename || null,
          normalized_query: normalizedQuery || null,
        },
      });
      setJobId(String(response.job_id));
      setNormalizedQuery(response.normalized_query);
      setCandidates(response.candidates);
      setStatus(`Found ${response.candidates.length} candidate(s)`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Search failed");
    }
  }

  async function batchSearch() {
    for (const job of jobs) {
      await search(job.job_id);
    }
  }

  async function selectCandidate(candidate: ManualCandidate | null = selected) {
    const activeJobId = numericJobId();
    if (!activeJobId) {
      setError("Select or enter a job before choosing a candidate.");
      return;
    }
    setError("");
    setStatus("Selecting candidate");
    try {
      const response = await apiFetch<{
        accepted: boolean;
        reasons: string[];
        selected_candidate: ManualCandidate | null;
      }>(`/api/manual/jobs/${activeJobId}/select-candidate`, {
        method: "POST",
        body: {
          candidate_id: candidate?.candidate_id ?? null,
          source_url: detailUrl || candidate?.url || null,
          strict_assets: strictAssets,
          safety: safetyPayload(),
        },
      });
      setSelected(response.selected_candidate ?? candidate);
      setRefusalReasons(response.reasons);
      setStatus(response.accepted ? "Candidate accepted" : "Review required");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Candidate selection failed");
    }
  }

  async function previewPlan() {
    const activeJobId = numericJobId();
    if (!activeJobId) {
      setError("A job is required before preview.");
      return;
    }
    setError("");
    setStatus("Building preview");
    try {
      const response = await apiFetch<ManualPreviewResponse>(
        `/api/manual/jobs/${activeJobId}/preview`,
        {
          method: "POST",
          body: {
            destination_root: destinationRoot,
            mode,
            folder_templates: linesToList(folderTemplates),
            filename_template: filenameTemplate,
            asset_policy: assetPolicy,
            include_source_snapshot: includeSourceSnapshot,
          },
        },
      );
      setPreview(response);
      setStatus("Preview ready");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Preview failed");
    }
  }

  async function executePlan() {
    if (!preview) {
      return;
    }
    setError("");
    setStatus("Executing");
    try {
      const response = await apiFetch<ManualExecutePlanResponse>(
        `/api/manual/plans/${preview.plan_id}/execute`,
        {
          method: "POST",
          body: {
            approved: true,
            plan_version: preview.plan.version,
          },
        },
      );
      setExecuteResult(response);
      setStatus(`Execution ${response.state}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Execute failed");
    }
  }

  function numericJobId(): number | null {
    const parsed = Number.parseInt(jobId, 10);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function safetyPayload(): Record<string, boolean> {
    return {
      file_conflict: safety.file_conflict,
      unresolved_multipart: safety.unresolved_multipart,
      unsafe_path: safety.unsafe_path,
      strict_assets_missing: safety.strict_assets_missing,
    };
  }

  return (
    <div className="page-stack">
      <Section title="Source Browse/Scan">
        <form className="grid three" onSubmit={scan}>
          <FormField label="Source directory">
            <input value={directory} onChange={(event) => setDirectory(event.target.value)} />
          </FormField>
          <CheckboxField checked={recursive} label="Recursive scan" onChange={setRecursive} />
          <FormField label="Ignore patterns">
            <textarea
              value={ignorePatterns}
              onChange={(event) => setIgnorePatterns(event.target.value)}
            />
          </FormField>
          <button type="submit">Scan source</button>
        </form>
        <div className="grid three">
          <FormField label="Browse root ID">
            <input value={browseRootId} onChange={(event) => setBrowseRootId(event.target.value)} />
          </FormField>
          <FormField label="Browse path">
            <input value={browsePath} onChange={(event) => setBrowsePath(event.target.value)} />
          </FormField>
          <button type="button" onClick={browseSource}>
            Browse source
          </button>
        </div>
        {browse ? (
          <ul className="dense-list" aria-label="Source browse results">
            {browse.entries.map((entry) => (
              <li key={entry.path}>
                <button
                  className="link-button"
                  type="button"
                  onClick={() => {
                    if (entry.is_dir) {
                      setDirectory(entry.path);
                      setBrowsePath(entry.path);
                    } else {
                      setFilename(entry.name);
                    }
                  }}
                >
                  {entry.name} {entry.is_dir ? "(directory)" : "(file)"}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </Section>

      <Section title="Search">
        <div className="grid four">
          <FormField label="Job ID">
            <input value={jobId} onChange={(event) => setJobId(event.target.value)} />
          </FormField>
          <FormField label="Pasted filename search">
            <input value={filename} onChange={(event) => setFilename(event.target.value)} />
          </FormField>
          <FormField label="Editable normalized query">
            <input
              value={normalizedQuery}
              onChange={(event) => setNormalizedQuery(event.target.value)}
            />
          </FormField>
          <div className="button-column">
            <button type="button" onClick={() => search()}>
              Search
            </button>
            <button disabled={!jobs.length} type="button" onClick={batchSearch}>
              Batch search
            </button>
          </div>
        </div>
        {jobs.length ? (
          <table>
            <caption>Scanned jobs</caption>
            <thead>
              <tr>
                <th>Job</th>
                <th>State</th>
                <th>Identity</th>
                <th>Files</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.job_id}>
                  <td>{job.job_id}</td>
                  <td>{job.state}</td>
                  <td>{job.media_identity}</td>
                  <td>{job.media_items.map((item) => item.path).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </Section>

      <Section title="Candidate Selection">
        <div className="grid three">
          <FormField label="Detail URL">
            <input value={detailUrl} onChange={(event) => setDetailUrl(event.target.value)} />
          </FormField>
          <CheckboxField checked={strictAssets} label="Strict assets" onChange={setStrictAssets} />
          <button type="button" onClick={() => selectCandidate()}>
            Select detail URL
          </button>
        </div>
        <div className="safety-grid" aria-label="Safety gates">
          {safetyLabels.map(([key, label]) => (
            <CheckboxField
              key={key}
              checked={safety[key]}
              label={label}
              onChange={(checked) =>
                setSafety((current) => ({ ...current, [key]: checked }))
              }
            />
          ))}
        </div>
        <div className="candidate-grid">
          {candidates.map((candidate) => (
            <CandidateCard
              key={candidate.candidate_id}
              candidate={candidate}
              selected={candidate.candidate_id === selected?.candidate_id}
              onSelect={(nextCandidate) => {
                setSelected(nextCandidate);
                void selectCandidate(nextCandidate);
              }}
            />
          ))}
        </div>
      </Section>

      <Section title="Preview/Execute">
        <div className="grid four">
          <FormField label="Destination root">
            <input
              value={destinationRoot}
              onChange={(event) => setDestinationRoot(event.target.value)}
            />
          </FormField>
          <FormField label="Organization mode">
            <select value={mode} onChange={(event) => setMode(event.target.value as OrganizationMode)}>
              <option value="preview">Preview</option>
              <option value="copy">Copy</option>
              <option value="move">Move</option>
              <option value="hardlink">Hardlink</option>
              <option value="symlink">Symlink</option>
              <option value="in_place">In place</option>
            </select>
          </FormField>
          <FormField label="Asset policy">
            <select value={assetPolicy} onChange={(event) => setAssetPolicy(event.target.value)}>
              <option value="lenient">Lenient</option>
              <option value="strict">Strict</option>
            </select>
          </FormField>
          <CheckboxField
            checked={includeSourceSnapshot}
            label="Include source snapshot"
            onChange={setIncludeSourceSnapshot}
          />
        </div>
        <div className="grid two">
          <FormField label="Folder templates">
            <textarea
              value={folderTemplates}
              onChange={(event) => setFolderTemplates(event.target.value)}
            />
          </FormField>
          <FormField label="Filename template">
            <input
              value={filenameTemplate}
              onChange={(event) => setFilenameTemplate(event.target.value)}
            />
          </FormField>
        </div>
        <div className="button-row">
          <button type="button" onClick={previewPlan}>
            Preview operation plan
          </button>
          <button disabled={!preview} type="button" onClick={executePlan}>
            Execute approved preview
          </button>
        </div>
        <OperationPlanView preview={preview} refusalReasons={refusalReasons} />
        {executeResult ? (
          <p className="status">Plan {executeResult.plan_id} is {executeResult.state}</p>
        ) : null}
      </Section>

      {status ? <p className="status">{status}</p> : null}
      {error ? <p className="status error">{error}</p> : null}
    </div>
  );
}
