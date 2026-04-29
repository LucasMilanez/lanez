import { useCallback, useEffect, useRef, useState } from "react";

type State = "idle" | "requesting-permission" | "recording" | "stopping" | "error";

interface UseVoiceRecorderResult {
  state: State;
  errorMessage: string | null;
  elapsedSeconds: number;
  start: () => Promise<void>;
  stop: () => Promise<Blob | null>;
  reset: () => void;
}

const MAX_DURATION_SECONDS = 30;

export function useVoiceRecorder(): UseVoiceRecorderResult {
  const [state, setState] = useState<State>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const tickRef = useRef<number | null>(null);
  const stopResolverRef = useRef<((blob: Blob | null) => void) | null>(null);

  const cleanupTimer = useCallback(() => {
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
  }, []);

  const cleanupStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const start = useCallback(async () => {
    setState("requesting-permission");
    setErrorMessage(null);
    setElapsedSeconds(0);
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorder.onstop = () => {
        cleanupTimer();
        cleanupStream();
        const mime = recorder.mimeType || "audio/webm";
        const blob = chunksRef.current.length > 0
          ? new Blob(chunksRef.current, { type: mime })
          : null;
        setState("idle");
        stopResolverRef.current?.(blob);
        stopResolverRef.current = null;
      };

      recorder.start();
      setState("recording");

      // Tick puro — apenas atualiza o contador. Auto-stop fica num useEffect separado.
      tickRef.current = window.setInterval(() => {
        setElapsedSeconds((s) => s + 1);
      }, 1000);
    } catch (err) {
      cleanupStream();
      setState("error");
      setErrorMessage(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Permissão de microfone negada. Habilite nas configurações do navegador."
          : "Não foi possível acessar o microfone."
      );
    }
  }, [cleanupTimer, cleanupStream]);

  const stop = useCallback(() => {
    return new Promise<Blob | null>((resolve) => {
      if (recorderRef.current?.state === "recording") {
        stopResolverRef.current = resolve;
        setState("stopping");
        recorderRef.current.stop();
      } else {
        resolve(null);
      }
    });
  }, []);

  const reset = useCallback(() => {
    // Se ainda gravando (usuário fechou o dialog em meio à gravação),
    // parar o MediaRecorder antes de soltar tracks/timer.
    if (recorderRef.current?.state === "recording") {
      try {
        recorderRef.current.stop();
      } catch {
        /* ignorar — recorder já em estado inválido */
      }
    }
    cleanupTimer();
    cleanupStream();
    recorderRef.current = null;
    chunksRef.current = [];
    stopResolverRef.current = null;
    setElapsedSeconds(0);
    setState("idle");
    setErrorMessage(null);
  }, [cleanupTimer, cleanupStream]);

  // Auto-stop em MAX_DURATION_SECONDS — separado do tick para evitar
  // side effects dentro do state updater (problemático em Strict Mode).
  useEffect(() => {
    if (
      elapsedSeconds >= MAX_DURATION_SECONDS &&
      recorderRef.current?.state === "recording"
    ) {
      recorderRef.current.stop();
    }
  }, [elapsedSeconds]);

  useEffect(() => () => {
    cleanupTimer();
    cleanupStream();
  }, [cleanupTimer, cleanupStream]);

  return { state, errorMessage, elapsedSeconds, start, stop, reset };
}
