import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface BriefingDetail {
  id: string;
  event_id: string;
  event_subject: string;
  event_start: string;
  event_end: string;
  attendees: string[];
  content: string;
  generated_at: string;
  model_used: string;
  input_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  output_tokens: number;
}

export function useBriefing(eventId: string) {
  return useQuery({
    queryKey: ["briefing", eventId],
    queryFn: () => api.get<BriefingDetail>(`/briefings/${eventId}`),
    staleTime: 30_000,
    enabled: !!eventId,
  });
}
