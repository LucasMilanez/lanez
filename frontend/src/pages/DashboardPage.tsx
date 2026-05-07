import { memo } from "react";
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
  ChevronRight,
  AlertTriangle,
  RefreshCw,
  Zap,
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
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useStatus, type StatusData } from "@/hooks/useStatus";
import { StatusCard } from "@/components/StatusCard";
import { TokenUsageChart } from "@/components/TokenUsageChart";
import { ErrorState } from "@/components/ErrorState";

// ---------------------------------------------------------------------------
// Alert Banner — contextual actions
// ---------------------------------------------------------------------------

const AlertBanner = memo(function AlertBanner({
  data,
}: {
  data: StatusData;
}) {
  const tokenExpired = data.token_expires_in_seconds < 0;
  const tokenExpiringSoon =
    !tokenExpired && data.token_expires_in_seconds < 7200; // < 2h

  if (!tokenExpired && !tokenExpiringSoon) return null;

  return (
    <div
      role="alert"
      className="flex items-center gap-3 rounded-xl border border-destructive/25 bg-destructive/[0.04] px-4 py-3"
    >
      <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-destructive">
          {tokenExpired
            ? "Token Microsoft expirado"
            : "Token Microsoft expira em breve"}
        </p>
        <p className="text-xs text-destructive/80 mt-0.5">
          {tokenExpired
            ? "Renove a autenticação para manter as integrações ativas."
            : `Expira ${formatDistanceToNow(new Date(data.token_expires_at), { addSuffix: true, locale: ptBR })}. Renove para evitar interrupções.`}
        </p>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="shrink-0 border-destructive/30 text-destructive hover:bg-destructive/10"
        onClick={() => {
          window.location.href = "/auth/refresh";
        }}
      >
        <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
        Renovar
      </Button>
    </div>
  );
});

// ---------------------------------------------------------------------------
// KPI Cards Section
// ---------------------------------------------------------------------------

const KpiCards = memo(function KpiCards({ data }: { data: StatusData }) {
  const tokenExpired = data.token_expires_in_seconds < 0;
  const tokenExpiresAt = new Date(data.token_expires_at);
  const tokenDescription = tokenExpired
    ? "Re-autenticação necessária"
    : `Expira ${formatDistanceToNow(tokenExpiresAt, { addSuffix: true, locale: ptBR })}`;

  // Show only name part of email for cleaner display
  const emailDisplay = data.user_email.includes("@")
    ? data.user_email
    : data.user_email;

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <StatusCard
        title="Microsoft 365"
        value={emailDisplay}
        description={tokenDescription}
        icon={<Shield className="h-4 w-4" />}
        variant={tokenExpired ? "destructive" : "default"}
        badge={tokenExpired ? "Expirado" : undefined}
      />

      <StatusCard
        title="Webhooks ativos"
        value={data.webhook_subscriptions.length}
        description={
          data.webhook_subscriptions.length > 0
            ? `${data.webhook_subscriptions.length} subscrições`
            : "Nenhuma subscrição ativa"
        }
        icon={<Webhook className="h-4 w-4" />}
      />

      <StatusCard
        title="Briefings 30d"
        value={data.briefings_count_30d}
        description="nos últimos 30 dias"
        icon={<FileText className="h-4 w-4" />}
      />

      <Link to="/memories" aria-label={`Memórias: ${data.memories_count} guardadas. Ver e gerir memórias.`}>
        <StatusCard
          title="Memórias"
          value={data.memories_count}
          description="Ver e gerir memórias"
          icon={<Brain className="h-4 w-4" />}
          variant="clickable"
        />
      </Link>
    </div>
  );
});

// ---------------------------------------------------------------------------
// Embeddings Table
// ---------------------------------------------------------------------------

const EmbeddingsTable = memo(function EmbeddingsTable({
  data,
}: {
  data: StatusData["embeddings_by_service"];
}) {
  return (
    <Card className="shadow-soft">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <Database className="h-4 w-4 text-muted-foreground" />
          Embeddings por serviço
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Database className="h-6 w-6 text-muted-foreground/40 mb-2" />
            <p className="text-sm text-muted-foreground">
              Nenhum embedding indexado ainda.
            </p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              Os embeddings são criados automaticamente ao sincronizar dados.
            </p>
          </div>
        ) : (
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
              {data.map((e) => (
                <TableRow key={e.service}>
                  <TableCell className="font-medium">{e.service}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {e.count.toLocaleString("pt-BR")}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
});

// ---------------------------------------------------------------------------
// Token Usage Section
// ---------------------------------------------------------------------------

const TokenUsageSection = memo(function TokenUsageSection({
  data,
}: {
  data: StatusData["tokens_30d"];
}) {
  const total = data.input + data.output + data.cache_read + data.cache_write;

  return (
    <Card className="shadow-soft">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            Tokens Anthropic · 30d
          </span>
          {total > 0 && (
            <span className="text-xs font-normal text-muted-foreground tabular-nums">
              Total: {total.toLocaleString("pt-BR")}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {total === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <BarChart3 className="h-6 w-6 text-muted-foreground/40 mb-2" />
            <p className="text-sm text-muted-foreground">
              Nenhum token consumido nos últimos 30 dias.
            </p>
            <p className="text-xs text-muted-foreground/70 mt-1 max-w-[240px]">
              Tokens são consumidos ao gerar briefings automáticos de reunião (Claude Haiku).
            </p>
          </div>
        ) : (
          <>
            <p className="sr-only">
              Gráfico de uso de tokens nos últimos 30 dias. Total de{" "}
              {total.toLocaleString("pt-BR")} tokens.
            </p>
            <TokenUsageChart data={data} />
          </>
        )}
      </CardContent>
    </Card>
  );
});

// ---------------------------------------------------------------------------
// MCP Activity Section
// ---------------------------------------------------------------------------

const McpActivitySection = memo(function McpActivitySection({
  data,
}: {
  data: StatusData["mcp_activity_30d"];
}) {
  return (
    <Card className="shadow-soft">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            <Zap className="h-4 w-4 text-muted-foreground" />
            Atividade MCP · 30d
          </span>
          {data.total_calls > 0 && (
            <span className="text-xs font-normal text-muted-foreground tabular-nums">
              {data.total_calls} chamadas
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {data.total_calls === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Zap className="h-6 w-6 text-muted-foreground/40 mb-2" />
            <p className="text-sm text-muted-foreground">
              Nenhuma chamada MCP nos últimos 30 dias.
            </p>
            <p className="text-xs text-muted-foreground/70 mt-1 max-w-[240px]">
              Chamadas são registradas quando um cliente MCP (Claude Desktop, etc.) usa as ferramentas.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Summary stats */}
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg bg-accent/50 px-3 py-2 text-center">
                <p className="text-lg font-semibold tabular-nums">{data.total_calls}</p>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Total</p>
              </div>
              <div className="rounded-lg bg-accent/50 px-3 py-2 text-center">
                <p className="text-lg font-semibold tabular-nums text-emerald-500">{data.successful}</p>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Sucesso</p>
              </div>
              <div className="rounded-lg bg-accent/50 px-3 py-2 text-center">
                <p className="text-lg font-semibold tabular-nums text-destructive">{data.failed}</p>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Erros</p>
              </div>
            </div>

            {/* Tools breakdown */}
            {data.tools_used.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="text-[11px] uppercase tracking-wider">
                      Ferramenta
                    </TableHead>
                    <TableHead className="text-right text-[11px] uppercase tracking-wider">
                      Chamadas
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.tools_used.map((t) => (
                    <TableRow key={t.service}>
                      <TableCell className="font-medium text-xs">{t.service}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {t.count}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
});

// ---------------------------------------------------------------------------
// Recent Briefings
// ---------------------------------------------------------------------------

const MAX_RECENT_BRIEFINGS = 5;

const RecentBriefings = memo(function RecentBriefings({
  briefings,
}: {
  briefings: StatusData["recent_briefings"];
}) {
  const displayed = briefings.slice(0, MAX_RECENT_BRIEFINGS);
  const hasMore = briefings.length > MAX_RECENT_BRIEFINGS;

  return (
    <Card className="shadow-soft">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            Briefings recentes
          </span>
          {briefings.length > 0 && (
            <Link
              to="/briefings"
              className="text-xs font-medium text-brand hover:text-brand/80 transition-colors flex items-center gap-1"
            >
              Ver todos
              <ChevronRight className="h-3.5 w-3.5" />
            </Link>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {displayed.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Calendar className="h-6 w-6 text-muted-foreground/40 mb-2" />
            <p className="text-sm text-muted-foreground">
              Nenhum briefing recente.
            </p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              Briefings são gerados automaticamente antes de reuniões.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-border -mx-2" aria-label="Lista de briefings recentes">
            {displayed.map((b) => (
              <li key={b.event_id}>
                <Link
                  to={`/briefings/${b.event_id}`}
                  className="flex items-center gap-3 rounded-md px-3 py-2.5 transition-colors hover:bg-accent/60 group"
                >
                  <span className="font-medium truncate flex-1">
                    {b.event_subject}
                  </span>
                  <span className="text-xs text-muted-foreground tabular-nums shrink-0">
                    {format(new Date(b.event_start), "dd 'de' MMM '·' HH:mm", {
                      locale: ptBR,
                    })}
                  </span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-foreground transition-colors" />
                </Link>
              </li>
            ))}
          </ul>
        )}
        {hasMore && (
          <div className="mt-3 text-center">
            <Link
              to="/briefings"
              className="text-xs font-medium text-brand hover:text-brand/80 transition-colors"
            >
              +{briefings.length - MAX_RECENT_BRIEFINGS} briefings anteriores →
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  );
});

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------

function DashboardSkeleton() {
  return (
    <div className="space-y-8">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-lg border shadow-soft p-5 space-y-3">
            <div className="flex items-start justify-between">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-7 w-7 rounded-md" />
            </div>
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-3 w-32" />
          </div>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="rounded-lg border shadow-soft p-5 space-y-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-[200px] w-full" />
          </div>
        ))}
      </div>
      <div className="rounded-lg border shadow-soft p-5 space-y-3">
        <Skeleton className="h-4 w-36" />
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full rounded-md" />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export function DashboardPage() {
  const { data, isLoading, error, refetch } = useStatus();

  if (isLoading) return <DashboardSkeleton />;
  if (error || !data) return <ErrorState onRetry={() => void refetch()} />;

  return (
    <div className="space-y-8">
      <AlertBanner data={data} />
      <KpiCards data={data} />

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <EmbeddingsTable data={data.embeddings_by_service} />
        <TokenUsageSection data={data.tokens_30d} />
        <McpActivitySection data={data.mcp_activity_30d} />
      </div>

      <RecentBriefings briefings={data.recent_briefings} />
    </div>
  );
}
