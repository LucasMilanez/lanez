import { useParams, Link } from "react-router-dom";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
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

export function BriefingDetailPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const { data, isLoading, error, refetch } = useBriefing(eventId ?? "");

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
      return <EmptyState title="Briefing não encontrado" />;
    }
    return <ErrorState onRetry={() => void refetch()} />;
  }

  if (!data) {
    return <EmptyState title="Briefing não encontrado" />;
  }

  return (
    <div className="space-y-6">
      <Link to="/briefings">
        <Button variant="ghost" size="sm">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Voltar
        </Button>
      </Link>

      <div>
        <h1 className="text-2xl font-bold">{data.event_subject}</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {format(new Date(data.event_start), "dd 'de' MMMM 'de' yyyy '·' HH:mm", {
            locale: ptBR,
          })}
          {" — "}
          {format(new Date(data.event_end), "HH:mm", { locale: ptBR })}
        </p>
        <div className="flex flex-wrap gap-1 mt-3">
          {data.attendees.map((a) => (
            <Badge key={a} variant="secondary">
              {a}
            </Badge>
          ))}
        </div>
        <div className="mt-3">
          <BriefingTTSButton content={data.content} />
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Gerado em{" "}
        {format(new Date(data.generated_at), "dd/MM/yyyy 'às' HH:mm", {
          locale: ptBR,
        })}
        {" · "}
        {data.input_tokens + data.cache_read_tokens + data.cache_write_tokens} tokens
        entrada · {data.output_tokens} saída · modelo {data.model_used}
      </p>

      <Separator />

      <BriefingMarkdown content={data.content} />
    </div>
  );
}
