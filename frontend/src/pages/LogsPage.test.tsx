import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LogsPage } from "./LogsPage";
import { installFetchMock } from "../test/mockFetch";

class MockEventSource {
  static instances: MockEventSource[] = [];
  readonly url: string;
  readonly listeners = new Map<string, (event: MessageEvent) => void>();
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    this.listeners.set(type, listener);
  }

  emit(type: string, data: unknown) {
    this.listeners.get(type)?.({ data: JSON.stringify(data) } as MessageEvent);
  }

  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LogsPage", () => {
  it("loads recent logs, streams live entries, filters and clears UI logs", async () => {
    installFetchMock([
      {
        path: "/api/logs/recent?limit=100",
        response: {
          entries: [
            {
              id: 1,
              timestamp: "2026-07-24T03:00:00+00:00",
              level: "INFO",
              logger: "backend.app.main",
              component: "app",
              message: "Xona application started",
              source: "application",
            },
          ],
          docker_logs_note: "Xona application logs are written to stdout, so they are visible with docker logs.",
        },
      },
      {
        path: "/api/logs/recent?limit=100&level=ERROR",
        response: {
          entries: [
            {
              id: 3,
              timestamp: "2026-07-24T03:00:02+00:00",
              level: "ERROR",
              logger: "backend.app.worker",
              component: "service.worker",
              message: "Worker failed without token=********",
              source: "application",
            },
          ],
          docker_logs_note: "Xona application logs are written to stdout, so they are visible with docker logs.",
        },
      },
    ]);

    render(<LogsPage />);

    expect(await screen.findByText("Xona application started")).toBeTruthy();
    expect(screen.getAllByText(/docker logs/i).length).toBeGreaterThan(0);
    expect(MockEventSource.instances[0]?.url).toBe("/api/logs/stream");

    MockEventSource.instances[0]?.emit("log", {
      id: 2,
      timestamp: "2026-07-24T03:00:01+00:00",
      level: "WARNING",
      logger: "backend.app.monitor",
      component: "service.monitor",
      message: "Monitor warning",
      source: "application",
    });
    expect(await screen.findByText("Monitor warning")).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/级别筛选/i), {
      target: { value: "ERROR" },
    });
    expect(await screen.findByText("Worker failed without token=********")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "清屏" }));
    await waitFor(() => expect(screen.queryByText("Worker failed without token=********")).toBeNull());
    expect(screen.getByText(/暂无日志/i)).toBeTruthy();
  });

  it("uses the shared error notice when recent logs cannot be loaded", async () => {
    installFetchMock([
      {
        path: "/api/logs/recent?limit=100",
        response: { detail: "日志服务暂不可用" },
        status: 503,
      },
    ]);

    render(<LogsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("日志加载失败");
    expect(screen.getByRole("alert")).toHaveTextContent("日志服务暂不可用");
    expect(screen.getByRole("button", { name: "重试" })).toBeTruthy();
  });

  it("keeps recent logs usable when live streaming or docker note is unavailable", async () => {
    vi.stubGlobal("EventSource", undefined);
    installFetchMock([
      {
        path: "/api/logs/recent?limit=100",
        response: { entries: [] },
      },
    ]);

    render(<LogsPage />);

    expect(await screen.findByText("暂无日志")).toBeTruthy();
    expect(screen.getAllByText(/docker logs/i).length).toBeGreaterThan(0);
  });
});
