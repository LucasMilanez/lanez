import { useState, useEffect } from "react";
import { History } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AuditEventBadge } from "@/components/AuditEventBadge";
import { AuditDetailDialog } from "@/components/AuditDetailDialog";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { useAuditLog } from "@/hooks/useAuditLog";
import { cn } from "@/lib/utils";
import type { AuditLogItem } from "@/hooks/useAuditLog";

const EVENT_TYPES = [
  "auth.login",
  "auth.logout",
  "auth.refresh",
  "mcp.call",
  "briefing.generated",
  "memory.created",
  "voice.transcribed",
  "webhook.received",
];

const pageSize = 50;

function summarizeEventData(item: AuditLogItem): string {
  const data = item.event_data as Record<string, unknown>;
  switch (item.event_type) {
    case "mcp.call":
      return `${data.tool_name ?? "?"}${data.success === false ? " (falhou)" : ""}`;
    case "briefing.generated":
      return `event=${data.event_id ?? "?"} model=${data.model_used ?? "?"}`;
    case "memory.created":
      return `source=${data.source ?? "?"} length=${data.content_length ?? "?"}`;
    case "voice.transcribed":
      return `${data.audio_bytes ?? "?"} bytes → ${data.transcription_length ?? "?"} chars`;
    case "webhook.received":
      return `${data.resource ?? "?"} ${data.change_type ?? ""}`;
    case "auth.login":
      return `${data.email ?? "?"}`;
    default:
      return "—";
  }
}

export function AuditPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selected, setSelected] = useState<AuditLogItem | null>(null);
  const [activeTypes, setActiveTypes] = useState<string[]>([]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const { data, isLoading, error, refetch } = useAuditLog({
    page,
    pageSize,
    eventTypes: activeTypes.length > 0 ? activeTypes : undefined,
    q: debouncedSearch || undefined,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  function toggleType(type: string) {
    setActiveTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
    setPage(1);
  }

  return (
    <div className="space-y-6">
      <Input
        placeholder="Buscar eventos..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-md"
      />

      <div className="flex flex-wrap gap-1.5">
        {EVENT_TYPES.map((type) => {
          const active = activeTypes.includes(type);
          return (
            <button
              key={type}
              type="button"
              onClick={() => toggleType(type)}
              aria-pressed={active}
              className={cn(
                "rounded-md transition-all",
                active
                  ? "ring-2 ring-brand ring-offset-2 ring-offset-background"
                  : "opacity-60 hover:opacity-100",
              )}
            >
              <AuditEventBadge eventType={type} />
            </button>
          );
        })}
      </div>

      {isLoading && <LoadingSkeleton count={5} className="h-12" />}

      {error && <ErrorState onRetry={() => void refetch()} />}

      {data && data.items.length === 0 && (
        <EmptyState
          title="Nenhum evento encontrado"
          description="Eventos de auditoria aparecerão aqui conforme o sistema for usado."
          icon={<History className="h-10 w-10" />}
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Quando</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Resumo</TableHead>
                <TableHead className="text-right">Latência</TableHead>
                <TableHead className="text-right">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((item) => (
                <TableRow
                  key={item.id}
                  className="cursor-pointer"
                  onClick={() => setSelected(item)}
                >
                  <TableCell className="font-mono text-xs">
                    {new Date(item.created_at).toLocaleString("pt-BR")}
                  </TableCell>
                  <TableCell>
                    <AuditEventBadge eventType={item.event_type} />
                  </TableCell>
                  <TableCell className="max-w-md truncate font-mono text-xs text-muted-foreground">
                    {summarizeEventData(item)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {item.latency_ms !== null ? `${item.latency_ms} ms` : "—"}
                  </TableCell>
                  <TableCell className="text-right text-xs">
                    {item.success ? (
                      <span className="text-green-600 dark:text-green-400">ok</span>
                    ) : (
                      <span className="text-destructive">erro</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between">
            <Button
              variant="outline"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Anterior
            </Button>
            <span className="text-sm text-muted-foreground">
              Página {page} de {totalPages}
            </span>
            <Button
              variant="outline"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Próximo
            </Button>
          </div>
        </>
      )}

      <AuditDetailDialog
        item={selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      />
    </div>
  );
}
