import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { ThemeProvider } from "@/theme/ThemeContext";
import { BriefingsListPage } from "@/pages/BriefingsListPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <BriefingsListPage />
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.mocked(global.fetch).mockReset();
});

describe("BriefingsListPage", () => {
  it("renders with mocked data", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        items: [
          {
            id: "1",
            event_id: "evt-1",
            event_subject: "Reunião de planejamento",
            event_start: "2025-06-01T10:00:00Z",
            event_end: "2025-06-01T11:00:00Z",
            attendees: ["alice@example.com"],
            generated_at: "2025-06-01T09:00:00Z",
          },
          {
            id: "2",
            event_id: "evt-2",
            event_subject: "Sprint review",
            event_start: "2025-06-02T14:00:00Z",
            event_end: "2025-06-02T15:00:00Z",
            attendees: ["bob@example.com"],
            generated_at: "2025-06-02T13:00:00Z",
          },
          {
            id: "3",
            event_id: "evt-3",
            event_subject: "Daily standup",
            event_start: "2025-06-03T09:00:00Z",
            event_end: "2025-06-03T09:15:00Z",
            attendees: ["carol@example.com"],
            generated_at: "2025-06-03T08:00:00Z",
          },
        ],
        total: 3,
        page: 1,
        page_size: 20,
      }),
    } as Response);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Reunião de planejamento")).toBeInTheDocument();
      expect(screen.getByText("Sprint review")).toBeInTheDocument();
      expect(screen.getByText("Daily standup")).toBeInTheDocument();
    });
  });
});
