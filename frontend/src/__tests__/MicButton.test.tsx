import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MicButton } from "@/components/voice/MicButton";

// Mock the hooks to avoid MediaRecorder/getUserMedia issues in jsdom
vi.mock("@/hooks/useVoiceRecorder", () => ({
  useVoiceRecorder: () => ({
    state: "idle",
    errorMessage: null,
    elapsedSeconds: 0,
    start: vi.fn(),
    stop: vi.fn(),
    reset: vi.fn(),
  }),
}));

vi.mock("@/hooks/useTranscribe", () => ({
  useTranscribe: () => ({
    mutate: vi.fn(),
    isPending: false,
    reset: vi.fn(),
  }),
}));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>{children}</BrowserRouter>
    </QueryClientProvider>
  );
}

describe("MicButton", () => {
  it("clicking opens the voice capture dialog", async () => {
    const user = userEvent.setup();
    render(<MicButton />, { wrapper: Wrapper });

    const button = screen.getByLabelText("Capturar voz");
    await user.click(button);

    expect(screen.getByText("Iniciar gravação")).toBeInTheDocument();
  });
});
