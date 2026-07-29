import { ChangeEvent, useEffect, useState } from "react";
import { UsersRound } from "lucide-react";

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
import { EmptyState } from "../components/EmptyState";
import { CheckboxField, FormField, Section } from "../components/FormField";
import { LoadingSkeleton } from "../components/LoadingSkeleton";
import { Tabs, type TabItem } from "../components/Tabs";
import { redactText } from "../utils/redaction";

type ActorTab = "list" | "sync";

const actorTabs: readonly TabItem<ActorTab>[] = [
  { id: "list", label: "列表" },
  { id: "sync", label: "同步" },
];

export function ActorLibraryPage() {
  const [activeTab, setActiveTab] = useState<ActorTab>("list");
  const [actors, setActors] = useState<ActorRead[]>([]);
  const [search, setSearch] = useState("");
  const [missingImage, setMissingImage] = useState(false);
  const [aliasDrafts, setAliasDrafts] = useState<Record<number, string>>({});
  const [mergeActor, setMergeActor] = useState<ActorRead | null>(null);
  const [selectedPortrait, setSelectedPortrait] = useState<File | null>(null);
  const [works, setWorks] = useState<Record<number, Record<string, unknown>[]>>({});
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadActors() {
    setError("");
    setLoading(true);
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
      const nextActors = Array.isArray(response.actors) ? response.actors : [];
      setActors(nextActors);
      setAliasDrafts(
        Object.fromEntries(
          nextActors.map((actor) => [actor.id, actor.aliases.join("\n")]),
        ),
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载演员");
    } finally {
      setLoading(false);
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
    setWorks((current) => ({
      ...current,
      [actor.id]: Array.isArray(response.works) ? response.works : [],
    }));
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

  async function syncVisibleActors() {
    if (!actors.length) {
      setStatus("没有可同步的演员");
      return;
    }
    for (const actor of actors) {
      await syncEmby(actor);
    }
    setStatus(`已同步 ${actors.length} 位演员`);
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
      <Tabs
        activeTab={activeTab}
        ariaLabel="演员库视图"
        tabs={actorTabs}
        onChange={setActiveTab}
      />
      <div className="tab-panel" role="tabpanel">
        {activeTab === "list" ? (
          <Section title="演员库">
            <div className="grid four">
              <FormField label="演员搜索">
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </FormField>
              <CheckboxField
                checked={missingImage}
                label="仅缺少图片"
                onChange={setMissingImage}
              />
              <FormField label="替换头像文件">
                <input accept="image/*" type="file" onChange={portraitChange} />
              </FormField>
              <div className="field-action">
                <button type="button" onClick={loadActors}>
                  筛选演员
                </button>
              </div>
            </div>

            {loading ? (
              <LoadingSkeleton rows={5} title="正在加载演员库" variant="table" />
            ) : actors.length ? (
              <div className="table-wrap actor-table-wrap">
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
                    {actors.map((actor) => (
                      <tr key={actor.id}>
                        <td>
                          <ActorPortrait actor={actor} />
                        </td>
                        <td>
                          <strong>{actor.canonical_name}</strong>
                          <p className="muted">
                            {actor.profile_url ?? actor.source}
                          </p>
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
                            {(works[actor.id] ?? actor.linked_works ?? []).map(
                              (work, index) => (
                                <li key={index}>{workTitle(work)}</li>
                              ),
                            )}
                          </ul>
                        </td>
                        <td>{actor.emby_person_id ?? "未关联"}</td>
                        <td>
                          <div className="button-column">
                            <button
                              type="button"
                              onClick={() => saveAliases(actor)}
                            >
                              保存别名
                            </button>
                            <button
                              type="button"
                              onClick={() => setMergeActor(actor)}
                            >
                              合并
                            </button>
                            <button
                              type="button"
                              onClick={() => replacePortrait(actor)}
                            >
                              替换图片
                            </button>
                            <button
                              type="button"
                              onClick={() => refreshActor(actor)}
                            >
                              刷新
                            </button>
                            <button type="button" onClick={() => syncEmby(actor)}>
                              同步 Emby
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                actions={[{ label: "刷新演员", onClick: loadActors }]}
                description="暂无本地演员缓存。"
                icon={UsersRound}
                title="未找到演员"
              />
            )}
          </Section>
        ) : (
          <Section title="演员同步">
            <div className="button-row">
              <button type="button" onClick={loadActors}>
                刷新演员列表
              </button>
              <button type="button" onClick={syncVisibleActors}>
                同步全部可见演员
              </button>
            </div>
            {loading ? (
              <LoadingSkeleton rows={4} title="正在加载同步列表" variant="table" />
            ) : actors.length ? (
              <div className="table-wrap actor-table-wrap">
                <table>
                  <caption>演员 Emby 同步</caption>
                  <thead>
                    <tr>
                      <th>头像</th>
                      <th>名称</th>
                      <th>Emby</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {actors.map((actor) => (
                      <tr key={actor.id}>
                        <td>
                          <ActorPortrait actor={actor} />
                        </td>
                        <td>
                          <strong>{actor.canonical_name}</strong>
                          <p className="muted">
                            {actor.profile_url ?? actor.source}
                          </p>
                        </td>
                        <td>{actor.emby_person_id ?? "未关联"}</td>
                        <td>
                          <div className="button-row">
                            <button
                              type="button"
                              onClick={() => refreshActor(actor)}
                            >
                              刷新
                            </button>
                            <button type="button" onClick={() => syncEmby(actor)}>
                              同步 Emby
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                actions={[{ label: "刷新演员列表", onClick: loadActors }]}
                description="没有可同步的演员。完成一次元数据匹配或刷新演员缓存后，再回到这里同步 Emby 人物信息。"
                icon={UsersRound}
                title="没有可同步演员"
              />
            )}
          </Section>
        )}
      </div>
      {status ? <p className="status">{status}</p> : null}
      {error ? <p className="status error">{redactText(error)}</p> : null}
      {activeTab === "list" ? (
        <ActorMergeDialog
          actor={mergeActor}
          onClose={() => setMergeActor(null)}
          onMerge={mergeDuplicate}
        />
      ) : null}
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
