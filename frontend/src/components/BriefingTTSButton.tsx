import { Pause, Play, StopCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSpeechSynthesis } from "@/hooks/useSpeechSynthesis";
import { stripMarkdown } from "@/lib/stripMarkdown";

interface BriefingTTSButtonProps {
  content: string;
}

export function BriefingTTSButton({ content }: BriefingTTSButtonProps) {
  const tts = useSpeechSynthesis();

  if (!tts.supported) return null;

  if (tts.state === "speaking") {
    return (
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={tts.pause}>
          <Pause className="h-4 w-4 mr-2" />
          Pausar
        </Button>
        <Button variant="outline" size="sm" onClick={tts.cancel}>
          <StopCircle className="h-4 w-4 mr-2" />
          Parar
        </Button>
      </div>
    );
  }

  if (tts.state === "paused") {
    return (
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={tts.resume}>
          <Play className="h-4 w-4 mr-2" />
          Continuar
        </Button>
        <Button variant="outline" size="sm" onClick={tts.cancel}>
          <StopCircle className="h-4 w-4 mr-2" />
          Parar
        </Button>
      </div>
    );
  }

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => tts.speak(stripMarkdown(content))}
    >
      <Play className="h-4 w-4 mr-2" />
      Ouvir resumo
    </Button>
  );
}
