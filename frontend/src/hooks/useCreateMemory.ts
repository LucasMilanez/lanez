import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";

interface MemoryResponse {
  id: string;
  content: string;
  tags: string[];
  created_at: string;
}

interface CreateMemoryInput {
  content: string;
  tags?: string[];
}

export function useCreateMemory() {
  return useMutation<MemoryResponse, ApiError, CreateMemoryInput>({
    mutationFn: ({ content, tags = [] }) =>
      api.post<MemoryResponse>("/memories", { content, tags }),
  });
}
