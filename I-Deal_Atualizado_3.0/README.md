# I-Deal 🎮

O **I-Deal** é uma plataforma web agregadora de preços ultraespecializado, desenvolvido para solucionar a fragmentação do mercado de jogos digitais. O sistema centraliza ofertas de diversas lojas em uma única interface, permitindo que o gamer tome decisões de compra baseadas em dados reais, histórico de preços e alertas automatizados.

---

## 👥 Membros do Grupo
1. **Gustavo Bertoluzzi Cardoso:** 22.123.016-2
2. **Isabella Vieira Silva Rossetto:** 22.222.036-0
3. **Henrique Hodel Babler:** 22.125.084-8
4. **Matheus Ferreira de Freitas:** 22.125.085-5

---

## 🎭 Atribuição de Papéis

### Papéis Parte 1:
* **Product Owner (PO):** Isabella Vieira Silva Rossetto
* **Scrum Master (SM):** Matheus Ferreira de Freitas
* **Developers (DEV):** Gustavo Bertoluzzi Cardoso e Henrique Hodel Babler

### Papéis Parte 2:
* **Product Owner (PO):** Matheus Ferreira de Freitas
* **Scrum Master (SM):** Isabella Vieira Silva Rossetto
* **Developers (DEV):** Gustavo Bertoluzzi Cardoso e Henrique Hodel Babler

---

## 📝 Descrição do Projeto

O projeto nasce da observação de uma dor comum entre consumidores de mídia digital: a **fadiga de decisão** causada pela dispersão de preços. Atualmente, para garantir o melhor valor em um jogo, o usuário precisa navegar manualmente por diversas plataformas (Steam, Epic Games, PS Store, Xbox, Nuuvem), muitas vezes perdendo promoções relâmpago ou caindo em "falsas promoções" (onde o preço é inflado antes de um desconto).

O **I-Deal** atua como uma camada de inteligência sobre o e-commerce de games, utilizando algoritmos para agrupar anúncios de diferentes lojas sob o mesmo título, oferecendo transparência total através de históricos de variação de preço.

---

## 🛠️ Principais Funcionalidades (MVP)
* **Busca Unificada:** Comparativo de múltiplas lojas em uma única tela.
* **Histórico de Preços:** Tabela com variação de preços ao longo do tempo.
* **Redirecionamento para Lojas:** Links diretos de compra com rastreamento de navegação.
* **API de Consulta de Preços:** Endpoints REST com dados do SQLite e MongoDB.
* **Alertas de Preço:** Notificações customizadas para o usuário *(planejado)*.
* **Filtros por Plataforma:** Segmentação por PC, PlayStation ou Xbox *(planejado)*.

---

## 🧰 Tecnologias Utilizadas

* **Backend:** Python, Flask, Flask-SQLAlchemy, Werkzeug
* **Banco Relacional:** SQLite
* **Banco NoSQL:** MongoDB (PyMongo)
* **Frontend:** HTML5, CSS3 (Jinja2 templates), design glassmorphism responsivo
* **Controle de Versão:** Git

---

## ⚙️ Instalação e Execução

```bash
# Clonar o repositório
git clone https://github.com/FreitasFMatheus/Projeto-I-Deal.git
cd Projeto-I-Deal/Projeto-I-Deal-main

# Criar ambiente virtual e instalar dependências
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Iniciar o MongoDB (necessário para a rota /api/prices/mongo)
# Consulte a documentação do seu SO para iniciar o serviço do MongoDB

# Rodar a aplicação
python app.py
```

Acesse: **http://127.0.0.1:5000**

---

## 🌐 Rotas da Aplicação

| Rota | Descrição |
|---|---|
| `/` | Página inicial — catálogo com menor preço por jogo |
| `/login` | Autenticação de usuário |
| `/register` | Cadastro de novo usuário |
| `/logout` | Encerra a sessão |
| `/game/<id>` | Detalhes do jogo com preços por loja e links de compra |
| `/redirect/<link_id>` | Redireciona para a loja e registra navegação |
| `/api/prices/steam` | API REST — preços via SQLite (`?game_id`, `?store`, `?min_price`, `?max_price`) |
| `/api/prices/mongo` | API REST — preços via MongoDB (`?game_title`, `?store`, `?max_price`) |
