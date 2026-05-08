import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/theme/ThemeContext";
import { I18nProvider } from "@/i18n/I18nContext";
import { AuthProvider } from "@/auth/AuthContext";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { makeQueryClient } from "./test-utils";

function wrapper(initialRoute: string) {
  const qc = makeQueryClient();
  return (
    <ThemeProvider>
      <I18nProvider>
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={[initialRoute]}>
            <AuthProvider>
              <Routes>
                {/* A landing real do app vive em "/", não em "/login" */}
                <Route path="/" element={<div>Landing Page</div>} />
                <Route element={<ProtectedRoute />}>
                  <Route path="/dashboard" element={<div>Dashboard Content</div>} />
                </Route>
              </Routes>
            </AuthProvider>
          </MemoryRouter>
        </QueryClientProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}

beforeEach(() => {
  vi.mocked(global.fetch).mockReset();
});

describe("ProtectedRoute", () => {
  it("redirects to / when not authenticated", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Não autenticado" }),
    } as Response);

    render(wrapper("/dashboard"));

    await waitFor(() => {
      expect(screen.getByText("Landing Page")).toBeInTheDocument();
    });
  });

  it("renders content when authenticated", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        id: "123",
        email: "test@example.com",
        token_expires_at: "2025-12-31T00:00:00Z",
        last_sync_at: null,
        created_at: "2025-01-01T00:00:00Z",
      }),
    } as Response);

    render(wrapper("/dashboard"));

    await waitFor(() => {
      expect(screen.getByText("Dashboard Content")).toBeInTheDocument();
    });
  });

  it("shows a spinner while loading, not a blank screen", () => {
    vi.mocked(global.fetch).mockImplementation(
      () => new Promise(() => {}), // never resolves — keeps loading: true
    );

    const { container } = render(wrapper("/dashboard"));

    // Must have visible content (not just an empty/invisible div)
    expect(container.firstChild).not.toBeEmptyDOMElement();
    // Spinner element uses animate-spin
    expect(container.querySelector(".animate-spin")).toBeInTheDocument();
  });
});
