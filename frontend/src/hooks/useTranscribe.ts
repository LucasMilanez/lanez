import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";

interface VoiceTranscriptionResponse {
  transcription: string;
  duration_ms: number;
}

export function useTranscribe() {
  return useMutation<VoiceTranscriptionResponse, ApiError, Blob>({
    mutationFn: async (audioBlob: Blob) => {
      const form = new FormData();
      const filename = audioBlob.type.includes("mp4") ? "audio.mp4" : "audio.webm";
      form.append("audio", audioBlob, filename);
      return api.postMultipart<VoiceTranscriptionResponse>("/voice/transcribe", form);
    },
  });
}
