# =============================================================================
# app.py — Aplicação principal Flask do projeto I-Deal
# =============================================================================
# Este é o ponto de entrada do sistema. Aqui ficam:
#   - Configurações do Flask e banco de dados
#   - Dados iniciais (seed) de jogos, preços e links
#   - Todas as rotas (endpoints) da aplicação
#
# Rotas existentes (Sprint 1):
#   /            → Página inicial com catálogo de jogos (1.4)
#   /login       → Tela de login (1.1)
#   /register    → Tela de cadastro (1.2)
#   /logout      → Encerrar sessão
#
# Rotas novas (tarefas MF):
#   /game/<id>           → Página de detalhes do jogo com links das lojas (2.3.1)
#   /redirect/<link_id>  → Redireciona para a loja e registra navegação (2.3.2)
#   /api/prices/steam    → Queries de preços no SQLite/SteamDB (3.1)
#   /api/prices/mongo    → Queries de preços no MongoDB (3.2)
# =============================================================================

import os
import logging
from datetime import datetime, timezone
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from models import db, User, Game, Price, StoreLink, NavigationLog, Alert
from price_fetcher import (
    update_all_prices, fetch_steam_price,
    fetch_all_prices_for_game, ensure_storelink,
    find_or_create_game,
)
from alerts import process_alerts

logging.basicConfig(level=logging.INFO)

# -----------------------------------------------------------------------------
# Configuração da aplicação Flask
# -----------------------------------------------------------------------------
app = Flask(__name__)

# Caminho absoluto da pasta do projeto (usado para localizar o arquivo ideal.db)
basedir = os.path.abspath(os.path.dirname(__file__))

# URI de conexão com o banco SQLite — o arquivo ideal.db fica na raiz do projeto
# Nota: 3 barras = caminho relativo, 4 barras = caminho absoluto
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'ideal.db')

# Desabilita o rastreamento de modificações do SQLAlchemy (economiza memória)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Chave secreta usada pelo Flask para assinar cookies de sessão e tokens CSRF
app.config['SECRET_KEY'] = 'uma_chave_super_secreta_e_segura_ideal2026'

# Inicializa o SQLAlchemy com a instância do Flask
db.init_app(app)


# =============================================================================
# Seed de dados iniciais — popula o banco na primeira execução
# =============================================================================
# Quando o banco está vazio (primeira vez rodando), inserimos dados de teste
# para que a aplicação já tenha conteúdo para demonstração.
with app.app_context():
    # Cria todas as tabelas definidas nos models (se não existirem)
    db.create_all()

    # --- Seed de Jogos (1.3.2) ---
    # Só insere se a tabela games estiver vazia
    if Game.query.count() == 0:
        games = [
            Game(
                title="Elden Ring",
                default_price=249.90,
                image_url="https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1245620/library_600x900.jpg",
                steam_app_id=1245620,
                itad_id="eldenring",
            ),
            Game(
                title="Cyberpunk 2077",
                default_price=199.90,
                image_url="https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1091500/library_600x900.jpg",
                steam_app_id=1091500,
                itad_id="cyberpunk2077",
            ),
            Game(
                title="Baldur's Gate 3",
                default_price=199.99,
                image_url="https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1086940/library_600x900.jpg",
                steam_app_id=1086940,
                itad_id="baldursgate3",
            ),
            Game(
                title="Hollow Knight",
                default_price=46.99,
                image_url="https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/367520/library_600x900.jpg",
                steam_app_id=367520,
                itad_id="hollowknight",
            ),
            Game(
                title="Red Dead Redemption 2",
                default_price=149.50,
                image_url="https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1174180/library_600x900.jpg",
                steam_app_id=1174180,
                itad_id="reddeadredemption2",
            ),
        ]
        db.session.bulk_save_objects(games)
        db.session.commit()

    # --- Seed de Preços (busca real em todas as lojas via ITAD + Steam) ---
    # Na primeira execução, chama update_all_prices que busca preços de todas
    # as lojas de uma vez: Steam (API direta) + Epic, GOG, Nuuvem, etc. (ITAD).
    if Price.query.count() == 0:
        update_all_prices(app)

    # --- Seed de Links das Lojas (2.3.1 — tarefa MF) ---
    # URLs reais de cada jogo em cada loja para redirecionamento
    if StoreLink.query.count() == 0:
        links = [
            # Elden Ring
            StoreLink(game_id=1, store="Steam",       url="https://store.steampowered.com/app/1245620/ELDEN_RING/"),
            StoreLink(game_id=1, store="Epic Games",   url="https://store.epicgames.com/pt-BR/p/elden-ring"),
            StoreLink(game_id=1, store="Nuuvem",       url="https://www.nuuvem.com/br-pt/item/elden-ring"),

            # Cyberpunk 2077
            StoreLink(game_id=2, store="Steam",       url="https://store.steampowered.com/app/1091500/Cyberpunk_2077/"),
            StoreLink(game_id=2, store="Epic Games",   url="https://store.epicgames.com/pt-BR/p/cyberpunk-2077"),
            StoreLink(game_id=2, store="GOG",          url="https://www.gog.com/game/cyberpunk_2077"),

            # Baldur's Gate 3
            StoreLink(game_id=3, store="Steam",       url="https://store.steampowered.com/app/1086940/Baldurs_Gate_3/"),
            StoreLink(game_id=3, store="Epic Games",   url="https://store.epicgames.com/pt-BR/p/baldurs-gate-3"),
            StoreLink(game_id=3, store="Nuuvem",       url="https://www.nuuvem.com/br-pt/item/baldurs-gate-3"),

            # Hollow Knight
            StoreLink(game_id=4, store="Steam",       url="https://store.steampowered.com/app/367520/Hollow_Knight/"),
            StoreLink(game_id=4, store="GOG",          url="https://www.gog.com/game/hollow_knight"),

            # Red Dead Redemption 2
            StoreLink(game_id=5, store="Steam",       url="https://store.steampowered.com/app/1174180/Red_Dead_Redemption_2/"),
            StoreLink(game_id=5, store="Epic Games",   url="https://store.epicgames.com/pt-BR/p/red-dead-redemption-2"),
            StoreLink(game_id=5, store="Nuuvem",       url="https://www.nuuvem.com/br-pt/item/red-dead-redemption-2"),
        ]
        db.session.bulk_save_objects(links)
        db.session.commit()


# =============================================================================
# Agendamento automático de atualização de preços (APScheduler)
# =============================================================================
# Cria um scheduler em background que dispara update_all_prices periodicamente.
# O scheduler roda em uma thread separada e não bloqueia o servidor Flask.
# Running in Flask debug mode can cause duplicate schedulers — usamos
# a variável de ambiente WERKZEUG_RUN_MAIN para evitar isso.
#
# Tarefa 5.5 (Sprint 2): "Conferência dos Bancos de 15 em 15 minutos".
# Intervalo configurável via PRICE_REFRESH_MINUTES (default 15min).
def _refresh_prices_and_check_alerts():
    """Tarefa do scheduler: atualiza preços e checa alertas (US03)."""
    update_all_prices(app)
    try:
        process_alerts(app)
    except Exception as e:
        logging.getLogger(__name__).error(f'process_alerts falhou: {e}')


def _start_price_scheduler():
    interval_minutes = int(os.environ.get('PRICE_REFRESH_MINUTES', '15'))
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=_refresh_prices_and_check_alerts,
        trigger='interval',
        minutes=interval_minutes,
        id='price_refresh',
        replace_existing=True,
        name='Atualização automática de preços + alertas',
    )
    scheduler.start()
    logging.getLogger(__name__).info(
        f'Scheduler de preços iniciado (a cada {interval_minutes} min).'
    )
    return scheduler

# Inicia o scheduler apenas quando não for a thread de reload do Werkzeug
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    _price_scheduler = _start_price_scheduler()


# =============================================================================
# AUTENTICAÇÃO — Decorator login_required
# =============================================================================
# Protege rotas que exigem login. Redireciona para /login se o usuário
# não estiver autenticado, salvando a URL original para redirecionar de volta.
from functools import wraps

def login_required(f):
    """Decorator que exige sessão ativa. Redireciona para login se necessário."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            flash('Você precisa estar logado para acessar esta página.', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated


# =============================================================================
# ROTAS EXISTENTES (Sprint 1 — mantidas)
# =============================================================================

@app.route('/')
@login_required
def index():
    """
    Página inicial — exibe o catálogo de jogos com o menor preço de cada um.
    (1.4 — Personalização do Site baseada no import dos dados do Banco)
    """
    games = Game.query.all()
    user_id = session.get('user_id')
    user = User.query.get(user_id) if user_id else None

    # Para cada jogo, buscar o menor preço atual entre todas as lojas
    # Isso alimenta o card com o "a partir de R$ XX,XX"
    games_with_prices = []
    for game in games:
        # Busca o menor preço mais recente para este jogo
        # Subconsulta: pega o preço mais recente de cada loja, depois o menor deles
        latest_prices = (
            Price.query
            .filter_by(game_id=game.id)
            .order_by(Price.date_recorded.desc())
            .all()
        )
        # Agrupa por loja e pega só o mais recente de cada
        seen_stores = {}
        for p in latest_prices:
            if p.store not in seen_stores:
                seen_stores[p.store] = p.price

        # Se não há nenhum preço real cadastrado, marca como "sem oferta"
        # (não usa default_price como fallback — isso enganaria o usuário)
        has_price = len(seen_stores) > 0
        min_price = min(seen_stores.values()) if has_price else None

        games_with_prices.append({
            'game': game,
            'min_price': min_price,
            'store_count': len(seen_stores),
            'has_price': has_price,
        })

    return render_template('index.html', games=games_with_prices, user=user)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Tela de login — autentica o usuário com email e senha.
    (1.1 — Criação de Classes para Login)
    """
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # Busca o usuário pelo email no banco
        user = User.query.filter_by(email=email).first()

        # Verifica se o usuário existe E se a senha bate com o hash
        if user and check_password_hash(user.password_hash, password):
            # Salva o ID do usuário na sessão (cookie criptografado)
            session['user_id'] = user.id
            flash('Login realizado com sucesso!', 'success')
            # Redireciona para a página que o usuário tentou acessar antes
            next_page = request.args.get('next') or url_for('index')
            return redirect(next_page)
        else:
            flash('Email ou senha incorretos.', 'error')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Tela de cadastro — cria um novo usuário no sistema.
    (1.2 — Criação de Classes para Cadastro)
    """
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        # Verifica se já existe um usuário com esse email
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Este email já está cadastrado.', 'error')
            return redirect(url_for('register'))

        # Cria o novo usuário com senha hasheada (nunca salvar senha em texto puro!)
        new_user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Cadastro realizado com sucesso! Faça login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/logout')
def logout():
    """Remove o usuário da sessão (faz logout)."""
    session.pop('user_id', None)
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('index'))


# =============================================================================
# 2.3.1 — Gerar Link para ir até o Site do jogo (NOVA — tarefa MF)
# =============================================================================
# Esta rota exibe a página de detalhes de um jogo, com:
#   - Preços de todas as lojas (ordenados do menor para o maior)
#   - Links clicáveis para ir direto à página de compra em cada loja
#   - Histórico de preços ao longo do tempo
@app.route('/game/<int:game_id>')
@login_required
def game_detail(game_id):
    """
    Página de detalhes do jogo — mostra preços por loja com links de compra.
    O usuário pode clicar em qualquer loja para ser redirecionado ao site.
    """
    # Busca o jogo pelo ID ou retorna 404 se não encontrar
    game = Game.query.get_or_404(game_id)
    user_id = session.get('user_id')
    user = User.query.get(user_id) if user_id else None

    # Busca todos os preços deste jogo, do mais recente para o mais antigo
    all_prices = (
        Price.query
        .filter_by(game_id=game.id)
        .order_by(Price.date_recorded.desc())
        .all()
    )

    # Agrupa por loja — pega só o preço mais recente de cada loja
    current_prices = {}
    for p in all_prices:
        if p.store not in current_prices:
            current_prices[p.store] = p

    # Ordena do menor preço para o maior (melhor oferta primeiro)
    sorted_prices = sorted(current_prices.values(), key=lambda p: p.price)

    # Busca os links das lojas para este jogo (2.3.1)
    store_links = {sl.store: sl for sl in StoreLink.query.filter_by(game_id=game.id).all()}

    # Monta a lista de ofertas com preço + link de cada loja
    offers = []
    for price_obj in sorted_prices:
        link = store_links.get(price_obj.store)
        offers.append({
            'store': price_obj.store,
            'price': price_obj.price,
            'link_id': link.id if link else None,
            'url': link.url if link else '#',
            'date': price_obj.date_recorded.strftime('%d/%m/%Y'),
        })

    # Prepara dados para o gráfico de histórico de preços
    price_history = []
    for p in reversed(all_prices):  # Ordem cronológica para o gráfico
        price_history.append({
            'store': p.store,
            'price': p.price,
            'date': p.date_recorded.strftime('%d/%m/%Y'),
        })

    return render_template(
        'game_detail.html',
        game=game,
        user=user,
        offers=offers,
        price_history=price_history,
    )


# =============================================================================
# 2.3.2 — Armazenar navegação no banco (NOVA — tarefa MF)
# =============================================================================
# Quando o usuário clica em "Comprar" numa loja, passa por esta rota antes
# de ser redirecionado. Assim registramos o clique no banco para análise.
@app.route('/redirect/<int:link_id>')
@login_required
def redirect_to_store(link_id):
    """
    Redireciona o usuário para a loja externa e registra o clique.
    Essa rota funciona como um "proxy" de redirecionamento que:
    1. Busca o link da loja no banco
    2. Registra a navegação (quem clicou, em qual jogo, qual loja, quando)
    3. Redireciona o navegador para a URL externa da loja
    """
    # Busca o link ou retorna 404
    store_link = StoreLink.query.get_or_404(link_id)

    # Registra o log de navegação no banco (2.3.2)
    log = NavigationLog(
        user_id=session.get('user_id'),   # None se o usuário não estiver logado
        game_id=store_link.game_id,
        store=store_link.store,
        url_visited=store_link.url,
    )
    db.session.add(log)
    db.session.commit()

    # Redireciona para a URL real da loja (o navegador sai do I-Deal)
    return redirect(store_link.url)


# =============================================================================
# 3.1 — Queries de Preços no SteamDB / SQLite (NOVA — tarefa MF)
# =============================================================================
# API REST que retorna dados de preços do banco SQLite em formato JSON.
# Simula consultas que em produção seriam feitas ao SteamDB.
#
# Parâmetros opcionais via query string:
#   ?game_id=1       → filtra por jogo
#   ?store=Steam     → filtra por loja
#   ?min_price=50    → preço mínimo
#   ?max_price=200   → preço máximo
#
# Exemplos de uso:
#   GET /api/prices/steam                    → todos os preços
#   GET /api/prices/steam?game_id=1          → preços do Elden Ring
#   GET /api/prices/steam?store=Steam        → preços só da Steam
#   GET /api/prices/steam?max_price=100      → jogos abaixo de R$100
@app.route('/api/prices/steam')
def api_prices_steam():
    """
    Endpoint REST para consultar preços no banco SQLite.
    Retorna JSON com preços filtrados conforme parâmetros da query string.
    (3.1 — Queries de Preços no SteamDB)
    """
    # Inicia a query base na tabela de preços
    query = Price.query

    # --- Aplica filtros opcionais conforme parâmetros recebidos ---

    # Filtro por jogo específico
    game_id = request.args.get('game_id', type=int)
    if game_id:
        query = query.filter(Price.game_id == game_id)

    # Filtro por loja específica
    store = request.args.get('store', type=str)
    if store:
        query = query.filter(Price.store == store)

    # Filtro por faixa de preço (mínimo)
    min_price = request.args.get('min_price', type=float)
    if min_price is not None:
        query = query.filter(Price.price >= min_price)

    # Filtro por faixa de preço (máximo)
    max_price = request.args.get('max_price', type=float)
    if max_price is not None:
        query = query.filter(Price.price <= max_price)

    # Ordena por data mais recente primeiro
    query = query.order_by(Price.date_recorded.desc())

    # Executa a query e converte os resultados para JSON
    prices = query.all()
    result = []
    for p in prices:
        # Busca o nome do jogo para incluir no JSON
        game = Game.query.get(p.game_id)
        result.append({
            'id': p.id,
            'game_id': p.game_id,
            'game_title': game.title if game else 'Desconhecido',
            'store': p.store,
            'price': p.price,
            'currency': p.currency,
            'date_recorded': p.date_recorded.isoformat(),
        })

    # Retorna o JSON com metadados da consulta
    return jsonify({
        'source': 'sqlite_steamdb',       # Identifica a fonte dos dados
        'total_results': len(result),
        'filters_applied': {
            'game_id': game_id,
            'store': store,
            'min_price': min_price,
            'max_price': max_price,
        },
        'prices': result,
    })


# =============================================================================
# 3.2 — Queries de Preços no MongoDB (NOVA — tarefa MF)
# =============================================================================
# API REST que consulta preços armazenados no MongoDB.
# O MongoDB é usado para armazenar dados não-estruturados e de alta velocidade,
# como caches de preços de APIs externas.
#
# IMPORTANTE: Para esta rota funcionar, o MongoDB precisa estar rodando:
#   sudo systemctl start mongodb
#
# Os dados são sincronizados do SQLite para o MongoDB na inicialização,
# simulando o que aconteceria com dados vindos de APIs externas.
#
# Parâmetros opcionais:
#   ?game_title=Elden Ring  → busca por título (case-insensitive)
#   ?store=Steam            → filtra por loja
#   ?max_price=200          → preço máximo
@app.route('/api/prices/mongo')
def api_prices_mongo():
    """
    Endpoint REST para consultar preços no MongoDB.
    Retorna JSON com preços consultados via PyMongo.
    (3.2 — Queries de Preços no MongoDB)
    """
    try:
        # Importa pymongo aqui para não quebrar o app caso MongoDB não esteja instalado
        from pymongo import MongoClient

        # Conecta ao MongoDB local (porta padrão 27017)
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=3000)

        # Seleciona o banco de dados "ideal_db" e a coleção "prices"
        mongo_db = client['ideal_db']
        collection = mongo_db['prices']

        # Se a coleção estiver vazia, sincroniza os dados do SQLite para o MongoDB
        # Em produção, isso seria feito por um job de sincronização (tarefa 5.x)
        if collection.count_documents({}) == 0:
            _sync_sqlite_to_mongo(collection)

        # --- Monta o filtro de consulta MongoDB ---
        mongo_filter = {}

        # Filtro por título do jogo (busca parcial, case-insensitive)
        game_title = request.args.get('game_title', type=str)
        if game_title:
            # Usa regex do MongoDB para busca parcial (ex: "elden" encontra "Elden Ring")
            mongo_filter['game_title'] = {'$regex': game_title, '$options': 'i'}

        # Filtro por loja
        store = request.args.get('store', type=str)
        if store:
            mongo_filter['store'] = store

        # Filtro por preço máximo
        max_price = request.args.get('max_price', type=float)
        if max_price is not None:
            mongo_filter['price'] = {'$lte': max_price}

        # Executa a query no MongoDB, ordenando por preço (menor primeiro)
        cursor = collection.find(mongo_filter).sort('price', 1)

        # Converte os resultados para uma lista JSON-serializável
        # O campo _id do MongoDB é um ObjectId, precisa converter para string
        results = []
        for doc in cursor:
            doc['_id'] = str(doc['_id'])  # ObjectId → string
            results.append(doc)

        client.close()

        return jsonify({
            'source': 'mongodb',              # Identifica a fonte dos dados
            'total_results': len(results),
            'filters_applied': {
                'game_title': game_title,
                'store': store,
                'max_price': max_price,
            },
            'prices': results,
        })

    except Exception as e:
        # Se o MongoDB não estiver rodando ou der erro, retorna mensagem amigável
        return jsonify({
            'source': 'mongodb',
            'error': f'Não foi possível conectar ao MongoDB: {str(e)}',
            'hint': 'Verifique se o MongoDB está rodando: sudo systemctl start mongodb',
        }), 503


def _sync_sqlite_to_mongo(collection):
    """
    Função auxiliar que copia os preços do SQLite para o MongoDB.
    Em produção, essa sincronização seria feita por um job agendado
    (tarefa 5.x — Sincronização de dados).

    Cada documento no MongoDB tem a estrutura:
    {
        "game_id": 1,
        "game_title": "Elden Ring",
        "store": "Steam",
        "price": 174.93,
        "currency": "BRL",
        "date_recorded": "2025-03-20T14:00:00"
    }
    """
    prices = Price.query.all()
    docs = []
    for p in prices:
        game = Game.query.get(p.game_id)
        docs.append({
            'game_id': p.game_id,
            'game_title': game.title if game else 'Desconhecido',
            'store': p.store,
            'price': p.price,
            'currency': p.currency,
            'date_recorded': p.date_recorded.isoformat(),
        })
    if docs:
        collection.insert_many(docs)


# =============================================================================
# 4. Atualização manual de preços via API (NOVA)
# =============================================================================
# Permite disparar a atualização imediata de todos os preços via requisição HTTP.
# Útil para testes, ou para forçar uma atualização fora do ciclo de 6 horas.
#
# Exemplo de uso:
#   curl -X POST http://localhost:5000/api/prices/refresh
#   ou no PowerShell:
#   Invoke-WebRequest -Uri http://localhost:5000/api/prices/refresh -Method POST
@app.route('/api/prices/refresh', methods=['POST'])
def api_prices_refresh():
    """
    Dispara a atualização manual de preços para todos os jogos.
    Busca preços reais nas APIs externas (Steam + ITAD) e salva no banco.
    Retorna um JSON com o resumo de quantos preços foram atualizados por jogo.
    """
    import threading

    # Resultados compartilhados entre a thread e a resposta
    result_container = {}
    error_container = {}

    def run_update():
        try:
            result_container.update(update_all_prices(app))
        except Exception as exc:
            error_container['msg'] = str(exc)

    # Roda a atualização em uma thread para não bloquear o request
    t = threading.Thread(target=run_update, daemon=True)
    t.start()
    t.join(timeout=60)  # Aguarda até 60 segundos

    if error_container:
        return jsonify({
            'status': 'error',
            'message': error_container.get('msg', 'Erro desconhecido'),
        }), 500

    if not result_container and t.is_alive():
        return jsonify({
            'status': 'running',
            'message': 'Atualização iniciada em background (demorou mais de 60s).',
        }), 202


    total_updated = sum(result_container.values())
    return jsonify({
        'status': 'ok',
        'message': f'{total_updated} preço(s) atualizados no banco.',
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'details': result_container,
    })


# =============================================================================
# US03 — Alertas de Preço (NOVAS rotas — Sprint 2)
# =============================================================================
# Permite ao usuário cadastrar alertas: "me avise quando jogo X estiver
# por R$ Y ou menos". Rotas:
#   GET  /alerts                  → lista alertas do usuário
#   POST /alerts/new              → cria alerta a partir de form
#   POST /alerts/<id>/toggle      → ativa/desativa
#   POST /alerts/<id>/delete      → remove
#   POST /alerts/test-email       → envia email de teste pra debug
# =============================================================================

@app.route('/alerts')
@login_required
def alerts_list():
    """Lista os alertas do usuário logado."""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    user_alerts = (
        Alert.query
        .filter_by(user_id=user_id)
        .order_by(Alert.active.desc(), Alert.created_at.desc())
        .all()
    )

    enriched = []
    for a in user_alerts:
        latest_q = Price.query.filter_by(game_id=a.game_id)
        if a.store_filter:
            latest_q = latest_q.filter_by(store=a.store_filter)
        latest = latest_q.order_by(Price.date_recorded.desc()).first()
        enriched.append({
            'alert': a,
            'current_price': latest.price if latest else None,
            'current_store': latest.store if latest else None,
            'hit_target': bool(latest and latest.price <= a.target_price),
        })

    games = Game.query.order_by(Game.title).all()

    # Pré-seleção: se vier ?prefill_game_id=X (ex: clicar "Criar alerta" na
    # página do jogo), o input já vem preenchido com aquele jogo.
    prefill_game_id = request.args.get('prefill_game_id', type=int)
    prefill_game = Game.query.get(prefill_game_id) if prefill_game_id else None

    return render_template(
        'alerts.html',
        user=user,
        alerts=enriched,
        games=games,
        prefill_game=prefill_game,
    )


@app.route('/alerts/new', methods=['POST'])
@login_required
def alerts_create():
    """Cria um novo alerta a partir do formulário.

    Aceita game_id (compat antigo, vindo de hidden) OU game_name (input com
    autocomplete via datalist). Se vier game_name, faz lookup case-insensitive
    primeiro exato; se não achar, tenta substring única.
    """
    user_id = session.get('user_id')

    # Pega target_price e store_filter (sempre obrigatórios/opcionais)
    try:
        target_price = float(str(request.form.get('target_price', '0')).replace(',', '.'))
    except (ValueError, TypeError):
        flash('Preço-alvo inválido.', 'error')
        return redirect(url_for('alerts_list'))

    store_filter = (request.form.get('store_filter') or '').strip() or None

    # Filtro 4.3.1+ — desconto mínimo (% sobre default_price). Vazio = sem filtro.
    min_discount_str = (request.form.get('min_discount_pct') or '').strip()
    min_discount_pct = None
    if min_discount_str:
        try:
            min_discount_pct = float(min_discount_str.replace(',', '.'))
            if min_discount_pct <= 0:
                min_discount_pct = None
            elif min_discount_pct > 99:
                flash('Desconto mínimo deve ser entre 1% e 99%.', 'error')
                return redirect(url_for('alerts_list'))
        except (ValueError, TypeError):
            flash('Desconto mínimo inválido.', 'error')
            return redirect(url_for('alerts_list'))

    # Resolução do jogo: tenta game_id primeiro (compat), depois game_name
    game = None
    raw_game_id = request.form.get('game_id', '').strip()
    if raw_game_id and raw_game_id.isdigit():
        game = Game.query.get(int(raw_game_id))

    if not game:
        game_name = (request.form.get('game_name') or '').strip()
        if game_name:
            # Match exato case-insensitive
            game = Game.query.filter(Game.title.ilike(game_name)).first()
            if not game:
                # Match por substring única
                matches = Game.query.filter(Game.title.ilike(f'%{game_name}%')).all()
                if len(matches) == 1:
                    game = matches[0]
                elif len(matches) > 1:
                    nomes = ', '.join(m.title for m in matches[:5])
                    flash(
                        f'"{game_name}" tem múltiplos resultados ({nomes}{"..." if len(matches) > 5 else ""}). '
                        f'Seja mais específico.',
                        'error',
                    )
                    return redirect(url_for('alerts_list'))

    if not game:
        flash(
            'Jogo não encontrado no catálogo. Verifique a grafia ou solicite o '
            'acompanhamento na página inicial.',
            'error',
        )
        return redirect(url_for('alerts_list'))

    if target_price <= 0:
        flash('O preço-alvo deve ser maior que zero.', 'error')
        return redirect(url_for('alerts_list'))

    alert = Alert(
        user_id=user_id,
        game_id=game.id,
        target_price=target_price,
        store_filter=store_filter,
        min_discount_pct=min_discount_pct,
        active=True,
    )
    db.session.add(alert)
    db.session.commit()

    extra = f' (≥ {min_discount_pct:.0f}% off)' if min_discount_pct else ''
    flash(f'Alerta criado para {game.title} em R$ {target_price:.2f}{extra}.'.replace('.', ','), 'success')
    return redirect(url_for('alerts_list'))


@app.route('/alerts/<int:alert_id>/toggle', methods=['POST'])
@login_required
def alerts_toggle(alert_id):
    """Ativa/desativa um alerta."""
    user_id = session.get('user_id')
    alert = Alert.query.filter_by(id=alert_id, user_id=user_id).first()
    if not alert:
        flash('Alerta não encontrado.', 'error')
        return redirect(url_for('alerts_list'))

    alert.active = not alert.active
    db.session.commit()
    flash(
        f'Alerta {"ativado" if alert.active else "desativado"} com sucesso.',
        'success' if alert.active else 'info',
    )
    return redirect(url_for('alerts_list'))


@app.route('/alerts/<int:alert_id>/delete', methods=['POST'])
@login_required
def alerts_delete(alert_id):
    """Remove um alerta."""
    user_id = session.get('user_id')
    alert = Alert.query.filter_by(id=alert_id, user_id=user_id).first()
    if not alert:
        flash('Alerta não encontrado.', 'error')
        return redirect(url_for('alerts_list'))

    db.session.delete(alert)
    db.session.commit()
    flash('Alerta removido.', 'info')
    return redirect(url_for('alerts_list'))


@app.route('/alerts/test-email', methods=['POST'])
@login_required
def alerts_test_email():
    """Envia um email de teste para o próprio usuário (debug do SMTP)."""
    from email_service import send_test_email
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    ok = send_test_email(user.email)
    if ok:
        flash(f'Email de teste enviado para {user.email}. Confira a caixa de entrada.', 'success')
    else:
        flash('Falha ao enviar email. Verifique SMTP_USER/SMTP_PASSWORD no .env.', 'error')
    return redirect(url_for('alerts_list'))


# =============================================================================
# Execução do servidor de desenvolvimento
# =============================================================================


# =============================================================================
# QA — Painel de teste (visível apenas para a conta QA)
# =============================================================================
# Conta especial usada para validar o fluxo de emails: dispara cenários
# pré-fabricados para todos os usuários reais cadastrados.
# A constante QA_EMAIL define quem tem acesso ao painel.
QA_EMAIL = 'qa@ideal.fei'

# Cenários pré-fabricados (cada um cobre uma loja diferente da paleta)
QA_TEST_SCENARIOS = [
    {
        'game_title': 'Elden Ring',          'store': 'Steam',
        'new_price': 149.90, 'target_price': 199.90, 'game_id': 1,
    },
    {
        'game_title': 'Cyberpunk 2077',      'store': 'Epic Games',
        'new_price':  59.97, 'target_price': 199.90, 'game_id': 2,
    },
    {
        'game_title': "Baldur's Gate 3",     'store': 'GOG',
        'new_price':  99.99, 'target_price': 199.99, 'game_id': 3,
    },
    {
        'game_title': 'Hollow Knight',       'store': 'Nuuvem',
        'new_price':  15.00, 'target_price':  46.99, 'game_id': 4,
    },
    {
        'game_title': 'Red Dead Redemption 2', 'store': 'Humble Store',
        'new_price':  74.75, 'target_price': 149.50, 'game_id': 5,
    },
]


def _is_qa_user():
    """True se o usuário logado tem o email QA."""
    user_id = session.get('user_id')
    if not user_id:
        return False
    user = User.query.get(user_id)
    return bool(user and user.email == QA_EMAIL)


@app.context_processor
def _inject_qa_flag():
    """Disponibiliza is_qa nos templates."""
    return {'is_qa': _is_qa_user(), 'QA_EMAIL': QA_EMAIL}


def _qa_send_scenario(user, scenario):
    """Envia 1 email de cenário para 1 usuário. Retorna True se enviou."""
    from email_service import send_alert_email
    base = request.host_url.rstrip('/') if request else 'http://localhost:5000'
    return send_alert_email(
        to=user.email,
        user_name=user.name,
        game_title=scenario['game_title'],
        store=scenario['store'],
        new_price=scenario['new_price'],
        target_price=scenario['target_price'],
        game_url=f"{base}/game/{scenario['game_id']}",
    )


@app.route('/qa/test-one-scenario-each-user', methods=['POST'])
@login_required
def qa_test_one_scenario():
    """[QA] Envia 1 cenário (rotacionado) para CADA usuário cadastrado."""
    if not _is_qa_user():
        flash('Acesso negado. Esta rota é exclusiva da conta QA.', 'error')
        return redirect(url_for('alerts_list'))

    users = User.query.filter(User.email != QA_EMAIL).all()
    sent = 0
    failed = 0
    for i, u in enumerate(users):
        scenario = QA_TEST_SCENARIOS[i % len(QA_TEST_SCENARIOS)]
        if _qa_send_scenario(u, scenario):
            sent += 1
        else:
            failed += 1

    flash(
        f'[QA] {sent} email(s) enviados, {failed} falharam '
        f'({len(users)} usuário(s) no total).',
        'success' if failed == 0 else 'info',
    )
    return redirect(url_for('alerts_list'))


@app.route('/qa/test-all-scenarios-each-user', methods=['POST'])
@login_required
def qa_test_all_scenarios():
    """[QA] Envia TODOS os 5 cenários para CADA usuário cadastrado."""
    if not _is_qa_user():
        flash('Acesso negado. Esta rota é exclusiva da conta QA.', 'error')
        return redirect(url_for('alerts_list'))

    users = User.query.filter(User.email != QA_EMAIL).all()
    sent = 0
    failed = 0
    for u in users:
        for scenario in QA_TEST_SCENARIOS:
            if _qa_send_scenario(u, scenario):
                sent += 1
            else:
                failed += 1

    total_expected = len(users) * len(QA_TEST_SCENARIOS)
    flash(
        f'[QA] {sent}/{total_expected} email(s) enviados, {failed} falharam '
        f'({len(users)} usuário(s) × {len(QA_TEST_SCENARIOS)} cenários).',
        'success' if failed == 0 else 'info',
    )
    return redirect(url_for('alerts_list'))


# =============================================================================
# Execução do servidor de desenvolvimento
# =============================================================================

# =============================================================================
# Busca ao vivo de jogos (Extra Sprint 2 — fora do Trello, valor agregado)
# =============================================================================
# Quando o usuário não encontra o jogo no catálogo local, esta rota consulta
# a Steam Store Search API (pública, sem chave) e mostra resultados ao vivo.
# Se o usuário gostar de algum, pode "Adicionar ao catálogo" — o jogo é
# inserido no banco e os preços buscados pela primeira vez.
import requests as _http_requests  # alias pra não conflitar com Flask `request`


@app.route('/search')
@login_required
def search():
    """Busca jogos no catálogo local + Steam Store Search (live)."""
    query = (request.args.get('q') or '').strip()
    user_id = session.get('user_id')
    user = User.query.get(user_id)

    local_results = []
    live_results = []

    if query:
        # 1) Busca no catálogo local (case-insensitive, substring)
        local_results = Game.query.filter(Game.title.ilike(f'%{query}%')).all()

        # 2) Sempre tenta complementar com busca ao vivo na Steam (até 8 sugestões),
        #    excluindo jogos que já existem no catálogo
        try:
            resp = _http_requests.get(
                'https://store.steampowered.com/api/storesearch',
                params={'cc': 'br', 'l': 'brazilian', 'term': query},
                timeout=8,
            )
            data = resp.json() if resp.status_code == 200 else {}
            existing_steam_ids = {
                g.steam_app_id
                for g in Game.query.filter(Game.steam_app_id.isnot(None)).all()
            }
            for item in (data.get('items') or [])[:8]:
                steam_id = item.get('id')
                if not steam_id or steam_id in existing_steam_ids:
                    continue
                price_info = item.get('price') or {}
                price_brl = (price_info.get('final') or 0) / 100 if price_info else None
                live_results.append({
                    'steam_id': steam_id,
                    'name': item.get('name', ''),
                    'image': item.get('tiny_image') or item.get('large_capsule_image') or '',
                    'price': price_brl if price_brl else None,
                })
        except Exception as exc:
            logging.getLogger(__name__).warning(f'Busca live falhou: {exc}')

    return render_template(
        'search.html',
        user=user,
        query=query,
        local_results=local_results,
        live_results=live_results,
    )


@app.route('/search/add', methods=['POST'])
@login_required
def search_add_to_catalog():
    """Adiciona um jogo da busca ao vivo ao catálogo local + busca preço inicial."""
    try:
        steam_id = int(request.form.get('steam_id', '0'))
    except (ValueError, TypeError):
        flash('ID inválido.', 'error')
        return redirect(url_for('search'))

    name = (request.form.get('name') or '').strip()
    if not steam_id or not name:
        flash('Dados incompletos para adicionar.', 'error')

    # find_or_create_game checa duplicação por steam_app_id E título normalizado
    new_game, created = find_or_create_game(
        title=name,
        steam_app_id=steam_id,
    )
    if not created:
        flash(f'{new_game.title} já estava no catálogo.', 'info')
        db.session.rollback()  # limpa o que find_or_create_game não tenha addado
        return redirect(url_for('game_detail', game_id=new_game.id))

    db.session.flush()

    # Busca preço em TODAS as lojas (Steam direto + ITAD para Epic/GOG/Nuuvem/Humble/Fanatical)
    # E cria StoreLink correspondente pra cada loja com preço.
    all_prices = {}
    try:
        all_prices = fetch_all_prices_for_game(name, steam_app_id=steam_id)
    except Exception as exc:
        logging.getLogger(__name__).warning(f'Falha ao buscar preços multi-loja: {exc}')

    now = datetime.now(timezone.utc)
    for store_name, price_val in all_prices.items():
        db.session.add(Price(
            game_id=new_game.id,
            store=store_name,
            price=price_val,
            currency='BRL',
            date_recorded=now,
        ))
        ensure_storelink(db.session, new_game, store_name)

    # Garante StoreLink Steam mesmo se ITAD/Steam não retornaram preço
    ensure_storelink(db.session, new_game, 'Steam')

    db.session.commit()

    n_stores = len(all_prices)
    extra = f' (preços em {n_stores} loja{"s" if n_stores != 1 else ""})' if n_stores else ''
    flash(f'{name} adicionado ao catálogo{extra}!', 'success')
    return redirect(url_for('game_detail', game_id=new_game.id))


# =============================================================================
# QA Panel — Controles de operação (só para conta QA)
# =============================================================================
# Página /qa com botões pra disparar updates, processar alertas, e fazer
# resets controlados. Toda operação destrutiva faz BACKUP do ideal.db antes.

import shutil as _shutil


def _qa_backup_db(suffix: str = 'qa-action') -> str | None:
    """Copia ideal.db pra ideal.db.backup-{suffix}-{timestamp}. Retorna o path."""
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    if not os.path.exists(db_path):
        return None
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = f'{db_path}.backup-{suffix}-{ts}'
    _shutil.copy2(db_path, backup_path)
    return backup_path


@app.route('/qa')
@login_required
def qa_panel():
    """Painel de operação — só visível pra conta QA."""
    if not _is_qa_user():
        flash('Acesso negado. Esta página é exclusiva da conta QA.', 'error')
        return redirect(url_for('index'))

    user_id = session.get('user_id')
    user = User.query.get(user_id)

    # Stats do banco
    from price_fetcher import ITAD_API_KEY
    stats = {
        'users': User.query.count(),
        'games': Game.query.count(),
        'prices': Price.query.count(),
        'alerts': Alert.query.count(),
        'alerts_active': Alert.query.filter_by(active=True).count(),
        'nav_logs': NavigationLog.query.count(),
        'store_links': StoreLink.query.count(),
        'itad_configured': bool(ITAD_API_KEY),
        'itad_key_preview': (ITAD_API_KEY[:4] + '...' + ITAD_API_KEY[-4:]) if ITAD_API_KEY else '(não configurada)',
        'smtp_configured': bool(os.environ.get('SMTP_USER') and os.environ.get('SMTP_PASSWORD')),
        'smtp_user': os.environ.get('SMTP_USER', '(não configurado)'),
    }

    return render_template('qa_panel.html', user=user, stats=stats)


# --- Ações de UPDATE (sem perda de dados) ---

@app.route('/qa/refresh-prices', methods=['POST'])
@login_required
def qa_refresh_prices():
    """Força update_all_prices() agora (síncrono — pode demorar 30-60s)."""
    if not _is_qa_user():
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    try:
        summary = update_all_prices(app)
        total = sum(summary.values())
        flash(f'[QA] {total} preço(s) atualizados em {len(summary)} jogo(s).', 'success')
    except Exception as e:
        flash(f'[QA] Erro ao atualizar: {e}', 'error')
    return redirect(url_for('qa_panel'))


@app.route('/qa/process-alerts', methods=['POST'])
@login_required
def qa_process_alerts():
    """Roda process_alerts() agora — checa todos alertas vs preços atuais."""
    if not _is_qa_user():
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    try:
        s = process_alerts(app)
        flash(
            f'[QA] checked={s["checked"]}, triggered={s["triggered"]}, '
            f'sent={s["sent"]}, skipped_cooldown={s["skipped_cooldown"]}, '
            f'failed={s["failed_send"]}.',
            'success' if s['sent'] >= 0 else 'info',
        )
    except Exception as e:
        flash(f'[QA] Erro: {e}', 'error')
    return redirect(url_for('qa_panel'))


@app.route('/qa/test-itad', methods=['POST'])
@login_required
def qa_test_itad():
    """Tenta resolver UUID de 'Elden Ring' na ITAD. Mostra resultado no flash."""
    if not _is_qa_user():
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))

    from price_fetcher import _itad_lookup_game_ids, fetch_itad_prices_bulk, ITAD_API_KEY
    if not ITAD_API_KEY:
        flash('[QA] ITAD_API_KEY não está configurada no .env.', 'error')
        return redirect(url_for('qa_panel'))

    try:
        ids = _itad_lookup_game_ids(['Elden Ring'])
        if not ids:
            flash('[QA] ITAD respondeu mas não encontrou "Elden Ring". Chave pode estar inválida.', 'error')
            return redirect(url_for('qa_panel'))
        uuid = list(ids.values())[0]
        prices = fetch_itad_prices_bulk([uuid])
        n_stores = len(prices.get(uuid, {})) if prices else 0
        flash(f'[QA] ITAD OK ✓ — Elden Ring resolvido, {n_stores} loja(s) com preço.', 'success')
    except Exception as e:
        flash(f'[QA] Erro ao testar ITAD: {e}', 'error')
    return redirect(url_for('qa_panel'))


# --- Ações de RESET (destrutivas — fazem backup automático antes) ---

@app.route('/qa/reset-cooldowns', methods=['POST'])
@login_required
def qa_reset_cooldowns():
    """Limpa last_triggered_at de todos os alertas (permite re-disparo imediato)."""
    if not _is_qa_user():
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    n = Alert.query.filter(Alert.last_triggered_at.isnot(None)).count()
    Alert.query.update({
        Alert.last_triggered_at: None,
        Alert.last_triggered_price: None,
        Alert.last_triggered_store: None,
    })
    db.session.commit()
    flash(f'[QA] {n} cooldown(s) resetados. Próximo process_alerts pode re-disparar.', 'success')
    return redirect(url_for('qa_panel'))


@app.route('/qa/clear-prices', methods=['POST'])
@login_required
def qa_clear_prices():
    """DESTRUTIVO — apaga TODA a tabela prices. Faz backup antes."""
    if not _is_qa_user():
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    backup = _qa_backup_db('clear-prices')
    n = Price.query.count()
    Price.query.delete()
    db.session.commit()
    flash(f'[QA] {n} preço(s) apagado(s). Backup: {os.path.basename(backup) if backup else "(falhou)"}.', 'info')
    return redirect(url_for('qa_panel'))


@app.route('/qa/clear-alerts', methods=['POST'])
@login_required
def qa_clear_alerts():
    """DESTRUTIVO — apaga TODOS os alertas. Faz backup antes."""
    if not _is_qa_user():
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    backup = _qa_backup_db('clear-alerts')
    n = Alert.query.count()
    Alert.query.delete()
    db.session.commit()
    flash(f'[QA] {n} alerta(s) apagado(s). Backup: {os.path.basename(backup) if backup else "(falhou)"}.', 'info')
    return redirect(url_for('qa_panel'))


@app.route('/qa/clear-nav-logs', methods=['POST'])
@login_required
def qa_clear_nav_logs():
    """DESTRUTIVO — apaga histórico de navegação. Faz backup antes."""
    if not _is_qa_user():
        flash('Acesso negado.', 'error')
        return redirect(url_for('index'))
    backup = _qa_backup_db('clear-nav-logs')
    n = NavigationLog.query.count()
    NavigationLog.query.delete()
    flash(f'[QA] {n} log(s) apagado(s). Backup: {os.path.basename(backup) if backup else "(falhou)"}.', 'info')
    return redirect(url_for('qa_panel'))


# =============================================================================
# Execução do servidor de desenvolvimento
# =============================================================================
if __name__ == '__main__':
    app.run(debug=True)
