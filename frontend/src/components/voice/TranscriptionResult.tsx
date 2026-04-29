import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useCreateMemory } from "@/hooks/useCreateMemory";

interface TranscriptionResultProps {
  initialText: string;
  onClose: () => void;
}

export function TranscriptionResult({ initialText, onClose }: TranscriptionResultProps) {
  const navigate = useNavigate();
  const createMemory = useCreateMemory();
  const [text, setText] = useState(initialText);

  const handleSaveAsMemory = () => {
    createMemory.mutate(
      { content: text, tags: ["voz"] },
      {
        onSuccess: () => {
          toast.success("Memória salva");
          onClose();
        },
        onError: (err) => {
          toast.error(`Falha ao salvar: ${err.detail}`);
        },
      }
    );
  };

  const handleSearchInBriefings = () => {
    const q = encodeURIComponent(text.trim());
    navigate(`/briefings?q=${q}`);
    onClose();
  };

  return (
    <div className="space-y-4">
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        className="font-mono text-sm"
        aria-label="Transcrição editável"
      />
      <div className="flex gap-2 justify-end">
        <Button
          variant="secondary"
          onClick={handleSearchInBriefings}
          disabled={!text.trim()}
        >
          Buscar nos briefings
        </Button>
        <Button
          onClick={handleSaveAsMemory}
          disabled={!text.trim() || createMemory.isPending}
        >
          {createMemory.isPending ? "Salvando..." : "Salvar como memória"}
        </Button>
      </div>
    </div>
  );
}
