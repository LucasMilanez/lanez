import { useState, useEffect } from "react";
import { FileText } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useBriefings } from "@/hooks/useBriefings";
import { BriefingCard } from "@/components/BriefingCard";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { useI18n, interpolate } from "@/i18n/I18nContext";

export function BriefingsListPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const pageSize = 20;
  const { t } = useI18n();

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const { data, isLoading, error, refetch } = useBriefings(page, pageSize, debouncedSearch);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div className="space-y-6">
      <Input
        placeholder={t.briefingsPage.searchPlaceholder}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-md"
      />

      {isLoading && <LoadingSkeleton count={5} className="h-24" />}

      {error && <ErrorState onRetry={() => void refetch()} />}

      {data && data.items.length === 0 && (
        <EmptyState
          title={t.briefingsPage.noBriefings}
          description={t.briefingsPage.noBriefingsDesc}
          icon={<FileText className="h-10 w-10" />}
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="space-y-4">
            {data.items.map((b) => (
              <BriefingCard key={b.id} briefing={b} />
            ))}
          </div>

          <div className="flex items-center justify-between">
            <Button
              variant="outline"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              {t.auditPage.previous}
            </Button>
            <span className="text-sm text-muted-foreground">
              {interpolate(t.common.pageOf, { current: page, total: totalPages })}
            </span>
            <Button
              variant="outline"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              {t.auditPage.next}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
