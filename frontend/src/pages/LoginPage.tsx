import { useState, useCallback } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  Play,
  Terminal,
  Copy,
  User,
  Search,
  Brain,
  Calendar,
  Loader2,
} from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { cn } from "@/lib/utils";

// ─── constants ───────────────────────────────────────────────────────────────

const GITHUB_URL = "https://github.com/LucasMilanez/lanez";

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 .5C5.65.5.5 5.66.5 12.02c0 5.08 3.29 9.39 7.86 10.91.57.1.78-.25.78-.55 0-.27-.01-1-.02-1.97-3.2.7-3.87-1.54-3.87-1.54-.52-1.33-1.27-1.69-1.27-1.69-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.02 1.76 2.69 1.25 3.34.95.1-.74.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.28 1.18-3.09-.12-.29-.51-1.46.11-3.04 0 0 .96-.31 3.16 1.18.92-.26 1.9-.39 2.88-.39.98 0 1.96.13 2.88.39 2.2-1.49 3.16-1.18 3.16-1.18.62 1.58.23 2.75.11 3.04.74.81 1.18 1.83 1.18 3.09 0 4.42-2.7 5.39-5.27 5.68.41.36.78 1.07.78 2.16 0 1.56-.01 2.81-.01 3.19 0 .31.21.66.79.55C20.22 21.4 23.5 17.1 23.5 12.02 23.5 5.66 18.35.5 12 .5z" />
    </svg>
  );
}

// HUD card wrapper (adds corner brackets)
function Hud({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("hud", className)}>
      <span className="corner-bl" />
      <span className="corner-br" />
      {children}
    </div>
  );
}

// ─── log entries (duplicated inside component for seamless loop) ──────────────

const LOG_ENTRIES = [
  { time: "14:22:08", type: "mcp.call",  typeCls: "text-[#22D3EE]", msg: "search_inbox",   meta: "→ 12 hits · 1.2s" },
  { time: "14:22:04", type: "briefing",  typeCls: "text-[#5EEAD4]", msg: '"Q3 Launch Sync"', meta: "generated · 4.1s" },
  { time: "14:21:51", type: "mcp.call",  typeCls: "text-[#22D3EE]", msg: "recall_memory",  meta: "→ 3 hits · 0.4s" },
  { time: "14:21:33", type: "webhook",   typeCls: "text-[#5EEAD4]", msg: "graph.calendar", meta: "received · 0.1s" },
  { time: "14:21:18", type: "mcp.call",  typeCls: "text-[#22D3EE]", msg: "read_note",      meta: "→ 1 hit · 0.8s" },
  { time: "14:20:55", type: "auth.refresh", typeCls: "text-[#FACC15]", msg: "graph.token", meta: "ok · 0.3s" },
  { time: "14:20:31", type: "mcp.call",  typeCls: "text-[#22D3EE]", msg: "list_events",   meta: "→ 7 hits · 0.6s" },
  { time: "14:20:09", type: "embed",     typeCls: "text-[#5EEAD4]", msg: "batch[24]",     meta: "indexed · 2.0s" },
] as const;

const STACK_ROWS = [
  { idx: "001", name: "FastAPI",              dot: "#10B981", role: "http server",     ver: "0.111.x",          notes: "async python, openapi out of box" },
  { idx: "002", name: "PostgreSQL",           dot: "#38BDF8", role: "primary store",   ver: "16.2 + pgvector",  notes: "bm25 + pgvector hybrid retrieval" },
  { idx: "003", name: "Redis",                dot: "#EF4444", role: "queue + cache",   ver: "7.4",              notes: "rq workers, sliding window" },
  { idx: "004", name: "Sentence Transformers",dot: "#A78BFA", role: "embeddings",      ver: "all-MiniLM-L6-v2", notes: "cpu inference, 384-dim" },
  { idx: "005", name: "Claude Haiku",         dot: "#22D3EE", role: "briefing.gen",    ver: "4.5",              notes: "synthesis pass over retrieval hits" },
  { idx: "006", name: "Groq Whisper",         dot: "#F59E0B", role: "voice.transcribe",ver: "large-v3-turbo",   notes: "sub-second on 60s audio" },
  { idx: "007", name: "MCP",                  dot: "#5EEAD4", role: "protocol",        ver: "2025-06-18",       notes: "streamable http transport" },
  { idx: "008", name: "React + Vite",         dot: "#FB7185", role: "admin ui",        ver: "19 / 6",           notes: "tailwind, shadcn primitives" },
] as const;

// ─── sub-sections ─────────────────────────────────────────────────────────────


function SiteHeader({ onLogin, isRedirecting }: { onLogin: () => void; isRedirecting: boolean }) {
  return (
    <header className="sticky top-0 z-40 border-b border-[#1B2029] bg-[#06070A]/85 backdrop-blur-xl">
      <div className="max-w-[1320px] mx-auto px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-4">
          {/* Logo mark */}
          <div className="flex items-center gap-2.5">
            <span className="relative inline-flex h-7 w-7 items-center justify-center rounded-[6px] border border-[#22D3EE]/50 bg-[#22D3EE]/10">
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="#22D3EE" strokeWidth="2.6" strokeLinecap="square">
                <path d="M4 8 H12" /><path d="M4 16 H20" /><path d="M12 12 H20" opacity=".55" />
              </svg>
              <span className="absolute -top-1 -right-1 h-1.5 w-1.5 rounded-full bg-[#22D3EE] shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
            </span>
            <div className="leading-tight">
              <div className="text-[14px] font-bold tracking-tight text-[#E8ECEF]">LANEZ</div>
              <div className="font-mono text-[9.5px] text-[#7A8290] -mt-0.5">MCP SERVER · v0.1</div>
            </div>
          </div>
          {/* Nav links */}
          <span className="hidden md:inline-flex items-center gap-2 ml-3 font-mono text-[11px] text-[#7A8290]">
            <span className="text-[#4F5664]">/</span>
            <a href="#overview" className="hover:text-[#E8ECEF] transition-colors">overview</a>
            <span className="text-[#4F5664]">/</span>
            <a href="#modules" className="hover:text-[#E8ECEF] transition-colors">modules</a>
            <span className="text-[#4F5664]">/</span>
            <a href="#connect" className="hover:text-[#E8ECEF] transition-colors">connect</a>
            <span className="text-[#4F5664]">/</span>
            <a href="#stack" className="hover:text-[#E8ECEF] transition-colors">stack</a>
          </span>
        </div>

        <div className="flex items-center gap-2">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost-lp rounded-md px-3 py-1.5 font-mono text-[11px] inline-flex items-center gap-2"
          >
            <GithubIcon className="h-3 w-3" />
            github
          </a>
          <button
            onClick={onLogin}
            disabled={isRedirecting}
            className="btn-ghost-lp rounded-md px-3 py-1.5 font-mono text-[11px] inline-flex items-center gap-1.5"
          >
            {isRedirecting ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
            admin →
          </button>
        </div>
      </div>
    </header>
  );
}

function TelemetryHUD() {
  return (
    <div className="col-span-12 lg:col-span-5">
      <Hud className="border border-[#1B2029] bg-[#0E1116]/80 backdrop-blur-sm">
        {/* Panel header */}
        <div className="flex items-center justify-between border-b border-[#1B2029] px-4 h-9">
          <div className="flex items-center gap-2 font-mono text-[10.5px] tracking-[0.16em] text-[#7A8290]">
            <span className="h-1.5 w-1.5 bg-[#22D3EE]" />
            LIVE.TELEMETRY
            <span
              className="ml-1 px-1.5 py-px rounded-sm border border-[#FACC15]/40 bg-[#FACC15]/[0.08] text-[#FACC15] text-[8.5px] tracking-[0.18em]"
              title="Illustrative data. Not real user telemetry."
            >
              DEMO
            </span>
          </div>
          <div className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-[#FF7849]/80" />
            <span className="h-2 w-2 rounded-full bg-[#FACC15]/80" />
            <span className="h-2 w-2 rounded-full bg-[#22D3EE]" />
          </div>
        </div>

        {/* Data flow grid */}
        <div className="px-5 pt-5 pb-2">
          <div className="grid grid-cols-3 gap-3">
            {/* Source */}
            <div className="border border-[#1B2029]/80 bg-[#06070A]/60 p-3">
              <div className="font-mono text-[9px] tracking-[0.16em] text-[#4F5664]">[ SOURCE ]</div>
              <div className="font-mono text-[10.5px] text-[#E8ECEF] mt-1">M365</div>
              <ul className="mt-3 space-y-1.5 font-mono text-[10.5px] text-[#E8ECEF]/85">
                <li className="flex items-center gap-1.5"><Calendar className="h-2.5 w-2.5 text-[#5EEAD4]" />calendar</li>
                <li className="flex items-center gap-1.5"><Search className="h-2.5 w-2.5 text-[#5EEAD4]" />mail</li>
                <li className="flex items-center gap-1.5"><Brain className="h-2.5 w-2.5 text-[#5EEAD4]" />onenote</li>
                <li className="flex items-center gap-1.5"><Search className="h-2.5 w-2.5 text-[#5EEAD4]" />onedrive</li>
              </ul>
            </div>
            {/* Core */}
            <div className="border border-[#22D3EE]/40 bg-[#22D3EE]/[0.04] p-3 relative">
              <span className="absolute top-1.5 right-1.5 h-1.5 w-1.5 bg-[#22D3EE] shadow-[0_0_8px_rgba(34,211,238,0.7)]" />
              <div className="font-mono text-[9px] tracking-[0.16em] text-[#22D3EE]/90">[ CORE ]</div>
              <div className="font-mono text-[10.5px] text-[#E8ECEF] mt-1">LANEZ</div>
              <ul className="mt-3 space-y-1.5 font-mono text-[10.5px] text-[#E8ECEF]/85">
                {["ingest", "embed", "index", "mcp.serve"].map((s) => (
                  <li key={s} className="flex items-center gap-1.5">
                    <span className="text-[#22D3EE]">▸</span>{s}
                  </li>
                ))}
              </ul>
            </div>
            {/* Client */}
            <div className="border border-[#1B2029]/80 bg-[#06070A]/60 p-3">
              <div className="font-mono text-[9px] tracking-[0.16em] text-[#4F5664]">[ CLIENT ]</div>
              <div className="font-mono text-[10.5px] text-[#E8ECEF] mt-1">MCP</div>
              <ul className="mt-3 space-y-1.5 font-mono text-[10.5px] text-[#E8ECEF]/85">
                {["claude", "cursor", "continue", "custom"].map((c) => (
                  <li key={c} className="flex items-center gap-1.5">
                    <span className="text-[#5EEAD4]">◇</span>{c}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Animated flow SVG */}
          <svg viewBox="0 0 600 30" className="block w-full h-7 mt-2" preserveAspectRatio="none">
            <defs>
              <linearGradient id="g1" x1="0" x2="1">
                <stop offset="0" stopColor="#5EEAD4" stopOpacity="0.0" />
                <stop offset=".4" stopColor="#5EEAD4" stopOpacity="0.6" />
                <stop offset="1" stopColor="#22D3EE" stopOpacity="0.9" />
              </linearGradient>
              <linearGradient id="g2" x1="0" x2="1">
                <stop offset="0" stopColor="#22D3EE" stopOpacity="0.9" />
                <stop offset=".6" stopColor="#5EEAD4" stopOpacity="0.5" />
                <stop offset="1" stopColor="#5EEAD4" stopOpacity="0.0" />
              </linearGradient>
            </defs>
            <path className="flow-path" d="M 5 15 L 200 15" stroke="url(#g1)" strokeWidth="1.5" fill="none" />
            <path className="flow-path" d="M 400 15 L 595 15" stroke="url(#g2)" strokeWidth="1.5" fill="none" style={{ animationDelay: "-1s" }} />
            <circle r="2" fill="#5EEAD4">
              <animateMotion dur="2.4s" repeatCount="indefinite" path="M 5 15 L 200 15" />
            </circle>
            <circle r="2" fill="#22D3EE">
              <animateMotion dur="2.4s" begin="-0.8s" repeatCount="indefinite" path="M 400 15 L 595 15" />
            </circle>
          </svg>
        </div>

        {/* Stats strip */}
        <div className="border-t border-[#1B2029] px-5 py-4 grid grid-cols-3 gap-3">
          {[
            { label: "TOOLS",    value: "09",   cls: "text-[#22D3EE]" },
            { label: "SERVICES", value: "04",   cls: "text-[#E8ECEF]" },
            { label: "PROTOCOL", value: "MCP",  cls: "text-[#E8ECEF]" },
          ].map(({ label, value, cls }) => (
            <div key={label}>
              <div className="font-mono text-[9px] tracking-[0.16em] text-[#4F5664]">{label}</div>
              <div className={cn("font-mono text-[22px] mt-0.5 tabular-nums leading-none", cls)}>{value}</div>
            </div>
          ))}
        </div>

        {/* Live log */}
        <div className="border-t border-[#1B2029] bg-[#06070A]/80 h-[140px] overflow-hidden relative">
          <div className="absolute top-1.5 left-3 font-mono text-[9px] tracking-[0.16em] text-[#4F5664] z-10 bg-[#06070A]/80 px-1">LOG.STREAM</div>
          <div className="log-stream font-mono text-[11px] leading-[1.55] py-3 px-4 space-y-0.5">
            {[...LOG_ENTRIES, ...LOG_ENTRIES].map((e, i) => (
              <div key={i}>
                <span className="text-[#4F5664]">{e.time}</span>{" "}
                <span className={e.typeCls}>{e.type}</span>{" "}
                <span className="text-[#E8ECEF]">{e.msg}</span>{" "}
                <span className="text-[#7A8290]">{e.meta}</span>
              </div>
            ))}
          </div>
          <div className="absolute inset-x-0 top-0 h-6 bg-gradient-to-b from-[#06070A] to-transparent pointer-events-none" />
          <div className="absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-[#06070A] to-transparent pointer-events-none" />
        </div>
      </Hud>

      {/* HUD info strip */}
      <div className="mt-2 flex items-center justify-between font-mono text-[9.5px] tracking-[0.18em] text-[#4F5664]">
        <span>TRANSPORT: STREAMABLE-HTTP</span>
        <span>EMBED: ALL-MINILM-L6-V2</span>
        <span>LICENSE: APACHE-2.0</span>
      </div>
    </div>
  );
}

function MarqueeStrip() {
  const items = [
    "9 MCP TOOLS", "4 M365 SERVICES", "OPEN SOURCE",
    "SELF-HOSTED", "OAUTH 2.0 + PKCE", "SPEC MCP 2025-06-18",
  ];
  const rendered = items.flatMap((item, i) => [
    <span key={`item-${i}`}><span className="text-[#22D3EE]">●</span> {item}</span>,
    <span key={`sep-${i}`} className="text-[#4F5664]">/</span>,
  ]);

  return (
    <section className="relative border-y border-[#1B2029] py-3 overflow-hidden">
      <div className="marquee-track font-mono text-[12px] tracking-[0.18em] text-[#7A8290] whitespace-nowrap">
        <span className="flex items-center gap-12">{rendered}</span>
        <span className="flex items-center gap-12" aria-hidden="true">{rendered}</span>
      </div>
    </section>
  );
}

function ModulesSection() {
  const modules = [
    {
      num: "01", tag: "RETRIEVE", icon: <Search className="h-5 w-5" />,
      title: "Hybrid search",
      desc: "BM25 over Postgres × pgvector embeddings. One round-trip surfaces the right email, note or file — no query fan-out.",
      stats: [{ k: "index", v: "bm25 + pgvector" }, { k: "model", v: "all-MiniLM-L6-v2" }, { k: "dims", v: "384" }],
    },
    {
      num: "02", tag: "SCHEDULE", icon: <Calendar className="h-5 w-5" />,
      title: "Event briefings",
      desc: "Every meeting on your calendar gets a markdown briefing 15 min before — participants, prior threads, decisions.",
      stats: [{ k: "trigger", v: "ms.graph.webhook" }, { k: "lead_time", v: "15 min" }, { k: "model", v: "claude haiku 4.5" }],
    },
    {
      num: "03", tag: "RECALL", icon: <Brain className="h-5 w-5" />,
      title: "Persistent memory",
      desc: "Notes the agent shouldn't forget — preferences, glossaries, recurring decisions. Tagged, embedded, recallable.",
      stats: [{ k: "store", v: "pgvector" }, { k: "embed", v: "all-MiniLM-L6-v2" }, { k: "scope", v: "user-isolated" }],
    },
  ] as const;

  return (
    <section id="modules" className="relative">
      <div className="max-w-[1320px] mx-auto px-6 pt-24 pb-24">
        <div className="grid grid-cols-12 gap-6 mb-12">
          <div className="col-span-12 lg:col-span-3">
            <span className="tag-mono"><span className="swatch" />03 MODULES</span>
          </div>
          <h2 className="col-span-12 lg:col-span-9 h-display text-[40px] sm:text-[56px] lg:text-[72px] text-[#E8ECEF]">
            Three primitives.<br />
            <span className="text-[#7A8290]">One protocol surface.</span>
          </h2>
        </div>

        <div className="grid grid-cols-12 gap-6">
          {modules.map((m) => (
            <article key={m.num} className="col-span-12 md:col-span-4">
              <Hud className="border border-[#1B2029] bg-[#0E1116]/40 p-6 h-full">
                <div className="flex items-center justify-between font-mono text-[10px] tracking-[0.16em] text-[#4F5664]">
                  <span>MODULE / {m.num}</span>
                  <span className="text-[#22D3EE]">{m.tag}</span>
                </div>
                <div className="mt-6 inline-flex items-center justify-center h-12 w-12 border border-[#22D3EE]/40 bg-[#22D3EE]/10 text-[#22D3EE]">
                  {m.icon}
                </div>
                <h3 className="mt-5 h-display text-[24px] text-[#E8ECEF]">{m.title}</h3>
                <p className="mt-3 text-[13.5px] leading-relaxed text-[#7A8290] font-mono">{m.desc}</p>
                <div className="mt-5 pt-5 border-t border-[#1B2029] space-y-1.5 font-mono text-[11px]">
                  {m.stats.map(({ k, v }) => (
                    <div key={k} className="flex justify-between">
                      <span className="text-[#4F5664]">{k}</span>
                      <span className="text-[#E8ECEF] tabular-nums">{v}</span>
                    </div>
                  ))}
                </div>
              </Hud>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function ProtocolSection() {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    const snippet = `{
  "mcpServers": {
    "lanez": {
      "command": "mcp-remote",
      "args": [
        "https://lanez-app.fly.dev/mcp",
        "--header",
        "Authorization: Bearer <token>"
      ]
    }
  }
}`;
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* silent */ }
  }, []);

  return (
    <section id="connect" className="relative border-t border-[#1B2029] bg-[#0A0C10]/40">
      <div className="max-w-[1320px] mx-auto px-6 pt-24 pb-24">
        <div className="grid grid-cols-12 gap-6 mb-12">
          <div className="col-span-12 lg:col-span-3">
            <span className="tag-mono"><span className="swatch" />04 PROTOCOL</span>
          </div>
          <h2 className="col-span-12 lg:col-span-9 h-display text-[40px] sm:text-[56px] lg:text-[72px] text-[#E8ECEF]">
            <span className="glow-cyan"># connect</span>{" "}
            <span className="text-[#7A8290]">in 30s.</span>
          </h2>
        </div>

        <div className="grid grid-cols-12 gap-6">
          {/* Steps */}
          <ol className="col-span-12 lg:col-span-5 space-y-3">
            {[
              {
                n: "01",
                title: "Sign in with Microsoft",
                desc: "OAuth 2.0 + PKCE. Read-only scopes. Refresh token encrypted at rest.",
                highlight: false,
              },
              {
                n: "02",
                title: <>Drop the snippet → <span className="font-mono text-[#22D3EE] text-[12.5px]">claude_desktop_config.json</span></>,
                desc: "Generate a 7-day token in Settings, paste, restart Claude.",
                highlight: true,
              },
              {
                n: "03",
                title: "Ask something only you would know",
                desc: '"What did we decide about the Q3 launch?" — it pulls the threads, the doc, the meeting.',
                highlight: false,
              },
            ].map(({ n, title, desc, highlight }) => (
              <li key={n}>
                <Hud
                  className={cn(
                    "p-5 flex gap-4",
                    highlight
                      ? "border border-[#22D3EE]/40 bg-[#22D3EE]/[0.04]"
                      : "border border-[#1B2029] bg-[#0E1116]/40",
                  )}
                >
                  <span className="font-mono text-[28px] text-[#22D3EE] leading-none tabular-nums">{n}</span>
                  <div>
                    <div className="font-bold tracking-tight text-[15px] text-[#E8ECEF]">{title}</div>
                    <p className="mt-1 font-mono text-[12px] text-[#7A8290] leading-relaxed">{desc}</p>
                  </div>
                </Hud>
              </li>
            ))}
          </ol>

          {/* Code block */}
          <div className="col-span-12 lg:col-span-7">
            <Hud className="border border-[#1B2029] bg-[#06070A]/90">
              {/* Tab strip */}
              <div className="flex items-center justify-between border-b border-[#1B2029]">
                <div className="flex">
                  <button className="px-4 h-9 font-mono text-[11px] text-[#E8ECEF] border-r border-[#1B2029] bg-[#0E1116] inline-flex items-center gap-2">
                    <span className="h-1.5 w-1.5 bg-[#22D3EE]" />
                    claude_desktop_config.json
                  </button>
                  <button className="px-4 h-9 font-mono text-[11px] text-[#7A8290] hover:text-[#E8ECEF] transition-colors">
                    cursor.json
                  </button>
                  <button className="px-4 h-9 font-mono text-[11px] text-[#7A8290] hover:text-[#E8ECEF] transition-colors">
                    custom.sh
                  </button>
                </div>
                <button
                  onClick={handleCopy}
                  className="px-3 font-mono text-[10.5px] text-[#7A8290] hover:text-[#E8ECEF] inline-flex items-center gap-1.5 transition-colors"
                >
                  <Copy className="h-3 w-3" />
                  {copied ? "copied!" : "copy"}
                </button>
              </div>

              {/* Code with line numbers */}
              <div className="grid grid-cols-[40px_1fr] font-mono text-[12.5px] leading-[1.7]">
                <div className="select-none text-right pr-3 py-5 text-[#4F5664] border-r border-[#1B2029] bg-[#0A0C10]/40">
                  {Array.from({ length: 12 }, (_, i) => <div key={i}>{i + 1}</div>)}
                </div>
                <pre className="px-5 py-5 overflow-x-auto text-[#E8ECEF]/85">
                  <code>{`{`}{"\n"}
{`  `}<span style={{ color: "#5EEAD4" }}>"mcpServers"</span>: {"{"}{"\n"}
{`    `}<span style={{ color: "#22D3EE" }}>"lanez"</span>: {"{"}{"\n"}
{`      `}<span style={{ color: "#5EEAD4" }}>"command"</span>: <span style={{ color: "#FF7849" }}>"mcp-remote"</span>,{"\n"}
{`      `}<span style={{ color: "#5EEAD4" }}>"args"</span>: [{"\n"}
{`        `}<span style={{ color: "#FF7849" }}>"https://lanez-app.fly.dev/mcp"</span>,{"\n"}
{`        `}<span style={{ color: "#FF7849" }}>"--header"</span>,{"\n"}
{`        `}<span style={{ color: "#FACC15" }}>"Authorization: Bearer {"<"}token{">"}"</span>{"\n"}
{`      `}]{"\n"}
{`    `}{"}"}{"\n"}
{`  `}{"}"}{"\n"}
{"}"}</code>
                </pre>
              </div>

              {/* Status strip */}
              <div className="border-t border-[#1B2029] px-4 h-8 flex items-center justify-between font-mono text-[10.5px] text-[#4F5664]">
                <div className="flex items-center gap-4">
                  <span className="text-[#22D3EE] inline-flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 bg-[#22D3EE]" /> SHA-256 verified
                  </span>
                  <span>spec MCP 2025-06-18</span>
                </div>
                <span>token.ttl 7d · scopes: read-only</span>
              </div>
            </Hud>
          </div>
        </div>
      </div>
    </section>
  );
}

function StackSection() {
  return (
    <section id="stack" className="relative border-t border-[#1B2029]">
      <div className="max-w-[1320px] mx-auto px-6 pt-24 pb-24">
        <div className="grid grid-cols-12 gap-6 mb-10">
          <div className="col-span-12 lg:col-span-3">
            <span className="tag-mono"><span className="swatch" />05 STACK</span>
          </div>
          <h2 className="col-span-12 lg:col-span-9 h-display text-[40px] sm:text-[56px] lg:text-[72px] text-[#E8ECEF]">
            Built from boring,<br />
            <span className="text-[#7A8290]">battle-tested parts.</span>
          </h2>
        </div>

        {/* Manifest table */}
        <Hud className="border border-[#1B2029] bg-[#0E1116]/30">
          {/* Header row */}
          <div className="grid grid-cols-12 border-b border-[#1B2029] h-9 px-5 items-center font-mono text-[10px] tracking-[0.16em] text-[#4F5664]">
            <div className="col-span-1">IDX</div>
            <div className="col-span-3">COMPONENT</div>
            <div className="col-span-2">ROLE</div>
            <div className="col-span-2">VERSION</div>
            <div className="col-span-3 hidden md:block">NOTES</div>
            <div className="col-span-1 text-right">STATUS</div>
          </div>

          <div className="divide-y divide-[#1B2029]/70 font-mono text-[12px]">
            {STACK_ROWS.map((row) => (
              <div
                key={row.idx}
                className="grid grid-cols-12 px-5 py-3 items-center hover:bg-[#22D3EE]/[0.03] transition-colors"
              >
                <div className="col-span-1 text-[#4F5664] tabular-nums">{row.idx}</div>
                <div className="col-span-3 text-[#E8ECEF] flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full flex-shrink-0" style={{ background: row.dot }} />
                  {row.name}
                </div>
                <div className="col-span-2 text-[#7A8290]">{row.role}</div>
                <div className="col-span-2 text-[#E8ECEF]">{row.ver}</div>
                <div className="col-span-3 hidden md:block text-[#7A8290]">{row.notes}</div>
                <div className="col-span-1 text-right text-[#22D3EE]">●</div>
              </div>
            ))}
          </div>
        </Hud>
      </div>
    </section>
  );
}

function EndSection({ onLogin, isRedirecting }: { onLogin: () => void; isRedirecting: boolean }) {
  return (
    <section className="relative border-t border-[#1B2029]">
      <div className="max-w-[1320px] mx-auto px-6 pt-24 pb-20">
        <div className="grid grid-cols-12 gap-6 items-end">
          <div className="col-span-12 lg:col-span-8">
            <span className="tag-mono"><span className="swatch" />END / TRANSMISSION</span>
            <h2 className="mt-4 h-display text-[44px] sm:text-[64px] lg:text-[88px]">
              <span className="text-grad-lp">Drop the snippet.</span><br />
              <span className="glow-cyan">Ask anything.</span>
            </h2>
            <p className="mt-6 max-w-[520px] font-mono text-[13px] text-[#7A8290] leading-relaxed">
              A portfolio piece by one developer. Self-host it, fork it, send a PR.
              Or just press the green button and watch.
            </p>
          </div>

          <div className="col-span-12 lg:col-span-4 flex flex-col gap-3">
            <a
              href="#connect"
              className="btn-phos rounded-md px-5 py-4 text-[14px] font-bold tracking-wide font-mono inline-flex items-center justify-between gap-2 uppercase"
            >
              <span className="inline-flex items-center gap-2">
                <Play className="h-3.5 w-3.5" /> run.demo()
              </span>
              <span className="opacity-70">→</span>
            </a>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost-lp rounded-md px-5 py-4 text-[14px] font-bold tracking-wide font-mono inline-flex items-center justify-between gap-2 uppercase"
            >
              <span className="inline-flex items-center gap-2">
                <Terminal className="h-3.5 w-3.5" /> read.source()
              </span>
              <span className="opacity-70">↗</span>
            </a>
            <button
              onClick={onLogin}
              disabled={isRedirecting}
              className="btn-ghost-lp rounded-md px-5 py-4 text-[14px] font-bold tracking-wide font-mono inline-flex items-center justify-between gap-2 uppercase"
            >
              <span className="inline-flex items-center gap-2">
                {isRedirecting
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <User className="h-3.5 w-3.5" />}
                <span className="sr-only">Admin login</span>
                <span aria-hidden="true">admin.login()</span>
              </span>
              <span className="opacity-70">→</span>
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function StatusBar() {
  return (
    <footer className="sticky bottom-0 border-t border-[#1B2029] bg-[#06070A]/95 backdrop-blur-xl">
      <div className="max-w-[1320px] mx-auto px-6 h-9 flex items-center justify-between font-mono text-[10.5px] text-[#7A8290]">
        <div className="flex items-center gap-5">
          <span className="inline-flex items-center gap-2">
            <span className="h-1.5 w-1.5 bg-[#22D3EE] shadow-[0_0_8px_rgba(34,211,238,0.7)]" />
            <span className="text-[#22D3EE]">CONNECTED</span>
          </span>
          <span>
            built by{" "}
            <a href="https://lanez.pt" className="text-[#E8ECEF] hover:text-[#22D3EE] transition-colors">
              Lucas Milanez
            </a>
          </span>
          <span className="hidden sm:inline">lanez.pt</span>
          <span className="hidden md:inline">apache 2.0</span>
        </div>
        <div className="flex items-center gap-5">
          <span className="hidden md:inline">MCP 2025-06-18</span>
          <span className="hidden sm:inline">apache 2.0</span>
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="hover:text-[#22D3EE] transition-colors">github ↗</a>
        </div>
      </div>
    </footer>
  );
}

// ─── main export ──────────────────────────────────────────────────────────────

export function LoginPage() {
  const { login, user } = useAuth();
  const [isRedirecting, setIsRedirecting] = useState(false);
  const [searchParams] = useSearchParams();
  const errorParam = searchParams.get("error");

  const handleLogin = useCallback(() => {
    setIsRedirecting(true);
    login();
  }, [login]);

  if (user) return <Navigate to="/dashboard" replace />;

  return (
    <div className="min-h-screen" style={{ background: "#06070A", color: "#E8ECEF" }}>
      <SiteHeader onLogin={handleLogin} isRedirecting={isRedirecting} />

      {/* ── HERO ─────────────────────────────────────────────────── */}
      <section id="overview" className="relative overflow-hidden">
        <div className="absolute inset-0 hero-glow pointer-events-none" />
        <div className="absolute inset-0 bg-grid pointer-events-none opacity-50" />
        <div className="absolute inset-0 bg-scan pointer-events-none" />
        <div className="absolute inset-0 lp-vignette pointer-events-none" />

        <div className="relative max-w-[1320px] mx-auto px-6 pt-14 pb-20 grid grid-cols-12 gap-6">
          {/* Left column */}
          <div className="col-span-12 lg:col-span-7 relative">
            <div className="flex items-center justify-between mb-7">
              <span className="tag-mono"><span className="swatch" /> NODE 001 / PORTFOLIO_PIECE</span>
              <span className="font-mono text-[10px] text-[#4F5664] hidden sm:inline">SPEC MCP 2025-06-18</span>
            </div>

            <h1 className="h-display text-[64px] sm:text-[88px] lg:text-[108px] text-[#E8ECEF]">
              <span className="block">M365</span>
              <span className="block flex items-end gap-3">
                <span className="text-grad-lp">as context</span>
                <span className="hidden sm:inline-block w-12 h-[2px] bg-[#22D3EE] mb-7" />
              </span>
              <span className="block">
                for any{" "}
                <span className="glow-cyan">
                  AI<span className="caret" />
                </span>
              </span>
            </h1>

            {/* Subline */}
            <div className="mt-8 max-w-[520px] grid grid-cols-[12px_1fr] gap-x-3">
              <span className="block w-[2px] bg-[#22D3EE] mt-1" />
              <p className="font-mono text-[13px] leading-[1.7] text-[#7A8290]">
                A self-hosted MCP server bridging{" "}
                <span className="text-[#E8ECEF]">Calendar · Mail · OneNote · OneDrive</span>{" "}
                into Claude Desktop or any MCP-aware client.
                pgvector semantic search. Read-only scopes.
                Runs on a $5 droplet.
              </p>
            </div>

            {/* CTAs */}
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <a
                href="#connect"
                className="btn-phos rounded-md px-5 py-3 text-[13px] font-bold tracking-wide font-mono inline-flex items-center gap-2 uppercase"
              >
                <Play className="h-3.5 w-3.5" />
                run.demo() <span className="opacity-60">·60s</span>
              </a>
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-ghost-lp rounded-md px-5 py-3 text-[13px] font-semibold font-mono inline-flex items-center gap-2 uppercase"
              >
                <Terminal className="h-3.5 w-3.5" />
                read.source()
              </a>
            </div>

            {/* Trust grid */}
            <div className="mt-12 grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-4 max-w-[640px]">
              {[
                { label: "AUTH",   value: "OAuth 2.0 + PKCE" },
                { label: "SCOPE",  value: "Read-only" },
                { label: "CRYPTO", value: "Fernet AES-256" },
                { label: "KDF",    value: "PBKDF2 480k" },
              ].map(({ label, value }) => (
                <div key={label}>
                  <div className="font-mono text-[9.5px] tracking-[0.18em] text-[#4F5664]">{label}</div>
                  <div className="font-mono text-[12px] text-[#E8ECEF]/90 mt-1">{value}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Right column — Telemetry HUD */}
          <TelemetryHUD />
        </div>

        {/* ASCII divider */}
        <div className="relative max-w-[1320px] mx-auto px-6">
          <div className="font-mono text-[10px] text-[#4F5664]/60 select-none whitespace-pre overflow-hidden">
            {"▌────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────  ────"}
          </div>
        </div>
      </section>

      <MarqueeStrip />
      <ModulesSection />
      <ProtocolSection />
      <StackSection />

      {/* Error alert */}
      {errorParam && (
        <div className="max-w-[1320px] mx-auto px-6 pb-6">
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-xl border border-[#EF4444]/25 bg-[#EF4444]/[0.04] px-3.5 py-3 max-w-md"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#EF4444]" />
            <div>
              <p className="font-medium text-[13px] text-[#EF4444]">Authentication failed</p>
              <p className="text-[11px] text-[#EF4444]/80 mt-0.5">
                Check your Microsoft account and try again.
              </p>
            </div>
          </div>
        </div>
      )}

      <EndSection onLogin={handleLogin} isRedirecting={isRedirecting} />
      <StatusBar />
    </div>
  );
}
