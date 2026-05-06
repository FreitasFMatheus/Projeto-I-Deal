"""
migrate_add_alerts.py
======================
Adiciona a tabela `alerts` ao banco de dados existente, sem tocar em
nenhuma outra tabela ou dado.

COMO É SEGURO:
  - `db.create_all()` do SQLAlchemy é IDEMPOTENTE: só cria tabelas que NÃO
    existem. Tabelas existentes (users, games, prices, store_links,
    navigation_logs) são totalmente ignoradas.
  - Antes de qualquer coisa, lê o estado atual do ideal.db direto via
    sqlite3 (sem importar o app, pra captura fiel do estado anterior).
  - Mostra antes/depois e confirma que NENHUMA linha foi alterada nas
    tabelas existentes.
  - NUNCA usa DROP, DELETE ou UPDATE.

USO:
    cd I-Deal_Atualizado_3.0
    python scripts/migrate_add_alerts.py

Faça backup do ideal.db antes (você já fez).
"""

import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
DB_PATH = os.path.join(PROJECT_ROOT, 'ideal.db')


def list_tables_and_counts(db_path: str):
    """Retorna [(table_name, row_count), ...] usando sqlite3 puro (sem importar app)."""
    if not os.path.exists(db_path):
        return []
    con = sqlite3.connect(db_path)
    try:
        tables = [
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
        ]
        result = []
        for t in tables:
            try:
                n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except Exception:
                n = -1
            result.append((t, n))
        return result
    finally:
        con.close()


def main():
    print('=' * 70)
    print(' I-Deal — Migração: adicionar tabela alerts (US03)')
    print('=' * 70)
    print(f' Banco: {DB_PATH}')
    print()

    if not os.path.exists(DB_PATH):
        print(' ERRO: ideal.db não encontrado.')
        print(' Rode `python app.py` uma vez antes para criar o banco com seed.')
        sys.exit(1)

    # 1) Snapshot ANTES — usa sqlite3 puro pra não disparar o create_all do app
    print(' >>> Estado ANTES da migração <<<')
    before = list_tables_and_counts(DB_PATH)
    if not before:
        print('   (banco vazio)')
    for t, n in before:
        print(f'   {t:25s} {n:>6} linhas')
    print()

    # 2) Importa o app — isso já dispara db.create_all() internamente.
    #    db.create_all() é idempotente: só cria o que falta.
    os.environ.setdefault('PRICE_REFRESH_MINUTES', '99999')
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    print(' Aplicando migração (db.create_all)...')
    from app import app  # noqa: E402  (importação dispara create_all)
    from models import db  # noqa: E402

    # 3) Garantia extra: chama explicitamente create_all dentro do app_context
    with app.app_context():
        db.create_all()
    print(' OK')
    print()

    # 4) Snapshot DEPOIS
    print(' >>> Estado DEPOIS da migração <<<')
    after = list_tables_and_counts(DB_PATH)
    before_names = {t for t, _ in before}
    for t, n in after:
        marker = ' ← NOVA' if t not in before_names else ''
        print(f'   {t:25s} {n:>6} linhas{marker}')
    print()

    # 5) Diff e veredito
    new_tables = [t for t, _ in after if t not in before_names]
    removed = [t for t, _ in before if t not in [a[0] for a in after]]
    before_d = dict(before)
    changed_counts = [
        (t, before_d[t], n)
        for t, n in after
        if t in before_d and before_d[t] != n
    ]

    print('=' * 70)
    print(' Resumo')
    print('=' * 70)
    if new_tables:
        print(f' ✓ Tabelas adicionadas: {", ".join(new_tables)}')
    else:
        print(' Nenhuma tabela nova precisava ser adicionada (todas já existiam).')

    if removed:
        print(f' [!!] ALERTA: tabelas REMOVIDAS detectadas: {", ".join(removed)}')

    if changed_counts:
        print(' [!!] ALERTA: contagem de linhas mudou:')
        for t, b, a in changed_counts:
            print(f'   {t}: {b} → {a}')
    else:
        print(' ✓ Contagem de linhas das tabelas existentes: INALTERADA')

    print('=' * 70)
    print(' Migração concluída com sucesso.')
    print(' Próximo passo: rodar `python app.py` e testar /alerts.')


if __name__ == '__main__':
    main()
