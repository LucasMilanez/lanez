import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VoiceCaptureDialog } from "@/components/voice/VoiceCaptureDialog";

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

const mockUseVoiceRecorder = vi.fn();
const mockUseTranscribe = vi.fn();

vi.mock("@/hooks/useVoiceRecorder", () => ({
  useVoiceRecorder: (...args: unknown[]) => mockUseVoiceRecorder(...args),
}));

vi.mock("@/hooks/useTranscribe", () => ({
  useTranscribe: (...args: unknown[]) => mockUseTranscribe(...args),
}));

beforeEach(() => {
  mockUseVoiceRecorder.mockReturnValue({
    state: "idle",
    errorMessage: null,
    elapsedSeconds: 0,
    start: vi.fn(),
    stop: vi.fn(),
    reset: vi.fn(),
  });

  mockUseTranscribe.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    reset: vi.fn(),
  });
});

describe("VoiceCaptureDialog", () => {
  it("shows 'Iniciar gravação' button when open", () => {
    render(
      <VoiceCaptureDialog open={true} onOpenChange={vi.fn()} />,
      { wrapper: Wrapper },
    );
    expect(screen.getByText("Iniciar gravação")).toBeInTheDocument();
  });

  it("shows error alert when recorder is in error state", () => {
    mockUseVoiceRecorder.mockReturnValue({
      state: "error",
      errorMessage: "Permissão de microfone negada. Habilite nas configurações do navegador.",
      elapsedSeconds: 0,
      start: vi.fn(),
      stop: vi.fn(),
      reset: vi.fn(),
    });

    render(
      <VoiceCaptureDialog open={true} onOpenChange={vi.fn()} />,
      { wrapper: Wrapper },
    );
    expect(screen.getByText(/Permissão de microfone negada/)).toBeInTheDocument();
  });
});
