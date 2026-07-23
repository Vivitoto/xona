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
      setError(exc instanceof Error ? exc.message : "Browse failed");
    }
  }

  return (
    <Section title="Storage Roots">
      <div className="grid two">
        <FormField
          description="One mounted root per line. Roots are validated by the backend before use."
          label="Storage roots"
        >
          <textarea
            value={listToLines(settings.roots)}
            onChange={(event) =>
              onChange({ roots: linesToList(event.target.value) })
            }
          />
        </FormField>
        <div className="inline-panel">
          <h3>Source Browse</h3>
          <div className="grid two">
            <FormField label="Root ID">
              <input
                inputMode="numeric"
                value={browseRootId}
                onChange={(event) => setBrowseRootId(event.target.value)}
              />
            </FormField>
            <FormField label="Relative path">
              <input
                value={browsePath}
                onChange={(event) => setBrowsePath(event.target.value)}
              />
            </FormField>
          </div>
          <button type="button" onClick={browse}>
            Browse source
          </button>
          {error ? <p className="status error">{error}</p> : null}
          {browseResult ? (
            <ul className="dense-list" aria-label="Browse entries">
              {browseResult.entries.map((entry) => (
                <li key={entry.path}>
                  <button
                    className="link-button"
                    disabled={!entry.is_dir}
                    type="button"
                    onClick={() => setBrowsePath(entry.path)}
                  >
                    {entry.is_dir ? "Directory" : "File"} {entry.name}
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
