import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
let preventExpectedError: (event: ErrorEvent) => void;

beforeEach(() => {
  preventExpectedError = (event: ErrorEvent) => {
    if (event.error instanceof Error && event.error.message.includes("page")) {
      event.preventDefault();
    }
    if (event.error instanceof Error && event.error.message.includes("temporary")) {
      event.preventDefault();
    }
  };
  window.addEventListener("error", preventExpectedError);
  consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
});

afterEach(() => {
  window.removeEventListener("error", preventExpectedError);
  consoleErrorSpy.mockRestore();
});

describe("ErrorBoundary", () => {
  it("shows a friendly fallback, error summary, and home action", () => {
    const onReturnHome = vi.fn();

    render(
      <ErrorBoundary resetKey="manual" onReturnHome={onReturnHome}>
        <CrashProbe />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("页面出错了");
    expect(screen.getByLabelText("错误摘要")).toHaveTextContent("boom from page");
    expect(consoleErrorSpy).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "返回仪表盘" }));
    expect(onReturnHome).toHaveBeenCalledTimes(1);
  });

  it("can retry the current page after a transient render failure", () => {
    let shouldThrow = true;
    render(
      <ErrorBoundary resetKey="logs">
        <SwitchableCrashProbe shouldThrow={() => shouldThrow} />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("页面出错了");

    shouldThrow = false;
    fireEvent.click(screen.getByRole("button", { name: "重试当前页面" }));
    expect(screen.getByText("页面恢复")).toBeTruthy();
  });

  it("resets when resetKey changes, matching page navigation behavior", () => {
    const { rerender } = render(
      <ErrorBoundary resetKey="logs">
        <CrashProbe />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("页面出错了");

    rerender(
      <ErrorBoundary resetKey="dashboard">
        <p>仪表盘页面正常</p>
      </ErrorBoundary>,
    );

    expect(screen.getByText("仪表盘页面正常")).toBeTruthy();
  });
});

function CrashProbe() {
  throw new Error("boom from page");
}

function SwitchableCrashProbe({ shouldThrow }: { shouldThrow: () => boolean }) {
  if (shouldThrow()) {
    throw new Error("temporary page failure");
  }
  return <p>页面恢复</p>;
}
