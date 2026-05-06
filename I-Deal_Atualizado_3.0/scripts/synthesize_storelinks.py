"""
synthesize_storelinks.py
=========================
Pra cada par (jogo, loja) que tem Price mas não tem StoreLink correspondente,
cria um StoreLink apontando para a página de BUSCA da loja com o título do jogo.

Assim, todo card da página de detalhes mostra um botão "Comprar" funcional
em vez de "Indisponível", mesmo pras lojas que vieram via ITAD sem link direto.

SEGURANÇA:
  - Faz backup automático do ideal.db antes de qualquer escrita.
  - NUNCA usa DELETE / UPDATE — só INSERT.
  - Idempotente: se já existe StoreLink pra (game_id, store), pula.

USO:
    cd I-Deal_Atualizado_3.0
    python scripts/synthesize_storelinks.py
    python scripts/synthesize_storelinks.py --dry-run   # simula sem escrever
"""

import argparse
import os
import shutil
import sys
from datetime import datetime
from urllib.parse import quote_plus

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('PRICE_REFRESH_MINUTES', '99999')

# Bloqueia chamadas externas durante o import do app
import price_fetcher  # noqa: E402
price_fetcher.update_all_prices = lambda app: {}

from app import app  # noqa: E402
from models import db, Game, Price, StoreLink  # noqa: E402


# =============================================================================
# Padrões de URL de busca por loja
# =============================================================================
# Cada função recebe um título e retorna a URL de busca daquela loja.
# Se o jogo tem steam_app_id e a loja for Steam, prefere o link direto.

def _url_steam(title: str, steam_id: int | None = None) -> str:
    if steam_id:
        return f'https://store.steampowered.com/app/{steam_id}/'
    return f'https://store.steampowered.com/search/?term={quote_plus(title)}'


def _url_epic(title: str, **_) -> str:
    return f'https://store.epicgames.com/pt-BR/browse?q={quote_plus(title)}'


def _url_gog(title: str, **_) -> str:
    return f'https://www.gog.com/en/games?query={quote_plus(title)}'


def _url_nuuvem(title: str, **_) -> str:
    return f'https://www.nuuvem.com/br-pt/catalog?search={quote_plus(title)}'


def _url_humble(title: str, **_) -> str:
    return f'https://www.humblebundle.com/store/search?search={quote_plus(title)}'


def _url_fanatical(title: str, **_) -> str:
    return f'https://www.fanatical.com/en/search?search={quote_plus(title)}'


URL_BUILDERS = {
    'Steam':        _url_steam,
    'Epic Games':   _url_epic,
    'GOG':          _url_gog,
    'Nuuvem':       _url_nuuvem,
    'Humble Store': _url_humble,
    'Fanatical':    _url_fanatical,
}


def make_backup(db_path: str) -> str:
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = f'{db_path}.backup-storelinks-{ts}'
    shutil.copy2(db_path, backup_path)
    return backup_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Simula sem escrever')
    args = parser.parse_args()

    db_path = os.path.join(PROJECT_ROOT, 'ideal.db')
    print('=' * 70)
    print(' I-Deal — Sintetização de StoreLinks faltantes')
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

    added = 0
    skipped_existing = 0
    skipped_unsupported_store = 0

    with app.app_context():
        # Pares (game_id, store) que TÊM Price
        rows = db.session.execute(
            db.select(Price.game_id, Price.store).distinct()
        ).all()
        pairs = [(r[0], r[1]) for r in rows]

        print(f' Pares (jogo, loja) com Price registrado: {len(pairs)}')

        # Pares que JÁ TÊM StoreLink
        existing_rows = db.session.execute(
            db.select(StoreLink.game_id, StoreLink.store)
        ).all()
        existing_links = {(r[0], r[1]) for r in existing_rows}
        print(f' StoreLinks existentes: {len(existing_links)}')

        # Mapa de title por game_id (cache)
        games_by_id = {g.id: g for g in Game.query.all()}

        for (game_id, store) in pairs:
            if (game_id, store) in existing_links:
                skipped_existing += 1
                continue

            game = games_by_id.get(game_id)
            if not game:
                continue

            url_builder = URL_BUILDERS.get(store)
            if not url_builder:
                skipped_unsupported_store += 1
                continue

            url = url_builder(game.title, steam_id=game.steam_app_id)

            if not args.dry_run:
                db.session.add(StoreLink(
                    game_id=game.id,
                    store=store,
                    url=url,
                ))
            print(f'  [+] {game.title:35s} | {store:12s} → {url}')
            added += 1

        if not args.dry_run:
            db.session.commit()

    print()
    print('=' * 70)
    print(' Resumo')
    print('=' * 70)
    print(f' StoreLinks adicionados:        {added}')
    print(f' Pulados (já existiam):         {skipped_existing}')
    print(f' Pulados (loja não suportada):  {skipped_unsupported_store}')
    print('=' * 70)

    if args.dry_run:
        print(' DRY-RUN — nada foi escrito.')
    else:
        print(' Sintetização concluída. Recarregue qualquer página /game/<id>')
        print(' e o botão "Comprar" vai funcionar pras lojas que antes mostravam "Indisponível".')


if __name__ == '__main__':
    main()
