import { ChangeEvent, useEffect, useState } from "react";

import { apiFetch } from "../api/client";
import type {
  ActorListResponse,
  ActorPortraitResponse,
  ActorRead,
  ActorRefreshResponse,
  ActorSyncEmbyResponse,
  ActorWorksResponse,
} from "../api/types";
import { ActorMergeDialog } from "../components/ActorMergeDialog";
import { ActorPortrait } from "../components/ActorPortrait";
import { CheckboxField, FormField, Section } from "../components/FormField";
import { redactText } from "../utils/redaction";

export function ActorLibraryPage() {
  const [actors, setActors] = useState<ActorRead[]>([]);
  const [search, setSearch] = useState("");
  const [missingImage, setMissingImage] = useState(false);
  const [aliasDrafts, setAliasDrafts] = useState<Record<number, string>>({});
  const [mergeActor, setMergeActor] = useState<ActorRead | null>(null);
  const [selectedPortrait, setSelectedPortrait] = useState<File | null>(null);
  const [works, setWorks] = useState<Record<number, Record<string, unknown>[]>>({});
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function loadActors() {
    setError("");
    const params = new URLSearchParams();
    if (search) {
      params.set("search", search);
    }
    if (missingImage) {
      params.set("missing_image", "true");
    }
    try {
      const response = await apiFetch<ActorListResponse>(
        `/api/actors${params.toString() ? `?${params}` : ""}`,
      );
      setActors(response.actors);
      setAliasDrafts(
        Object.fromEntries(
          response.actors.map((actor) => [actor.id, actor.aliases.join("\n")]),
        ),
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load actors");
    }
  }

  useEffect(() => {
    void loadActors();
  }, []);

  async function saveAliases(actor: ActorRead) {
    const response = await apiFetch<ActorRead>(`/api/actors/${actor.id}/aliases`, {
      method: "PUT",
      body: {
        aliases: lines(aliasDrafts[actor.id] ?? ""),
      },
    });
    replaceActor(response);
    setStatus(`Aliases saved for ${response.canonical_name}`);
  }

  async function mergeDuplicate(duplicateActorId: number) {
    if (!mergeActor || !Number.isFinite(duplicateActorId)) {
      return;
    }
    try {
      const response = await apiFetch<ActorRead>(
        `/api/actors/${mergeActor.id}/merge`,
        {
          method: "POST",
          body: { duplicate_actor_id: duplicateActorId },
        },
      );
      replaceActor(response);
      setMergeActor(null);
      setStatus(`Merged actor ${duplicateActorId}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Actor merge failed");
    }
  }

  async function replacePortrait(actor: ActorRead) {
    const blob = selectedPortrait ?? new Blob(["synthetic portrait"], { type: "image/jpeg" });
    const response = await apiFetch<ActorPortraitResponse>(
      `/api/actors/${actor.id}/portrait`,
      {
        method: "POST",
        headers: {
          "Content-Type": blob.type || "application/octet-stream",
        },
        body: blob,
      },
    );
    replaceActor(response.actor);
    setStatus(`Portrait replaced (${response.size_bytes} bytes)`);
  }

  async function refreshActor(actor: ActorRead) {
    const response = await apiFetch<ActorRefreshResponse>(
      `/api/actors/${actor.id}/refresh`,
      { method: "POST" },
    );
    replaceActor(response.actor);
    setStatus(`Actor refreshed ${redactText(response.diagnostics)}`);
  }

  async function loadWorks(actor: ActorRead) {
    const response = await apiFetch<ActorWorksResponse>(
      `/api/actors/${actor.id}/works`,
    );
    setWorks((current) => ({ ...current, [actor.id]: response.works }));
  }

  async function syncEmby(actor: ActorRead) {
    const response = await apiFetch<ActorSyncEmbyResponse>(
      `/api/actors/${actor.id}/sync-emby`,
      { method: "POST" },
    );
    replaceActor(response.actor);
    setStatus(
      `Emby sync ${response.uploaded_portrait ? "uploaded portrait" : "linked"} ${redactText(
        response.diagnostics,
      )}`,
    );
  }

  function replaceActor(actor: ActorRead) {
    setActors((current) =>
      current.map((entry) => (entry.id === actor.id ? actor : entry)),
    );
    setAliasDrafts((current) => ({
      ...current,
      [actor.id]: actor.aliases.join("\n"),
    }));
  }

  function portraitChange(event: ChangeEvent<HTMLInputElement>) {
    setSelectedPortrait(event.target.files?.[0] ?? null);
  }

  return (
    <div className="page-stack">
      <Section title="Actor Library">
        <div className="grid four">
          <FormField label="Actor search">
            <input value={search} onChange={(event) => setSearch(event.target.value)} />
          </FormField>
          <CheckboxField
            checked={missingImage}
            label="Missing-image only"
            onChange={setMissingImage}
          />
          <FormField label="Replacement portrait file">
            <input accept="image/*" type="file" onChange={portraitChange} />
          </FormField>
          <button type="button" onClick={loadActors}>
            Filter actors
          </button>
        </div>

        <table>
          <caption>Actors</caption>
          <thead>
            <tr>
              <th>Portrait</th>
              <th>Name</th>
              <th>Aliases</th>
              <th>Linked works</th>
              <th>Emby</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {actors.length ? (
              actors.map((actor) => (
                <tr key={actor.id}>
                  <td>
                    <ActorPortrait actor={actor} />
                  </td>
                  <td>
                    <strong>{actor.canonical_name}</strong>
                    <p className="muted">{actor.profile_url ?? actor.source}</p>
                  </td>
                  <td>
                    <textarea
                      aria-label={`Aliases for ${actor.canonical_name}`}
                      value={aliasDrafts[actor.id] ?? ""}
                      onChange={(event) =>
                        setAliasDrafts((current) => ({
                          ...current,
                          [actor.id]: event.target.value,
                        }))
                      }
                    />
                  </td>
                  <td>
                    <button type="button" onClick={() => loadWorks(actor)}>
                      Linked works
                    </button>
                    <ul className="dense-list">
                      {(works[actor.id] ?? actor.linked_works ?? []).map((work, index) => (
                        <li key={index}>{workTitle(work)}</li>
                      ))}
                    </ul>
                  </td>
                  <td>{actor.emby_person_id ?? "Not linked"}</td>
                  <td>
                    <div className="button-column">
                      <button type="button" onClick={() => saveAliases(actor)}>
                        Save aliases
                      </button>
                      <button type="button" onClick={() => setMergeActor(actor)}>
                        Merge
                      </button>
                      <button type="button" onClick={() => replacePortrait(actor)}>
                        Replace image
                      </button>
                      <button type="button" onClick={() => refreshActor(actor)}>
                        Refresh
                      </button>
                      <button type="button" onClick={() => syncEmby(actor)}>
                        Sync Emby
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6}>No actors found.</td>
              </tr>
            )}
          </tbody>
        </table>
        {status ? <p className="status">{status}</p> : null}
        {error ? <p className="status error">{redactText(error)}</p> : null}
      </Section>
      <ActorMergeDialog
        actor={mergeActor}
        onClose={() => setMergeActor(null)}
        onMerge={mergeDuplicate}
      />
    </div>
  );
}

function lines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function workTitle(work: Record<string, unknown>): string {
  return typeof work.title === "string" ? work.title : JSON.stringify(work);
}
