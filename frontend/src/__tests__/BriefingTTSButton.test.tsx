import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, setLocale } from "./test-utils";
import { BriefingTTSButton } from "@/components/BriefingTTSButton";

vi.mock("@/hooks/useSpeechSynthesis", () => ({
  useSpeechSynthesis: vi.fn(),
}));

describe("BriefingTTSButton", () => {
  beforeEach(() => {
    // Os testes usam as strings em PT; forçamos o locale antes de renderizar.
    setLocale("pt");
  });

  it("renders a disabled button with tooltip when TTS is not supported", async () => {
    const { useSpeechSynthesis } = await import("@/hooks/useSpeechSynthesis");
    vi.mocked(useSpeechSynthesis).mockReturnValue({
      state: "idle",
      speak: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
      cancel: vi.fn(),
      supported: false,
    });

    renderWithProviders(<BriefingTTSButton content="test content" />);
    // Quando o botão está disabled, o aria-label é "Síntese de voz..." — que
    // sobrescreve o nome acessível. Buscamos pelo texto visível do botão.
    const btn = screen.getByText("Ouvir resumo").closest("button");
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title");
  });

  it("shows Pausar and Parar buttons when speaking", async () => {
    const { useSpeechSynthesis } = await import("@/hooks/useSpeechSynthesis");
    vi.mocked(useSpeechSynthesis).mockReturnValue({
      state: "speaking",
      speak: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
      cancel: vi.fn(),
      supported: true,
    });

    renderWithProviders(<BriefingTTSButton content="test content" />);
    expect(screen.getByText("Pausar")).toBeInTheDocument();
    expect(screen.getByText("Parar")).toBeInTheDocument();
  });
});
