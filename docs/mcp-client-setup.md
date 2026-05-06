# Configurar Claude Desktop com Lanez

Lanez expõe 9 ferramentas via MCP (Model Context Protocol). Este guia
configura o Claude Desktop para usá-las.

## Pré-requisitos

- Conta com login OAuth Microsoft no Lanez ja feito ao menos uma vez.
- Node.js 18+ instalado (para `npx mcp-remote`).
- Claude Desktop instalado (https://claude.ai/download).

## 1. Obter Bearer token

O Lanez emite JWT no painel web. A forma mais fácil de obter o token:

1. Fazer login no painel: `https://lanez.vercel.app`
2. Ir em **Configurações** (menu lateral)
3. Clicar em **"Gerar token MCP"**
4. Copiar o token exibido (válido por 7 dias)

### Alternativa (via API direta)

Se já estiver autenticado (cookie ativo), acessar:

```
GET https://lanez-app.fly.dev/auth/token
```

Retorna:

```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 604800
}
```

## 2. Editar `claude_desktop_config.json`

Localização:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Adicionar a entrada `lanez` em `mcpServers`:

```json
{
  "mcpServers": {
    "lanez": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://lanez-app.fly.dev/mcp",
        "--header",
        "Authorization: Bearer <COLE_O_TOKEN_AQUI>"
      ]
    }
  }
}
```

## 3. Reiniciar Claude Desktop

Fechar completamente (não basta minimizar) e reabrir. O ícone de
ferramentas (slider) deve mostrar 9 entradas Lanez:
`get_calendar_events`, `search_emails`, `get_onenote_pages`,
`search_files`, `web_search`, `semantic_search`, `save_memory`,
`recall_memory`, `get_briefing`.

## Troubleshooting

- **401 nas requests**: token expirou. Refazer passo 1.
- **404 ao listar tools**: URL errada. Confirmar que é `https://lanez-app.fly.dev/mcp` (sem `/call`, sem `/sse`).
- **Tools não aparecem**: verificar logs do Claude Desktop em
  `~/Library/Logs/Claude/mcp*.log` (macOS) ou
  `%APPDATA%\Claude\logs\mcp*.log` (Windows).
- **Tool retorna erro de Graph API**: token Microsoft pode ter expirado.
  Fazer login no painel `https://lanez.vercel.app` para renovar.
