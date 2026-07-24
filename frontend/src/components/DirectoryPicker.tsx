import { useId, useState } from "react";

import { apiFetch } from "../api/client";
import type { BrowseResponse, StorageRootList, StorageRootRead } from "../api/types";

export function DirectoryPicker({
  buttonLabel = "选择目录",
  initialPath = "",
  onSelect,
  title = "选择目录",
}: {
  buttonLabel?: string;
  initialPath?: string;
  onSelect: (path: string) => void;
  title?: string;
}) {
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [roots, setRoots] = useState<StorageRootRead[]>([]);
  const [selectedRoot, setSelectedRoot] = useState<StorageRootRead | null>(null);
  const [currentPath, setCurrentPath] = useState("");
  const [browseResult, setBrowseResult] = useState<BrowseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadRoots(path = initialPath) {
    setError("");
    setLoading(true);
    try {
      const response = await apiFetch<StorageRootList>("/api/storage-roots");
      setRoots(response.roots);
      const root = findRootForPath(response.roots, path) ?? response.roots[0] ?? null;
      setSelectedRoot(root);
      if (root) {
        await browse(root, toRelativePath(path, root.path));
      } else {
        setBrowseResult(null);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载存储根");
    } finally {
      setLoading(false);
    }
  }

  async function browse(root = selectedRoot, path = currentPath) {
    if (!root) {
      setError("请先配置存储根目录");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const query = new URLSearchParams({
        root_id: String(root.id),
        path,
      });
      const response = await apiFetch<BrowseResponse>(
        `/api/storage-roots/browse?${query}`,
      );
      setSelectedRoot(response.root);
      setBrowseResult(response);
      setCurrentPath(toRelativePath(path, response.root.path));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "目录浏览失败");
    } finally {
      setLoading(false);
    }
  }

  function openPicker() {
    setOpen(true);
    setCurrentPath("");
    setBrowseResult(null);
    void loadRoots();
  }

  function switchRoot(root: StorageRootRead) {
    setSelectedRoot(root);
    void browse(root, "");
  }

  function enterDirectory(path: string) {
    if (!selectedRoot) {
      return;
    }
    void browse(selectedRoot, toRelativePath(path, selectedRoot.path));
  }

  function goUp() {
    if (!selectedRoot) {
      return;
    }
    void browse(selectedRoot, parentPath(currentPath));
  }

  function selectCurrentDirectory() {
    if (!selectedRoot) {
      return;
    }
    onSelect(joinPath(selectedRoot.path, currentPath));
    setOpen(false);
  }

  return (
    <>
      <button className="secondary" type="button" onClick={openPicker}>
        {buttonLabel}
      </button>
      {open ? (
        <div
          aria-labelledby={titleId}
          aria-modal="true"
          className="dialog-backdrop"
          role="dialog"
        >
          <div className="dialog directory-picker-dialog">
            <div className="row row-between">
              <div>
                <h2 id={titleId}>{title}</h2>
                <p className="muted">选择一个存储根，然后点击目录逐层进入。</p>
              </div>
              <button className="secondary" type="button" onClick={() => setOpen(false)}>
                关闭
              </button>
            </div>

            {roots.length ? (
              <div className="root-picker" aria-label="存储根列表">
                {roots.map((root) => (
                  <button
                    aria-pressed={selectedRoot?.id === root.id}
                    className="root-option"
                    key={root.id}
                    type="button"
                    onClick={() => switchRoot(root)}
                  >
                    <span className="root-name">{root.path}</span>
                    <span className="badge">{root.source === "env" ? "环境变量" : "用户"}</span>
                  </button>
                ))}
              </div>
            ) : null}

            <div className="directory-toolbar">
              <button disabled={loading || !selectedRoot} type="button" onClick={() => void browse()}>
                刷新
              </button>
              <button
                className="secondary"
                disabled={loading || !selectedRoot || !currentPath}
                type="button"
                onClick={goUp}
              >
                上一层
              </button>
              <button
                className="secondary"
                disabled={!selectedRoot}
                type="button"
                onClick={selectCurrentDirectory}
              >
                选择当前目录
              </button>
            </div>

            {error ? <p className="status error">{error}</p> : null}
            {browseResult && selectedRoot ? (
              <div className="directory-browser">
                <p className="directory-path">
                  当前目录：<code>{joinPath(selectedRoot.path, currentPath)}</code>
                </p>
                {browseResult.entries.length ? (
                  <ul className="directory-tree" aria-label="目录浏览结果">
                    {browseResult.entries.map((entry) => (
                      <li key={entry.path}>
                        <button
                          className="directory-entry"
                          disabled={!entry.is_dir}
                          type="button"
                          onClick={() => enterDirectory(entry.path)}
                        >
                          <span className="directory-icon" aria-hidden="true">
                            {entry.is_dir ? "📁" : "📄"}
                          </span>
                          <span className="directory-main">
                            <strong>{entry.name}</strong>
                            <small>{entry.path}</small>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">当前目录为空。</p>
                )}
              </div>
            ) : (
              <p className="muted">
                {loading ? "加载中..." : "请先配置或选择一个存储根目录。"}
              </p>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}

function findRootForPath(roots: StorageRootRead[], path: string): StorageRootRead | null {
  const normalizedPath = normalizeSeparators(path);
  if (!normalizedPath) {
    return null;
  }
  return (
    roots
      .filter((root) => {
        const rootPath = normalizeSeparators(root.path).replace(/\/+$/g, "");
        return normalizedPath === rootPath || normalizedPath.startsWith(`${rootPath}/`);
      })
      .sort((left, right) => right.path.length - left.path.length)[0] ?? null
  );
}

function toRelativePath(path: string, rootPath: string): string {
  const normalizedPath = normalizeSeparators(path);
  const normalizedRoot = normalizeSeparators(rootPath).replace(/\/+$/g, "");
  if (!normalizedPath || normalizedPath === normalizedRoot) {
    return "";
  }
  if (normalizedPath.startsWith(`${normalizedRoot}/`)) {
    return normalizedPath.slice(normalizedRoot.length + 1);
  }
  return normalizedPath.replace(/^\/+/, "");
}

function parentPath(path: string): string {
  const normalized = normalizeSeparators(path).replace(/\/+$/g, "");
  if (!normalized) {
    return "";
  }
  const index = normalized.lastIndexOf("/");
  return index <= 0 ? "" : normalized.slice(0, index);
}

function joinPath(rootPath: string, relativePath: string): string {
  const normalizedRoot = normalizeSeparators(rootPath).replace(/\/+$/g, "");
  const normalizedRelative = normalizeSeparators(relativePath).replace(/^\/+/, "");
  return normalizedRelative ? `${normalizedRoot}/${normalizedRelative}` : normalizedRoot;
}

function normalizeSeparators(path: string): string {
  return path.trim().replace(/\\/g, "/");
}
