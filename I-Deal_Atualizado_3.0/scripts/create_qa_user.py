"""
create_qa_user.py
==================
Cria a conta QA no banco. Idempotente: se a conta já existe,
atualiza apenas a senha (não duplica usuário).

A conta QA tem visibilidade do "Painel QA" na tela de alertas,
de onde dispara emails de cenário para todos os outros usuários.

USO:
    cd I-Deal_Atualizado_3.0
    python scripts/create_qa_user.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('PRICE_REFRESH_MINUTES', '99999')

# Bloqueia chamada externa do scheduler durante o import
import price_fetcher
price_fetcher.update_all_prices = lambda app: {}

from werkzeug.security import generate_password_hash  # noqa: E402
from app import app, QA_EMAIL  # noqa: E402
from models import db, User  # noqa: E402

QA_NAME = 'QA Tester'
QA_PASSWORD = 'qatest1234'


def main():
    print('=' * 60)
    print(' I-Deal — Criar/atualizar conta QA')
    print('=' * 60)
    print(f' Email:    {QA_EMAIL}')
    print(f' Senha:    {QA_PASSWORD}')
    print()

    with app.app_context():
        existing = User.query.filter_by(email=QA_EMAIL).first()
        if existing:
            existing.name = QA_NAME
            existing.password_hash = generate_password_hash(QA_PASSWORD)
            db.session.commit()
            print(' [OK] Usuário QA já existia — senha atualizada.')
        else:
            qa = User(
                name=QA_NAME,
                email=QA_EMAIL,
                password_hash=generate_password_hash(QA_PASSWORD),
            )
            db.session.add(qa)
            db.session.commit()
            print(' [OK] Usuário QA criado.')

        total = User.query.count()
        print(f' Total de usuários no banco agora: {total}')

    print()
    print(' Pronto. Faça login com:')
    print(f'   email:  {QA_EMAIL}')
    print(f'   senha:  {QA_PASSWORD}')
    print()
    print(' O Painel QA aparece automaticamente em /alerts quando logar.')


if __name__ == '__main__':
    main()
