/**
 * Fixture data for demo mode. Activated when `VITE_DEMO_MODE=true` is set
 * at build/dev time. Used only to produce portfolio screenshots — NEVER
 * shipped to production.
 *
 * Design goals:
 * - Numbers believable but clearly fake (no real client names).
 * - Timestamps relative to "now" so the UI always looks fresh when
 *   rendering the screenshots.
 * - Covers all 8 pages: Dashboard, Briefings list, Briefing detail,
 *   Memories, Audit, Settings, Login landing.
 */
import type { User } from "@/auth/AuthContext";
import type { StatusData } from "@/hooks/useStatus";
import type { BriefingDetail } from "@/hooks/useBriefing";
import type { BriefingListResponse } from "@/hooks/useBriefings";
import type { AuditLogListResponse } from "@/hooks/useAuditLog";

const NOW = new Date();
const minutesAgo = (m: number) => new Date(NOW.getTime() - m * 60_000).toISOString();
const hoursFromNow = (h: number) => new Date(NOW.getTime() + h * 3_600_000).toISOString();
const daysAgo = (d: number) => new Date(NOW.getTime() - d * 86_400_000).toISOString();

// ---------------------------------------------------------------------------
// User (used by AuthContext)
// ---------------------------------------------------------------------------

export const demoUser: User = {
  id: "demo-user-01",
  email: "demo@example.com",
  token_expires_at: hoursFromNow(5),
  last_sync_at: minutesAgo(2),
  created_at: daysAgo(90),
};

// ---------------------------------------------------------------------------
// /status → Dashboard
// ---------------------------------------------------------------------------

export const demoStatus: StatusData = {
  user_email: "demo@example.com",
  token_expires_at: hoursFromNow(5),
  token_expires_in_seconds: 5 * 3600 + 42 * 60,
  last_sync_at: minutesAgo(2),
  webhook_subscriptions: [
    { resource: "me/events", expires_at: hoursFromNow(48) },
    { resource: "me/messages", expires_at: hoursFromNow(48) },
    { resource: "me/onenote/pages", expires_at: hoursFromNow(48) },
  ],
  embeddings_by_service: [
    { service: "Mail", count: 22_418 },
    { service: "OneNote", count: 9_602 },
    { service: "OneDrive", count: 5_140 },
    { service: "Calendar", count: 1_034 },
  ],
  memories_count: 204,
  briefings_count_30d: 126,
  recent_briefings: [
    { event_id: "evt-1", event_subject: "Q3 Launch Sync", event_start: hoursFromNow(1) },
    { event_id: "evt-2", event_subject: "Design review — navigation", event_start: hoursFromNow(3) },
    { event_id: "evt-3", event_subject: "1:1 with João", event_start: hoursFromNow(6) },
    { event_id: "evt-4", event_subject: "Product roadmap FY26", event_start: hoursFromNow(26) },
    { event_id: "evt-5", event_subject: "Hiring sync — staff eng", event_start: hoursFromNow(48) },
    { event_id: "evt-6", event_subject: "Security review", event_start: hoursFromNow(72) },
  ],
  tokens_30d: {
    input: 156_728,
    output: 115_452,
    cache_read: 90_712,
    cache_write: 49_438,
  },
  mcp_activity_30d: {
    total_calls: 1_284,
    successful: 1_272,
    failed: 12,
    tools_used: [
      { service: "search_emails", count: 412 },
      { service: "recall_memory", count: 298 },
      { service: "get_calendar_events", count: 241 },
      { service: "semantic_search", count: 187 },
      { service: "get_briefing", count: 146 },
    ],
  },
  config: { briefing_history_window_days: 90 },
};

// ---------------------------------------------------------------------------
// /briefings → Briefings list
// ---------------------------------------------------------------------------

const briefingsList = [
  {
    id: "b-01",
    event_id: "evt-1",
    event_subject: "Q3 Launch Sync",
    event_start: hoursFromNow(1),
    event_end: hoursFromNow(2),
    attendees: ["demo@example.com", "joao@example.com", "maria@example.com"],
    generated_at: minutesAgo(2),
  },
  {
    id: "b-02",
    event_id: "evt-2",
    event_subject: "Design review — navigation",
    event_start: hoursFromNow(3),
    event_end: hoursFromNow(4),
    attendees: ["demo@example.com", "paulo@example.com", "sofia@example.com", "carlos@example.com", "ana@example.com"],
    generated_at: minutesAgo(18),
  },
  {
    id: "b-03",
    event_id: "evt-3",
    event_subject: "1:1 with João",
    event_start: hoursFromNow(6),
    event_end: hoursFromNow(7),
    attendees: ["demo@example.com", "joao@example.com"],
    generated_at: minutesAgo(54),
  },
  {
    id: "b-04",
    event_id: "evt-4",
    event_subject: "Product roadmap FY26",
    event_start: hoursFromNow(26),
    event_end: hoursFromNow(27),
    attendees: ["demo@example.com", "maria@example.com", "ceo@example.com"],
    generated_at: minutesAgo(120),
  },
  {
    id: "b-05",
    event_id: "evt-5",
    event_subject: "Hiring sync — staff eng",
    event_start: hoursFromNow(48),
    event_end: hoursFromNow(49),
    attendees: ["demo@example.com", "recruiter@example.com", "eng-lead@example.com"],
    generated_at: minutesAgo(240),
  },
];

export const demoBriefingsPage1: BriefingListResponse = {
  items: briefingsList,
  total: 126,
  page: 1,
  page_size: 20,
};

// ---------------------------------------------------------------------------
// /briefings/:event_id → Briefing detail
// ---------------------------------------------------------------------------

export const demoBriefingDetail: BriefingDetail = {
  id: "b-01",
  event_id: "evt-1",
  event_subject: "Q3 Launch Sync",
  event_start: hoursFromNow(1),
  event_end: hoursFromNow(2),
  attendees: ["demo@example.com", "joao@example.com", "maria@example.com"],
  generated_at: minutesAgo(2),
  model_used: "claude-haiku-4-5",
  input_tokens: 18_240,
  output_tokens: 2_410,
  cache_read_tokens: 14_802,
  cache_write_tokens: 3_438,
  content: `## Context

The Q3 product launch has been the main thread with **João** and **Maria** over the past three weeks. Scope was frozen on April 18 after Maria's review; the engineering team is now on track to ship by June 30.

## Decisions on the table

- **Mobile app** — João has confirmed this is the #1 priority for H2. The team has chosen **React Native** (they already know React). Maria wants confirmation on whether it lands in the Q3 scope or slips to Q4.
- **Salesforce CRM integration** — Maria requested delivery **before the June sales kickoff**. Scope already estimated last week, pending sign-off on the €3k/month budget uplift.
- **Contract renewal** — current engagement ends June 30. João mentioned possibly extending to 12 months if mobile is included.

## Recent threads

- **April 1** — Updated Q3 proposal sent (scope + €5k/month for 3 months).
- **April 18** — Sprint review notes in OneNote: mobile-first mentioned as strategic by CEO.
- **May 3** — Maria approved API v2 direction; rate limiting and versioning greenlit.

## Relevant files

- \`TechNova_Contract_2025.docx\` (OneDrive) — current agreement, renewal clause in section 7.
- \`Roadmap_H2_FY26.md\` (OneNote) — mobile app scope draft.

## Talking points for this meeting

1. Confirm mobile app goes into Q3 or Q4.
2. Lock the Salesforce delivery date and budget.
3. Propose the 12-month extension as a single contract rather than two renewals.
4. Ask about hiring — João hinted last week they might want an embedded engineer for H2.
`,
};

// ---------------------------------------------------------------------------
// /memories → Memories page (returns a plain array, not a paginated response)
// ---------------------------------------------------------------------------

export const demoMemories = [
  {
    id: "m-01",
    content: "João is TechNova's main contact for contract negotiations. Prefers email over Slack.",
    tags: ["contacts", "technova"],
    created_at: daysAgo(14),
  },
  {
    id: "m-02",
    content: "Default to Portuguese for meeting summaries with João and Maria. Switch to English only when the audience includes the CEO.",
    tags: ["preferences", "language"],
    created_at: daysAgo(9),
  },
  {
    id: "m-03",
    content: "Current TechNova contract: €5,000/month, Jan–Jun 2026, billed on the 1st, net 15. Renewal meeting scheduled for May.",
    tags: ["technova", "contracts"],
    created_at: daysAgo(7),
  },
  {
    id: "m-04",
    content: "Q3 launch decisions: mobile = React Native (not Flutter). Scope frozen April 18. Ship target June 30.",
    tags: ["q3-launch", "decisions"],
    created_at: daysAgo(4),
  },
  {
    id: "m-05",
    content: "Lead developer for the Salesforce integration is Sofia. Escalate blockers to her, not Maria.",
    tags: ["contacts", "salesforce"],
    created_at: daysAgo(2),
  },
  {
    id: "m-06",
    content: "When generating briefings, always prioritize emails from the last 14 days over older threads unless the meeting is explicitly a retrospective.",
    tags: ["preferences", "briefings"],
    created_at: minutesAgo(360),
  },
];

// ---------------------------------------------------------------------------
// /audit → Audit page (paginated)
// ---------------------------------------------------------------------------

export const demoAuditPage1: AuditLogListResponse = {
  total: 1_284,
  page: 1,
  page_size: 50,
  items: [
    { id: "a-01", event_type: "mcp.call", event_data: { tool_name: "search_emails", success: true }, success: true, error_message: null, latency_ms: 412, created_at: minutesAgo(1) },
    { id: "a-02", event_type: "mcp.call", event_data: { tool_name: "recall_memory", success: true }, success: true, error_message: null, latency_ms: 148, created_at: minutesAgo(3) },
    { id: "a-03", event_type: "briefing.generated", event_data: { event_id: "evt-1", model_used: "claude-haiku-4-5" }, success: true, error_message: null, latency_ms: 4_128, created_at: minutesAgo(5) },
    { id: "a-04", event_type: "mcp.call", event_data: { tool_name: "get_calendar_events", success: true }, success: true, error_message: null, latency_ms: 312, created_at: minutesAgo(7) },
    { id: "a-05", event_type: "webhook.received", event_data: { resource: "me/events", change_type: "updated" }, success: true, error_message: null, latency_ms: 98, created_at: minutesAgo(9) },
    { id: "a-06", event_type: "mcp.call", event_data: { tool_name: "semantic_search", success: true }, success: true, error_message: null, latency_ms: 524, created_at: minutesAgo(12) },
    { id: "a-07", event_type: "memory.created", event_data: { source: "mcp", content_length: 142 }, success: true, error_message: null, latency_ms: 218, created_at: minutesAgo(15) },
    { id: "a-08", event_type: "mcp.call", event_data: { tool_name: "search_files", success: false }, success: false, error_message: "Graph API rate limit exceeded", latency_ms: 1_802, created_at: minutesAgo(22) },
    { id: "a-09", event_type: "auth.refresh", event_data: { expires_in_seconds: 3600 }, success: true, error_message: null, latency_ms: 340, created_at: minutesAgo(38) },
    { id: "a-10", event_type: "voice.transcribed", event_data: { audio_bytes: 84_128, transcription_length: 212 }, success: true, error_message: null, latency_ms: 920, created_at: minutesAgo(44) },
    { id: "a-11", event_type: "mcp.call", event_data: { tool_name: "read_file_by_url", success: true }, success: true, error_message: null, latency_ms: 812, created_at: minutesAgo(58) },
    { id: "a-12", event_type: "mcp.call", event_data: { tool_name: "get_briefing", success: true }, success: true, error_message: null, latency_ms: 68, created_at: minutesAgo(72) },
    { id: "a-13", event_type: "auth.login", event_data: { email: "demo@example.com" }, success: true, error_message: null, latency_ms: 1_240, created_at: minutesAgo(180) },
    { id: "a-14", event_type: "mcp.call", event_data: { tool_name: "save_memory", success: true }, success: true, error_message: null, latency_ms: 264, created_at: minutesAgo(210) },
    { id: "a-15", event_type: "briefing.generated", event_data: { event_id: "evt-2", model_used: "claude-haiku-4-5" }, success: true, error_message: null, latency_ms: 3_720, created_at: minutesAgo(245) },
  ],
};

// ---------------------------------------------------------------------------
// /auth/token — MCP token for Settings page
// ---------------------------------------------------------------------------

export const demoAuthToken = {
  access_token: "eyJhbGciOiJIUzI1NiJ9.DEMO.this_is_a_placeholder_token_for_screenshots_only_do_not_use",
  token_type: "bearer",
  expires_in: 7 * 24 * 3600,
  instructions:
    "Paste this token into your MCP client configuration. Example for Claude Desktop: \"Authorization: Bearer <access_token>\".",
};
