import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface StatusData {
  user_email: string;
  token_expires_at: string;
  token_expires_in_seconds: number;
  last_sync_at: string | null;
  webhook_subscriptions: Array<{ resource: string; expires_at: string }>;
  embeddings_by_service: Array<{ service: string; count: number }>;
  memories_count: number;
  briefings_count_30d: number;
  recent_briefings: Array<{
    event_id: string;
    event_subject: string;
    event_start: string;
  }>;
  tokens_30d: {
    input: number;
    output: number;
    cache_read: number;
    cache_write: number;
  };
  config: { briefing_history_window_days: number };
}

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: () => api.get<StatusData>("/status"),
    staleTime: 30_000,
  });
}
