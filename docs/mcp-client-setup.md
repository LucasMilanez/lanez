# Connecting an MCP client to Lanez

Lanez exposes 10 tools via the [Model Context Protocol](https://modelcontextprotocol.io/) (spec `2025-06-18`). Any MCP-compatible client can connect — this guide uses **Claude Desktop** as the example, but the same configuration works for Cursor, Continue, or any other MCP-aware client.

## Prerequisites

- An active Lanez account (complete the Microsoft OAuth flow in the web panel at least once).
- Node.js 18+ installed (required by `mcp-remote`).
- An MCP client (e.g. [Claude Desktop](https://claude.ai/download)).

## 1. Get a Bearer token

Lanez issues a 7-day JWT that the MCP client will send on every request.

The easiest way to get one:

1. Sign in to the web panel at [https://lanez.vercel.app](https://lanez.vercel.app)
2. Open **Settings** from the sidebar
3. Click **"Generate MCP token"**
4. Copy the token — it is valid for 7 days

### Alternative — direct API call

If you already have an active session cookie, you can hit the endpoint directly:

```
GET https://lanez-app.fly.dev/auth/token
```

Response:

```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 604800
}
```

## 2. Edit `claude_desktop_config.json`

Location of the config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add a `lanez` entry to `mcpServers`:

```json
{
  "mcpServers": {
    "lanez": {
      "command": "mcp-remote",
      "args": [
        "https://lanez-app.fly.dev/mcp",
        "--header",
        "Authorization: Bearer <PASTE_YOUR_TOKEN_HERE>"
      ]
    }
  }
}
```

> If `mcp-remote` is not on your `PATH`, replace `"command": "mcp-remote"` with `"command": "npx"` and prepend `"-y", "mcp-remote",` to the `args` array.

## 3. Restart the MCP client

Quit the client fully (not just minimize) and reopen. The tools icon should show the following 10 entries provided by Lanez:

| Tool | Purpose |
|------|---------|
| `get_calendar_events` | List Outlook calendar events in a date range |
| `search_emails` | Full-text search across the inbox |
| `get_onenote_pages` | List OneNote pages, optionally with page content |
| `search_files` | Search OneDrive and SharePoint (with optional content reading for `.txt`/`.md`/`.csv`/`.docx`) |
| `read_file_by_url` | Read a file from a direct OneDrive/SharePoint URL |
| `web_search` | Web search via self-hosted SearXNG |
| `semantic_search` | Cross-service semantic search over all indexed content |
| `save_memory` | Persist a note, decision or preference for future sessions |
| `recall_memory` | Retrieve relevant memories by semantic similarity |
| `get_briefing` | Fetch the auto-generated briefing for a meeting |

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| **401 on every request** | Token expired. Generate a new one (step 1). |
| **404 when listing tools** | Wrong URL. Confirm the MCP endpoint is exactly `https://lanez-app.fly.dev/mcp` — no `/call`, no `/sse`. |
| **Tools don't show up at all** | Check the Claude Desktop logs at `~/Library/Logs/Claude/mcp*.log` (macOS) or `%APPDATA%\Claude\logs\mcp*.log` (Windows). |
| **Tool returns a Graph API error** | Your Microsoft token might have expired. Sign in to [https://lanez.vercel.app](https://lanez.vercel.app) to refresh it. |
| **`mcp-remote` not found** | Install it globally (`npm install -g mcp-remote`) or switch to the `npx -y mcp-remote` form described above. |
