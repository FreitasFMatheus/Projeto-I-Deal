# SETUP - Ambiente de Desenvolvimento (I-Deal)

Guia rapido para colocar o projeto rodando no Windows + VS Code.

---

## 1. Pre-requisitos

- **Python 3.10+** (testado com 3.10 e 3.12) - <https://www.python.org/downloads/>
  - Na instalacao, marque **"Add Python to PATH"**.
- **Git** - <https://git-scm.com/download/win>
- **VS Code** - <https://code.visualstudio.com/>
- **MongoDB Community** *(opcional - so necessario para a rota `/api/prices/mongo`)*
  - <https://www.mongodb.com/try/download/community>

Confirme no PowerShell:

```powershell
python --version
git --version
```

---

## 2. Abrir no VS Code

Abra **a pasta `I-Deal_Atualizado_3.0`** como workspace (nao a pasta-mae). Isso garante que `.vscode/`, `venv/` e `app.py` fiquem na raiz do workspace.

```powershell
cd "C:\Users\Matheus Freitas\Downloads\Projeto-I-Deal-main\Projeto-I-Deal-main\I-Deal_Atualizado_3.0"
code .
```

Na primeira abertura o VS Code vai sugerir as extensoes recomendadas (Python, Pylance, Jinja, SQLite Viewer, Thunder Client) - pode aceitar todas.

---

## 3. Setup automatico (recomendado)

No terminal integrado do VS Code (Ctrl + crase), rode UM dos dois:

**PowerShell:**
```powershell
.\setup.ps1
```

**CMD:**
```cmd
setup.bat
```

O script:
1. confere o Python,
2. cria o `venv`,
3. ativa o ambiente,
4. instala tudo do `requirements.txt`,
5. copia `.env.example` -> `.env`.

> Se aparecer **"running scripts is disabled"** no PowerShell, rode UMA vez:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

---

## 4. Setup manual (se preferir)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

---

## 5. Configurar o `.env`

Abra `.env` no VS Code e preencha (todos sao opcionais para subir o app):

| Variavel | O que e | Observacao |
|---|---|---|
| `ITAD_API_KEY` | Chave da IsThereAnyDeal | Sem ela o `price_fetcher` ignora a chamada externa - o app sobe normal com dados do SQLite/seed. Pegue em <https://isthereanydeal.com/apps/> |
| `MONGODB_URI` | URI do MongoDB | Padrao: `mongodb://localhost:27017/` |
| `MONGODB_DB` | Nome do banco Mongo | Padrao: `ideal_db` |
| `FLASK_SECRET_KEY` | Chave de sessao do Flask | Troque em producao |

---

## 6. Rodar a aplicacao

Com o venv ativo (deve aparecer `(venv)` no prompt):

```powershell
python app.py
```

Acesse <http://127.0.0.1:5000>.

### Modo Debug no VS Code (F5)
O `.vscode/launch.json` ja vem com duas configs prontas:
- **Python: Flask (app.py)** - executa direto o `app.py` (com o scheduler e o seed).
- **Python: Flask (flask run)** - usa o servidor de desenvolvimento do Flask, sem reload, ideal para debug com breakpoints.

---

## 7. Estrutura dos arquivos criados pelo setup

```
I-Deal_Atualizado_3.0/
|-- .vscode/
|   |-- settings.json      # Aponta o interpretador para .\venv\Scripts\python.exe
|   |-- launch.json        # Configuracoes de debug (F5)
|   `-- extensions.json    # Extensoes recomendadas
|-- venv/                  # Ambiente virtual (NAO versionado)
|-- .env                   # Suas variaveis (NAO versionado)
|-- .env.example           # Modelo do .env
|-- .gitignore             # Regras Python/Flask/VS Code
|-- setup.ps1              # Setup PowerShell
|-- setup.bat              # Setup CMD
|-- SETUP.md               # Este arquivo
|-- app.py                 # Aplicacao Flask
|-- models.py              # SQLAlchemy models
|-- price_fetcher.py       # Integracao ITAD + scheduler
|-- requirements.txt
|-- ideal.db               # SQLite (criado/seedado na primeira execucao)
|-- openapi.json
|-- static/
`-- templates/
```

---

## 8. Rotas da aplicacao (resumo)

| Rota | Descricao |
|---|---|
| `/` | Catalogo (redireciona para `/login` se nao autenticado) |
| `/login` | Tela de login |
| `/register` | Cadastro |
| `/logout` | Encerra sessao |
| `/game/<id>` | Detalhes do jogo + links das lojas |
| `/redirect/<link_id>` | Registra clique e redireciona pra loja |
| `/api/prices/steam` | API REST sobre o SQLite (filtros: `game_id`, `store`, `min_price`, `max_price`) |
| `/api/prices/mongo` | API REST sobre o MongoDB (filtros: `game_title`, `store`, `max_price`) |

Para testar a API direto do VS Code, use a extensao **Thunder Client** (recomendada).

---

## 9. Troubleshooting

**`python` nao e reconhecido** - reinstale o Python marcando "Add to PATH" ou tente `py -3` no lugar de `python`.

**`Activate.ps1` bloqueado** - execute `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` uma vez.

**Pylance nao ve as libs** - `Ctrl+Shift+P` -> "Python: Select Interpreter" -> escolha `.\venv\Scripts\python.exe`.

**`/api/prices/mongo` retorna erro** - o MongoDB local nao esta rodando. Esta rota e opcional; o resto do app funciona sem ela.

**Quero zerar o banco e ressemear** - feche o app e apague `ideal.db`. Na proxima execucao o `app.py` recria + seed.

---

## 10. Validacao rapida

Depois do setup, com o app rodando:

```powershell
# Em outro terminal
curl http://127.0.0.1:5000/api/prices/steam
```

Deve retornar JSON com a lista de precos do seed inicial.
