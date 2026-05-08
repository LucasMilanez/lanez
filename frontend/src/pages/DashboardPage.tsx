import { memo } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { formatDistanceToNow, format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { enUS } from "date-fns/locale";
import {
  Shield,
  Webhook,
  FileText,
  Brain,
  AlertTriangle,
  RefreshCw,
  Clock,
  ChevronRight,
  ArrowRight,
  RotateCw,
  ChevronDown,
  Mail,
  HardDrive,
  Calendar,
  NotebookPen,
  Database,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useStatus, type StatusData } from "@/hooks/useStatus";
import { useI18n, interpolate } from "@/i18n/I18nContext";
import { DonutChart } from "@/components/DonutChart";
import { ErrorState } from "@/components/ErrorState";
import { api, ApiError } from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTokenValue(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(value);
}

function getServiceIcon(service: string) {
  const s = service.toLowerCase();
  if (s.includes("mail") || s.includes("email")) return Mail;
  if (s.includes("onenote") || s.includes("note")) return NotebookPen;
  if (s.includes("onedrive") || s.includes("drive") || s.includes("file")) return HardDrive;
  if (s.includes("calendar") || s.includes("event")) return Calendar;
  return Database;
}

// ---------------------------------------------------------------------------
// Alert Banner
// ---------------------------------------------------------------------------

const AlertBanner = memo(function AlertBanner({ data }: { data: StatusData }) {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const dateLocale = locale === "pt" ? ptBR : enUS;
  const tokenExpired = data.token_expires_in_seconds < 0;
  const tokenExpiringSoon = !tokenExpired && data.token_expires_in_seconds < 7200;

  if (!tokenExpired && !tokenExpiringSoon) return null;

  const handleRenew = async () => {
    try {
      await api.post("/auth/refresh");
      await qc.invalidateQueries({ queryKey: ["status"] });
      toast.success(t.settingsPage.renewSuccess);
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : t.settingsPage.renewError;
      toast.error(message);
    }
  };

  return (
    <div
      role="alert"
      className="flex items-center gap-3 px-4 py-3 rounded-lg border border-destructive/25 bg-destructive/[0.05]"
    >
      <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-destructive/10 text-destructive shrink-0">
        <AlertTriangle className="h-[15px] w-[15px]" />
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-medium text-foreground">
          {tokenExpired
            ? t.dashboard.alertTokenExpired
            : `${t.dashboard.alertTokenExpiring} — ${formatDistanceToNow(new Date(data.token_expires_at), { addSuffix: false, locale: dateLocale })}`}
        </p>
        <p className="text-[12px] text-muted-foreground mt-0.5">
          {tokenExpired
            ? t.dashboard.alertTokenExpiredDesc
            : t.dashboard.alertTokenExpiringDesc.replace(
                "{time}",
                formatDistanceToNow(new Date(data.token_expires_at), { addSuffix: true, locale: dateLocale }),
              )}
        </p>
      </div>
      <button
        type="button"
        className="shrink-0 inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px] font-medium bg-destructive/[0.12] text-destructive border border-destructive/30 hover:bg-destructive/[0.18] transition-colors"
        onClick={() => void handleRenew()}
      >
        <RefreshCw className="h-3 w-3" />
        {t.dashboard.renew}
      </button>
    </div>
  );
});

// ---------------------------------------------------------------------------
// KPI Cards
// ---------------------------------------------------------------------------

const KpiCards = memo(function KpiCards({ data }: { data: StatusData }) {
  const { t, locale } = useI18n();
  const dateLocale = locale === "pt" ? ptBR : enUS;
  const tokenExpired = data.token_expires_in_seconds < 0;
  const tokenExpiresAt = new Date(data.token_expires_at);

  return (
    <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Microsoft 365 */}
      <article className="group rounded-xl border border-border bg-card/60 p-5 transition-all duration-200 hover:border-muted-foreground/20 hover:-translate-y-px">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
              {t.dashboard.microsoft365}
            </div>
            <div className="mt-2 text-sm font-semibold truncate max-w-[160px]" title={data.user_email}>
              {data.user_email}
            </div>
          </div>
          <span className="inline-flex items-center justify-center h-8 w-8 rounded-md bg-accent border border-border text-foreground/80 shrink-0">
            <Shield className="h-[15px] w-[15px]" />
          </span>
        </div>
        <div className="mt-5 flex items-center gap-1.5 text-[11.5px]">
          {tokenExpired ? (
            <span className="text-destructive flex items-center gap-1.5">
              <AlertTriangle className="h-3 w-3" />
              {t.dashboard.tokenExpired}
            </span>
          ) : (
            <span className="text-amber-500 dark:text-amber-400 flex items-center gap-1.5">
              <Clock className="h-3 w-3" />
              {interpolate(t.dashboard.tokenExpires, {
                time: formatDistanceToNow(tokenExpiresAt, { addSuffix: true, locale: dateLocale }),
              })}
            </span>
          )}
        </div>
      </article>

      {/* Webhooks */}
      <article className="group rounded-xl border border-border bg-card/60 p-5 transition-all duration-200 hover:border-muted-foreground/20 hover:-translate-y-px">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
              {t.dashboard.webhooksActive}
            </div>
            <div className="mt-2 text-[28px] font-semibold tracking-tight leading-none tabular-nums">
              {data.webhook_subscriptions.length}
            </div>
          </div>
          <span className="inline-flex items-center justify-center h-8 w-8 rounded-md bg-accent border border-border text-foreground/80 shrink-0">
            <Webhook className="h-[15px] w-[15px]" />
          </span>
        </div>
        <div className="mt-5 flex items-center gap-1.5 text-[11.5px]">
          {data.webhook_subscriptions.length > 0 ? (
            <span className="text-emerald-500 flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              {interpolate(t.dashboard.subscriptions, { count: data.webhook_subscriptions.length })}
            </span>
          ) : (
            <span className="text-muted-foreground">{t.dashboard.noSubscriptions}</span>
          )}
        </div>
      </article>

      {/* Briefings 30d */}
      <article className="group rounded-xl border border-border bg-card/60 p-5 transition-all duration-200 hover:border-muted-foreground/20 hover:-translate-y-px">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
              {t.dashboard.briefings30d}
            </div>
            <div className="mt-2 text-[28px] font-semibold tracking-tight leading-none tabular-nums">
              {data.briefings_count_30d}
            </div>
          </div>
          <span className="inline-flex items-center justify-center h-8 w-8 rounded-md bg-accent border border-border text-foreground/80 shrink-0">
            <FileText className="h-[15px] w-[15px]" />
          </span>
        </div>
        <div className="mt-5 text-[11.5px] text-muted-foreground">
          {t.dashboard.last30days}
        </div>
      </article>

      {/* Memories */}
      <Link to="/memories" aria-label={`${t.dashboard.memories}: ${data.memories_count}`}>
        <article className="group rounded-xl border border-border bg-card/60 p-5 transition-all duration-200 hover:border-brand/40 hover:-translate-y-px cursor-pointer h-full">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                {t.dashboard.memories}
              </div>
              <div className="mt-2 text-[28px] font-semibold tracking-tight leading-none tabular-nums">
                {data.memories_count}
              </div>
            </div>
            <span className="inline-flex items-center justify-center h-8 w-8 rounded-md bg-accent border border-border text-foreground/80 shrink-0">
              <Brain className="h-[15px] w-[15px]" />
            </span>
          </div>
          <div className="mt-5 inline-flex items-center gap-1 text-[11.5px] text-brand group-hover:text-brand/80 transition-colors">
            {t.dashboard.viewManageMemories}
            <ArrowRight className="h-3 w-3" />
          </div>
        </article>
      </Link>
    </section>
  );
});

// ---------------------------------------------------------------------------
// Embeddings Card (with progress bars)
// ---------------------------------------------------------------------------

const EmbeddingsCard = memo(function EmbeddingsCard({
  data,
}: {
  data: StatusData["embeddings_by_service"];
}) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const maxCount = data.length > 0 ? Math.max(...data.map((e) => e.count)) : 0;
  const totalCount = data.reduce((sum, e) => sum + e.count, 0);

  const handleRefresh = () => {
    void qc.invalidateQueries({ queryKey: ["status"] });
  };

  return (
    <article className="lg:col-span-4 rounded-xl border border-border bg-card/60 transition-all duration-200 hover:border-muted-foreground/20 hover:-translate-y-px">
      <header className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
            {t.dashboard.embeddingsByService}
          </div>
          <div className="mt-0.5 text-sm font-semibold text-foreground">
            {t.dashboard.embeddingsSubtitle}
          </div>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          className="text-muted-foreground hover:text-foreground transition-colors"
          title="Refresh"
          aria-label="Refresh embeddings"
        >
          <RotateCw className="h-[14px] w-[14px]" />
        </button>
      </header>
      <div className="p-5">
        {data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Database className="h-6 w-6 text-muted-foreground/40 mb-2" />
            <p className="text-sm text-muted-foreground">{t.dashboard.noEmbeddings}</p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              {t.dashboard.embeddingsAutoCreated}
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-3">
              {data.map((e, i) => {
                const Icon = getServiceIcon(e.service);
                const pct = maxCount > 0 ? (e.count / maxCount) * 100 : 0;
                // Opacity decreases for lower-ranked items
                const opacity = Math.max(0.4, 1 - i * 0.15);
                return (
                  <div key={e.service}>
                    <div className="flex items-center justify-between text-[12.5px]">
                      <div className="flex items-center gap-2">
                        <Icon className="h-[13px] w-[13px] text-muted-foreground" />
                        <span className="text-foreground">{e.service}</span>
                      </div>
                      <span className="font-mono tabular-nums text-foreground">
                        {e.count.toLocaleString()}
                      </span>
                    </div>
                    <div className="mt-1.5 h-[3px] rounded-full bg-border overflow-hidden">
                      <div
                        className="h-full rounded-full bg-brand transition-all duration-500"
                        style={{ width: `${pct}%`, opacity }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-5 pt-4 border-t border-border flex items-center justify-between text-[12px]">
              <span className="text-muted-foreground">{t.dashboard.total}</span>
              <span className="font-mono tabular-nums text-foreground">
                {totalCount.toLocaleString()}
              </span>
            </div>
          </>
        )}
      </div>
    </article>
  );
});

// ---------------------------------------------------------------------------
// Token Usage Card (Donut + Legend + Mini bars)
// ---------------------------------------------------------------------------

const TokenUsageCard = memo(function TokenUsageCard({
  data,
}: {
  data: StatusData["tokens_30d"];
}) {
  const { t } = useI18n();
  const total = data.input + data.output + data.cache_read + data.cache_write;

  const segments = [
    { label: "Input", value: data.input, color: "hsl(220 15% 35%)" },
    { label: "Output", value: data.output, color: "hsl(215 18% 45%)" },
    { label: "Cache Read", value: data.cache_read, color: "hsl(35 25% 45%)" },
    { label: "Cache Write", value: data.cache_write, color: "hsl(28 50% 64%)" },
  ];

  return (
    <article className="lg:col-span-4 rounded-xl border border-border bg-card/60 transition-all duration-200 hover:border-muted-foreground/20 hover:-translate-y-px">
      <header className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
            {t.dashboard.tokensAnthropic}
          </div>
          <div className="mt-0.5 text-sm font-semibold text-foreground">
            {t.dashboard.tokensSubtitle}
          </div>
        </div>
        {total > 0 && (
          <div className="text-[11.5px] text-muted-foreground font-mono tabular-nums">
            {total.toLocaleString()}
          </div>
        )}
      </header>
      <div className="p-5">
        {total === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Database className="h-6 w-6 text-muted-foreground/40 mb-2" />
            <p className="text-sm text-muted-foreground">{t.dashboard.noTokens}</p>
            <p className="text-xs text-muted-foreground/70 mt-1 max-w-[240px]">
              {t.dashboard.tokensExplain}
            </p>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-5">
              <DonutChart
                segments={segments}
                size={120}
                centerLabel="total"
                centerValue={formatTokenValue(total)}
              />
              <div className="flex-1 space-y-2 text-[12px]">
                {segments.map((seg) => (
                  <div key={seg.label} className="flex items-center justify-between">
                    <span className="flex items-center gap-2">
                      <span
                        className="h-2 w-2 rounded-sm"
                        style={{ background: seg.color }}
                      />
                      <span className="text-foreground">{seg.label}</span>
                    </span>
                    <span className="font-mono tabular-nums text-muted-foreground">
                      {seg.value.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </article>
  );
});

// ---------------------------------------------------------------------------
// MCP Activity Card
// ---------------------------------------------------------------------------

const McpActivityCard = memo(function McpActivityCard({
  data,
}: {
  data: StatusData["mcp_activity_30d"];
}) {
  const { t } = useI18n();

  return (
    <article className="lg:col-span-4 rounded-xl border border-border bg-card/60 transition-all duration-200 hover:border-muted-foreground/20 hover:-translate-y-px">
      <header className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
            {t.dashboard.mcpActivity}
          </div>
          <div className="mt-0.5 text-sm font-semibold text-foreground">
            {t.dashboard.mcpSubtitle}
          </div>
        </div>
        {data.total_calls > 0 && (
          <button className="text-muted-foreground hover:text-foreground text-[12px] inline-flex items-center gap-1 transition-colors">
            30d <ChevronDown className="h-3 w-3" />
          </button>
        )}
      </header>
      <div className="p-5">
        {data.total_calls === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Database className="h-6 w-6 text-muted-foreground/40 mb-2" />
            <p className="text-sm text-muted-foreground">{t.dashboard.noMcpCalls}</p>
            <p className="text-xs text-muted-foreground/70 mt-1 max-w-[240px]">
              {t.dashboard.mcpExplain}
            </p>
          </div>
        ) : (
          <>
            {/* Stat triplet */}
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-md border border-border bg-background/40 p-3">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  {t.dashboard.total}
                </div>
                <div className="mt-1.5 text-xl font-semibold tabular-nums">
                  {data.total_calls.toLocaleString()}
                </div>
              </div>
              <div className="rounded-md border border-border bg-background/40 p-3">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  {t.dashboard.success}
                </div>
                <div className="mt-1.5 text-xl font-semibold tabular-nums text-emerald-500">
                  {data.successful.toLocaleString()}
                </div>
              </div>
              <div className="rounded-md border border-border bg-background/40 p-3">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  {t.dashboard.errors}
                </div>
                <div className="mt-1.5 text-xl font-semibold tabular-nums text-destructive">
                  {data.failed.toLocaleString()}
                </div>
              </div>
            </div>

            {/* Tools used */}
            {data.tools_used.length > 0 && (
              <div className="mt-5">
                <div className="text-[10.5px] text-muted-foreground uppercase tracking-wider mb-2">
                  {t.dashboard.topTools}
                </div>
                <ul className="space-y-2">
                  {data.tools_used.map((tool) => (
                    <li
                      key={tool.service}
                      className="flex items-center justify-between text-[12.5px]"
                    >
                      <span className="font-mono text-[11.5px] text-foreground">
                        {tool.service}
                      </span>
                      <span className="font-mono tabular-nums text-muted-foreground">
                        {tool.count.toLocaleString()}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </article>
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
  const { t, locale } = useI18n();
  const dateLocale = locale === "pt" ? ptBR : enUS;
  const displayed = briefings.slice(0, MAX_RECENT_BRIEFINGS);

  return (
    <section className="rounded-xl border border-border bg-card/60 transition-all duration-200 hover:border-muted-foreground/20">
      <header className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
            {t.dashboard.recentBriefings}
          </div>
          <div className="mt-0.5 text-sm font-semibold text-foreground">
            {t.dashboard.recentBriefingsSubtitle}
          </div>
        </div>
        {briefings.length > 0 && (
          <Link
            to="/briefings"
            className="text-[12px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1 transition-colors"
          >
            {t.common.viewAll}
            <ArrowRight className="h-3 w-3" />
          </Link>
        )}
      </header>
      {displayed.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 text-center px-5">
          <Calendar className="h-6 w-6 text-muted-foreground/40 mb-2" />
          <p className="text-sm text-muted-foreground">{t.dashboard.noBriefings}</p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            {t.dashboard.briefingsAutoGenerated}
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border" aria-label={t.dashboard.recentBriefings}>
          {displayed.map((b) => (
            <li key={b.event_id}>
              <Link
                to={`/briefings/${b.event_id}`}
                className="flex items-center gap-4 px-5 py-3.5 hover:bg-accent/30 transition-colors group"
              >
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-accent border border-border shrink-0">
                  <FileText className="h-[14px] w-[14px] text-muted-foreground" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] font-medium truncate text-foreground">
                    {b.event_subject}
                  </div>
                  <div className="mt-1 text-[11.5px] text-muted-foreground font-mono">
                    {format(
                      new Date(b.event_start),
                      locale === "pt" ? "dd 'de' MMM · HH:mm" : "MMM dd · HH:mm",
                      { locale: dateLocale },
                    )}
                  </div>
                </div>
                <ChevronRight className="h-[14px] w-[14px] text-muted-foreground group-hover:text-foreground transition-colors shrink-0" />
              </Link>
            </li>
          ))}
        </ul>
      )}
      {briefings.length > MAX_RECENT_BRIEFINGS && (
        <div className="px-5 py-3 border-t border-border text-center">
          <Link
            to="/briefings"
            className="text-xs font-medium text-brand hover:text-brand/80 transition-colors"
          >
            {interpolate(t.dashboard.moreBriefings, {
              count: briefings.length - MAX_RECENT_BRIEFINGS,
            })}
          </Link>
        </div>
      )}
    </section>
  );
});

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-xl border border-border bg-card/60 p-5 space-y-3">
            <div className="flex items-start justify-between">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-8 w-8 rounded-md" />
            </div>
            <Skeleton className="h-7 w-16" />
            <Skeleton className="h-3 w-32" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="lg:col-span-4 rounded-xl border border-border bg-card/60 p-5 space-y-3"
          >
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-[180px] w-full" />
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-border bg-card/60 p-5 space-y-3">
        <Skeleton className="h-4 w-36" />
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-md" />
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
    <div className="space-y-6">
      <AlertBanner data={data} />
      <KpiCards data={data} />
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <EmbeddingsCard data={data.embeddings_by_service} />
        <TokenUsageCard data={data.tokens_30d} />
        <McpActivityCard data={data.mcp_activity_30d} />
      </section>
      <RecentBriefings briefings={data.recent_briefings} />
    </div>
  );
}
