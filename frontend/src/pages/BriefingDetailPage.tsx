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
import { useI18n } from "@/i18n/I18nContext";

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

      <p className="text-xs text-muted-foreground tabular-nums">
        Gerado em{" "}
        {format(new Date(data.generated_at), "dd/MM/yyyy 'às' HH:mm", {
          locale: dateLocale,
        })}
        {" · "}
        {data.input_tokens + data.cache_read_tokens + data.cache_write_tokens} tokens
        entrada · {data.output_tokens} saída · modelo{" "}
        <span className="font-mono">{data.model_used}</span>
      </p>

      <Separator />

      <BriefingMarkdown content={data.content} />
    </div>
  );
}
