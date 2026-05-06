"""
dedupe_games.py
=================
Detecta e mescla jogos duplicados no catálogo.

Estratégia:
  - Agrupa Games por título normalizado (normalize_title de US06).
  - Pra cada grupo com 2+ jogos, mantém o de menor id (o mais antigo)
    e MIGRA Prices, StoreLinks, Alerts e NavigationLogs dos demais
    pro mais antigo. Depois deleta os duplicados.

SEGURANÇA:
  - Faz backup automático do ideal.db antes de qualquer escrita.
  - Idempotente — se rodar 2x, só age se houver duplicatas reais.
  - Usa transação: rollback total em caso de erro.

USO:
    cd I-Deal_Atualizado_3.0
    python scripts/dedupe_games.py
    python scripts/dedupe_games.py --dry-run   # simula sem escrever
"""

import argparse
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('PRICE_REFRESH_MINUTES', '99999')

import price_fetcher  # noqa: E402
price_fetcher.update_all_prices = lambda app: {}

from price_fetcher import normalize_title  # noqa: E402
from app import app  # noqa: E402
from models import db, Game, Price, StoreLink, NavigationLog, Alert  # noqa: E402


def make_backup(db_path: str) -> str:
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = f'{db_path}.backup-dedupe-{ts}'
    shutil.copy2(db_path, backup_path)
    return backup_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    db_path = os.path.join(PROJECT_ROOT, 'ideal.db')
    print('=' * 70)
    print(' I-Deal — Dedupe de jogos no catálogo')
    print('=' * 70)
    print(f' Banco:    {db_path}')
    print(f' Dry-run:  {args.dry_run}')
    print('=' * 70)

    if not os.path.exists(db_path):
        print(' ERRO: ideal.db não encontrado.')
        sys.exit(1)

    if not args.dry_run:
        backup = make_backup(db_path)
        print(f' [OK] Backup: {os.path.basename(backup)}')

    games_merged = 0
    rows_migrated = 0
    games_deleted = 0

    with app.app_context():
        # 1) Agrupa por título normalizado
        groups = defaultdict(list)
        all_games = Game.query.order_by(Game.id).all()
        for g in all_games:
            key = normalize_title(g.title) or g.title.lower().strip()
            groups[key].append(g)

        duplicates = {k: v for k, v in groups.items() if len(v) > 1}

        print(f' Total de jogos: {len(all_games)}')
        print(f' Grupos com duplicata: {len(duplicates)}')
        print()

        if not duplicates:
            print(' Nenhuma duplicata encontrada — tudo limpo.')
            return

        # 2) Pra cada grupo, mescla pro mais antigo
        for key, group in duplicates.items():
            group_sorted = sorted(group, key=lambda g: g.id)
            keeper = group_sorted[0]
            losers = group_sorted[1:]

            print(f' Grupo "{key}" ({len(group)} jogos):')
            print(f'   manter: id={keeper.id} "{keeper.title}"')
            for loser in losers:
                print(f'   mesclar e deletar: id={loser.id} "{loser.title}"')

                # Migra Prices
                n = Price.query.filter_by(game_id=loser.id).update({'game_id': keeper.id})
                rows_migrated += n
                # Migra StoreLinks (apenas os que NÃO criariam duplicata por (game_id, store))
                for sl in StoreLink.query.filter_by(game_id=loser.id).all():
                    exists = StoreLink.query.filter_by(game_id=keeper.id, store=sl.store).first()
                    if exists:
                        if not args.dry_run:
                            db.session.delete(sl)
                    else:
                        sl.game_id = keeper.id
                        rows_migrated += 1
                # Migra Alerts
                n = Alert.query.filter_by(game_id=loser.id).update({'game_id': keeper.id})
                rows_migrated += n
                # Migra NavigationLogs
                n = NavigationLog.query.filter_by(game_id=loser.id).update({'game_id': keeper.id})
                rows_migrated += n

                # Delete o duplicado
                if not args.dry_run:
                    db.session.delete(loser)
                games_deleted += 1
                games_merged += 1

        if not args.dry_run:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f' [ERRO] Rollback: {e}')
                sys.exit(1)
        else:
            db.session.rollback()

    print()
    print('=' * 70)
    print(' Resumo')
    print('=' * 70)
    print(f' Grupos de duplicatas resolvidos: {len(duplicates)}')
    print(f' Jogos deletados (mesclados):     {games_deleted}')
    print(f' Linhas migradas (Price/SL/Alert/Nav): {rows_migrated}')
    print('=' * 70)
    if args.dry_run:
        print(' DRY-RUN — nada foi escrito.')
    else:
        print(' Dedupe concluído.')


if __name__ == '__main__':
    main()
