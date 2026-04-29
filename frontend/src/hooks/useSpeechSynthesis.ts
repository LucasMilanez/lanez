import { useCallback, useEffect, useState } from "react";

type State = "idle" | "speaking" | "paused";

interface UseSpeechSynthesisResult {
  state: State;
  speak: (text: string) => void;
  pause: () => void;
  resume: () => void;
  cancel: () => void;
  supported: boolean;
}

export function useSpeechSynthesis(): UseSpeechSynthesisResult {
  const supported =
    typeof window !== "undefined" && "speechSynthesis" in window;

  const [state, setState] = useState<State>("idle");

  // Chrome popula getVoices() assincronamente — disparar carregamento no mount
  // e ouvir 'voiceschanged' garante que a voz pt-BR fique disponível na 1ª chamada.
  useEffect(() => {
    if (!supported) return;
    window.speechSynthesis.getVoices(); // trigger inicial
    const handler = () => {
      window.speechSynthesis.getVoices(); // mantém o cache do browser quente
    };
    window.speechSynthesis.addEventListener("voiceschanged", handler);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", handler);
    };
  }, [supported]);

  useEffect(() => {
    return () => {
      if (supported) window.speechSynthesis.cancel();
    };
  }, [supported]);

  const speak = useCallback((text: string) => {
    if (!supported || !text) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "pt-BR";

    const voices = window.speechSynthesis.getVoices();
    const ptVoice = voices.find((v) => v.lang.startsWith("pt"));
    if (ptVoice) utter.voice = ptVoice;

    utter.onstart = () => setState("speaking");
    utter.onend = () => setState("idle");
    utter.onerror = () => setState("idle");

    window.speechSynthesis.speak(utter);
  }, [supported]);

  const pause = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.pause();
    setState("paused");
  }, [supported]);

  const resume = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.resume();
    setState("speaking");
  }, [supported]);

  const cancel = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setState("idle");
  }, [supported]);

  return { state, speak, pause, resume, cancel, supported };
}
