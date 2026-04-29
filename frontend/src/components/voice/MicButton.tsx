import { Mic } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { VoiceCaptureDialog } from "@/components/voice/VoiceCaptureDialog";

export function MicButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Capturar voz"
        onClick={() => setOpen(true)}
      >
        <Mic className="h-4 w-4" />
      </Button>
      <VoiceCaptureDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
