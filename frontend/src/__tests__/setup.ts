import "@testing-library/jest-dom";
import { vi } from "vitest";

global.fetch = vi.fn();

// Mock window.matchMedia for jsdom (not available by default)
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// ---------------------------------------------------------------------------
// Mocks de voz — Fase 6b (jsdom não suporta MediaRecorder nem SpeechSynthesis)
// ---------------------------------------------------------------------------

// MediaRecorder e getUserMedia
Object.defineProperty(global.navigator, "mediaDevices", {
  writable: true,
  value: { getUserMedia: vi.fn() },
});

global.MediaRecorder = vi.fn().mockImplementation(() => ({
  start: vi.fn(),
  stop: vi.fn(),
  ondataavailable: null,
  onstop: null,
  state: "inactive",
  mimeType: "audio/webm",
})) as unknown as typeof MediaRecorder;

// SpeechSynthesis — incluir addEventListener/removeEventListener para o
// useEffect de pré-aquecimento de voices não estourar em jsdom.
Object.defineProperty(global.window, "speechSynthesis", {
  writable: true,
  value: {
    speak: vi.fn(),
    cancel: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    getVoices: vi.fn(() => []),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  },
});

global.SpeechSynthesisUtterance = vi.fn().mockImplementation((text) => ({
  text,
  lang: "",
  voice: null,
  onstart: null,
  onend: null,
  onerror: null,
})) as unknown as typeof SpeechSynthesisUtterance;
