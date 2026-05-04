#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# DESTRUTIVO — bootstrap one-shot, NÃO rotina.
# Só usar na primeira ida ao ar ou quando precisar resetar subs.
#
# Deleta TODAS as WebhookSubscription do banco de produção.
# O renewal_loop do app recria automaticamente com a URL de
# produção (WEBHOOK_NOTIFICATION_URL) em até 30 minutos.
# Para forçar imediatamente: flyctl restart -a lanez
# ============================================================

echo "1. Conectando no banco de prod (Neon) via Fly SSH..."
echo "2. Deletando TODAS as webhook subscriptions..."

flyctl ssh console -a lanez -C "python -c \"
import asyncio
from app.database import AsyncSessionLocal
from app.models.webhook import WebhookSubscription
from sqlalchemy import delete

async def cleanup():
    async with AsyncSessionLocal() as db:
        result = await db.execute(delete(WebhookSubscription))
        await db.commit()
        print(f'Removidas {result.rowcount} subscriptions antigas')

asyncio.run(cleanup())
\""

echo "3. Próximo loop de renewal (a cada 30 min) recria automaticamente."
echo "   Para forçar agora: flyctl restart -a lanez"
