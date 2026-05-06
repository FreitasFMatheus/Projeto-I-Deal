"""
seed_more_games.py
===================
Adiciona ~30 jogos populares ao catálogo do I-Deal.
Idempotente: se já existir jogo com o mesmo steam_app_id, pula.

NUNCA usa DROP / DELETE / UPDATE — só INSERT.
Faz backup do ideal.db antes de qualquer escrita.

USO:
    cd I-Deal_Atualizado_3.0
    python scripts/seed_more_games.py
    python scripts/seed_more_games.py --dry-run   # simula sem escrever
    python scripts/seed_more_games.py --fetch-prices   # busca preço Steam de cada novo jogo
"""

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('PRICE_REFRESH_MINUTES', '99999')

# Bloqueia o scheduler de chamar Steam ao importar o app
import price_fetcher  # noqa: E402
_original_update = price_fetcher.update_all_prices
price_fetcher.update_all_prices = lambda app: {}

from app import app  # noqa: E402
from models import db, Game, Price, StoreLink  # noqa: E402

# Restaura o original caso o user use --fetch-prices
price_fetcher.update_all_prices = _original_update


# =============================================================================
# Catálogo expandido
# =============================================================================
# Cada entrada: (title, default_price, steam_app_id, itad_id, image_url, store_links_dict)
# image_url segue o padrão Steam library asset (600x900)
def _img(steam_id):
    return f'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{steam_id}/library_600x900.jpg'


GAMES_CATALOG = [
    # === RPGs / Action RPGs ===
    ('The Witcher 3: Wild Hunt',       79.99, 292030, 'thewitcher3wildhunt'),
    ('Diablo IV',                     299.50, 2344520, 'diabloiv'),
    ('Path of Exile 2',                 0.00, 2694490, 'pathofexile2'),
    ('Dragon Age: The Veilguard',     299.99, 1845910, 'dragonagetheveilguard'),
    ('Final Fantasy XVI',             349.50, 2515020, 'finalfantasyxvi'),
    # === Souls-likes ===
    ('Dark Souls III',                179.50, 374320,  'darksouls3'),
    ('Lies of P',                     199.90, 1627720, 'liesofp'),
    ('Black Myth: Wukong',            249.50, 2358720, 'blackmythwukong'),
    # === FPS / Tiro ===
    ('Counter-Strike 2',                0.00, 730,     'counterstrike2'),
    ('Call of Duty',                  299.90, 1938090, 'callofduty'),
    ('Apex Legends',                    0.00, 1172470, 'apexlegends'),
    ('Hunt: Showdown 1896',           149.50, 594650,  'huntshowdown'),
    # === Indies aclamados ===
    ('Stardew Valley',                 30.99, 413150,  'stardewvalley'),
    ('Hades',                          59.99, 1145360, 'hades'),
    ('Hades II',                       77.99, 1145350, 'hadesii'),
    ('Celeste',                        46.99, 504230,  'celeste'),
    ('Outer Wilds',                    79.90, 753640,  'outerwilds'),
    # === Sandbox / Survival ===
    ('Minecraft',                     159.99, 2477700, 'minecraft'),
    ('Terraria',                       19.99, 105600,  'terraria'),
    ('Valheim',                        46.99, 892970,  'valheim'),
    ('Don\'t Starve Together',         28.99, 322330,  'dontstarvetogether'),
    ('Palworld',                      109.50, 1623730, 'palworld'),
    # === Estratégia / Simulação ===
    ('Cities: Skylines II',           149.50, 949230,  'citiesskylines2'),
    ('Football Manager 2024',          99.50, 1904540, 'footballmanager2024'),
    ('Frostpunk 2',                   199.99, 1601580, 'frostpunk2'),
    # === Multiplayer / Co-op ===
    ('Helldivers 2',                  199.50, 553850,  'helldivers2'),
    ('Sea of Thieves',                149.50, 1172620, 'seaofthieves'),
    # === Aventura / História ===
    ('Disco Elysium',                  79.99, 632470,  'discoelysium'),
    ('Death Stranding',               149.50, 1190460, 'deathstranding'),
    ('Alan Wake 2',                   249.50, 2474120, 'alanwake2'),
    ('Indiana Jones and the Great Circle', 299.50, 2677660, 'indianajones'),
    # === Retro / Clássicos ===
    ('Portal 2',                       19.99, 620,     'portal2'),
    ('Half-Life: Alyx',                99.50, 546560,  'halflifealyx'),
    # === Esportes ===
    ('EA SPORTS FC 24',               199.50, 2195250, 'easportsfc24'),
]


def make_backup(db_path: str) -> str | None:
    if not os.path.exists(db_path):
        return None
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = f'{db_path}.backup-seed-{timestamp}'
    shutil.copy2(db_path, backup_path)
    return backup_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Simula sem escrever')
    parser.add_argument('--fetch-prices', action='store_true',
                        help='Busca preço Steam de cada novo jogo (mais lento, requer rede)')
    args = parser.parse_args()

    db_path = os.path.join(PROJECT_ROOT, 'ideal.db')
    print('=' * 70)
    print(' I-Deal — Expansão do catálogo')
    print('=' * 70)
    print(f' Banco:        {db_path}')
    print(f' Dry-run:      {args.dry_run}')
    print(f' Buscar preço: {args.fetch_prices}')
    print(f' Catálogo:     {len(GAMES_CATALOG)} jogos disponíveis')
    print('=' * 70)

    # Backup
    if not args.dry_run and os.path.exists(db_path):
        backup = make_backup(db_path)
        print(f' [OK] Backup: {backup}')

    added = 0
    skipped = 0
    fetched_prices = 0

    with app.app_context():
        print(f' Jogos já no banco: {Game.query.count()}')
        print()

        now = datetime.now(timezone.utc)

        from price_fetcher import find_or_create_game

        for entry in GAMES_CATALOG:
            title, default_price, steam_id, itad_id = entry

            if args.dry_run:
                # Em dry-run só simula a checagem por steam_app_id
                existing = Game.query.filter_by(steam_app_id=steam_id).first()
                if existing:
                    skipped += 1
                else:
                    print(f'  [+] {title} (Steam {steam_id})')
                    added += 1
                continue

            # find_or_create_game garante anti-duplicação (por steam_app_id e título normalizado)
            new_game, created = find_or_create_game(
                title=title,
                steam_app_id=steam_id,
                default_price=default_price,
                image_url=_img(steam_id),
                itad_id=itad_id,
            )
            if not created:
                skipped += 1
                continue
            db.session.flush()

            # Link da Steam (sempre tem)
            db.session.add(StoreLink(
                game_id=new_game.id,
                store='Steam',
                url=f'https://store.steampowered.com/app/{steam_id}/',
            ))

            # Busca preço Steam se solicitado
            if args.fetch_prices:
                price_val = price_fetcher.fetch_steam_price(steam_id)
                if price_val is not None:
                    db.session.add(Price(
                        game_id=new_game.id,
                        store='Steam',
                        price=price_val,
                        currency='BRL',
                        date_recorded=now,
                    ))
                    fetched_prices += 1

            added += 1
            print(f'  [+] {title} (Steam {steam_id})')

        if not args.dry_run:
            db.session.commit()

    print()
    print('=' * 70)
    print(' Resumo')
    print('=' * 70)
    print(f'  Adicionados:   {added}')
    print(f'  Pulados (já existiam): {skipped}')
    if args.fetch_prices:
        print(f'  Preços buscados: {fetched_prices}')
    print('=' * 70)
    print(' Pronto. Reinicie o app para ver o novo catálogo.')


if __name__ == '__main__':
    main()
