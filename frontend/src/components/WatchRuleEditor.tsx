import { useEffect, useMemo } from "react";

import type { OrganizationMode, WatchRule } from "../api/types";
import { CheckboxField, FormField } from "./FormField";

export type WatchRuleDraft = Omit<WatchRule, "rule_id"> & { rule_id?: string };

const modeOptions: OrganizationMode[] = [
  "copy",
  "move",
  "hardlink",
  "symlink",
  "in_place",
  "preview",
];

export const emptyWatchRuleDraft: WatchRuleDraft = {
  source_directory: "",
  destination_directory: "",
  recursive: true,
  realtime: true,
  polling_interval_seconds: 60,
  stability_seconds: 30,
  stable_check_count: 2,
  organization_mode: "copy",
  folder_templates: ["{studio}", "{title}"],
  filename_template: "{xchina_id} - {title}",
  asset_policy: "strict",
  emby_options: {
    notify: false,
    retry_on_failure: true,
  },
  metadata_options: {
    write_nfo: true,
    poster: true,
    fanart: true,
    actor_outputs: true,
  },
  include_patterns: ["*.mkv", "*.mp4"],
  exclude_patterns: [],
  excluded_destination_prefixes: [],
  confidence_threshold: 92,
  enabled: true,
};

export function WatchRuleEditor({
  draft,
  onChange,
  onSubmit,
  onBrowse,
}: {
  draft: WatchRuleDraft;
  onChange: (draft: WatchRuleDraft) => void;
  onSubmit: () => void;
  onBrowse: () => void;
}) {
  const destinationInsideSource = useMemo(
    () => isInsidePath(draft.destination_directory, draft.source_directory),
    [draft.destination_directory, draft.source_directory],
  );

  useEffect(() => {
    if (!destinationInsideSource || !draft.destination_directory) {
      return;
    }
    if (draft.excluded_destination_prefixes.includes(draft.destination_directory)) {
      return;
    }
    onChange({
      ...draft,
      excluded_destination_prefixes: [
        ...draft.excluded_destination_prefixes,
        draft.destination_directory,
      ],
    });
  }, [destinationInsideSource, draft, onChange]);

  function patch(patchValue: Partial<WatchRuleDraft>) {
    onChange({ ...draft, ...patchValue });
  }

  function patchMetadata(key: string, value: unknown) {
    patch({ metadata_options: { ...draft.metadata_options, [key]: value } });
  }

  function patchEmby(key: string, value: unknown) {
    patch({ emby_options: { ...draft.emby_options, [key]: value } });
  }

  return (
    <div className="editor-grid">
      <div className="grid three">
        <FormField label="Source directory">
          <input
            value={draft.source_directory}
            onChange={(event) => patch({ source_directory: event.target.value })}
          />
        </FormField>
        <FormField label="Destination directory">
          <input
            value={draft.destination_directory}
            onChange={(event) =>
              patch({ destination_directory: event.target.value })
            }
          />
        </FormField>
        <button type="button" onClick={onBrowse}>
          Browse storage roots
        </button>
      </div>

      {destinationInsideSource ? (
        <p className="status warning">
          Destination is inside the watched source. Xona will auto-exclude{" "}
          {draft.destination_directory}.
        </p>
      ) : null}

      <div className="segmented" aria-label="Monitor mode">
        <button
          aria-pressed={draft.realtime}
          type="button"
          onClick={() => patch({ realtime: true })}
        >
          Real-time
        </button>
        <button
          aria-pressed={!draft.realtime}
          type="button"
          onClick={() => patch({ realtime: false })}
        >
          Polling
        </button>
      </div>

      <div className="grid four">
        <CheckboxField
          checked={draft.enabled}
          label="Enabled"
          onChange={(enabled) => patch({ enabled })}
        />
        <CheckboxField
          checked={draft.recursive}
          label="Recursive"
          onChange={(recursive) => patch({ recursive })}
        />
        <FormField label="Polling interval seconds">
          <input
            min={1}
            type="number"
            value={draft.polling_interval_seconds}
            onChange={(event) =>
              patch({ polling_interval_seconds: Number(event.target.value) })
            }
          />
        </FormField>
        <FormField label="Stability duration seconds">
          <input
            min={0}
            type="number"
            value={draft.stability_seconds}
            onChange={(event) =>
              patch({ stability_seconds: Number(event.target.value) })
            }
          />
        </FormField>
        <FormField label="Stable check count">
          <input
            min={1}
            type="number"
            value={draft.stable_check_count}
            onChange={(event) =>
              patch({ stable_check_count: Number(event.target.value) })
            }
          />
        </FormField>
        <FormField label="Confidence threshold">
          <input
            max={100}
            min={0}
            type="number"
            value={draft.confidence_threshold}
            onChange={(event) =>
              patch({ confidence_threshold: Number(event.target.value) })
            }
          />
        </FormField>
        <FormField label="Asset policy">
          <select
            value={draft.asset_policy}
            onChange={(event) => patch({ asset_policy: event.target.value })}
          >
            <option value="strict">Strict</option>
            <option value="lenient">Lenient</option>
          </select>
        </FormField>
      </div>

      <div className="segmented" aria-label="Organization mode">
        {modeOptions.map((mode) => (
          <button
            aria-pressed={draft.organization_mode === mode}
            key={mode}
            type="button"
            onClick={() => patch({ organization_mode: mode })}
          >
            {mode}
          </button>
        ))}
      </div>

      <div className="grid two">
        <FormField label="Folder templates">
          <textarea
            value={draft.folder_templates.join("\n")}
            onChange={(event) =>
              patch({
                folder_templates: lines(event.target.value),
              })
            }
          />
        </FormField>
        <FormField label="Filename template">
          <input
            value={draft.filename_template}
            onChange={(event) => patch({ filename_template: event.target.value })}
          />
        </FormField>
      </div>

      <div className="grid three">
        <CheckboxField
          checked={Boolean(draft.metadata_options.write_nfo)}
          label="Write metadata NFO"
          onChange={(checked) => patchMetadata("write_nfo", checked)}
        />
        <CheckboxField
          checked={Boolean(draft.metadata_options.poster)}
          label="Download poster image"
          onChange={(checked) => patchMetadata("poster", checked)}
        />
        <CheckboxField
          checked={Boolean(draft.metadata_options.fanart)}
          label="Download fanart image"
          onChange={(checked) => patchMetadata("fanart", checked)}
        />
        <CheckboxField
          checked={Boolean(draft.metadata_options.actor_outputs)}
          label="Write .actors outputs"
          onChange={(checked) => patchMetadata("actor_outputs", checked)}
        />
        <CheckboxField
          checked={Boolean(draft.emby_options.notify)}
          label="Notify Emby after local completion"
          onChange={(checked) => patchEmby("notify", checked)}
        />
        <CheckboxField
          checked={Boolean(draft.emby_options.retry_on_failure)}
          label="Retry Emby notification"
          onChange={(checked) => patchEmby("retry_on_failure", checked)}
        />
      </div>

      <div className="grid three">
        <FormField label="Include patterns">
          <textarea
            value={draft.include_patterns.join("\n")}
            onChange={(event) => patch({ include_patterns: lines(event.target.value) })}
          />
        </FormField>
        <FormField label="Exclude patterns">
          <textarea
            value={draft.exclude_patterns.join("\n")}
            onChange={(event) => patch({ exclude_patterns: lines(event.target.value) })}
          />
        </FormField>
        <FormField label="Excluded destination prefixes">
          <textarea
            value={draft.excluded_destination_prefixes.join("\n")}
            onChange={(event) =>
              patch({ excluded_destination_prefixes: lines(event.target.value) })
            }
          />
        </FormField>
      </div>

      <button type="button" onClick={onSubmit}>
        {draft.rule_id ? "Update watch rule" : "Create watch rule"}
      </button>
    </div>
  );
}

function lines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function isInsidePath(candidate: string, parent: string): boolean {
  const normalizedParent = normalizePath(parent);
  const normalizedCandidate = normalizePath(candidate);
  return Boolean(
    normalizedParent &&
      normalizedCandidate &&
      normalizedCandidate !== normalizedParent &&
      normalizedCandidate.startsWith(`${normalizedParent}/`),
  );
}

function normalizePath(path: string): string {
  return path.trim().replace(/\/+$/g, "");
}
