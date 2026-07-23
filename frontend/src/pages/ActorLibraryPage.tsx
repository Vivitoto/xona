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
      setError(exc instanceof Error ? exc.message : "无法加载演员");
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
    setStatus(`已保存 ${response.canonical_name} 的别名`);
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
      setStatus(`已合并演员 ${duplicateActorId}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "演员合并失败");
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
    setStatus(`头像已替换（${response.size_bytes} 字节）`);
  }

  async function refreshActor(actor: ActorRead) {
    const response = await apiFetch<ActorRefreshResponse>(
      `/api/actors/${actor.id}/refresh`,
      { method: "POST" },
    );
    replaceActor(response.actor);
    setStatus(`演员已刷新 ${redactText(response.diagnostics)}`);
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
      `Emby 同步${response.uploaded_portrait ? "已上传头像" : "已关联"} ${redactText(
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
      <Section title="演员库">
        <div className="grid four">
          <FormField label="演员搜索">
            <input value={search} onChange={(event) => setSearch(event.target.value)} />
          </FormField>
          <CheckboxField
            checked={missingImage}
            label="仅缺少图片"
            onChange={setMissingImage}
          />
          <FormField label="替换头像文件">
            <input accept="image/*" type="file" onChange={portraitChange} />
          </FormField>
          <button type="button" onClick={loadActors}>
            筛选演员
          </button>
        </div>

        <table>
          <caption>演员</caption>
          <thead>
            <tr>
              <th>头像</th>
              <th>名称</th>
              <th>别名</th>
              <th>关联作品</th>
              <th>Emby</th>
              <th>操作</th>
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
                      aria-label={`${actor.canonical_name} 的别名`}
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
                      关联作品
                    </button>
                    <ul className="dense-list">
                      {(works[actor.id] ?? actor.linked_works ?? []).map((work, index) => (
                        <li key={index}>{workTitle(work)}</li>
                      ))}
                    </ul>
                  </td>
                  <td>{actor.emby_person_id ?? "未关联"}</td>
                  <td>
                    <div className="button-column">
                      <button type="button" onClick={() => saveAliases(actor)}>
                        保存别名
                      </button>
                      <button type="button" onClick={() => setMergeActor(actor)}>
                        合并
                      </button>
                      <button type="button" onClick={() => replacePortrait(actor)}>
                        替换图片
                      </button>
                      <button type="button" onClick={() => refreshActor(actor)}>
                        刷新
                      </button>
                      <button type="button" onClick={() => syncEmby(actor)}>
                        同步 Emby
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6}>未找到演员。</td>
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
