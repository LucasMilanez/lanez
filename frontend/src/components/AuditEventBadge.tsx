import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const TYPE_VAR: Record<string, string> = {
  "auth.login": "--badge-auth-login",
  "auth.logout": "--badge-auth-logout",
  "auth.refresh": "--badge-auth-refresh",
  "mcp.call": "--badge-mcp-call",
  "briefing.generated": "--badge-briefing-generated",
  "memory.created": "--badge-memory-created",
  "voice.transcribed": "--badge-voice-transcribed",
  "webhook.received": "--badge-webhook-received",
};

interface AuditEventBadgeProps {
  eventType: string;
  className?: string;
}

export function AuditEventBadge({ eventType, className }: AuditEventBadgeProps) {
  const varName = TYPE_VAR[eventType];
  const style = varName
    ? {
        backgroundColor: `hsl(var(${varName}) / 0.15)`,
        color: `hsl(var(${varName}))`,
        borderColor: `hsl(var(${varName}) / 0.3)`,
      }
    : undefined;

  return (
    <Badge
      variant="secondary"
      className={cn("font-mono text-xs", className)}
      style={style}
    >
      {eventType}
    </Badge>
  );
}
