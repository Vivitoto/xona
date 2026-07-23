import { useState } from "react";

import { apiFetch } from "../../api/client";
import type { AppSettings, BrowseResponse } from "../../api/types";
import { FormField, Section } from "../../components/FormField";
import { linesToList, listToLines } from "./settingsForm";

export function StorageSettings({
  settings,
  onChange,
}: {
  settings: AppSettings["storage"];
  onChange: (patch: Partial<AppSettings["storage"]>) => void;
}) {
  const [browseRootId, setBrowseRootId] = useState("1");
  const [browsePath, setBrowsePath] = useState("");
  const [browseResult, setBrowseResult] = useState<BrowseResponse | null>(null);
  const [error, setError] = useState("");

  async function browse() {
    setError("");
    try {
      const query = new URLSearchParams({
        root_id: browseRootId,
        path: browsePath,
      });
      setBrowseResult(
        await apiFetch<BrowseResponse>(`/api/storage-roots/browse?${query}`),
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "浏览失败");
    }
  }

  return (
    <Section title="存储根">
      <div className="grid two">
        <FormField
          description="每行一个挂载根目录。后端会在使用前验证这些根目录。"
          label="存储根"
        >
          <textarea
            value={listToLines(settings.roots)}
            onChange={(event) =>
              onChange({ roots: linesToList(event.target.value) })
            }
          />
        </FormField>
        <div className="inline-panel">
          <h3>源浏览</h3>
          <div className="grid two">
            <FormField label="根 ID">
              <input
                inputMode="numeric"
                value={browseRootId}
                onChange={(event) => setBrowseRootId(event.target.value)}
              />
            </FormField>
            <FormField label="相对路径">
              <input
                value={browsePath}
                onChange={(event) => setBrowsePath(event.target.value)}
              />
            </FormField>
          </div>
          <button type="button" onClick={browse}>
            浏览源目录
          </button>
          {error ? <p className="status error">{error}</p> : null}
          {browseResult ? (
            <ul className="dense-list" aria-label="浏览条目">
              {browseResult.entries.map((entry) => (
                <li key={entry.path}>
                  <button
                    className="link-button"
                    disabled={!entry.is_dir}
                    type="button"
                    onClick={() => setBrowsePath(entry.path)}
                  >
                    {entry.is_dir ? "目录" : "文件"} {entry.name}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </Section>
  );
}
