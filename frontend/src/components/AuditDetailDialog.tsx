/**
 * Audit event detail dialog.
 *
 * Shows the event type badge, a "failed" marker if !success, a localized
 * timestamp, latency, error block and the event_data formatted as JSON.
 */

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { AuditEventBadge } from "@/components/AuditEventBadge";
import { useI18n } from "@/i18n/I18nContext";
import type { AuditLogItem } from "@/hooks/useAuditLog";

interface AuditDetailDialogProps {
  item: AuditLogItem | null;
  onOpenChange: (open: boolean) => void;
}

export function AuditDetailDialog({ item, onOpenChange }: AuditDetailDialogProps) {
  const { t, locale } = useI18n();
  return (
    <Dialog open={item !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        {item && (
          <>
            <DialogHeader>
              <div className="flex items-center gap-2">
                <AuditEventBadge eventType={item.event_type} />
                {!item.success && (
                  <span className="text-xs font-medium text-destructive">
                    {t.auditPage.failed}
                  </span>
                )}
              </div>
              <DialogTitle className="font-mono text-sm">
                {new Date(item.created_at).toLocaleString(locale === "pt" ? "pt-BR" : "en-US")}
              </DialogTitle>
              <DialogDescription>
                {item.latency_ms !== null && `${item.latency_ms} ms`}
              </DialogDescription>
            </DialogHeader>

            {item.error_message && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm">
                <span className="font-medium">{t.auditPage.errorLabelPrefix}: </span>
                {item.error_message}
              </div>
            )}

            <div className="space-y-2">
              <h4 className="text-sm font-medium">{t.auditPage.details}</h4>
              <pre className="rounded-md bg-muted p-4 text-xs font-mono overflow-auto max-h-96">
                {JSON.stringify(item.event_data, null, 2)}
              </pre>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
