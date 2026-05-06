# =============================================================================
# email_service.py — Envio de emails de alerta (US03 — Sprint 2)
# =============================================================================
# Módulo isolado responsável por enviar emails via SMTP.
# Lê toda a configuração de variáveis de ambiente — NUNCA hardcoded.
#
# Uso:
#   from email_service import send_alert_email
#   send_alert_email(
#       to='usuario@example.com',
#       user_name='João',
#       game_title='Elden Ring',
#       store='Steam',
#       new_price=149.90,
#       target_price=150.00,
#       game_url='http://localhost:5000/game/1',
#   )
# =============================================================================

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

# Carrega .env se python-dotenv estiver instalado (já está em requirements.txt)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _smtp_config() -> dict:
    """Lê configuração SMTP das variáveis de ambiente."""
    return {
        'host':      os.environ.get('SMTP_HOST', 'smtp.gmail.com'),
        'port':      int(os.environ.get('SMTP_PORT', '587')),
        'user':      os.environ.get('SMTP_USER', ''),
        'password':  os.environ.get('SMTP_PASSWORD', '').replace(' ', ''),  # remove espaços do App Password
        'from_name': os.environ.get('SMTP_FROM_NAME', 'I-Deal Notificações'),
    }


def is_configured() -> bool:
    """Retorna True se SMTP_USER e SMTP_PASSWORD estão preenchidos."""
    cfg = _smtp_config()
    return bool(cfg['user'] and cfg['password'])


# =============================================================================
# Template HTML — segue identidade visual do site (glass / roxo / verde)
# =============================================================================
def _build_alert_html(user_name: str, game_title: str, store: str,
                      new_price: float, target_price: float,
                      game_url: str) -> str:
    """Monta o HTML do email com a identidade visual do I-Deal."""
    saving = max(target_price - new_price, 0)
    saving_pct = (saving / target_price * 100) if target_price > 0 else 0
    return f"""\
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Alerta de Preço — I-Deal</title>
</head>
<body style="margin:0;padding:0;background:#0d0f1a;font-family:'Segoe UI',Roboto,Arial,sans-serif;color:#fff;">
  <div style="max-width:560px;margin:0 auto;padding:32px 20px;">
    <div style="text-align:center;margin-bottom:28px;">
      <h1 style="margin:0;font-size:32px;font-weight:800;
                 background:linear-gradient(90deg,#6366f1,#10b981);
                 -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                 background-clip:text;color:#6366f1;letter-spacing:1px;">I-Deal</h1>
    </div>

    <div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);
                border-radius:16px;padding:28px;">

      <p style="font-size:14px;color:#aaa;margin:0 0 8px;">Olá, {user_name}!</p>
      <h2 style="margin:0 0 24px;font-size:22px;font-weight:600;">
        Seu alerta foi disparado 🎯
      </h2>

      <p style="font-size:15px;line-height:1.6;color:#ddd;margin:0 0 20px;">
        O jogo <strong style="color:#fff;">{game_title}</strong> baixou de preço na
        <strong style="color:#fff;">{store}</strong> e está agora abaixo do valor que você definiu.
      </p>

      <div style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.3);
                  border-radius:12px;padding:20px;margin:0 0 24px;text-align:center;">
        <div style="font-size:13px;color:#aaa;margin-bottom:6px;">Preço atual</div>
        <div style="font-size:36px;font-weight:800;color:#10b981;">
          R$ {f"{new_price:.2f}".replace('.', ',')}
        </div>
        <div style="font-size:13px;color:#888;margin-top:6px;">
          Seu alvo era R$ {f"{target_price:.2f}".replace('.', ',')}
          &nbsp;·&nbsp; economia de R$ {f"{saving:.2f}".replace('.', ',')} ({saving_pct:.0f}%)
        </div>
      </div>

      <div style="text-align:center;margin:0 0 12px;">
        <a href="{game_url}"
           style="display:inline-block;background:#6366f1;color:#fff;
                  padding:14px 36px;border-radius:8px;text-decoration:none;
                  font-weight:600;font-size:15px;">
          Ver oferta no I-Deal →
        </a>
      </div>

      <p style="font-size:12px;color:#666;text-align:center;margin:20px 0 0;line-height:1.5;">
        Você está recebendo este email porque cadastrou um alerta de preço no I-Deal.<br>
        Para gerenciar ou desativar seus alertas, acesse "Meus Alertas" no site.
      </p>
    </div>

    <div style="text-align:center;margin-top:20px;font-size:11px;color:#555;">
      I-Deal — Agregador de preços de jogos digitais
    </div>
  </div>
</body>
</html>
"""


def _build_alert_text(user_name: str, game_title: str, store: str,
                      new_price: float, target_price: float,
                      game_url: str) -> str:
    """Versão texto puro do email (fallback)."""
    return (
        f"Olá, {user_name}!\n\n"
        f"Seu alerta foi disparado!\n\n"
        f"{game_title} está agora por R$ {new_price:.2f} na {store} "
        f"(seu alvo era R$ {target_price:.2f}).\n\n"
        f"Veja a oferta: {game_url}\n\n"
        f"--\n"
        f"I-Deal — Agregador de preços de jogos digitais"
    ).replace('.', ',')


# =============================================================================
# API pública
# =============================================================================
def send_alert_email(to: str, user_name: str, game_title: str, store: str,
                     new_price: float, target_price: float,
                     game_url: str) -> bool:
    """
    Envia o email de alerta de preço.
    Retorna True se enviou com sucesso, False caso contrário (sem levantar exceção).
    """
    cfg = _smtp_config()

    if not cfg['user'] or not cfg['password']:
        logger.warning('SMTP não configurado (SMTP_USER/SMTP_PASSWORD vazios) — email não enviado.')
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'🎮 {game_title} caiu pra R$ {new_price:.2f} na {store}!'.replace('.', ',')
    msg['From'] = f"{cfg['from_name']} <{cfg['user']}>"
    msg['To'] = to

    html = _build_alert_html(user_name, game_title, store, new_price, target_price, game_url)
    text = _build_alert_text(user_name, game_title, store, new_price, target_price, game_url)
    msg.attach(MIMEText(text, 'plain', 'utf-8'))
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP(cfg['host'], cfg['port'], timeout=20) as server:
            server.starttls()
            server.login(cfg['user'], cfg['password'])
            server.send_message(msg)
        logger.info(f'Email de alerta enviado para {to}: {game_title} R$ {new_price:.2f}')
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f'SMTP auth falhou (verifique App Password): {e}')
        return False
    except Exception as e:
        logger.error(f'Erro ao enviar email para {to}: {e}')
        return False


def send_test_email(to: str) -> bool:
    """Envia um email de teste (útil pra debug). Retorna True se enviou."""
    return send_alert_email(
        to=to,
        user_name='Teste',
        game_title='Elden Ring',
        store='Steam',
        new_price=149.90,
        target_price=199.90,
        game_url='http://localhost:5000/game/1',
    )
