import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Info, Copy, Key } from "lucide-react";
import { useStatus } from "@/hooks/useStatus";
import { useAuth } from "@/auth/AuthContext";
import { api } from "@/lib/api";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ErrorState } from "@/components/ErrorState";
import { useState } from "react";

export function SettingsPage() {
  const { data, isLoading, error, refetch } = useStatus();
  const { user } = useAuth();
  const [mcpToken, setMcpToken] = useState<string | null>(null);
  const [loadingToken, setLoadingToken] = useState(false);

  const handleRefreshToken = async () => {
    try {
      await api.post("/auth/refresh");
      toast.success("Token renovado com sucesso.");
      void refetch();
    } catch {
      toast.error("Erro ao renovar token.");
    }
  };

  const handleGenerateMcpToken = async () => {
    setLoadingToken(true);
    try {
      const resp = await api.get<{ access_token: string }>("/auth/token");
      setMcpToken(resp.access_token);
      toast.success("Token gerado. Copie e cole no seu cliente MCP.");
    } catch {
      toast.error("Erro ao gerar token MCP.");
    } finally {
      setLoadingToken(false);
    }
  };

  const mcpBaseUrl = "https://lanez-app.fly.dev/mcp";

  const handleCopyConfig = async () => {
    if (!mcpToken) return;
    const config = `"mcpServers": {
  "lanez": {
    "command": "npx",
    "args": [
      "-y",
      "mcp-remote",
      "${mcpBaseUrl}",
      "--header",
      "Authorization: Bearer ${mcpToken}"
    ]
  }
}`;
    try {
      await navigator.clipboard.writeText(config);
      toast.success("Configuração copiada!");
    } catch {
      toast.error("Falha ao copiar. Selecione manualmente.");
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
      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription>
          Configurações somente leitura nesta versão.
        </AlertDescription>
      </Alert>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="shadow-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Janela histórica de briefings
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-display text-3xl font-semibold tabular-nums tracking-tight">
              {data.config.briefing_history_window_days}
              <span className="ml-1 text-base font-medium text-muted-foreground">
                dias
              </span>
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              Configurado via env no servidor
            </p>
          </CardContent>
        </Card>

        <Card className="shadow-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Email autenticado
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-display text-base font-semibold truncate">
              {user?.email}
            </p>
          </CardContent>
        </Card>

        <Card className="shadow-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Última sincronização
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-display text-base font-semibold tabular-nums">
              {data.last_sync_at
                ? format(new Date(data.last_sync_at), "dd/MM/yyyy 'às' HH:mm", {
                    locale: ptBR,
                  })
                : "Nunca"}
            </p>
          </CardContent>
        </Card>

        <Card className="shadow-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Token Microsoft
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground tabular-nums">
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

      {/* Token MCP para clientes externos */}
      <Card className="shadow-soft border-primary/20">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold">
            <Key className="h-4 w-4" />
            Conectar cliente MCP (Claude Desktop, Cursor, etc.)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Gere a configuração para conectar um cliente MCP ao Lanez.
            O token gerado é válido por 7 dias.
          </p>

          {!mcpToken ? (
            <Button
              variant="default"
              size="sm"
              onClick={() => void handleGenerateMcpToken()}
              disabled={loadingToken}
            >
              <Key className="h-3.5 w-3.5 mr-1.5" />
              {loadingToken ? "Gerando..." : "Gerar configuração MCP"}
            </Button>
          ) : (
            <div className="space-y-4">
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  Adicione este bloco ao seu <code>claude_desktop_config.json</code>:
                </p>
                <div className="relative">
                  <pre className="bg-muted rounded-md p-3 pr-10 text-xs font-mono whitespace-pre overflow-x-auto">
{`"mcpServers": {
  "lanez": {
    "command": "npx",
    "args": [
      "-y",
      "mcp-remote",
      "https://lanez-app.fly.dev/mcp",
      "--header",
      "Authorization: Bearer ${mcpToken}"
    ]
  }
}`}
                  </pre>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute top-2 right-2 h-6 w-6"
                    onClick={() => void handleCopyConfig()}
                    title="Copiar configuração"
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              <div className="text-xs text-muted-foreground space-y-2 border-t pt-3">
                <p className="font-medium text-foreground">Como usar:</p>
                <ol className="list-decimal list-inside space-y-1">
                  <li>
                    Abra o arquivo de config do Claude Desktop:
                    <br />
                    <code className="text-[10px]">%APPDATA%\Claude\claude_desktop_config.json</code> (Windows)
                    <br />
                    <code className="text-[10px]">~/Library/Application Support/Claude/claude_desktop_config.json</code> (macOS)
                  </li>
                  <li>Adicione o bloco <code>"mcpServers"</code> acima ao JSON existente</li>
                  <li>Salve e reinicie o Claude Desktop completamente</li>
                  <li>9 ferramentas Lanez devem aparecer no menu de tools</li>
                </ol>
              </div>

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handleCopyConfig()}
                >
                  <Copy className="h-3.5 w-3.5 mr-1.5" />
                  Copiar config
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void handleGenerateMcpToken()}
                  disabled={loadingToken}
                >
                  Gerar novo token
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
