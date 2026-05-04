#!/usr/bin/env bash
set -euo pipefail

# One-shot: roda alembic upgrade head dentro da máquina Fly.
# Uso: bash scripts/migrate.sh
#
# Justificativa: o startup do app já roda alembic upgrade head (Tarefa 2).
# Este script existe para casos onde o startup falha por erro de migration
# e a máquina entra em crash-loop — você abre console e roda manualmente
# para diagnóstico.

flyctl ssh console -a lanez -C "alembic upgrade head"
