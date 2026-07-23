import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { installFetchMock } from "./test/mockFetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders a heading named Xona", () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
      { path: "/api/actors", response: { actors: [] } },
    ]);
    render(<App />);

    expect(screen.getByRole("heading", { name: "Xona" })).toBeTruthy();
  });

  it("exposes every first-release navigation destination", () => {
    installFetchMock([
      { path: "/api/jobs?state=review_required", response: { jobs: [] } },
      { path: "/api/watch-rules", response: { rules: [] } },
      { path: "/api/actors", response: { actors: [] } },
    ]);
    render(<App />);

    for (const name of [
      "Dashboard",
      "Manual Organizer",
      "Automatic Monitors",
      "Review Queue",
      "Task Center",
      "Actor Library",
      "History/Rollback",
      "Settings",
    ]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
  });
});
