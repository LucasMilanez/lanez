import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./test-utils";
import { BriefingsListPage } from "@/pages/BriefingsListPage";

beforeEach(() => {
  vi.mocked(global.fetch).mockReset();
});

describe("BriefingsListPage", () => {
  it("renders with mocked data", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      headers: new Headers({ "content-type": "application/json" }),
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

    renderWithProviders(<BriefingsListPage />);

    await waitFor(() => {
      expect(screen.getByText("Reunião de planejamento")).toBeInTheDocument();
      expect(screen.getByText("Sprint review")).toBeInTheDocument();
      expect(screen.getByText("Daily standup")).toBeInTheDocument();
    });
  });
});
