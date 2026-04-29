import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { BriefingTTSButton } from "@/components/BriefingTTSButton";

vi.mock("@/hooks/useSpeechSynthesis", () => ({
  useSpeechSynthesis: vi.fn(),
}));

describe("BriefingTTSButton", () => {
  it("renders null when speech synthesis is not supported", async () => {
    const { useSpeechSynthesis } = await import("@/hooks/useSpeechSynthesis");
    vi.mocked(useSpeechSynthesis).mockReturnValue({
      state: "idle",
      speak: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
      cancel: vi.fn(),
      supported: false,
    });

    const { container } = render(<BriefingTTSButton content="test content" />);
    expect(container.innerHTML).toBe("");
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

    render(<BriefingTTSButton content="test content" />);
    expect(screen.getByText("Pausar")).toBeInTheDocument();
    expect(screen.getByText("Parar")).toBeInTheDocument();
  });
});
