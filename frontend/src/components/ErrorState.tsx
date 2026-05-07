import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/i18n/I18nContext";

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  const { t } = useI18n();
  const displayMessage = message ?? t.common.errorLoading;

  return (
    <Alert variant="destructive">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>{t.common.error}</AlertTitle>
      <AlertDescription className="flex items-center justify-between">
        <span>{displayMessage}</span>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry} className="ml-4">
            {t.common.retry}
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
