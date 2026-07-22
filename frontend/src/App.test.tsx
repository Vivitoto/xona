import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders a heading named Xona", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Xona" })).toBeTruthy();
  });
});
