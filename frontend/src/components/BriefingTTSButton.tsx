import { Pause, Play, StopCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSpeechSynthesis } from "@/hooks/useSpeechSynthesis";
import { stripMarkdown } from "@/lib/stripMarkdown";
import { useI18n } from "@/i18n/I18nContext";

interface BriefingTTSButtonProps {
  content: string;
}

export function BriefingTTSButton({ content }: BriefingTTSButtonProps) {
  const tts = useSpeechSynthesis();
  const { t } = useI18n();

  if (!tts.supported)
    return (
      <Button
        variant="outline"
        size="sm"
        disabled
        title={t.tts.unavailable}
        aria-label={t.tts.unavailable}
      >
        <Play className="h-4 w-4 mr-2" />
        {t.tts.listen}
      </Button>
    );

  if (tts.state === "speaking") {
    return (
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={tts.pause}>
          <Pause className="h-4 w-4 mr-2" />
          {t.tts.pause}
        </Button>
        <Button variant="outline" size="sm" onClick={tts.cancel}>
          <StopCircle className="h-4 w-4 mr-2" />
          {t.tts.stop}
        </Button>
      </div>
    );
  }

  if (tts.state === "paused") {
    return (
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={tts.resume}>
          <Play className="h-4 w-4 mr-2" />
          {t.tts.resume}
        </Button>
        <Button variant="outline" size="sm" onClick={tts.cancel}>
          <StopCircle className="h-4 w-4 mr-2" />
          {t.tts.stop}
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
      {t.tts.listen}
    </Button>
  );
}
