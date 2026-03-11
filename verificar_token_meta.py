#!/usr/bin/env python3
"""
ImagineBooks - Verificacao Diaria do Token Meta Ads
Checa se o token ainda e valido e envia alerta por email se expirou ou vai expirar em breve.
"""

import json
import os
import smtplib
import ssl
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path


def load_config():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        env = {}
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env[key.strip()] = value.strip()
        return env
    return os.environ


ENV = load_config()
META_TOKEN = ENV.get("META_ACCESS_TOKEN", "")
GMAIL_USER = ENV.get("GMAIL_USER", "")
GMAIL_PASS = ENV.get("GMAIL_APP_PASSWORD", "")
ALERT_EMAIL = "lps.souza14@gmail.com"


def check_token():
    """Verifica validade do token via debug_token endpoint."""
    url = (
        f"https://graph.facebook.com/v25.0/debug_token"
        f"?input_token={META_TOKEN}"
        f"&access_token={META_TOKEN}"
    )
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx) as resp:
            data = json.loads(resp.read())
            token_data = data.get("data", {})
            is_valid = token_data.get("is_valid", False)
            expires_at = token_data.get("expires_at", 0)
            return is_valid, expires_at
    except Exception as e:
        print(f"Erro ao verificar token: {e}")
        return False, 0


def send_alert(status, expires_at):
    """Envia email de alerta sobre o token."""
    now = datetime.now()

    if expires_at > 0:
        exp_date = datetime.fromtimestamp(expires_at)
        days_left = (exp_date - now).days
        exp_fmt = exp_date.strftime("%d/%m/%Y %H:%M")
    else:
        days_left = -1
        exp_fmt = "Desconhecido"

    if status == "expired":
        subject = "ALERTA: Token Meta Ads EXPIRADO - ImagineBooks"
        color = "#ef5350"
        icon = "\u274c"
        message = "O token do Meta Ads <strong>EXPIROU</strong>. Os relatorios automaticos e o dashboard estao sem dados de anuncios."
    elif status == "expiring_soon":
        subject = f"AVISO: Token Meta Ads expira em {days_left} dias - ImagineBooks"
        color = "#f9a825"
        icon = "\u26a0\ufe0f"
        message = f"O token do Meta Ads vai expirar em <strong>{days_left} dias</strong> ({exp_fmt})."
    else:
        return

    html = f"""
<html>
<body style="margin:0; padding:0; background:#0a2a2f; font-family:Arial,sans-serif;">
<div style="max-width:500px; margin:0 auto; background:#0a2a2f;">

    <div style="height:4px; display:flex;">
        <div style="flex:1; background:#f0f0f0;"></div>
        <div style="flex:1; background:#9e9e9e;"></div>
        <div style="flex:1; background:#1565c0;"></div>
        <div style="flex:1; background:#f9a825;"></div>
        <div style="flex:1; background:#e65100;"></div>
        <div style="flex:1; background:#2e7d32;"></div>
        <div style="flex:1; background:#6a1b9a;"></div>
        <div style="flex:1; background:#5d4037;"></div>
    </div>

    <div style="background:linear-gradient(135deg, #0a2a2f 0%, #0d4f5a 100%); padding:30px; text-align:center; border-bottom:2px solid {color};">
        <p style="font-size:40px; margin:0;">{icon}</p>
        <h1 style="color:white; margin:10px 0 0; font-size:20px;">ImagineBooks</h1>
        <p style="color:{color}; margin:8px 0 0; font-size:14px; font-weight:700;">{subject}</p>
    </div>

    <div style="padding:24px;">
        <div style="background:#112e33; border:1px solid {color}; border-radius:10px; padding:20px;">
            <p style="color:#b8d4d9; font-size:14px; line-height:1.6; margin:0 0 16px;">{message}</p>
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;">
                <tr>
                    <td style="color:#7aa3ab; font-size:12px; padding:6px 0;">Status:</td>
                    <td style="color:{color}; font-size:12px; font-weight:700; text-align:right; padding:6px 0;">{'EXPIRADO' if status == 'expired' else f'Expira em {days_left} dias'}</td>
                </tr>
                <tr>
                    <td style="color:#7aa3ab; font-size:12px; padding:6px 0;">Data de expiracao:</td>
                    <td style="color:white; font-size:12px; font-weight:700; text-align:right; padding:6px 0;">{exp_fmt}</td>
                </tr>
                <tr>
                    <td style="color:#7aa3ab; font-size:12px; padding:6px 0;">Verificado em:</td>
                    <td style="color:white; font-size:12px; text-align:right; padding:6px 0;">{now.strftime('%d/%m/%Y %H:%M')}</td>
                </tr>
            </table>

            <p style="color:#e87c3e; font-size:11px; font-weight:700; letter-spacing:1px; text-transform:uppercase; margin:16px 0 8px; border-top:1px solid rgba(232,124,62,0.3); padding-top:12px;">COMO RENOVAR</p>
            <ol style="color:#b8d4d9; font-size:13px; line-height:1.8; padding-left:20px; margin:0;">
                <li>Acesse o Graph API Explorer do Facebook</li>
                <li>Gere um novo token com as permissoes necessarias</li>
                <li>Va ao repositorio <strong>leandro-14ps/imaginebooks-dashboard</strong></li>
                <li>Settings > Secrets > Atualize <strong>META_ACCESS_TOKEN</strong></li>
                <li>Atualize tambem no arquivo <strong>.env</strong> local</li>
            </ol>
        </div>
    </div>

    <div style="padding:20px; text-align:center; border-top:1px solid rgba(26,122,138,0.2);">
        <p style="color:#7aa3ab; font-size:11px; margin:0;">Verificacao automatica diaria | ImagineBooks</p>
    </div>

    <div style="height:4px; display:flex;">
        <div style="flex:1; background:#f0f0f0;"></div>
        <div style="flex:1; background:#9e9e9e;"></div>
        <div style="flex:1; background:#1565c0;"></div>
        <div style="flex:1; background:#f9a825;"></div>
        <div style="flex:1; background:#e65100;"></div>
        <div style="flex:1; background:#2e7d32;"></div>
        <div style="flex:1; background:#6a1b9a;"></div>
        <div style="flex:1; background:#5d4037;"></div>
    </div>
</div>
</body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"ImagineBooks Alerta <{GMAIL_USER}>"
    msg["To"] = ALERT_EMAIL

    plain = f"{subject}\n\nRenove o token no GitHub Secrets do repo leandro-14ps/imaginebooks-dashboard (META_ACCESS_TOKEN) e no .env local."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.login(GMAIL_USER, GMAIL_PASS)
    server.sendmail(GMAIL_USER, ALERT_EMAIL, msg.as_string())
    server.quit()
    print(f"Alerta enviado para {ALERT_EMAIL}!")


def main():
    print("Verificando token do Meta Ads...")
    is_valid, expires_at = check_token()

    if not is_valid:
        print("Token EXPIRADO!")
        send_alert("expired", expires_at)
        return

    if expires_at > 0:
        now = datetime.now()
        exp_date = datetime.fromtimestamp(expires_at)
        days_left = (exp_date - now).days
        print(f"Token valido. Expira em {days_left} dias ({exp_date.strftime('%d/%m/%Y')})")

        if days_left <= 5:
            print(f"Menos de 5 dias! Enviando alerta...")
            send_alert("expiring_soon", expires_at)
        else:
            print("Token OK, nenhum alerta necessario.")
    elif expires_at == 0:
        print("Token sem data de expiracao (nunca expira). OK.")
    else:
        print("Nao foi possivel determinar expiracao. Enviando alerta.")
        send_alert("expired", 0)


if __name__ == "__main__":
    main()
