import { Link } from "react-router-dom";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { BriefingListItem } from "@/hooks/useBriefings";

interface BriefingCardProps {
  briefing: BriefingListItem;
}

export function BriefingCard({ briefing }: BriefingCardProps) {
  const maxAttendees = 3;
  const visible = briefing.attendees.slice(0, maxAttendees);
  const remaining = briefing.attendees.length - maxAttendees;

  return (
    <Link to={`/briefings/${briefing.event_id}`}>
      <Card className="hover:bg-accent transition-colors">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{briefing.event_subject}</CardTitle>
          <p className="text-sm text-muted-foreground">
            {format(new Date(briefing.event_start), "dd 'de' MMM 'de' yyyy '·' HH:mm", {
              locale: ptBR,
            })}
          </p>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-1">
            {visible.map((a) => (
              <Badge key={a} variant="secondary">
                {a}
              </Badge>
            ))}
            {remaining > 0 && (
              <Badge variant="outline">+{remaining} mais</Badge>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
