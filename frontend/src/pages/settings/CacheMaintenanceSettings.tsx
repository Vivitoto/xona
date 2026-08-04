import { useEffect, useMemo, useState } from "react";

import { apiFetch } from "../../api/client";
import type {
  CacheAreaStats,
  CacheMaintenanceCleanupResponse,
  CacheMaintenanceResponse,
} from "../../api/types";
import { CheckboxField, Section } from "../../components/FormField";
import { LoadingSkeleton } from "../../components/LoadingSkeleton";

export function CacheMaintenanceSettings() {
  const [stats, setStats] = useState<CacheMaintenanceResponse | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [cleaning, setCleaning] = useState(false);

  async function loadStats() {
    setError("");
    setLoading(true);
    try {
      const payload = await apiFetch<CacheMaintenanceResponse>(
        "/api/settings/cache-maintenance",
      );
      setStats(payload);
      setSelectedKeys((current) =>
        current.filter((key) => payload.areas.some((area) => area.key === key)),
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载缓存概览");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadStats();
  }, []);

  const cleanableAreas = useMemo(
    () => stats?.areas.filter(canCleanupArea) ?? [],
    [stats],
  );
  const allCleanableSelected =
    cleanableAreas.length > 0 &&
    cleanableAreas.every((area) => selectedKeys.includes(area.key));

  function toggleArea(key: string, checked: boolean) {
    setSelectedKeys((current) => {
      if (checked) {
        return current.includes(key) ? current : [...current, key];
      }
      return current.filter((item) => item !== key);
    });
  }

  function toggleAllCleanable(checked: boolean) {
    setSelectedKeys(checked ? cleanableAreas.map((area) => area.key) : []);
  }

  async function cleanupSelected() {
    if (!selectedKeys.length) {
      setError("请先选择要清理的缓存区域。");
      return;
    }
    const labels = stats?.areas
      .filter((area) => selectedKeys.includes(area.key))
      .map((area) => area.label)
      .join("、");
    if (!window.confirm(`确认清理这些缓存？\n${labels}\n不会删除媒体文件或已整理输出目录。`)) {
      return;
    }
    setStatus("");
    setError("");
    setCleaning(true);
    try {
      const result = await apiFetch<CacheMaintenanceCleanupResponse>(
        "/api/settings/cache-maintenance/cleanup",
        { method: "POST", body: { area_keys: selectedKeys } },
      );
      setStatus(
        `缓存清理完成：删除 ${result.deleted_files} 个文件，释放 ${formatBytes(
          result.deleted_bytes,
        )}。`,
      );
      setSelectedKeys([]);
      await loadStats();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "缓存清理失败");
    } finally {
      setCleaning(false);
    }
  }

  return (
    <Section title="缓存维护">
      <p className="section-lead">
        只统计并清理 Xona 配置目录内的缓存：本地元数据截图/封面、素材缓存、演员头像缓存，以及安全配置下的 XChina 页面缓存。不会触碰媒体文件或已整理输出目录。
      </p>

      {loading && !stats ? (
        <LoadingSkeleton rows={4} title="正在加载缓存概览" variant="table" />
      ) : stats ? (
        <>
          <div className="metric-grid metric-grid-compact cache-maintenance-summary">
            <div className="metric metric-primary">
              <span>缓存文件</span>
              <strong>{stats.total_file_count}</strong>
              <small>配置目录内</small>
            </div>
            <div className="metric metric-warning">
              <span>占用空间</span>
              <strong>{formatBytes(stats.total_size_bytes)}</strong>
              <small>估算值</small>
            </div>
            <div className="metric metric-success">
              <span>可清理区域</span>
              <strong>{cleanableAreas.length}</strong>
              <small>安全路径</small>
            </div>
          </div>

          <div className="cache-maintenance-toolbar">
            <CheckboxField
              checked={allCleanableSelected}
              disabled={!cleanableAreas.length || cleaning}
              label="选择全部可清理缓存"
              onChange={toggleAllCleanable}
            />
            <div className="button-row">
              <button
                className="secondary button-compact"
                disabled={loading || cleaning}
                type="button"
                onClick={loadStats}
              >
                刷新概览
              </button>
              <button
                className="button-compact danger-button"
                disabled={!selectedKeys.length || cleaning}
                type="button"
                onClick={cleanupSelected}
              >
                {cleaning ? "正在清理" : "清理所选缓存"}
              </button>
            </div>
          </div>

          <div className="table-wrap cache-maintenance-table">
            <table>
              <caption>缓存维护区域</caption>
              <thead>
                <tr>
                  <th>选择</th>
                  <th>区域</th>
                  <th>路径</th>
                  <th>文件</th>
                  <th>大小</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {stats.areas.map((area) => (
                  <tr key={area.key}>
                    <td>
                      <input
                        aria-label={`选择${area.label}`}
                        checked={selectedKeys.includes(area.key)}
                        disabled={!canCleanupArea(area) || cleaning}
                        type="checkbox"
                        onChange={(event) => toggleArea(area.key, event.target.checked)}
                      />
                    </td>
                    <td>
                      <strong>{area.label}</strong>
                    </td>
                    <td>
                      <code className="path-cell" title={area.path}>{area.path}</code>
                    </td>
                    <td>{area.file_count}</td>
                    <td>{formatBytes(area.size_bytes)}</td>
                    <td>
                      <CacheAreaStatus area={area} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {status ? <p className="status">{status}</p> : null}
      {error ? <p className="status error" role="alert">{error}</p> : null}
    </Section>
  );
}

function CacheAreaStatus({ area }: { area: CacheAreaStats }) {
  if (!area.cleanup_supported) {
    return (
      <span className="status-pill status-pill-warning">
        路径不安全，已禁用清理
      </span>
    );
  }
  if (!area.exists) {
    return <span className="status-pill status-pill-neutral">目录不存在</span>;
  }
  if (!area.file_count) {
    return <span className="status-pill status-pill-neutral">空缓存</span>;
  }
  return <span className="status-pill status-pill-success">可清理</span>;
}

function canCleanupArea(area: CacheAreaStats): boolean {
  return area.cleanup_supported && area.exists && area.file_count > 0;
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  const units = ["KB", "MB", "GB", "TB"];
  let size = value / 1024;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  const precision = size >= 10 ? 1 : 2;
  return `${size.toFixed(precision)} ${units[unitIndex]}`;
}
