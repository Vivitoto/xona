import { useEffect, useMemo } from "react";

import type { OrganizationMode, WatchRule } from "../api/types";
import { DirectoryPicker } from "./DirectoryPicker";
import { CheckboxField, FormField } from "./FormField";

export type WatchRuleDraft = Omit<WatchRule, "rule_id"> & { rule_id?: string };

const modeOptions: OrganizationMode[] = [
  "copy",
  "move",
  "hardlink",
  "symlink",
  "in_place",
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
    include_source_snapshot: false,
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
}: {
  draft: WatchRuleDraft;
  onChange: (draft: WatchRuleDraft) => void;
  onSubmit: () => void;
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

  function addExcludedDestinationPrefix(path: string) {
    const nextPrefix = path.trim();
    if (!nextPrefix || draft.excluded_destination_prefixes.includes(nextPrefix)) {
      return;
    }
    patch({
      excluded_destination_prefixes: [
        ...draft.excluded_destination_prefixes,
        nextPrefix,
      ],
    });
  }

  return (
    <div className="editor-grid">
      <div className="grid two">
        <div className="path-field">
          <FormField
            description="要监控的源目录。"
            label="源目录"
          >
            <input
              placeholder="/downloads/incoming"
              value={draft.source_directory}
              onChange={(event) => patch({ source_directory: event.target.value })}
            />
          </FormField>
          <DirectoryPicker
            initialPath={draft.source_directory}
            onSelect={(source_directory) => patch({ source_directory })}
            title="选择监控源目录"
          />
        </div>
        <div className="path-field">
          <FormField
            description="目标位于源目录内时会自动排除。"
            label="目标目录"
          >
            <input
              placeholder="/media/jav"
              value={draft.destination_directory}
              onChange={(event) =>
                patch({ destination_directory: event.target.value })
              }
            />
          </FormField>
          <DirectoryPicker
            initialPath={draft.destination_directory}
            onSelect={(destination_directory) => patch({ destination_directory })}
            title="选择监控目标目录"
          />
        </div>
      </div>

      {destinationInsideSource ? (
        <p className="status warning">
          目标目录位于被监控源目录内。Xona 将自动排除{" "}
          {draft.destination_directory}。
        </p>
      ) : null}

      <div className="segmented" aria-label="监控模式">
        <button
          aria-pressed={draft.realtime}
          className="button-compact"
          type="button"
          onClick={() => patch({ realtime: true })}
        >
          实时
        </button>
        <button
          aria-pressed={!draft.realtime}
          className="button-compact"
          type="button"
          onClick={() => patch({ realtime: false })}
        >
          轮询
        </button>
      </div>

      <div className="grid four">
        <CheckboxField
          checked={draft.enabled}
          label="启用"
          onChange={(enabled) => patch({ enabled })}
        />
        <CheckboxField
          checked={draft.recursive}
          label="递归"
          onChange={(recursive) => patch({ recursive })}
        />
        <FormField label="轮询间隔（秒）">
          <input
            min={1}
            placeholder="60"
            type="number"
            value={draft.polling_interval_seconds}
            onChange={(event) =>
              patch({ polling_interval_seconds: Number(event.target.value) })
            }
          />
        </FormField>
        <FormField label="稳定等待时间（秒）">
          <input
            min={0}
            placeholder="30"
            type="number"
            value={draft.stability_seconds}
            onChange={(event) =>
              patch({ stability_seconds: Number(event.target.value) })
            }
          />
        </FormField>
        <FormField label="稳定检查次数">
          <input
            min={1}
            placeholder="2"
            type="number"
            value={draft.stable_check_count}
            onChange={(event) =>
              patch({ stable_check_count: Number(event.target.value) })
            }
          />
        </FormField>
        <FormField label="置信度阈值">
          <input
            max={100}
            min={0}
            placeholder="92"
            type="number"
            value={draft.confidence_threshold}
            onChange={(event) =>
              patch({ confidence_threshold: Number(event.target.value) })
            }
          />
        </FormField>
        <FormField label="资源缺失处理">
          <select
            value={draft.asset_policy}
            onChange={(event) => patch({ asset_policy: event.target.value })}
          >
            <option value="strict">缺失停止整理</option>
            <option value="lenient">缺失继续整理</option>
          </select>
        </FormField>
      </div>

      <div className="segmented" aria-label="整理模式">
        {modeOptions.map((mode) => (
          <button
            aria-pressed={organizationModeOrCopy(draft.organization_mode) === mode}
            className="button-compact"
            key={mode}
            type="button"
            onClick={() => patch({ organization_mode: mode })}
          >
            {organizationModeLabel(mode)}
          </button>
        ))}
      </div>

      <div className="grid two">
        <FormField label="文件夹模板">
          <textarea
            placeholder={'{studio}\n{title}'}
            value={draft.folder_templates.join("\n")}
            onChange={(event) =>
              patch({
                folder_templates: lines(event.target.value),
              })
            }
          />
        </FormField>
        <FormField label="文件名模板">
          <input
            placeholder="{xchina_id} - {title}"
            value={draft.filename_template}
            onChange={(event) => patch({ filename_template: event.target.value })}
          />
        </FormField>
      </div>

      <div className="grid three">
        <CheckboxField
          checked={Boolean(draft.metadata_options.write_nfo)}
          label="写入 .nfo 元数据"
          onChange={(checked) => patchMetadata("write_nfo", checked)}
        />
        <CheckboxField
          checked={Boolean(draft.metadata_options.poster)}
          label="下载海报图片"
          onChange={(checked) => patchMetadata("poster", checked)}
        />
        <CheckboxField
          checked={Boolean(draft.metadata_options.fanart)}
          label="下载 fanart 图片"
          onChange={(checked) => patchMetadata("fanart", checked)}
        />
        <CheckboxField
          checked={Boolean(draft.metadata_options.actor_outputs)}
          label="写入 .actors 输出"
          onChange={(checked) => patchMetadata("actor_outputs", checked)}
        />
        <CheckboxField
          checked={Boolean(draft.metadata_options.include_source_snapshot)}
          label="保存来源页面快照"
          onChange={(checked) => patchMetadata("include_source_snapshot", checked)}
        />
        <CheckboxField
          checked={Boolean(draft.emby_options.notify)}
          label="本地完成后通知 Emby"
          onChange={(checked) => patchEmby("notify", checked)}
        />
        <CheckboxField
          checked={Boolean(draft.emby_options.retry_on_failure)}
          label="重试 Emby 通知"
          onChange={(checked) => patchEmby("retry_on_failure", checked)}
        />
      </div>

      <div className="grid three">
        <FormField label="包含模式">
          <textarea
            placeholder={'*.mkv\n*.mp4'}
            value={draft.include_patterns.join("\n")}
            onChange={(event) => patch({ include_patterns: lines(event.target.value) })}
          />
        </FormField>
        <FormField label="排除模式">
          <textarea
            placeholder={'*.sample.*\n@eaDir/**'}
            value={draft.exclude_patterns.join("\n")}
            onChange={(event) => patch({ exclude_patterns: lines(event.target.value) })}
          />
        </FormField>
        <div className="path-field path-field-textarea">
          <FormField
            description="每行一个目录前缀，也可选择后追加。"
            label="已排除目标前缀"
          >
            <textarea
              placeholder="/downloads/incoming/organized"
              value={draft.excluded_destination_prefixes.join("\n")}
              onChange={(event) =>
                patch({ excluded_destination_prefixes: lines(event.target.value) })
              }
            />
          </FormField>
          <DirectoryPicker
            buttonLabel="添加前缀"
            initialPath={draft.destination_directory || draft.source_directory}
            onSelect={addExcludedDestinationPrefix}
            title="选择排除前缀目录"
          />
        </div>
      </div>

      <button className="primary" type="button" onClick={onSubmit}>
        {draft.rule_id ? "更新监控规则" : "创建监控规则"}
      </button>
    </div>
  );
}

function organizationModeLabel(mode: OrganizationMode): string {
  switch (mode) {
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
  }
}

function organizationModeOrCopy(mode: string): OrganizationMode {
  return mode === "preview" ? "copy" : (mode as OrganizationMode);
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
