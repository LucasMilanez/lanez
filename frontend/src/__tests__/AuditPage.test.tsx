import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";

// Mock useAuditLog before importing AuditPage
vi.mock("@/hooks/useAuditLog", () => ({
  useAuditLog: vi.fn(),
}));

import { AuditPage } from "@/pages/AuditPage";
import { useAuditLog } from "@/hooks/useAuditLog";

const mockUseAuditLog = useAuditLog as ReturnType<typeof vi.fn>;

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AuditPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AuditPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading skeleton when isLoading", () => {
    mockUseAuditLog.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });
    renderPage();
    // LoadingSkeleton renders divs with animate-pulse
    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows table with badges when items are present", () => {
    mockUseAuditLog.mockReturnValue({
      data: {
        items: [
          {
            id: "1",
            event_type: "mcp.call",
            event_data: { tool_name: "search_emails", success: true },
            success: true,
            error_message: null,
            latency_ms: 100,
            created_at: "2026-04-30T10:00:00Z",
          },
          {
            id: "2",
            event_type: "auth.login",
            event_data: { email: "test@example.com" },
            success: true,
            error_message: null,
            latency_ms: null,
            created_at: "2026-04-30T09:00:00Z",
          },
        ],
        total: 2,
        page: 1,
        page_size: 50,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getAllByText("mcp.call").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("auth.login").length).toBeGreaterThanOrEqual(1);
  });

  it("opens detail dialog when row is clicked", async () => {
    mockUseAuditLog.mockReturnValue({
      data: {
        items: [
          {
            id: "1",
            event_type: "mcp.call",
            event_data: { tool_name: "search_emails" },
            success: true,
            error_message: null,
            latency_ms: 100,
            created_at: "2026-04-30T10:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    renderPage();

    // Click on the row
    const row = screen.getByText("search_emails").closest("tr");
    if (row) fireEvent.click(row);

    // Dialog should show the Detalhes heading and pre with JSON
    expect(screen.getByText("Detalhes")).toBeTruthy();
  });
});
