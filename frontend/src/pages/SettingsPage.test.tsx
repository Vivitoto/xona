import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AppSettings } from "../api/types";
import { SettingsPage } from "./SettingsPage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SettingsPage", () => {
  it("renders all settings sections and keeps FlareSolverr endpoint exact", async () => {
    installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      { method: "PUT", path: "/api/settings", response: settingsFixture() },
    ]);

    render(<SettingsPage />);

    expect(await screen.findByRole("heading", { name: "XChina" })).toBeTruthy();

    expect(
      screen.getByLabelText(/精确 FlareSolverr 端点/i),
    ).toHaveValue("http://solver:8191/custom");
    expect(
      screen.getByText(/客户端不会追加 \/v1/i),
    ).toBeTruthy();
    expect(screen.getByLabelText(/代理 URL/i)).toHaveValue(
      "http://********:********@proxy.test:8080",
    );

    for (const heading of [
      "Emby",
      "媒体目录",
      "命名模板",
      "元数据/资源",
      "置信度/安全",
      "认证",
    ]) {
      fireEvent.click(screen.getByRole("tab", { name: heading }));
      expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    }
  });

  it("omits unchanged secret placeholders and submits explicit new secrets", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      { method: "PUT", path: "/api/settings", response: settingsFixture() },
    ]);

    render(<SettingsPage />);

    await screen.findByRole("heading", { name: "XChina" });
    fireEvent.click(screen.getByRole("tab", { name: "Emby" }));
    await screen.findByLabelText(/Emby API key/i);
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const firstPut = calls.find((call) => call.method === "PUT");
    expect(JSON.stringify(firstPut?.body)).not.toContain("********");
    expect((firstPut?.body as AppSettings).emby).not.toHaveProperty("api_key");
    expect((firstPut?.body as AppSettings).xchina).not.toHaveProperty("proxy_url");

    fireEvent.change(screen.getByLabelText(/Emby API key/i), {
      target: { value: "new-emby-key" },
    });
    fireEvent.click(screen.getByRole("tab", { name: "XChina" }));
    fireEvent.change(screen.getByLabelText(/代理 URL/i), {
      target: { value: "http://user:pass@proxy.test:8080" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(calls.filter((call) => call.method === "PUT")).toHaveLength(2),
    );
    const secondPut = calls.filter((call) => call.method === "PUT")[1];
    expect((secondPut.body as AppSettings).emby.api_key).toBe("new-emby-key");
    expect((secondPut.body as AppSettings).xchina.proxy_url).toBe(
      "http://user:pass@proxy.test:8080",
    );
  });

  it("previews naming templates through the backend endpoint", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      {
        method: "POST",
        path: "/api/settings/templates/preview",
        response: {
          folder_path: "Studio/Sample Work",
          filename: "XC-001 - Sample Work",
          validation_errors: [],
          warnings: [],
        },
      },
    ]);

    render(<SettingsPage />);
    await screen.findByRole("heading", { name: "XChina" });
    fireEvent.click(screen.getByRole("tab", { name: "命名模板" }));
    await screen.findByLabelText(/文件名模板/i);
    fireEvent.click(screen.getByRole("button", { name: "预览命名模板" }));

    expect(await screen.findByText("XC-001 - Sample Work")).toBeTruthy();
    expect(
      calls.some(
        (call) =>
          call.method === "POST" &&
          call.url === "/api/settings/templates/preview",
      ),
    ).toBe(true);
  });

  it("blocks saving when preflight validation finds template errors", async () => {
    const { calls } = installFetchMock([
      { path: "/api/settings", response: settingsFixture() },
      { method: "PUT", path: "/api/settings", response: settingsFixture() },
    ]);

    render(<SettingsPage />);
    await screen.findByRole("heading", { name: "XChina" });
    fireEvent.click(screen.getByRole("tab", { name: "命名模板" }));
    fireEvent.change(await screen.findByLabelText(/文件名模板/i), {
      target: { value: "{unknown_variable}" },
    });

    expect(await screen.findByText(/命名模板包含未知变量/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "保存设置" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
    expect(calls.filter((call) => call.method === "PUT")).toHaveLength(0);
  });
});

function settingsFixture(): AppSettings {
  return {
    storage: { roots: ["/media"] },
    xchina: {
      base_url: "https://www.xchina.co",
      flaresolverr_url: "http://solver:8191/custom",
      proxy_url: "http://********:********@proxy.test:8080",
      cache_dir: "/config/cache/xchina",
    },
    emby: {
      enabled: true,
      server_url: "http://emby.test",
      api_key: "********",
      path_mappings: [{ container_root: "/media", emby_root: "/visible" }],
      upload_actor_portraits: true,
    },
    naming: {
      folder_templates: ["{studio}", "{title}"],
      filename_template: "{xchina_id} - {title}",
    },
    metadata_assets: {
      write_nfo: true,
      include_source_snapshot: false,
      asset_policy: "strict",
      max_asset_bytes: 10485760,
    },
    confidence_safety: {
      confidence_threshold: 92,
      refuse_destination_collisions: true,
      refuse_unresolved_multipart: true,
      cache_dir: "/config/cache/safety",
    },
    auth: {
      enabled: false,
      username: "vito",
    },
  };
}
