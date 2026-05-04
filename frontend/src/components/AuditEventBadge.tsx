/**
 * Badge colorida por tipo de evento de auditoria — Fase 7.
 *
 * Usa Tailwind literais para as 8 cores conhecidas. Esta é a ÚNICA exceção
 * justificada da fase ao princípio "cores via tokens shadcn", análoga ao
 * bg-red-500 do RecordingIndicator da Fase 6b.
 */

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const TYPE_STYLES: Record<string, string> = {
  "auth.login": "bg-green-500/15 text-green-700 dark:text-green-400",
  "auth.logout": "bg-slate-500/15 text-slate-700 dark:text-slate-400",
  "auth.refresh": "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  "mcp.call": "bg-purple-500/15 text-purple-700 dark:text-purple-400",
  "briefing.generated": "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  "memory.created": "bg-cyan-500/15 text-cyan-700 dark:text-cyan-400",
  "voice.transcribed": "bg-pink-500/15 text-pink-700 dark:text-pink-400",
  "webhook.received": "bg-indigo-500/15 text-indigo-700 dark:text-indigo-400",
};

const FALLBACK_STYLE = "bg-muted text-muted-foreground";

interface AuditEventBadgeProps {
  eventType: string;
  className?: string;
}

export function AuditEventBadge({ eventType, className }: AuditEventBadgeProps) {
  const style = TYPE_STYLES[eventType] ?? FALLBACK_STYLE;
  return (
    <Badge
      variant="secondary"
      className={cn(style, "font-mono text-xs", className)}
    >
      {eventType}
    </Badge>
  );
}
