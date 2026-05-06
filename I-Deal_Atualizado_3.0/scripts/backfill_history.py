"""
backfill_history.py
====================
Gera histórico realista de preços para os últimos N dias (default 14),
ancorado no PREÇO ATUAL de cada par (jogo, loja) já presente no banco.

SEGURANÇA:
  1. Faz backup automático de ideal.db ANTES de qualquer escrita.
  2. NUNCA usa DELETE / UPDATE / DROP — só INSERT.
  3. É IDEMPOTENTE: se já existe Price para (game_id, store, data), pula.
  4. Em caso de erro, faz rollback antes do commit.

USO:
    cd I-Deal_Atualizado_3.0
    python scripts/backfill_history.py             # 14 dias (default)
    python scripts/backfill_history.py --days 30   # 30 dias
    python scripts/backfill_history.py --dry-run   # só simula, não escreve
"""

import argparse
import os
import random
import shutil
import sys
from datetime import datetime, timedelta, timezone

# --- Garantir que conseguimos importar app.py / models.py do projeto ---------
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Evita disparar o scheduler do Flask só por importar o app
os.environ.setdefault('PRICE_REFRESH_MINUTES', '99999')

from sqlalchemy import func  # noqa: E402

from app import app  # noqa: E402
from models import db, Game, Price  # noqa: E402

DB_FILENAME = 'ideal.db'
DEFAULT_DAYS = 14

# Variação realista do random walk
DAILY_NOISE_PCT = 0.025      # ±2,5% por dia
SALE_PROBABILITY = 0.07      # 7% de chance de iniciar uma promoção em qualquer dia
SALE_DEPTH_RANGE = (0.15, 0.30)   # promoção tira 15-30% do preço
SALE_DURATION_RANGE = (1, 3)      # promoção dura 1-3 dias

# Limites para não gerar valores absurdos
PRICE_FLOOR_MULT = 0.30   # nunca abaixo de 30% do preço-âncora
PRICE_CEIL_MULT = 1.15    # nunca acima de 115% do preço-âncora


# =============================================================================
# Backup
# =============================================================================
def make_backup(db_path: str) -> str:
    """Copia ideal.db para ideal.db.backup-YYYYMMDD-HHMMSS. Retorna path do backup."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f'Banco de dados não encontrado: {db_path}')
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = f'{db_path}.backup-{timestamp}'
    shutil.copy2(db_path, backup_path)
    return backup_path


# =============================================================================
# Geração realista
# =============================================================================
def generate_history_series(anchor_price: float, num_days: int) -> list[float]:
    """
    Gera uma lista de num_days preços, com index 0 = mais antigo, index -1 = mais recente.
    Algoritmo: random walk com média revertida ao anchor + eventos de promoção.
    O último preço gerado fica próximo do anchor (preserva o "preço atual").
    """
    if num_days <= 0:
        return []

    # Trabalhamos do PRESENTE para o PASSADO (mais fácil ancorar no preço atual)
    series = [anchor_price]
    sale_remaining = 0
    sale_factor = 1.0

    for i in range(num_days - 1):
        prev = series[-1]

        # Termina ou continua promoção em curso
        if sale_remaining > 0:
            sale_remaining -= 1
            new = prev * (1 + random.uniform(-0.01, 0.01))
            series.append(_clamp(new, anchor_price))
            continue

        # Random: começa uma "promoção" no passado
        if random.random() < SALE_PROBABILITY:
            depth = random.uniform(*SALE_DEPTH_RANGE)
            sale_factor = 1 - depth
            sale_remaining = random.randint(*SALE_DURATION_RANGE) - 1
            new = anchor_price * sale_factor * (1 + random.uniform(-0.02, 0.02))
            series.append(_clamp(new, anchor_price))
            continue

        # Random walk normal — leve mean reversion para o anchor
        noise = random.uniform(-DAILY_NOISE_PCT, DAILY_NOISE_PCT)
        mean_revert = (anchor_price - prev) * 0.10
        new = prev + mean_revert + (prev * noise)
        series.append(_clamp(new, anchor_price))

    # Inverte: index 0 = mais antigo, index -1 = mais recente
    series.reverse()
    return [round(p, 2) for p in series]


def _clamp(price: float, anchor: float) -> float:
    return max(anchor * PRICE_FLOOR_MULT, min(anchor * PRICE_CEIL_MULT, price))


# =============================================================================
# Backfill principal
# =============================================================================
def backfill(num_days: int, dry_run: bool, seed: int | None) -> dict:
    if seed is not None:
        random.seed(seed)

    summary = {
        'pairs_processed': 0,
        'pairs_skipped_no_anchor': 0,
        'rows_inserted': 0,
        'rows_skipped_existing': 0,
        'games_touched': set(),
    }

    with app.app_context():
        games = Game.query.all()
        if not games:
            print('AVISO: Nenhum jogo na tabela games. Nada a fazer.')
            return summary

        now = datetime.now(timezone.utc)
        # Lista de datetimes (UTC, meio-dia) para os últimos num_days dias
        target_datetimes = [
            now.replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=offset)
            for offset in range(num_days)
        ]

        for game in games:
            # Identifica todas as lojas que já têm pelo menos um preço pra esse jogo
            store_rows = (
                db.session.query(Price.store)
                .filter(Price.game_id == game.id)
                .distinct()
                .all()
            )
            stores = [s[0] for s in store_rows]

            if not stores:
                # Sem preço-âncora pra esse jogo, pula com aviso
                continue

            for store in stores:
                # Pega o preço mais recente DESSE par (game, store) como âncora
                anchor = (
                    Price.query
                    .filter(Price.game_id == game.id, Price.store == store)
                    .order_by(Price.date_recorded.desc())
                    .first()
                )
                if anchor is None:
                    summary['pairs_skipped_no_anchor'] += 1
                    continue

                summary['pairs_processed'] += 1
                summary['games_touched'].add(game.title)

                series = generate_history_series(anchor.price, num_days)

                # series[i] corresponde ao dia mais antigo primeiro;
                # target_datetimes[i] vai do mais recente pro mais antigo,
                # então invertemos um deles para casar.
                target_datetimes_chrono = list(reversed(target_datetimes))

                for dt, price in zip(target_datetimes_chrono, series):
                    # Idempotência: pula se já existir Price nesse dia para esse par
                    existing = (
                        db.session.query(Price.id)
                        .filter(
                            Price.game_id == game.id,
                            Price.store == store,
                            func.date(Price.date_recorded) == dt.date(),
                        )
                        .first()
                    )
                    if existing:
                        summary['rows_skipped_existing'] += 1
                        continue

                    if not dry_run:
                        db.session.add(Price(
                            game_id=game.id,
                            store=store,
                            price=price,
                            currency=anchor.currency or 'BRL',
                            date_recorded=dt,
                        ))
                    summary['rows_inserted'] += 1

        if not dry_run:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                raise RuntimeError(f'Falha no commit, rollback executado: {e}')
        else:
            db.session.rollback()

    summary['games_touched'] = sorted(summary['games_touched'])
    return summary


# =============================================================================
# Entry point
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--days', type=int, default=DEFAULT_DAYS, help=f'Quantos dias de histórico (default: {DEFAULT_DAYS})')
    parser.add_argument('--dry-run', action='store_true', help='Simula sem escrever no banco')
    parser.add_argument('--seed', type=int, default=None, help='Seed para reprodutibilidade')
    parser.add_argument('--no-backup', action='store_true', help='[NÃO RECOMENDADO] pula o backup')
    args = parser.parse_args()

    db_path = os.path.join(PROJECT_ROOT, DB_FILENAME)

    print('=' * 70)
    print(' I-Deal — Backfill de histórico de preços')
    print('=' * 70)
    print(f' Banco:        {db_path}')
    print(f' Dias:         {args.days}')
    print(f' Dry-run:      {args.dry_run}')
    print(f' Seed:         {args.seed}')
    print('=' * 70)

    # 1) Backup
    if not args.dry_run and not args.no_backup:
        try:
            backup = make_backup(db_path)
            print(f' [OK] Backup criado em: {backup}')
        except Exception as e:
            print(f' [ERRO] Não foi possível criar backup: {e}')
            print(' Abortando por segurança. Use --no-backup se quiser pular (não recomendado).')
            sys.exit(1)
    elif args.dry_run:
        print(' [DRY-RUN] Pulando backup (nenhuma escrita será feita).')
    else:
        print(' [AVISO] --no-backup ativo. Nenhum backup será criado.')

    # 2) Backfill
    try:
        summary = backfill(num_days=args.days, dry_run=args.dry_run, seed=args.seed)
    except Exception as e:
        print(f'\n [ERRO] Backfill falhou: {e}')
        print('  Banco original intacto (rollback feito ou backup disponível).')
        sys.exit(1)

    # 3) Relatório
    print('\n' + '=' * 70)
    print(' Resumo do Backfill')
    print('=' * 70)
    print(f' Pares (jogo, loja) processados:   {summary["pairs_processed"]}')
    print(f' Pares sem preço-âncora (pulados): {summary["pairs_skipped_no_anchor"]}')
    print(f' Linhas inseridas:                 {summary["rows_inserted"]}')
    print(f' Linhas puladas (já existiam):     {summary["rows_skipped_existing"]}')
    print(f' Jogos tocados ({len(summary["games_touched"])}):')
    for g in summary['games_touched']:
        print(f'   - {g}')
    print('=' * 70)

    if args.dry_run:
        print(' DRY-RUN concluído. Nada foi escrito.')
    else:
        print(' Backfill concluído com sucesso.')
        print(' Recarregue qualquer página /game/<id> e o gráfico já vai mostrar a série.')


if __name__ == '__main__':
    main()
