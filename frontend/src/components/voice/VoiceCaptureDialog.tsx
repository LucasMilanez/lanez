import { useState } from "react";
import { toast } from "sonner";
import { Mic, Square } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { RecordingIndicator } from "@/components/voice/RecordingIndicator";
import { TranscriptionResult } from "@/components/voice/TranscriptionResult";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { useTranscribe } from "@/hooks/useTranscribe";

interface VoiceCaptureDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function VoiceCaptureDialog({ open, onOpenChange }: VoiceCaptureDialogProps) {
  const recorder = useVoiceRecorder();
  const transcribe = useTranscribe();
  const [transcription, setTranscription] = useState<string | null>(null);

  const handleClose = () => {
    recorder.reset();
    transcribe.reset();
    setTranscription(null);
    onOpenChange(false);
  };

  const handleStart = async () => {
    setTranscription(null);
    transcribe.reset();
    await recorder.start();
  };

  const handleStop = async () => {
    const blob = await recorder.stop();
    if (!blob) {
      toast.error("Nenhum áudio capturado");
      return;
    }
    transcribe.mutate(blob, {
      onSuccess: (data) => setTranscription(data.transcription),
      onError: (err) => toast.error(`Falha na transcrição: ${err.detail}`),
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(o) : handleClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Captura por voz</DialogTitle>
          <DialogDescription>
            Grave até 30 segundos. A gravação para automaticamente no limite.
          </DialogDescription>
        </DialogHeader>

        {recorder.state === "error" && recorder.errorMessage && (
          <Alert variant="destructive">
            <AlertDescription>{recorder.errorMessage}</AlertDescription>
          </Alert>
        )}

        {transcription === null ? (
          <div className="flex flex-col items-center gap-4 py-6">
            {recorder.state === "recording" || recorder.state === "stopping" ? (
              <>
                <RecordingIndicator elapsedSeconds={recorder.elapsedSeconds} />
                <Button
                  variant="destructive"
                  size="lg"
                  onClick={handleStop}
                  disabled={recorder.state === "stopping"}
                >
                  <Square className="h-4 w-4 mr-2" />
                  Parar
                </Button>
              </>
            ) : transcribe.isPending ? (
              <p className="text-sm text-muted-foreground">Transcrevendo...</p>
            ) : (
              <Button size="lg" onClick={handleStart}>
                <Mic className="h-4 w-4 mr-2" />
                Iniciar gravação
              </Button>
            )}
          </div>
        ) : (
          <TranscriptionResult initialText={transcription} onClose={handleClose} />
        )}
      </DialogContent>
    </Dialog>
  );
}
