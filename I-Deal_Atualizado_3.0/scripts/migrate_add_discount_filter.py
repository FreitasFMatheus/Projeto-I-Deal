"""
migrate_add_discount_filter.py
================================
Adiciona a coluna `min_discount_pct` na tabela `alerts` SEM apagar dados.

Se a coluna já existir, não faz nada (idempotente).
Faz backup automático do ideal.db antes da operação.

USO:
    cd I-Deal_Atualizado_3.0
    python scripts/migrate_add_discount_filter.py
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
DB_PATH = os.path.join(PROJECT_ROOT, 'ideal.db')


def main():
    print('=' * 60)
    print(' I-Deal — Migração: filtro de desconto em alertas')
    print('=' * 60)
    print(f' Banco: {DB_PATH}')

    if not os.path.exists(DB_PATH):
        print(' ERRO: ideal.db não encontrado.')
        sys.exit(1)

    # Backup
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = f'{DB_PATH}.backup-add-discount-{ts}'
    shutil.copy2(DB_PATH, backup)
    print(f' [OK] Backup: {os.path.basename(backup)}')

    con = sqlite3.connect(DB_PATH)
    try:
        # Checa se coluna já existe
        cols = [r[1] for r in con.execute("PRAGMA table_info(alerts)").fetchall()]
        if 'min_discount_pct' in cols:
            print(' Coluna `min_discount_pct` já existe — nada a fazer.')
            return

        # Conta alertas antes
        n_before = con.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]
        print(f' Alertas antes: {n_before}')

        # ALTER TABLE
        con.execute('ALTER TABLE alerts ADD COLUMN min_discount_pct REAL')
        con.commit()
        print(' [OK] Coluna `min_discount_pct REAL` adicionada.')

        n_after = con.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]
        print(f' Alertas depois: {n_after} (deve ser igual a antes)')

        # Confirma
        cols_after = [r[1] for r in con.execute('PRAGMA table_info(alerts)').fetchall()]
        print(f' Colunas finais: {cols_after}')

        if n_before != n_after:
            print(f' [ALERTA] Contagem mudou! ({n_before} → {n_after})')
        else:
            print(' ✓ Dados existentes preservados.')

    finally:
        con.close()

    print('=' * 60)
    print(' Migração concluída.')


if __name__ == '__main__':
    main()
