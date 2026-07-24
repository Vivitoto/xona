import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ActorLibraryPage } from "./ActorLibraryPage";
import { installFetchMock } from "../test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ActorLibraryPage", () => {
  it("supports actor filtering, aliases, merge, portrait replacement, refresh, works, and Emby sync", async () => {
    const { calls } = installFetchMock([
      {
        path: "/api/actors",
        response: { actors: [actorFixture()] },
      },
      {
        path: "/api/actors?search=Actor&missing_image=true",
        response: { actors: [actorFixture()] },
      },
      {
        method: "PUT",
        path: "/api/actors/1/aliases",
        response: actorFixture({ aliases: ["Alias One", "Alias Two"] }),
      },
      {
        method: "POST",
        path: "/api/actors/1/merge",
        response: actorFixture({ aliases: ["Alias One", "Actor 1"] }),
      },
      {
        method: "POST",
        path: "/api/actors/1/portrait",
        response: {
          actor: actorFixture({ portrait_source_url: "blob:portrait" }),
          sha256: "portrait-sha",
          size_bytes: 18,
        },
      },
      {
        method: "POST",
        path: "/api/actors/1/refresh",
        response: {
          actor: actorFixture({ aliases: ["Alias New"] }),
          diagnostics: { api_key: "secret" },
        },
      },
      {
        path: "/api/actors/1/works",
        response: { actor_id: 1, works: [{ title: "Sample Work" }] },
      },
      {
        method: "POST",
        path: "/api/actors/1/sync-emby",
        response: {
          actor: actorFixture({ emby_person_id: "person-1" }),
          uploaded_portrait: true,
          diagnostics: { token: "secret" },
        },
      },
    ]);

    render(<ActorLibraryPage />);

    expect(await screen.findByText("Actor One")).toBeTruthy();
    expect(
      screen.getByRole("img", { name: "Actor One 缺少头像" }),
    ).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/演员搜索/i), {
      target: { value: "Actor" },
    });
    fireEvent.click(screen.getByLabelText(/仅缺少图片/i));
    fireEvent.click(screen.getByRole("button", { name: "筛选演员" }));
    await waitFor(() =>
      expect(
        calls.some(
          (call) => call.url === "/api/actors?search=Actor&missing_image=true",
        ),
      ).toBe(true),
    );

    fireEvent.change(screen.getByLabelText(/Actor One 的别名/i), {
      target: { value: "Alias One\nAlias Two" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存别名" }));
    expect(await screen.findByText(/已保存/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "合并" }));
    fireEvent.change(screen.getByLabelText(/重复演员 ID/i), {
      target: { value: "2" },
    });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "合并" }));
    expect(await screen.findByText(/已合并演员 2/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "替换图片" }));
    expect(await screen.findByText(/头像已替换/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    expect(await screen.findByText(/演员已刷新/)).toBeTruthy();
    expect(screen.queryByText("secret")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "关联作品" }));
    expect(await screen.findByText("Sample Work")).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "同步" }));
    fireEvent.click(screen.getByRole("button", { name: "同步 Emby" }));
    expect(await screen.findByText(/Emby 同步已上传头像/)).toBeTruthy();
    expect(screen.queryByText("secret")).toBeNull();

    await waitFor(() => {
      for (const path of [
        "/api/actors/1/aliases",
        "/api/actors/1/merge",
        "/api/actors/1/portrait",
        "/api/actors/1/refresh",
        "/api/actors/1/works",
        "/api/actors/1/sync-emby",
      ]) {
        expect(calls.some((call) => call.url === path)).toBe(true);
      }
    });
  });
});

function actorFixture(patch: Partial<ReturnType<typeof baseActor>> = {}) {
  return { ...baseActor(), ...patch };
}

function baseActor() {
  return {
    id: 1,
    canonical_name: "Actor One",
    aliases: ["Alias One"],
    source: "xchina",
    source_id: "ACT-001",
    profile_url: "https://xchina.example.test/models/actor-one.html",
    portrait_source_url: null,
    portrait_cache_path: null,
    portrait_sha256: null,
    portrait_size_bytes: null,
    biography: null,
    profile_fields: {},
    associated_works: [],
    emby_person_id: null,
    linked_works: [],
  };
}
