import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "@/App";

beforeEach(() => {
  vi.mocked(global.fetch).mockReset();
  // /auth/me returns 401 → unauthenticated
  vi.mocked(global.fetch).mockResolvedValue({
    ok: false,
    status: 401,
    statusText: "Unauthorized",
    json: async () => ({ detail: "Não autenticado" }),
  } as Response);
});

describe("App", () => {
  it("renders without crashing", () => {
    render(<App />);
    // App should render — when unauthenticated it shows login
    expect(document.body).toBeTruthy();
  });
});
