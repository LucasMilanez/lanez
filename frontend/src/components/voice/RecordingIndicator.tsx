import { cn } from "@/lib/utils";

interface RecordingIndicatorProps {
  elapsedSeconds: number;
  maxSeconds?: number;
}

export function RecordingIndicator({
  elapsedSeconds,
  maxSeconds = 30,
}: RecordingIndicatorProps) {
  // Formato MM:SS sempre com 2 dígitos em cada — "00:05 / 00:30"
  const formatted = `${String(Math.floor(elapsedSeconds / 60)).padStart(2, "0")}:${String(
    elapsedSeconds % 60
  ).padStart(2, "0")}`;
  const max = `${String(Math.floor(maxSeconds / 60)).padStart(2, "0")}:${String(
    maxSeconds % 60
  ).padStart(2, "0")}`;

  return (
    <div className="flex items-center gap-3">
      <span className={cn("h-3 w-3 rounded-full bg-red-500 animate-pulse")} />
      <span className="font-mono text-sm">
        {formatted} / {max}
      </span>
    </div>
  );
}
