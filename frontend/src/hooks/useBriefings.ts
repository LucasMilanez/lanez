import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface BriefingListItem {
  id: string;
  event_id: string;
  event_subject: string;
  event_start: string;
  event_end: string;
  attendees: string[];
  generated_at: string;
}

export interface BriefingListResponse {
  items: BriefingListItem[];
  total: number;
  page: number;
  page_size: number;
}

export function useBriefings(page: number, pageSize: number, q: string) {
  return useQuery({
    queryKey: ["briefings", { page, pageSize, q }],
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (q) params.set("q", q);
      return api.get<BriefingListResponse>(`/briefings?${params.toString()}`);
    },
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}
