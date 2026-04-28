# Lanez — Painel

Frontend React do Lanez. Roda em dev a `http://localhost:5173` e proxia
requests para o backend FastAPI em `http://localhost:8000`.

## Pré-requisitos

- Node 20+
- Backend Lanez rodando em :8000 (ver README do projeto raiz)

## Comandos

    npm install
    npm run dev      # http://localhost:5173
    npm run build    # build de produção em dist/
    npm test         # roda Vitest

## Stack

Vite, React 18, TypeScript, Tailwind 3.4, shadcn/ui, TanStack Query v5,
React Router v6, Recharts, react-markdown.
