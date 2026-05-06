# =============================================================================
# alerts.py — Lógica de processamento de alertas de preço (US03)
# =============================================================================
# Quando o scheduler atualiza preços, esta função é chamada para:
#   1. Buscar todos os alertas ativos
#   2. Para cada um, comparar com o preço mais recente do jogo (na loja-filtro
#      ou na loja com o menor preço, se sem filtro)
#   3. Se preço_atual <= target_price → enviar email
#   4. Aplicar cooldown anti-spam (não dispara o mesmo alerta mais de 1x por
#      janela de tempo, mesmo que o preço continue baixo)
#
# Cooldown padrão: 24h. Configurável via ALERT_COOLDOWN_HOURS no .env.
# =============================================================================

import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


# =============================================================================
# Função principal — chamada pelo scheduler depois de update_all_prices()
# =============================================================================
def process_alerts(flask_app, base_url: str = 'http://localhost:5000') -> dict:
    """
    Verifica todos os alertas ativos e dispara emails para os que bateram o alvo.

    Args:
        flask_app: instância Flask (precisa do app_context para queries)
        base_url:  URL base do site, usada nos links dos emails

    Retorna dict com estatísticas: {checked, triggered, sent, skipped_cooldown}
    """
    from models import db, Alert, Price
    from email_service import send_alert_email, is_configured

    stats = {
        'checked': 0,
        'triggered': 0,
        'sent': 0,
        'skipped_cooldown': 0,
        'failed_send': 0,
    }

    cooldown_hours = int(os.environ.get('ALERT_COOLDOWN_HOURS', '24'))
    cooldown_delta = timedelta(hours=cooldown_hours)
    now_utc = datetime.now(timezone.utc)

    if not is_configured():
        logger.warning('SMTP não configurado — process_alerts pulando envio.')

    with flask_app.app_context():
        active_alerts = Alert.query.filter_by(active=True).all()
        stats['checked'] = len(active_alerts)

        for alert in active_alerts:
            # 1. Encontra o preço mais recente que se encaixa no filtro
            query = (
                Price.query
                .filter(Price.game_id == alert.game_id)
                .order_by(Price.date_recorded.desc())
            )
            if alert.store_filter:
                query = query.filter(Price.store == alert.store_filter)

            latest_price = query.first()
            if latest_price is None:
                continue  # sem preço disponível ainda

            # 2. Bateu o alvo?
            if latest_price.price > alert.target_price:
                continue

            # 2b. (Filtro 4.3.1+) — bateu o desconto mínimo?
            # Calcula o desconto vs default_price (preço de referência do jogo).
            # Se o usuário definiu min_discount_pct, só dispara se o desconto >= esse valor.
            if alert.min_discount_pct is not None and alert.min_discount_pct > 0:
                game = alert.game
                ref_price = game.default_price
                if ref_price and ref_price > 0:
                    discount_pct = (ref_price - latest_price.price) / ref_price * 100
                    if discount_pct < alert.min_discount_pct:
                        continue  # preço bate o alvo, mas desconto vs default ainda é pequeno

            stats['triggered'] += 1

            # 3. Cooldown — já disparou recentemente?
            if alert.last_triggered_at is not None:
                # SQLite armazena sem tz; força UTC se vier naïve
                last = alert.last_triggered_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if now_utc - last < cooldown_delta:
                    stats['skipped_cooldown'] += 1
                    continue

            # 4. Envia email
            user = alert.user
            game = alert.game
            game_url = f'{base_url.rstrip("/")}/game/{game.id}'

            ok = send_alert_email(
                to=user.email,
                user_name=user.name,
                game_title=game.title,
                store=latest_price.store,
                new_price=latest_price.price,
                target_price=alert.target_price,
                game_url=game_url,
            )


            if ok:
                stats['sent'] += 1
                alert.last_triggered_at = now_utc
                alert.last_triggered_price = latest_price.price
                alert.last_triggered_store = latest_price.store
            else:
                stats['failed_send'] += 1

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f'Erro ao commitar last_triggered_at: {e}')

    logger.info(
        f'Alertas processados: checked={stats["checked"]} '
        f'triggered={stats["triggered"]} sent={stats["sent"]} '
        f'skipped_cooldown={stats["skipped_cooldown"]} failed={stats["failed_send"]}'
    )
    return stats
