import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface AuditLogItem {
  id: string;
  event_type: string;
  event_data: Record<string, unknown>;
  success: boolean;
  error_message: string | null;
  latency_ms: number | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditFilters {
  page: number;
  pageSize: number;
  eventTypes?: string[];
  since?: string;
  until?: string;
  q?: string;
}

export function useAuditLog(filters: AuditFilters) {
  return useQuery({
    queryKey: ["audit", filters],
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(filters.page),
        page_size: String(filters.pageSize),
      });
      if (filters.eventTypes) {
        for (const t of filters.eventTypes) {
          params.append("event_type", t);
        }
      }
      if (filters.since) params.set("since", filters.since);
      if (filters.until) params.set("until", filters.until);
      if (filters.q) params.set("q", filters.q);
      return api.get<AuditLogListResponse>(`/audit?${params.toString()}`);
    },
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}
