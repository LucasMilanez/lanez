import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { ThemeProvider } from "@/theme/ThemeContext";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/hooks/useCreateMemory", () => ({
  useCreateMemory: () => ({
    mutate: vi.fn(
      (_input: unknown, options: { onSuccess?: () => void } = {}) => {
        options.onSuccess?.();
      },
    ),
    isPending: false,
  }),
}));

import { TranscriptionResult } from "@/components/voice/TranscriptionResult";

function renderComponent(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <TranscriptionResult initialText="test transcription" onClose={onClose} />
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

describe("TranscriptionResult", () => {
  it("does NOT call onClose after saving memory", async () => {
    const onClose = vi.fn();
    renderComponent(onClose);
    fireEvent.click(screen.getByRole("button", { name: /salvar como memória/i }));
    await waitFor(() => {
      expect(onClose).not.toHaveBeenCalled();
    });
  });

  it("textarea is still visible after saving memory", async () => {
    renderComponent();
    fireEvent.click(screen.getByRole("button", { name: /salvar como memória/i }));
    await waitFor(() => {
      expect(screen.getByRole("textbox")).toBeInTheDocument();
    });
  });

  it("calls onClose when searching in briefings", () => {
    const onClose = vi.fn();
    renderComponent(onClose);
    fireEvent.click(screen.getByRole("button", { name: /buscar nos briefings/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
