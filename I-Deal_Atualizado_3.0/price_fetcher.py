# =============================================================================
# price_fetcher.py — Busca de preços reais em lojas externas
# =============================================================================
# Este módulo é responsável por buscar os preços atuais de jogos diretamente
# nas APIs das lojas, garantindo dados em tempo real no banco do I-Deal.
#
# Fontes de dados utilizadas:
#
#   1. Steam Store API (pública, sem chave)
#      endpoint: store.steampowered.com/api/appdetails?appids=ID&cc=br
#      cobre: preço Steam em BRL
#
#   2. IsThereAnyDeal API v2 (pública, requer chave gratuita — API Key)
#      endpoint: api.isthereanydeal.com
#      cobre: Steam, Epic Games, GOG, Nuuvem e +50 lojas em BRL
#      documentação: https://docs.isthereanydeal.com/
#      chave gratuita em: https://isthereanydeal.com/apps/my/
#
# Wrappers dedicados (Sprint 2, cards 5.1, 5.2, 5.3):
#   - fetch_steam_price()  → 5.1 (API direta da Steam)
#   - fetch_gog_price()    → 5.2 (via ITAD)
#   - fetch_epic_price()   → 5.3 (via ITAD)
#   - fetch_nuuvem_price() → bônus
#
# Normalização (US06):
#   - normalize_title() limpa edições/anos/símbolos pra matching cross-loja
#   - coverage_report() relata cobertura mínima de lojas por jogo
#
# Configuração:
#   Defina ITAD_API_KEY no .env. Sem ela, apenas Steam é atualizado.
#
# Exemplo:
#   $env:ITAD_API_KEY = "sua_chave_aqui"
#   python app.py
# =============================================================================

import os
import re
import logging
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env automaticamente
load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

ITAD_API_KEY = os.environ.get('ITAD_API_KEY', '')
ITAD_BASE_URL = 'https://api.isthereanydeal.com'
HTTP_TIMEOUT = 10  # segundos

# Lojas que queremos exibir no I-Deal (nome exato como ITAD retorna em shop.name)
ITAD_STORES_WANTED = {'Steam', 'Epic Games', 'GOG', 'Nuuvem', 'Humble Store', 'Fanatical'}

# Algumas lojas (Humble Store, Fanatical) listam apenas em USD via ITAD,
# mesmo com country=BR. Convertemos por taxa fixa pra apresentar tudo em R$
# e permitir comparação. Em produção real, deveria buscar cotação ao vivo.
USD_TO_BRL_RATE = float(os.environ.get('USD_TO_BRL_RATE', '5.50'))
# Lojas que costumam retornar preço em USD pela API ITAD
USD_LIKELY_STORES = {'Humble Store', 'Fanatical'}

# Cobertura mínima desejada por jogo (US06 — validação)
MIN_STORE_COVERAGE = 2


# =============================================================================
# 1. Steam Store API (pública, sem chave) — Card 5.1
# =============================================================================

def fetch_steam_price(steam_app_id: int) -> float | None:
    """
    Busca o preço atual de um jogo na Steam em BRL via API pública.
    Card 5.1 (Sprint 2): Sincronização Steam DB.

    Retorna o preço final em reais (já com desconto) ou None em caso de erro.
    """
    url = f'https://store.steampowered.com/api/appdetails?appids={steam_app_id}&cc=br&l=brazilian'
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        app_data = data.get(str(steam_app_id), {})
        if not app_data.get('success'):
            logger.warning(f'Steam: app {steam_app_id} não encontrado.')
            return None

        # Jogo gratuito
        if app_data.get('data', {}).get('is_free'):
            return 0.0

        price_overview = app_data.get('data', {}).get('price_overview')
        if not price_overview:
            logger.warning(f'Steam: sem price_overview para app {steam_app_id}.')
            return None

        # A Steam retorna centavos: 17999 = R$ 179,99
        return round(price_overview['final'] / 100, 2)

    except requests.exceptions.RequestException as e:
        logger.error(f'Steam: erro ao buscar app {steam_app_id}: {e}')
        return None


# =============================================================================
# 2. IsThereAnyDeal API (multi-loja)
# =============================================================================

def _itad_lookup_game_ids(titles: list[str]) -> dict[str, str]:
    """
    Resolve UUIDs ITAD a partir de uma lista de títulos.
    Endpoint: POST /lookup/id/title/v1?key=API_KEY
    """
    if not ITAD_API_KEY:
        return {}

    try:
        resp = requests.post(
            f'{ITAD_BASE_URL}/lookup/id/title/v1',
            params={'key': ITAD_API_KEY},
            json=titles,
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json()
        return {title: gid for title, gid in raw.items() if gid is not None}
    except requests.exceptions.RequestException as e:
        logger.error(f'ITAD lookup: erro ao resolver títulos {titles}: {e}')
        return {}


def fetch_itad_prices_bulk(game_uuids: list[str], country: str = 'BR') -> dict[str, dict[str, float]]:
    """
    Busca preços de múltiplos jogos via ITAD em uma chamada.
    Retorna: dict {uuid: {nome_loja: preço}}
    """
    if not ITAD_API_KEY or not game_uuids:
        return {}

    try:
        resp = requests.post(
            f'{ITAD_BASE_URL}/games/prices/v3',
            params={'key': ITAD_API_KEY, 'country': country},
            json=game_uuids,
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        result = {}
        for game_entry in data:
            gid = game_entry.get('id')
            shops = {}
            for deal in game_entry.get('deals', []):
                shop_name = deal.get('shop', {}).get('name', '')
                if shop_name not in ITAD_STORES_WANTED:
                    continue
                price_obj = deal.get('price', {}) or {}
                price_amount = price_obj.get('amount')
                if price_amount is None:
                    continue
                # Converte USD → BRL se a moeda retornada pela ITAD não for BRL.
                # Algumas lojas (ex: Humble, Fanatical) só listam em USD mesmo
                # quando passamos country=BR.
                price_currency = (price_obj.get('currency') or '').upper()
                price_val = float(price_amount)
                if price_currency and price_currency != 'BRL':
                    if price_currency == 'USD':
                        price_val = price_val * USD_TO_BRL_RATE
                    else:
                        # Moeda desconhecida — pula esse preço pra não enganar o usuário
                        logger.warning(f'{shop_name}: moeda {price_currency} desconhecida, pulando.')
                        continue
                price_val = round(price_val, 2)
                if shop_name not in shops or price_val < shops[shop_name]:
                    shops[shop_name] = price_val
            if shops:
                result[gid] = shops

        return result

    except requests.exceptions.RequestException as e:
        logger.error(f'ITAD prices: erro ao buscar preços: {e}')
        return {}


# =============================================================================
# 3. Wrappers dedicados por loja — Cards 5.2 e 5.3
# =============================================================================
# Os wrappers abaixo expõem buscas individuais por loja. Hoje todos passam
# pela ITAD por baixo (única fonte agregadora confiável de preços em BRL),
# mas a interface fica preparada para trocar a fonte por loja se necessário.

def fetch_gog_price(title: str, country: str = 'BR') -> float | None:
    """
    Busca o preço atual de um jogo na GOG em BRL.
    Card 5.2 (Sprint 2): Sincronização GOG.

    Retorna o preço em reais ou None se não encontrado / sem ITAD_API_KEY.
    """
    return _fetch_single_store_price(title, store_name='GOG', country=country)


def fetch_epic_price(title: str, country: str = 'BR') -> float | None:
    """
    Busca o preço atual de um jogo na Epic Games em BRL.
    Card 5.3 (Sprint 2): Sincronização Epic Games.
    """
    return _fetch_single_store_price(title, store_name='Epic Games', country=country)


def fetch_nuuvem_price(title: str, country: str = 'BR') -> float | None:
    """Busca o preço atual de um jogo na Nuuvem em BRL (bônus)."""
    return _fetch_single_store_price(title, store_name='Nuuvem', country=country)


def _fetch_single_store_price(title: str, store_name: str, country: str = 'BR') -> float | None:
    """
    Helper genérico — busca preço de UM título em UMA loja via ITAD.
    Usado pelos wrappers fetch_gog_price/fetch_epic_price/fetch_nuuvem_price.
    """
    if not ITAD_API_KEY:
        logger.info(f'{store_name}: ITAD_API_KEY ausente, pulando "{title}".')
        return None

    title_to_uuid = _itad_lookup_game_ids([title])
    uuid = title_to_uuid.get(title)
    if not uuid:
        logger.warning(f'{store_name}: título "{title}" não encontrado na ITAD.')
        return None

    prices = fetch_itad_prices_bulk([uuid], country=country)
    return prices.get(uuid, {}).get(store_name)


# =============================================================================
# 4. Normalização de títulos — US06 (Sincronizar e Normalizar Dados)
# =============================================================================

# Padrões de "ruído" frequentes em títulos — removidos antes do matching
_TITLE_NOISE_PATTERNS = [
    r'\(\d{4}\)',                       # "(2020)"
    r'\bgame of the year(?: edition)?\b',
    r'\bgoty(?: edition)?\b',
    r"\bdirector'?s cut\b",
    r'\bremastered\b',
    r'\bremaster\b',
    r'\bdefinitive edition\b',
    r'\bcomplete edition\b',
    r'\bdeluxe edition\b',
    r'\bultimate edition\b',
    r"\bcollector'?s edition\b",
    r'\benhanced edition\b',
    r'\bgold edition\b',
    r'\bedition\b',
    r'[™®©]',
]


def normalize_title(title: str) -> str:
    """
    Normaliza um título de jogo para matching consistente entre lojas.
    Card US06 (Sprint 2): Sincronizar e Normalizar Dados.

    Operações aplicadas:
      - lowercase
      - remoção de edições especiais ("Ultimate Edition", "GOTY", etc.)
      - remoção de ano entre parênteses: "(2020)"
      - remoção de marcas comerciais (™ ® ©)
      - troca de pontuação por espaço
      - colapso de espaços múltiplos

    Exemplos:
        "Cyberpunk 2077: Ultimate Edition" → "cyberpunk 2077"
        "The Witcher 3: Wild Hunt - GOTY Edition" → "the witcher 3 wild hunt"
        "ELDEN RING™" → "elden ring"
    """
    if not title:
        return ''

    t = title.lower()
    for pattern in _TITLE_NOISE_PATTERNS:
        t = re.sub(pattern, '', t, flags=re.IGNORECASE)

    # Pontuação separadora vira espaço
    t = re.sub(r'[:\-_/]+', ' ', t)
    # Remove pontuação restante (mantém letras, dígitos, apóstrofos e espaços)
    t = re.sub(r"[^\w\s']", '', t)
    # Colapsa whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def coverage_report(games_with_prices: dict, expected_stores: int = MIN_STORE_COVERAGE) -> dict:
    """
    Relata cobertura de lojas por jogo (US06 — validação).

    Args:
        games_with_prices: dict {game_title: {store: price}}
        expected_stores: cobertura mínima desejada (default 2)

    Retorna dict com:
        - fully_covered: títulos com >= expected_stores lojas
        - partial: lista de (title, n_stores) com 1 <= n_stores < expected_stores
        - missing: títulos com 0 lojas
        - total: total de jogos
        - min_expected: cobertura mínima usada
    """
    fully_covered = []
    partial = []
    missing = []

    for title, prices in games_with_prices.items():
        n = len(prices)
        if n >= expected_stores:
            fully_covered.append(title)
        elif n >= 1:
            partial.append((title, n))
        else:
            missing.append(title)

    return {
        'fully_covered': fully_covered,
        'partial': partial,
        'missing': missing,
        'total': len(games_with_prices),
        'min_expected': expected_stores,
    }


# =============================================================================
# 5. Atualização do banco — orquestrador
# =============================================================================



# =============================================================================
# 4b. Anti-duplicação — find_or_create_game()
# =============================================================================
# Toda criação de Game deve passar por aqui. Garante que não vai entrar jogo
# duplicado no catálogo, mesmo que o usuário ou um script tente criar um igual.
#
# Estratégia de matching (em ordem):
#   1. Igualdade por steam_app_id (mais confiável, ID numérico único da Steam)
#   2. Igualdade por título normalizado (normalize_title remove edições/anos/ ™)
#
# Se já existe, retorna o existente E sinaliza que NÃO criou (return existing, False).
# Se não existe, cria E retorna (return new_game, True).

def find_or_create_game(
    title: str,
    steam_app_id: int | None = None,
    default_price: float = 99.90,
    image_url: str | None = None,
    itad_id: str | None = None,
):
    """
    Busca um Game existente por steam_app_id OU por título normalizado.
    Se não achar, cria um novo. Retorna (game, created) onde created=True
    significa que o jogo era novo.

    Usar via:
        from models import db
        game, created = find_or_create_game('Hollow Knight', steam_app_id=367520)
        if created:
            db.session.flush()  # garante game.id disponível
        # ... usa game ...

    O caller é responsável pelo db.session.commit().
    """
    from models import Game

    # 1) Tentativa por steam_app_id (se fornecido) — mais confiável
    if steam_app_id:
        existing = Game.query.filter_by(steam_app_id=steam_app_id).first()
        if existing:
            return existing, False

    # 2) Tentativa por título normalizado — pega "Cyberpunk 2077" vs
    #    "Cyberpunk 2077: Ultimate Edition" como o mesmo jogo
    if title:
        normalized = normalize_title(title)
        if normalized:
            for g in Game.query.all():
                if normalize_title(g.title) == normalized:
                    return g, False

    # 3) Não existe — cria
    from models import db, Game as GameModel
    if not image_url and steam_app_id:
        image_url = (
            f'https://shared.fastly.steamstatic.com/store_item_assets/'
            f'steam/apps/{steam_app_id}/library_600x900.jpg'
        )
    new_game = GameModel(
        title=title,
        default_price=default_price,
        image_url=image_url,
        steam_app_id=steam_app_id,
        itad_id=itad_id,
    )
    db.session.add(new_game)
    return new_game, True

# =============================================================================
# 5. URL builders por loja + auto-criação de StoreLinks
# =============================================================================
# Quando o sistema descobre um preço pra um par (jogo, loja) que não tem
# StoreLink, cria automaticamente um link de busca da loja com o título.
# Isso garante que TODO preço exibido no front tem um botão "Comprar"
# funcional, sem depender de seed manual de URLs.

from urllib.parse import quote_plus  # noqa: E402


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


def build_store_url(store_name: str, title: str, steam_id: int | None = None) -> str | None:
    """Retorna a URL de busca/produto pra uma loja, ou None se loja desconhecida."""
    builder = URL_BUILDERS.get(store_name)
    if not builder:
        return None
    return builder(title, steam_id=steam_id)


def ensure_storelink(db_session, game, store_name: str) -> bool:
    """
    Garante que existe um StoreLink pra (game, store_name).
    Se não existe, cria com URL de busca da loja.
    Retorna True se criou, False se já existia ou loja desconhecida.

    Não dá commit — quem chama é responsável pelo commit.
    """
    from models import StoreLink

    existing = StoreLink.query.filter_by(game_id=game.id, store=store_name).first()
    if existing:
        return False

    url = build_store_url(store_name, game.title, steam_id=game.steam_app_id)
    if not url:
        return False

    db_session.add(StoreLink(
        game_id=game.id,
        store=store_name,
        url=url,
    ))
    return True


# =============================================================================
# 6. Helper: busca preços de UM jogo específico em todas as lojas
# =============================================================================
# Usado pelo fluxo de "adicionar jogo da busca ao vivo" — quando o usuário
# confirma um jogo na Steam, queremos preços de todas as lojas + links.

def fetch_all_prices_for_game(title: str, steam_app_id: int | None = None,
                              country: str = 'BR') -> dict[str, float]:
    """
    Busca preços em TODAS as lojas suportadas pra um jogo específico.

    Combina:
      - Steam direto (via fetch_steam_price, se houver steam_app_id)
      - Todas as lojas via ITAD (Epic, GOG, Nuuvem, Humble, Fanatical)

    Retorna dict {store_name: price}. Lojas sem preço são omitidas.
    """
    prices: dict[str, float] = {}

    # 1. Steam direto (mais preciso pra essa loja)
    if steam_app_id:
        steam_price = fetch_steam_price(steam_app_id)
        if steam_price is not None:
            prices['Steam'] = steam_price

    # 2. ITAD para todas as outras lojas (e Steam se não pegamos antes)
    if ITAD_API_KEY:
        title_to_uuid = _itad_lookup_game_ids([title])
        uuid = title_to_uuid.get(title)
        if uuid:
            itad_prices = fetch_itad_prices_bulk([uuid], country=country)
            store_prices = itad_prices.get(uuid, {})
            for store, price in store_prices.items():
                # Steam direto tem precedência se já está em prices
                if store == 'Steam' and 'Steam' in prices:
                    continue
                prices[store] = price

    return prices


# =============================================================================
# 7. Atualização do banco — orquestrador
# =============================================================================

def update_all_prices(app) -> dict:
    """
    Atualiza os preços de TODOS os jogos no banco.

    Estratégia eficiente (em batch):
      1. Resolve UUIDs ITAD de todos os jogos (1 chamada de API)
      2. Busca preços de todas as lojas para todos os jogos (1 chamada)
      3. Complementa/sobrescreve com o preço direto da Steam por jogo
      4. Aplica normalização (US06) e gera relatório de cobertura
      5. Salva todos os preços no banco (histórico acumulado)
      6. Cria StoreLinks faltantes automaticamente pra cada (jogo, loja)
         que tem preço — garante botão "Comprar" funcional na UI

    Retorna dict {game_title: quantidade_de_preços_salvos}
    """
    from models import db, Game, Price

    logger.info('=== Iniciando atualização de preços ===')
    now = datetime.now(timezone.utc)

    with app.app_context():
        games = Game.query.all()

    if not games:
        return {}

    titles = [g.title for g in games]
    title_to_uuid = _itad_lookup_game_ids(titles)
    logger.info(f'ITAD: {len(title_to_uuid)}/{len(titles)} UUIDs resolvidos.')

    uuids = list(title_to_uuid.values())
    uuid_to_prices = fetch_itad_prices_bulk(uuids) if uuids else {}

    summary = {}
    storelinks_created = 0
    games_prices_view = {}
    with app.app_context():
        for game in Game.query.all():
            prices_to_save = {}

            gid = title_to_uuid.get(game.title)
            if gid and gid in uuid_to_prices:
                prices_to_save.update(uuid_to_prices[gid])

            if game.steam_app_id:
                steam_price = fetch_steam_price(game.steam_app_id)
                if steam_price is not None:
                    prices_to_save['Steam'] = steam_price

            games_prices_view[game.title] = dict(prices_to_save)

            if not prices_to_save:
                logger.warning(f'Sem preços para "{game.title}".')
                summary[game.title] = 0
                continue

            count = 0
            for store_name, price_val in prices_to_save.items():
                # Salva preço
                db.session.add(Price(
                    game_id=game.id,
                    store=store_name,
                    price=price_val,
                    currency='BRL',
                    date_recorded=now,
                ))
                count += 1
                # Auto-cria StoreLink se não existir (pra UI mostrar "Comprar")
                if ensure_storelink(db.session, game, store_name):
                    storelinks_created += 1

            summary[game.title] = count
            logger.info(
                f'"{game.title}" (norm: "{normalize_title(game.title)}"): '
                f'{count} preço(s) — {prices_to_save}'
            )

        db.session.commit()

    report = coverage_report(games_prices_view, expected_stores=MIN_STORE_COVERAGE)
    logger.info(f'=== Atualização concluída: {sum(summary.values())} preços salvos ===')
    logger.info(
        f'Cobertura: {len(report["fully_covered"])}/{report["total"]} jogos '
        f'com >= {report["min_expected"]} lojas, '
        f'{len(report["partial"])} parciais, '
        f'{len(report["missing"])} sem preços.'
    )
    if storelinks_created > 0:
        logger.info(f'StoreLinks auto-criados: {storelinks_created}')
    if report['missing']:
        logger.warning(f'Jogos SEM preços: {report["missing"]}')

    return summary
