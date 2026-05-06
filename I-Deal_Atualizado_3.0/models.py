# =============================================================================
# models.py — Definição de todas as tabelas do banco de dados (SQLAlchemy ORM)
# =============================================================================
# Este arquivo centraliza os "models" do projeto I-Deal. Cada classe Python
# representa uma tabela no banco de dados SQLite (ideal.db).
#
# Tabelas existentes (Sprint 1 — feitas por IR):
#   - User   (1.3.1) : cadastro de usuários
#   - Game   (1.3.2) : catálogo de jogos
#
# Tabelas adicionadas:
#   - Price         (1.3.3) : registros de preço por jogo/loja  [IR — faltante]
#   - StoreLink     (2.3.1) : links das lojas para cada jogo    [MF]
#   - NavigationLog (2.3.2) : histórico de navegação do usuário [MF]
#   - Alert         (US03)  : alertas de preço por usuário/jogo [MF — Sprint 2]
# =============================================================================

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

# Instância global do SQLAlchemy — será inicializada no app.py com db.init_app(app)
db = SQLAlchemy()


# =============================================================================
# 1.3.1 — Tabela de Usuários (já existia — mantida sem alterações)
# =============================================================================
# Armazena os dados de cada usuário cadastrado no sistema.
# O campo password_hash guarda o hash da senha (nunca a senha em texto puro).
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)              # Chave primária auto-incremento
    name = db.Column(db.String(100), nullable=False)           # Nome completo do usuário
    email = db.Column(db.String(120), unique=True, nullable=False)  # E-mail único (usado no login)
    password_hash = db.Column(db.String(256), nullable=False)  # Hash da senha (Werkzeug scrypt)

    # Relacionamento: um usuário pode ter vários registros de navegação
    navigation_logs = db.relationship('NavigationLog', backref='user', lazy=True)
    # Relacionamento: um usuário pode ter vários alertas de preço (US03)
    alerts = db.relationship('Alert', backref='user', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.name}>'


# =============================================================================
# 1.3.2 — Tabela de Jogos (já existia — mantida sem alterações estruturais)
# =============================================================================
# Armazena os jogos do catálogo. Cada jogo tem um preço padrão de referência
# e uma imagem de capa vinda da Steam.
class Game(db.Model):
    __tablename__ = 'games'

    id = db.Column(db.Integer, primary_key=True)               # Chave primária
    title = db.Column(db.String(150), nullable=False)           # Nome do jogo (ex: "Elden Ring")
    default_price = db.Column(db.Float, nullable=False)         # Preço padrão de referência (R$)
    image_url = db.Column(db.String(300), nullable=True)        # URL da imagem de capa
    steam_app_id = db.Column(db.Integer, nullable=True)         # ID do app na Steam (ex: 1245620)
    itad_id = db.Column(db.String(100), nullable=True)          # Slug do jogo na IsThereAnyDeal

    # Relacionamentos: um jogo pode ter vários preços, links e alertas
    prices = db.relationship('Price', backref='game', lazy=True)
    store_links = db.relationship('StoreLink', backref='game', lazy=True)
    alerts = db.relationship('Alert', backref='game', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Game {self.title}>'


# =============================================================================
# 1.3.3 — Tabela de Preços (NOVA — estava faltando no código original)
# =============================================================================
# Registra o preço de um jogo em uma loja específica numa determinada data.
# Essa tabela é fundamental para:
#   - Comparar preços entre lojas (funcionalidade core do I-Deal)
#   - Gerar o histórico de preços ao longo do tempo
#   - Identificar o "menor preço de todos os tempos"
#
# Exemplo de registro:
#   game_id=1 (Elden Ring), store="Steam", price=199.90, date=2025-03-13
class Price(db.Model):
    __tablename__ = 'prices'

    id = db.Column(db.Integer, primary_key=True)               # Chave primária
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)  # FK para games
    store = db.Column(db.String(100), nullable=False)           # Nome da loja (ex: "Steam", "Epic")
    price = db.Column(db.Float, nullable=False)                 # Preço atual na loja (R$)
    currency = db.Column(db.String(10), default='BRL')          # Moeda (padrão: Real)
    date_recorded = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)              # Data/hora do registro (UTC)
    )

    def __repr__(self):
        return f'<Price {self.store}: R${self.price:.2f}>'


# =============================================================================
# 2.3.1 — Links das Lojas para cada Jogo (NOVA — tarefa MF)
# =============================================================================
# Armazena a URL de compra de cada jogo em cada loja.
# Quando o usuário clica em "Comprar" num card de preço, ele é redirecionado
# para a URL da loja correspondente.
#
# Exemplo de registro:
#   game_id=1, store="Steam", url="https://store.steampowered.com/app/1245620"
class StoreLink(db.Model):
    __tablename__ = 'store_links'

    id = db.Column(db.Integer, primary_key=True)               # Chave primária
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)  # FK para games
    store = db.Column(db.String(100), nullable=False)           # Nome da loja
    url = db.Column(db.String(500), nullable=False)             # URL de compra na loja

    def __repr__(self):
        return f'<StoreLink {self.store}>'


# =============================================================================
# 2.3.2 — Histórico de Navegação do Usuário (NOVA — tarefa MF)
# =============================================================================
# Toda vez que um usuário clica em um link de loja (redirecionamento externo),
# registramos aqui. Isso permite:
#   - Saber quais jogos são mais populares
#   - Analisar quais lojas são mais acessadas
#   - Oferecer recomendações personalizadas no futuro
#
# Exemplo de registro:
#   user_id=1, game_id=1, store="Steam", timestamp=2025-03-20 14:30:00
class NavigationLog(db.Model):
    __tablename__ = 'navigation_logs'

    id = db.Column(db.Integer, primary_key=True)               # Chave primária
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)   # FK para users (None se não logado)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)  # FK para games
    store = db.Column(db.String(100), nullable=False)           # Loja que o usuário clicou
    url_visited = db.Column(db.String(500), nullable=False)     # URL completa visitada
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)              # Data/hora do clique (UTC)
    )

    def __repr__(self):
        return f'<NavigationLog user={self.user_id} store={self.store}>'


# =============================================================================
# US03 — Alerta de Preço (NOVA — Sprint 2)
# =============================================================================
# O usuário cadastra um alerta dizendo: "me avise quando o jogo X estiver
# por R$ Y ou menos". Quando o scheduler atualiza os preços, todos os alertas
# ativos são checados — se algum preço novo bater o alvo, dispara um email
# para o usuário.
class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    target_price = db.Column(db.Float, nullable=False)
    store_filter = db.Column(db.String(100), nullable=True)   # None = qualquer loja
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )
    last_triggered_at = db.Column(db.DateTime, nullable=True)
    last_triggered_price = db.Column(db.Float, nullable=True)
    last_triggered_store = db.Column(db.String(100), nullable=True)
    # 4.3.1+ — Filtro adicional: dispara só se o desconto vs Game.default_price
    # for >= min_discount_pct (em %). None = sem restrição de desconto.
    min_discount_pct = db.Column(db.Float, nullable=True)

    def __repr__(self):
        return f'<Alert user={self.user_id} game={self.game_id} target=R${self.target_price:.2f}>'
