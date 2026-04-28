import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Info } from "lucide-react";
import { useStatus } from "@/hooks/useStatus";
import { useAuth } from "@/auth/AuthContext";
import { api } from "@/lib/api";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ErrorState } from "@/components/ErrorState";

export function SettingsPage() {
  const { data, isLoading, error, refetch } = useStatus();
  const { user } = useAuth();

  const handleRefreshToken = async () => {
    try {
      await api.post("/auth/refresh");
      toast.success("Token renovado com sucesso.");
      void refetch();
    } catch {
      toast.error("Erro ao renovar token.");
    }
  };

  if (isLoading) {
    return <LoadingSkeleton count={4} className="h-24" />;
  }

  if (error || !data) {
    return <ErrorState onRetry={() => void refetch()} />;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Configurações</h1>

      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription>
          Configurações somente leitura nesta versão.
        </AlertDescription>
      </Alert>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Janela histórica de briefings</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {data.config.briefing_history_window_days} dias
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Configurado via env no servidor
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Email autenticado</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-medium">{user?.email}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Última sincronização</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-medium">
              {data.last_sync_at
                ? format(new Date(data.last_sync_at), "dd/MM/yyyy 'às' HH:mm", {
                    locale: ptBR,
                  })
                : "Nunca"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Token Microsoft</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Expira em{" "}
              {format(new Date(data.token_expires_at), "dd/MM/yyyy 'às' HH:mm", {
                locale: ptBR,
              })}
            </p>
            <Button variant="outline" size="sm" onClick={() => void handleRefreshToken()}>
              Renovar token agora
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
