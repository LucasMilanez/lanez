import { Link } from "react-router-dom";
import { formatDistanceToNow, format } from "date-fns";
import { ptBR } from "date-fns/locale";
import {
  Shield,
  Webhook,
  FileText,
  Brain,
  Database,
  BarChart3,
  Calendar,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useStatus } from "@/hooks/useStatus";
import { StatusCard } from "@/components/StatusCard";
import { TokenUsageChart } from "@/components/TokenUsageChart";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ErrorState } from "@/components/ErrorState";

export function DashboardPage() {
  const { data, isLoading, error, refetch } = useStatus();

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <LoadingSkeleton count={7} className="h-32" />
      </div>
    );
  }

  if (error || !data) {
    return <ErrorState onRetry={() => void refetch()} />;
  }

  const tokenExpiresAt = new Date(data.token_expires_at);
  const tokenExpired = data.token_expires_in_seconds < 0;
  const tokenDescription = tokenExpired
    ? "Token expirado"
    : `Expira ${formatDistanceToNow(tokenExpiresAt, { addSuffix: true, locale: ptBR })}`;

  return (
    <div className="space-y-8">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatusCard
          title="Microsoft 365"
          value={data.user_email}
          description={tokenDescription}
          icon={<Shield className="h-4 w-4" />}
        />

        <StatusCard
          title="Webhooks ativos"
          value={data.webhook_subscriptions.length}
          description={data.webhook_subscriptions.map((w) => w.resource).join(", ") || "Nenhum"}
          icon={<Webhook className="h-4 w-4" />}
        />

        <StatusCard
          title="Briefings 30d"
          value={data.briefings_count_30d}
          description="nos últimos 30 dias"
          icon={<FileText className="h-4 w-4" />}
        />

        <StatusCard
          title="Memórias"
          value={data.memories_count}
          icon={<Brain className="h-4 w-4" />}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="shadow-soft">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold tracking-tight">
              <Database className="h-4 w-4 text-muted-foreground" />
              Embeddings por serviço
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-[11px] uppercase tracking-wider">
                    Serviço
                  </TableHead>
                  <TableHead className="text-right text-[11px] uppercase tracking-wider">
                    Quantidade
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.embeddings_by_service.map((e) => (
                  <TableRow key={e.service}>
                    <TableCell className="font-medium">{e.service}</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {e.count}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="shadow-soft">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold tracking-tight">
              <BarChart3 className="h-4 w-4 text-muted-foreground" />
              Uso de tokens · 30 dias
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <TokenUsageChart data={data.tokens_30d} />
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-soft">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            Briefings recentes
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {data.recent_briefings.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">
              Nenhum briefing recente.
            </p>
          ) : (
            <ul className="divide-y divide-border -mx-2">
              {data.recent_briefings.map((b) => (
                <li key={b.event_id}>
                  <Link
                    to={`/briefings/${b.event_id}`}
                    className="flex items-center justify-between gap-4 rounded-md px-3 py-2.5 transition-colors hover:bg-accent/60"
                  >
                    <span className="font-medium truncate">
                      {b.event_subject}
                    </span>
                    <span className="text-xs text-muted-foreground tabular-nums shrink-0">
                      {format(new Date(b.event_start), "dd 'de' MMM '·' HH:mm", {
                        locale: ptBR,
                      })}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
