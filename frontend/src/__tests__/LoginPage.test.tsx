import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { ThemeProvider } from "@/theme/ThemeContext";
import { AuthProvider } from "@/auth/AuthContext";
import { LoginPage } from "@/pages/LoginPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AuthProvider>
            <LoginPage />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.mocked(global.fetch).mockReset();
  // Not authenticated
  vi.mocked(global.fetch).mockResolvedValue({
    ok: false,
    status: 401,
    statusText: "Unauthorized",
    json: async () => ({ detail: "Não autenticado" }),
  } as Response);
});

describe("LoginPage", () => {
  it("renders login button", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Entrar com Microsoft")).toBeInTheDocument();
    });
  });
});
