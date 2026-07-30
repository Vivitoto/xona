import { useEffect, useMemo, useRef, useState } from "react";
import { ScrollText } from "lucide-react";

import { apiFetch } from "../api/client";
import type { LogEntryRead, LogListResponse } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { CheckboxField, FormField, Section } from "../components/FormField";
import { LoadingSkeleton } from "../components/LoadingSkeleton";

const logLevels = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] as const;
type LogLevelFilter = (typeof logLevels)[number];
const dockerLogsFallback = "也可通过 docker logs 查看。";

export function LogsPage() {
  const [entries, setEntries] = useState<LogEntryRead[]>([]);
  const [level, setLevel] = useState<LogLevelFilter>("ALL");
  const [live, setLive] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const [dockerNote, setDockerNote] = useState(dockerLogsFallback);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  async function loadRecent() {
    setError("");
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (level !== "ALL") {
        params.set("level", level);
      }
      const response = await apiFetch<LogListResponse>(`/api/logs/recent?${params}`);
      setEntries(Array.isArray(response.entries) ? response.entries : []);
      setDockerNote(response.docker_logs_note || dockerLogsFallback);
      setStatus("日志已刷新");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载日志");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadRecent();
  }, [level]);

  useEffect(() => {
    if (!live) {
      return;
    }
    if (typeof EventSource === "undefined") {
      setStatus("当前浏览器不支持实时日志，已保留最近日志");
      return;
    }

    setStatus("实时日志已连接");
    const lastId = entries.at(-1)?.id;
    const url = lastId ? `/api/logs/stream?since_id=${lastId}` : "/api/logs/stream";
    let source: EventSource;
    try {
      source = new EventSource(url);
    } catch {
      setStatus("实时日志连接不可用，已保留最近日志");
      return;
    }

    source.addEventListener("log", (event) => {
      try {
        const entry = JSON.parse((event as MessageEvent).data) as LogEntryRead;
        setEntries((current) => appendEntry(current, entry));
      } catch {
        setError("日志流数据格式异常");
      }
    });
    source.onerror = () => {
      setStatus("实时日志连接中断，浏览器会自动重试");
    };

    return () => source.close();
  }, [live, level]);

  useEffect(() => {
    if (autoScroll) {
      logEndRef.current?.scrollIntoView?.({ block: "end" });
    }
  }, [entries, autoScroll]);

  const visibleEntries = useMemo(
    () => (level === "ALL" ? entries : entries.filter((entry) => entry.level === level)),
    [entries, level],
  );
  const latestErrorCount = entries.filter((entry) => errorLevels.has(entry.level)).length;
  const latestWarningCount = entries.filter((entry) => entry.level === "WARNING").length;

  return (
    <div className="page-stack logs-page">
      <div className="metric-grid">
        <div className="metric metric-primary">
          <span>日志条目</span>
          <strong>{entries.length}</strong>
          <small>最近日志</small>
        </div>
        <div className="metric metric-warning">
          <span>警告</span>
          <strong>{latestWarningCount}</strong>
          <small>WARNING</small>
        </div>
        <div className="metric metric-warning">
          <span>错误</span>
          <strong>{latestErrorCount}</strong>
          <small>ERROR / CRITICAL</small>
        </div>
      </div>

      <Section title="实时日志">
        <div className="section-toolbar">
          <div className="button-row">
            <button type="button" onClick={loadRecent}>
              刷新
            </button>
            <button className="secondary" type="button" onClick={() => setEntries([])}>
              清屏
            </button>
          </div>
        </div>

        <div className="log-controls">
          <FormField label="级别筛选">
            <select value={level} onChange={(event) => setLevel(event.target.value as LogLevelFilter)}>
              {logLevels.map((nextLevel) => (
                <option key={nextLevel} value={nextLevel}>
                  {nextLevel === "ALL" ? "全部" : nextLevel}
                </option>
              ))}
            </select>
          </FormField>
          <CheckboxField checked={live} label="实时跟随" onChange={setLive} />
          <CheckboxField checked={autoScroll} label="自动滚动到底部" onChange={setAutoScroll} />
        </div>

        <p className="muted">{dockerNote}</p>

        {loading && !visibleEntries.length ? (
          <LoadingSkeleton rows={5} title="正在加载日志" variant="table" />
        ) : visibleEntries.length ? (
          <div className="log-console" aria-label="实时日志输出">
            {visibleEntries.map((entry) => (
              <article className="log-line" key={entry.id}>
                <time dateTime={entry.timestamp}>{formatTimestamp(entry.timestamp)}</time>
                <span className={`status-pill ${levelTone(entry.level)}`}>{entry.level}</span>
                <span className="log-source" title={entry.logger}>
                  {entry.component || shortLogger(entry.logger)}
                </span>
                <code>{entry.message}</code>
              </article>
            ))}
            <div ref={logEndRef} />
          </div>
        ) : (
          <EmptyState
            actions={[{ label: "刷新日志", onClick: loadRecent }]}
            description="暂无应用日志。"
            icon={ScrollText}
            title="暂无日志"
          />
        )}
      </Section>

      {status ? <p className="status floating-status">{status}</p> : null}
      {error ? (
        <ErrorNotice
          title="日志加载失败"
          message={error}
          actions={[{ label: "重试", onClick: loadRecent }]}
        />
      ) : null}
    </div>
  );
}

const errorLevels = new Set(["ERROR", "CRITICAL"]);

function appendEntry(entries: LogEntryRead[], nextEntry: LogEntryRead): LogEntryRead[] {
  if (entries.some((entry) => entry.id === nextEntry.id)) {
    return entries;
  }
  return [...entries, nextEntry].slice(-500);
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString();
}

function levelTone(level: string): string {
  if (level === "ERROR" || level === "CRITICAL") {
    return "status-pill-danger";
  }
  if (level === "WARNING") {
    return "status-pill-warning";
  }
  if (level === "INFO") {
    return "status-pill-success";
  }
  return "status-pill-neutral";
}

function shortLogger(logger: string): string {
  if (logger === "backend.app.main") {
    return "app";
  }
  const prefixes: Array<[string, string]> = [
    ["backend.app.api.", "api."],
    ["backend.app.services.", "service."],
    ["backend.app.integrations.", "integration."],
    ["backend.app.core.", "core."],
  ];
  for (const [prefix, label] of prefixes) {
    if (logger.startsWith(prefix)) {
      return `${label}${logger.slice(prefix.length)}`;
    }
  }
  return logger;
}
