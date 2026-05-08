import { format } from "date-fns";
import { ptBR, enUS } from "date-fns/locale";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Copy, Key, Check, Eye, EyeOff, AlertTriangle } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useStatus } from "@/hooks/useStatus";
import { useAuth } from "@/auth/AuthContext";
import { api, ApiError } from "@/lib/api";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ErrorState } from "@/components/ErrorState";
import { useState } from "react";
import { useI18n } from "@/i18n/I18nContext";

function maskToken(token: string): string {
  if (token.length <= 8) return "•".repeat(token.length);
  return `${"•".repeat(20)}${token.slice(-4)}`;
}

export function SettingsPage() {
  const { data, isLoading, error, refetch } = useStatus();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [mcpToken, setMcpToken] = useState<string | null>(null);
  const [tokenRevealed, setTokenRevealed] = useState(false);
  const [loadingToken, setLoadingToken] = useState(false);
  const [copied, setCopied] = useState(false);
  const { t, locale } = useI18n();
  const dateLocale = locale === "pt" ? ptBR : enUS;

  const handleRefreshToken = async () => {
    try {
      await api.post("/auth/refresh");
      await qc.invalidateQueries({ queryKey: ["status"] });
      toast.success(t.settingsPage.renewSuccess);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : t.settingsPage.renewError;
      toast.error(msg);
    }
  };

  const handleGenerateMcpToken = async () => {
    setLoadingToken(true);
    try {
      const resp = await api.get<{ access_token: string }>("/auth/token");
      setMcpToken(resp.access_token);
      setTokenRevealed(false);
      toast.success(t.settingsPage.tokenGenerated);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : t.settingsPage.renewError;
      toast.error(msg);
    } finally {
      setLoadingToken(false);
    }
  };

  const mcpBaseUrl = "https://lanez-app.fly.dev/mcp";

  const handleCopyConfig = async () => {
    if (!mcpToken) return;
    const config = `"mcpServers": {
  "lanez": {
    "command": "mcp-remote",
    "args": [
      "${mcpBaseUrl}",
      "--header",
      "Authorization: Bearer ${mcpToken}"
    ]
  }
}`;
    try {
      await navigator.clipboard.writeText(config);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.success(t.settingsPage.configCopied);
    } catch {
      toast.error(t.settingsPage.copyFailed);
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
      <div className="grid gap-4 md:grid-cols-2">
        {/* Read-only card — styled distinctly from interactive cards */}
        <Card className="shadow-soft opacity-95">
          <CardHeader className="pb-2">
            <CardTitle className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {t.settingsPage.briefingWindow}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-display text-3xl font-semibold tabular-nums tracking-tight">
              {data.config.briefing_history_window_days}
              <span className="ml-1 text-base font-medium text-muted-foreground">
                {t.settingsPage.days}
              </span>
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              {t.settingsPage.configuredViaEnv}
            </p>
          </CardContent>
        </Card>

        <Card className="shadow-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {t.settingsPage.authenticatedEmail}
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
              {t.settingsPage.lastSync}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-display text-base font-semibold tabular-nums">
              {data.last_sync_at
                ? format(new Date(data.last_sync_at), "dd/MM/yyyy 'às' HH:mm", {
                    locale: dateLocale,
                  })
                : t.settingsPage.never}
            </p>
          </CardContent>
        </Card>

        <Card className="shadow-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {t.settingsPage.microsoftToken}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground tabular-nums">
              {t.settingsPage.expiresAt}{" "}
              {format(new Date(data.token_expires_at), "dd/MM/yyyy 'às' HH:mm", {
                locale: dateLocale,
              })}
            </p>
            <Button variant="outline" size="sm" onClick={() => void handleRefreshToken()}>
              {t.settingsPage.renewNow}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Token MCP para clientes externos */}
      <Card className="shadow-soft border-primary/20">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold">
            <Key className="h-4 w-4" />
            {t.settingsPage.connectMcpClient}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {t.settingsPage.mcpConfigDesc} {t.settingsPage.tokenValid7Days}
          </p>

          {!mcpToken ? (
            <Button
              variant="default"
              size="sm"
              onClick={() => void handleGenerateMcpToken()}
              disabled={loadingToken}
            >
              <Key className="h-3.5 w-3.5 mr-1.5" />
              {loadingToken ? t.settingsPage.generatingToken : t.settingsPage.generateMcpConfig}
            </Button>
          ) : (
            <div className="space-y-4">
              {/* Security warning */}
              <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/[0.04] p-3">
                <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  {t.settingsPage.tokenWarning}
                </p>
              </div>

              {/* Masked token display */}
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  {t.settingsPage.mcpTokenGenerated}
                </p>
                <div className="flex items-center gap-2 rounded-md border bg-muted px-3 py-2">
                  <code className="flex-1 font-mono text-xs break-all">
                    {tokenRevealed ? mcpToken : maskToken(mcpToken)}
                  </code>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    onClick={() => setTokenRevealed((v) => !v)}
                    title={tokenRevealed ? t.common.hide : t.common.reveal}
                    aria-label={tokenRevealed ? t.common.hide : t.common.reveal}
                  >
                    {tokenRevealed ? (
                      <EyeOff className="h-3.5 w-3.5" />
                    ) : (
                      <Eye className="h-3.5 w-3.5" />
                    )}
                  </Button>
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  {t.settingsPage.mcpPasteInstruction}
                </p>
                <div className="relative">
                  <pre className="bg-muted rounded-md p-3 pr-10 text-xs font-mono whitespace-pre overflow-x-auto">
{`"mcpServers": {
  "lanez": {
    "command": "mcp-remote",
    "args": [
      "${mcpBaseUrl}",
      "--header",
      "Authorization: Bearer ${tokenRevealed ? mcpToken : "<token>"}"
    ]
  }
}`}
                  </pre>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute top-2 right-2 h-6 w-6"
                    onClick={() => void handleCopyConfig()}
                    title={copied ? t.settingsPage.configCopied : t.settingsPage.copyConfig}
                    aria-label={copied ? t.settingsPage.configCopied : t.settingsPage.copyConfig}
                  >
                    {copied ? (
                      <Check className="h-3.5 w-3.5 text-green-500" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </Button>
                </div>
              </div>

              <div className="text-xs text-muted-foreground space-y-2 border-t pt-3">
                <p className="font-medium text-foreground">{t.settingsPage.howToUse}</p>
                <ol className="list-decimal list-inside space-y-1">
                  <li>
                    {t.settingsPage.openConfigFile}
                    <br />
                    <code className="text-[10px]">%APPDATA%\Claude\claude_desktop_config.json</code>{" "}
                    {t.settingsPage.onWindows}
                    <br />
                    <code className="text-[10px]">~/Library/Application Support/Claude/claude_desktop_config.json</code>{" "}
                    {t.settingsPage.onMacOS}
                  </li>
                  <li>{t.settingsPage.addMcpServersBlock}</li>
                  <li>{t.settingsPage.saveAndRestart}</li>
                  <li>{t.settingsPage.toolsShouldAppear}</li>
                </ol>
              </div>

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handleCopyConfig()}
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5 mr-1.5 text-green-500" />
                  ) : (
                    <Copy className="h-3.5 w-3.5 mr-1.5" />
                  )}
                  {copied ? t.settingsPage.configCopied : t.settingsPage.copyConfig}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void handleGenerateMcpToken()}
                  disabled={loadingToken}
                >
                  {t.settingsPage.generateNewToken}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
