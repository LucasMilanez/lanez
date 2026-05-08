import { useParams, Link } from "react-router-dom";
import { format } from "date-fns";
import { ptBR, enUS } from "date-fns/locale";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useBriefing } from "@/hooks/useBriefing";
import { BriefingMarkdown } from "@/components/BriefingMarkdown";
import { BriefingTTSButton } from "@/components/BriefingTTSButton";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ApiError } from "@/lib/api";
import { useI18n, interpolate } from "@/i18n/I18nContext";

export function BriefingDetailPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const { data, isLoading, error, refetch } = useBriefing(eventId ?? "");
  const { t, locale } = useI18n();
  const dateLocale = locale === "pt" ? ptBR : enUS;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <LoadingSkeleton count={1} className="h-8 w-48" />
        <LoadingSkeleton count={1} className="h-4 w-32" />
        <LoadingSkeleton count={3} className="h-24" />
      </div>
    );
  }

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return <EmptyState title={t.briefingsPage.notFound} />;
    }
    return <ErrorState onRetry={() => void refetch()} />;
  }

  if (!data) {
    return <EmptyState title={t.briefingsPage.notFound} />;
  }

  return (
    <div className="space-y-6">
      <Link to="/briefings">
        <Button variant="ghost" size="sm">
          <ArrowLeft className="h-4 w-4 mr-2" />
          {t.common.back}
        </Button>
      </Link>

      <div className="space-y-3">
        <h2 className="font-display text-2xl font-semibold tracking-tight text-balance">
          {data.event_subject}
        </h2>
        <p className="text-sm text-muted-foreground tabular-nums">
          {format(new Date(data.event_start), "dd 'de' MMMM 'de' yyyy '·' HH:mm", {
            locale: dateLocale,
          })}
          {" — "}
          {format(new Date(data.event_end), "HH:mm", { locale: dateLocale })}
        </p>
        <div className="flex flex-wrap gap-1">
          {data.attendees.map((a) => (
            <Badge key={a} variant="secondary">
              {a}
            </Badge>
          ))}
        </div>
        <div>
          <BriefingTTSButton content={data.content} />
        </div>
      </div>

      <details className="group rounded-md border border-border bg-card/40 overflow-hidden">
        <summary className="cursor-pointer select-none px-4 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors list-none flex items-center justify-between">
          <span>{t.briefingsPage.technicalDetails}</span>
          <span className="text-[10px] text-muted-foreground/70 transition-transform group-open:rotate-90">▸</span>
        </summary>
        <div className="px-4 pb-3 pt-1 text-xs text-muted-foreground tabular-nums space-y-1">
          <p>
            {interpolate(t.briefingsPage.generatedAt, {
              date: format(new Date(data.generated_at), "dd/MM/yyyy 'às' HH:mm", {
                locale: dateLocale,
              }),
            })}
          </p>
          <p>
            {interpolate(t.briefingsPage.inputTokens, {
              count: (
                data.input_tokens +
                data.cache_read_tokens +
                data.cache_write_tokens
              ).toLocaleString(),
            })}
            {" · "}
            {interpolate(t.briefingsPage.outputTokens, {
              count: data.output_tokens.toLocaleString(),
            })}
            {" · "}
            {interpolate(t.briefingsPage.model, { name: "" })}
            <span className="font-mono">{data.model_used}</span>
          </p>
        </div>
      </details>

      <Separator />

      <BriefingMarkdown content={data.content} />
    </div>
  );
}
