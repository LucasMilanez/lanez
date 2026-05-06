import { useState, useCallback } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import {
  Loader2,
  AlertCircle,
  Search,
  Brain,
  Calendar,
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  Lock,
  Shield,
  PlayCircle,
} from "lucide-react";

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.87-1.54-3.87-1.54-.52-1.32-1.27-1.67-1.27-1.67-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.02 1.75 2.69 1.25 3.34.96.1-.74.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.7 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11 11 0 015.78 0c2.21-1.49 3.18-1.18 3.18-1.18.62 1.59.23 2.76.11 3.05.74.81 1.18 1.84 1.18 3.1 0 4.43-2.69 5.41-5.25 5.69.41.36.78 1.07.78 2.16 0 1.56-.01 2.81-.01 3.19 0 .31.21.67.8.56C20.21 21.39 23.5 17.08 23.5 12 23.5 5.65 18.35.5 12 .5z" />
    </svg>
  );
}
import { Button } from "@/components/ui/button";
import { useAuth } from "@/auth/AuthContext";
import { cn } from "@/lib/utils";

const GITHUB_URL = "https://github.com/LucasMilanez/lanez";
const PORTFOLIO_URL = "https://lanez.pt";
const DEMO_VIDEO_URL = import.meta.env.VITE_DEMO_VIDEO_URL ?? "";

const pillars = [
  {
    icon: Search,
    title: "Busca semântica cross-service",
    description:
      "pgvector + all-MiniLM-L6-v2 (384d). Encontra por significado em e-mail, calendário, OneNote e OneDrive simultaneamente, em <2s.",
  },
  {
    icon: Calendar,
    title: "Briefings automáticos pré-reunião",
    description:
      "Webhook do Graph detecta o evento, coleta contexto multi-fonte (e-mails, notas, arquivos, memórias) e gera prep estruturado via Claude Haiku.",
  },
  {
    icon: Brain,
    title: "Memória persistente",
    description:
      "save_memory / recall_memory. A AI lembra decisões, preferências e contexto entre sessões. Cada interação fica mais inteligente que a anterior.",
  },
] as const;

const stack = [
  "FastAPI",
  "PostgreSQL + pgvector",
  "Redis",
  "Sentence Transformers",
  "Claude Haiku 4.5",
  "Groq Whisper",
  "MCP 2025-06-18",
  "React + Vite",
] as const;

const configSnippet = `{
  "mcpServers": {
    "lanez": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://lanez-app.fly.dev/mcp",
        "--header", "Authorization: Bearer <token>"
      ]
    }
  }
}`;

export function LoginPage() {
  const { login, user, loading } = useAuth();
  const [isRedirecting, setIsRedirecting] = useState(false);
  const [searchParams] = useSearchParams();
  const errorParam = searchParams.get("error");

  const handleLogin = useCallback(() => {
    setIsRedirecting(true);
    login();
  }, [login]);

  const scrollToDemo = useCallback((e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    document
      .getElementById("demo-video")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="h-5 w-5 animate-spin text-brand" />
      </div>
    );
  }

  if (user) return <Navigate to="/dashboard" replace />;

  return (
    <div className="relative min-h-screen bg-background text-foreground">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[640px] overflow-hidden"
        style={{
          background: [
            "radial-gradient(ellipse 80% 60% at 50% 0%, hsl(var(--brand) / 0.18), transparent 70%)",
            "radial-gradient(ellipse 50% 40% at 80% 30%, hsl(217 91% 60% / 0.10), transparent 60%)",
          ].join(", "),
        }}
      />

      <div className="relative mx-auto max-w-3xl px-6 py-12 sm:py-16 md:py-20">
        <header className="flex items-center gap-4 mb-14">
          <a
            href={PORTFOLIO_URL}
            className="group inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-3 w-3 transition-transform group-hover:-translate-x-0.5" />
            lanez.pt
          </a>
          <span className="h-4 w-px bg-border" aria-hidden="true" />
          <div className="flex items-center gap-2.5">
            <img
              src="/favicon.svg"
              alt=""
              aria-hidden="true"
              className="h-7 w-7"
            />
            <div className="flex items-baseline gap-2">
              <span className="font-display text-base font-semibold tracking-tight">
                Lanez
              </span>
              <span className="text-[11px] font-mono text-muted-foreground/70">
                v0.1
              </span>
            </div>
          </div>
        </header>

        <section className="space-y-6 mb-16">
          <div className="inline-flex items-center gap-1.5 rounded-full border border-brand/20 bg-brand/[0.04] px-3 py-1">
            <span className="text-[11px] font-medium text-brand">
              Open source · MCP Server
            </span>
          </div>

          <h1 className="font-display text-4xl sm:text-5xl md:text-[3.25rem] font-semibold tracking-tight leading-[1.05]">
            O{" "}
            <span className="bg-gradient-to-r from-brand via-blue-400 to-cyan-300 bg-clip-text text-transparent">
              Microsoft 365
            </span>{" "}
            como contexto para qualquer AI.
          </h1>

          <p className="text-[15px] sm:text-base text-muted-foreground leading-relaxed max-w-2xl">
            Lanez é um servidor MCP self-hosted que conecta Calendar, Mail, OneNote
            e OneDrive a Claude Desktop, Cursor e qualquer cliente que fale o
            protocolo. Substitui o Microsoft Copilot ($30/mês) por ~$1/mês com
            busca semântica, memória persistente e briefings automáticos pré-reunião.
          </p>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <a
              href="#demo-video"
              onClick={scrollToDemo}
              className={cn(
                "inline-flex items-center gap-2 rounded-xl bg-foreground text-background",
                "h-11 px-5 text-[14px] font-semibold shadow-elevated",
                "transition-all duration-150 hover:scale-[1.02] active:scale-[0.98]",
              )}
            >
              <PlayCircle className="h-4 w-4" />
              Watch demo (60s)
            </a>

            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                "inline-flex items-center gap-2 rounded-xl border border-border bg-card",
                "h-11 px-5 text-[14px] font-medium",
                "transition-all duration-150 hover:border-brand/40 hover:bg-card/80",
              )}
            >
              <GithubIcon className="h-4 w-4" />
              View on GitHub
              <ExternalLink className="h-3.5 w-3.5 opacity-60" />
            </a>
          </div>
        </section>

        <section id="demo-video" className="mb-20 scroll-mt-12">
          <SectionLabel>See it in action</SectionLabel>
          <div className="overflow-hidden rounded-2xl border border-border bg-card">
            <div className="relative aspect-video w-full bg-background">
              {DEMO_VIDEO_URL ? (
                <iframe
                  src={DEMO_VIDEO_URL}
                  title="Lanez — 60-second walkthrough"
                  loading="lazy"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                  allowFullScreen
                  className="absolute inset-0 h-full w-full"
                />
              ) : (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-muted-foreground">
                  <PlayCircle className="h-8 w-8 opacity-40" strokeWidth={1.5} />
                  <p className="text-[12.5px] font-medium">
                    Vídeo em produção
                  </p>
                  <p className="text-[11px] opacity-70 max-w-xs text-center px-6">
                    Walkthrough de 60 segundos chegando em breve. Enquanto isso,
                    o código já está aberto no GitHub.
                  </p>
                </div>
              )}
            </div>
          </div>
          <div className="mt-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <p className="text-[12px] text-muted-foreground">
              60-second walkthrough: searching emails, saving memories,
              generating briefings.
            </p>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[12px] font-medium text-foreground hover:text-brand transition-colors"
            >
              Curtiu? Vê o código no GitHub
              <ArrowRight className="h-3.5 w-3.5" />
            </a>
          </div>
        </section>

        <section className="grid grid-cols-2 sm:grid-cols-4 gap-px rounded-2xl border border-border bg-border overflow-hidden mb-20">
          {[
            { value: "9", label: "MCP Tools" },
            { value: "<2s", label: "p50 latency" },
            { value: "204", label: "Tests passing" },
            { value: "~$1/mês", label: "Custo demo" },
          ].map(({ value, label }) => (
            <div key={label} className="bg-card px-4 py-5 text-center">
              <p className="font-display text-2xl font-semibold tracking-tight">
                {value}
              </p>
              <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground mt-1">
                {label}
              </p>
            </div>
          ))}
        </section>

        <section className="mb-20">
          <SectionLabel>Três pilares</SectionLabel>
          <div className="grid sm:grid-cols-3 gap-4">
            {pillars.map(({ icon: Icon, title, description }) => (
              <article
                key={title}
                className="rounded-2xl border border-border bg-card p-5 hover:border-brand/30 transition-colors"
              >
                <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-brand/10 text-brand mb-3.5">
                  <Icon className="h-4 w-4" strokeWidth={2.25} />
                </span>
                <h3 className="font-display text-[15px] font-semibold tracking-tight mb-1.5">
                  {title}
                </h3>
                <p className="text-[12.5px] text-muted-foreground leading-relaxed">
                  {description}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="mb-20">
          <SectionLabel>Conectar em 30 segundos</SectionLabel>
          <ol className="space-y-3.5">
            <Step n={1} title="Login Microsoft 365 (read-only)">
              OAuth 2.0 + PKCE com escopos read-only para Calendar, Mail, OneNote
              e OneDrive. Tokens criptografados Fernet AES-256 + PBKDF2 480k iterações.
            </Step>

            <Step n={2} title="Cole o snippet no claude_desktop_config.json">
              <pre className="mt-3 rounded-xl border border-border bg-background p-4 overflow-x-auto text-[12px] font-mono leading-relaxed">
                <code className="text-foreground/85">{configSnippet}</code>
              </pre>
            </Step>

            <Step n={3} title="As 9 tools aparecem no Claude Desktop">
              <code className="text-[11.5px] font-mono text-muted-foreground break-words">
                get_calendar_events · search_emails · get_onenote_pages ·
                search_files · web_search · semantic_search · save_memory ·
                recall_memory · get_briefing
              </code>
            </Step>
          </ol>
        </section>

        <section className="mb-16">
          <SectionLabel>Stack</SectionLabel>
          <div className="flex flex-wrap gap-2">
            {stack.map((tech) => (
              <span
                key={tech}
                className="rounded-lg border border-border bg-card px-3 py-1.5 text-[12px] font-medium text-foreground/80"
              >
                {tech}
              </span>
            ))}
          </div>
        </section>

        <section className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-12 text-[11.5px] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <Lock className="h-3 w-3" />
            OAuth 2.0 + PKCE
          </span>
          <span className="opacity-30">·</span>
          <span className="flex items-center gap-1.5">
            <Shield className="h-3 w-3" />
            Read-only scopes
          </span>
          <span className="opacity-30">·</span>
          <span>Audit trail append-only</span>
          <span className="opacity-30">·</span>
          <span>Fernet AES-256 + PBKDF2 480k</span>
        </section>

        {errorParam && (
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-xl border border-destructive/25 bg-destructive/[0.04] px-3.5 py-3 mb-6 max-w-md"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div>
              <p className="font-medium text-[13px] text-destructive">
                Falha na autenticação
              </p>
              <p className="text-[11px] text-destructive/80 mt-0.5">
                Verifique sua conta Microsoft e tente novamente.
              </p>
            </div>
          </div>
        )}

        <footer className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pt-8 border-t border-border/60">
          <p className="text-[12px] text-muted-foreground">
            Construído por{" "}
            <a
              href={PORTFOLIO_URL}
              className="font-medium text-foreground hover:text-brand transition-colors"
            >
              Lucas Milanez
            </a>
            {" · "}
            <a
              href={PORTFOLIO_URL}
              className="hover:text-foreground transition-colors"
            >
              lanez.pt
            </a>
            {" · "}
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-foreground transition-colors"
            >
              GitHub
            </a>
          </p>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-2.5 text-[12px] font-medium text-muted-foreground hover:text-foreground"
            onClick={handleLogin}
            disabled={isRedirecting}
            aria-busy={isRedirecting}
          >
            {isRedirecting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Conectando…</span>
              </>
            ) : (
              <>
                <span>Admin login</span>
                <ArrowRight className="h-3.5 w-3.5 ml-0.5" />
              </>
            )}
          </Button>
        </footer>
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        {children}
      </h2>
      <div className="h-px flex-1 bg-border" />
    </div>
  );
}

function Step({
  n,
  title,
  children,
}: {
  n: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li className="flex gap-4 rounded-2xl border border-border bg-card p-5">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand text-brand-foreground font-display text-[13px] font-semibold">
        {n}
      </span>
      <div className="flex-1 min-w-0 pt-0.5">
        <h4 className="font-display text-[14px] font-semibold tracking-tight mb-1">
          {title}
        </h4>
        <div className="text-[13px] text-muted-foreground leading-relaxed">
          {children}
        </div>
      </div>
    </li>
  );
}
