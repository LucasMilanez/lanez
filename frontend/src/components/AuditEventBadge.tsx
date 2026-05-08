import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useI18n } from "@/i18n/I18nContext";

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

type EventTypeKey = keyof typeof TYPE_VAR;

interface AuditEventBadgeProps {
  eventType: string;
  className?: string;
}

export function AuditEventBadge({ eventType, className }: AuditEventBadgeProps) {
  const { t } = useI18n();
  const varName = TYPE_VAR[eventType];
  const style = varName
    ? {
        backgroundColor: `hsl(var(${varName}) / 0.15)`,
        color: `hsl(var(${varName}))`,
        borderColor: `hsl(var(${varName}) / 0.3)`,
      }
    : undefined;

  const labels = t.auditPage.eventTypes as Record<string, string>;
  const label = labels[eventType as EventTypeKey] ?? eventType;

  return (
    <Badge
      variant="secondary"
      className={cn("font-mono text-xs", className)}
      style={style}
      title={eventType}
    >
      {label}
    </Badge>
  );
}
