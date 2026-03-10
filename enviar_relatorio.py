#!/usr/bin/env python3
"""
ImagineBooks - Envio Automatico de Relatorio por Email
Puxa dados do Meta Ads + WooCommerce e envia relatorio HTML por email.
Versao para GitHub Actions (usa variaveis de ambiente).
"""

import json
import os
import smtplib
import ssl
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path

# ==================== CONFIGURACOES ====================
def load_config():
    """Carrega config de variaveis de ambiente (GitHub Actions) ou .env (local)."""
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
META_AD_ACCOUNT = "act_381961628220751"
WC_KEY = ENV.get("WC_CONSUMER_KEY", "")
WC_SECRET = ENV.get("WC_CONSUMER_SECRET", "")
WC_URL = ENV.get("WC_STORE_URL", "https://www.imaginebooks.com.br")
GMAIL_USER = ENV.get("GMAIL_USER", "")
GMAIL_PASS = ENV.get("GMAIL_APP_PASSWORD", "")
EMAIL_TO = ENV.get("EMAIL_TO", "")
DASHBOARD_URL = "https://leandro-14ps.github.io/imaginebooks-dashboard/"

# ==================== BUSCAR DADOS ====================
def fetch_meta_insights(days=3):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    until = datetime.now().strftime("%Y-%m-%d")

    url = (
        f"https://graph.facebook.com/v25.0/{META_AD_ACCOUNT}/insights"
        f"?fields=spend,impressions,clicks,reach,actions,cost_per_action_type"
        f"&time_range=%7B%22since%22%3A%22{since}%22%2C%22until%22%3A%22{until}%22%7D"
        f"&access_token={META_TOKEN}"
    )

    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx) as resp:
            data = json.loads(resp.read())
            if data.get("data"):
                return data["data"][0], since, until
    except Exception as e:
        print(f"Erro Meta API: {e}")
    return None, since, until


def fetch_wc_orders(days=3):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    url = (
        f"{WC_URL}/wp-json/wc/v3/orders"
        f"?per_page=100&after={since}"
        f"&consumer_key={WC_KEY}&consumer_secret={WC_SECRET}"
    )

    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"Erro WooCommerce API: {e}")
    return []


# ==================== PROCESSAR DADOS ====================
def process_data(meta, orders):
    stats = {}

    if meta:
        stats["spend"] = float(meta.get("spend", 0))
        stats["reach"] = int(meta.get("reach", 0))
        stats["impressions"] = int(meta.get("impressions", 0))
        stats["clicks"] = int(meta.get("clicks", 0))

        purchases = 0
        add_to_cart = 0
        page_likes = 0
        cost_per_purchase = 0
        for a in meta.get("actions", []):
            if a["action_type"] == "purchase":
                purchases = int(a["value"])
            if a["action_type"] == "add_to_cart":
                add_to_cart = int(a["value"])
            if a["action_type"] == "onsite_conversion.post_net_like":
                page_likes = int(a["value"])

        for c in meta.get("cost_per_action_type", []):
            if c["action_type"] == "purchase":
                cost_per_purchase = float(c["value"])

        stats["meta_purchases"] = purchases
        stats["add_to_cart"] = add_to_cart
        stats["page_likes"] = page_likes
        stats["cost_per_purchase"] = cost_per_purchase
    else:
        stats["spend"] = 0
        stats["reach"] = 0
        stats["impressions"] = 0
        stats["clicks"] = 0
        stats["meta_purchases"] = 0
        stats["add_to_cart"] = 0
        stats["page_likes"] = 0
        stats["cost_per_purchase"] = 0

    completed = [o for o in orders if o["status"] in ("completed", "processing")]
    failed = [o for o in orders if o["status"] == "failed"]

    revenue = sum(float(o["total"]) for o in completed)
    ticket = revenue / len(completed) if completed else 0
    roas = revenue / stats["spend"] if stats["spend"] > 0 else 0

    products = {}
    for o in completed:
        for item in o.get("line_items", []):
            name = item["name"].replace("ImagineBooks Judô - ", "")
            products[name] = products.get(name, 0) + item["quantity"]

    stats["completed"] = len(completed)
    stats["failed"] = len(failed)
    stats["revenue"] = revenue
    stats["ticket"] = ticket
    stats["roas"] = roas
    stats["products"] = sorted(products.items(), key=lambda x: -x[1])

    return stats


# ==================== GERAR SUGESTOES ====================
def generate_suggestions(stats):
    suggestions = []

    if stats["roas"] < 1 and stats["spend"] > 0:
        suggestions.append("ROAS abaixo de 1x — considere otimizar publicos e criativos das campanhas.")

    if stats["failed"] > 0:
        suggestions.append(f"{stats['failed']} pedido(s) com falha no pagamento — considere oferecer desconto via Pix para recuperar vendas.")

    if stats["add_to_cart"] > 0 and stats["completed"] > 0:
        conv_rate = stats["completed"] / stats["add_to_cart"] * 100
        if conv_rate < 20:
            suggestions.append(f"Taxa de conversao carrinho->compra em {conv_rate:.0f}% — remarketing pode recuperar carrinhos abandonados.")

    if stats["ticket"] > 0 and stats["ticket"] < 100:
        suggestions.append("Ticket medio baixo — promover bundles ou colecao completa pode aumentar o valor por pedido.")

    if stats["reach"] > 0 and stats["completed"] == 0:
        suggestions.append("Alcance alto mas sem vendas — revisar segmentacao de publico e landing page.")

    if not suggestions:
        suggestions.append("Metricas estaveis no periodo. Continue monitorando e testando novos criativos.")

    return suggestions


# ==================== GERAR TEXTO WHATSAPP ====================
def build_whatsapp_text(stats, since, until, suggestions):
    since_fmt = datetime.strptime(since, "%Y-%m-%d").strftime("%d/%m/%Y")
    until_fmt = datetime.strptime(until, "%Y-%m-%d").strftime("%d/%m/%Y")

    def fmt_money(v):
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def fmt_num(v):
        return f"{v:,}".replace(",", ".")

    roas_emoji = "\U0001f7e2" if stats["roas"] >= 1 else "\U0001f534"

    products_text = ""
    for name, qty in stats["products"][:5]:
        products_text += f"  \u2022 {name}: {qty} un.\n"
    if not products_text:
        products_text = "  Nenhuma venda no periodo\n"

    suggestions_text = ""
    for i, s in enumerate(suggestions, 1):
        suggestions_text += f"  {i}. {s}\n"

    text = f"""\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501
\U0001f4ca *IMAGINEBOOKS*
*Relatorio de Performance*
\U0001f4c5 {since_fmt} a {until_fmt}
\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501

\U0001f4e3 *META ADS*
\U0001f441 Alcance: *{fmt_num(stats['reach'])}*
\U0001f4f0 Impressoes: *{fmt_num(stats['impressions'])}*
\U0001f465 Novos seguidores: *{stats['page_likes']}*
\U0001f4b0 Investido: *{fmt_money(stats['spend'])}*

\U0001f6d2 *VENDAS (SITE)*
\U0001f6cd Add ao carrinho: *{stats['add_to_cart']}*
\u2705 Vendas realizadas: *{stats['completed']}*
\u274c Pedidos com falha: *{stats['failed']}*
\U0001f3af Custo por resultado: *{fmt_money(stats['cost_per_purchase']) if stats['cost_per_purchase'] > 0 else 'N/A'}*

\U0001f4b0 *RESULTADOS FINANCEIROS*
\U0001f4b5 Receita: *{fmt_money(stats['revenue'])}*
\U0001f9fe Ticket medio: *{fmt_money(stats['ticket'])}*
{roas_emoji} ROAS: *{stats['roas']:.2f}x* {'(Positivo)' if stats['roas'] >= 1 else '(Negativo)'}

\U0001f4e6 *PRODUTOS MAIS VENDIDOS*
{products_text}
\U0001f4a1 *SUGESTOES*
{suggestions_text}
\U0001f517 *Dashboard completo:*
{DASHBOARD_URL}

\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"""

    return text


# ==================== GERAR EMAIL HTML ====================
def build_email_html(stats, since, until, suggestions, whatsapp_text=""):
    since_fmt = datetime.strptime(since, "%Y-%m-%d").strftime("%d/%m/%Y")
    until_fmt = datetime.strptime(until, "%Y-%m-%d").strftime("%d/%m/%Y")

    roas_color = "#4caf50" if stats["roas"] >= 1 else "#ef5350"
    roas_label = "Positivo" if stats["roas"] >= 1 else "Negativo"

    products_html = ""
    for name, qty in stats["products"][:5]:
        products_html += f'<tr><td style="padding:8px 12px; color:#b8d4d9; font-size:13px; border-bottom:1px solid rgba(26,122,138,0.1);">{name}</td><td style="padding:8px 12px; color:white; font-weight:700; text-align:right; border-bottom:1px solid rgba(26,122,138,0.1);">{qty} un.</td></tr>'

    if not products_html:
        products_html = '<tr><td colspan="2" style="padding:12px; color:#7aa3ab; text-align:center;">Nenhuma venda no periodo</td></tr>'

    suggestions_html = ""
    for s in suggestions:
        suggestions_html += f'<li style="padding:8px 0; color:#b8d4d9; font-size:13px; line-height:1.5; border-bottom:1px solid rgba(26,122,138,0.1);">{s}</li>'

    def fmt_money(v):
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def fmt_num(v):
        return f"{v:,}".replace(",", ".")

    html = f"""
<html>
<body style="margin:0; padding:0; background:#0a2a2f; font-family:Arial,Helvetica,sans-serif;">
<div style="max-width:600px; margin:0 auto; background:#0a2a2f;">

    <!-- Belt Strip -->
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

    <!-- Header -->
    <div style="background:linear-gradient(135deg, #0a2a2f 0%, #0d4f5a 100%); padding:30px; text-align:center; border-bottom:2px solid #1a7a8a;">
        <h1 style="color:white; margin:0; font-size:24px; font-weight:800;">ImagineBooks</h1>
        <p style="color:#7aa3ab; margin:5px 0 0; font-size:11px; letter-spacing:2px; text-transform:uppercase;">Relatorio de Performance</p>
        <p style="color:#e87c3e; margin:8px 0 0; font-size:14px; font-weight:600;">{since_fmt} a {until_fmt}</p>
    </div>

    <!-- Meta Ads -->
    <div style="padding:24px 24px 0;">
        <p style="color:#e87c3e; font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; margin:0 0 16px; border-bottom:1px solid rgba(232,124,62,0.3); padding-bottom:8px;">META ADS</p>

        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td width="50%" style="padding:8px;">
                    <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px; text-align:center;">
                        <p style="color:#7aa3ab; font-size:10px; text-transform:uppercase; letter-spacing:1px; margin:0;">Alcance</p>
                        <p style="color:#1565c0; font-size:24px; font-weight:800; margin:6px 0 0;">{fmt_num(stats['reach'])}</p>
                    </div>
                </td>
                <td width="50%" style="padding:8px;">
                    <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px; text-align:center;">
                        <p style="color:#7aa3ab; font-size:10px; text-transform:uppercase; letter-spacing:1px; margin:0;">Impressoes</p>
                        <p style="color:#1a7a8a; font-size:24px; font-weight:800; margin:6px 0 0;">{fmt_num(stats['impressions'])}</p>
                    </div>
                </td>
            </tr>
            <tr>
                <td width="50%" style="padding:8px;">
                    <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px; text-align:center;">
                        <p style="color:#7aa3ab; font-size:10px; text-transform:uppercase; letter-spacing:1px; margin:0;">Novos Seguidores</p>
                        <p style="color:#2e7d32; font-size:24px; font-weight:800; margin:6px 0 0;">{fmt_num(stats['page_likes'])}</p>
                    </div>
                </td>
                <td width="50%" style="padding:8px;">
                    <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px; text-align:center;">
                        <p style="color:#7aa3ab; font-size:10px; text-transform:uppercase; letter-spacing:1px; margin:0;">Investido</p>
                        <p style="color:#e87c3e; font-size:24px; font-weight:800; margin:6px 0 0;">{fmt_money(stats['spend'])}</p>
                    </div>
                </td>
            </tr>
        </table>
    </div>

    <!-- WooCommerce -->
    <div style="padding:24px 24px 0;">
        <p style="color:#e87c3e; font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; margin:0 0 16px; border-bottom:1px solid rgba(232,124,62,0.3); padding-bottom:8px;">VENDAS (SITE)</p>

        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td width="50%" style="padding:8px;">
                    <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px; text-align:center;">
                        <p style="color:#7aa3ab; font-size:10px; text-transform:uppercase; letter-spacing:1px; margin:0;">Vendas</p>
                        <p style="color:#2e7d32; font-size:24px; font-weight:800; margin:6px 0 0;">{stats['completed']}</p>
                    </div>
                </td>
                <td width="50%" style="padding:8px;">
                    <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px; text-align:center;">
                        <p style="color:#7aa3ab; font-size:10px; text-transform:uppercase; letter-spacing:1px; margin:0;">Pedidos com Falha</p>
                        <p style="color:#ef5350; font-size:24px; font-weight:800; margin:6px 0 0;">{stats['failed']}</p>
                    </div>
                </td>
            </tr>
            <tr>
                <td width="50%" style="padding:8px;">
                    <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px; text-align:center;">
                        <p style="color:#7aa3ab; font-size:10px; text-transform:uppercase; letter-spacing:1px; margin:0;">Add ao Carrinho</p>
                        <p style="color:#f9a825; font-size:24px; font-weight:800; margin:6px 0 0;">{stats['add_to_cart']}</p>
                    </div>
                </td>
                <td width="50%" style="padding:8px;">
                    <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px; text-align:center;">
                        <p style="color:#7aa3ab; font-size:10px; text-transform:uppercase; letter-spacing:1px; margin:0;">Custo por Resultado</p>
                        <p style="color:#6a1b9a; font-size:24px; font-weight:800; margin:6px 0 0;">{fmt_money(stats['cost_per_purchase']) if stats['cost_per_purchase'] > 0 else 'N/A'}</p>
                    </div>
                </td>
            </tr>
        </table>
    </div>

    <!-- Financial Highlights -->
    <div style="padding:24px 24px 0;">
        <p style="color:#e87c3e; font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; margin:0 0 16px; border-bottom:1px solid rgba(232,124,62,0.3); padding-bottom:8px;">RESULTADOS FINANCEIROS</p>

        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td width="33%" style="padding:6px;">
                    <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px; text-align:center;">
                        <p style="color:#7aa3ab; font-size:10px; text-transform:uppercase; letter-spacing:1px; margin:0;">Receita</p>
                        <p style="color:#2e7d32; font-size:20px; font-weight:800; margin:6px 0 0;">{fmt_money(stats['revenue'])}</p>
                    </div>
                </td>
                <td width="33%" style="padding:6px;">
                    <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px; text-align:center;">
                        <p style="color:#7aa3ab; font-size:10px; text-transform:uppercase; letter-spacing:1px; margin:0;">Ticket Medio</p>
                        <p style="color:#f9a825; font-size:20px; font-weight:800; margin:6px 0 0;">{fmt_money(stats['ticket'])}</p>
                    </div>
                </td>
                <td width="33%" style="padding:6px;">
                    <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px; text-align:center;">
                        <p style="color:#7aa3ab; font-size:10px; text-transform:uppercase; letter-spacing:1px; margin:0;">ROAS</p>
                        <p style="color:{roas_color}; font-size:20px; font-weight:800; margin:6px 0 0;">{stats['roas']:.2f}x</p>
                        <p style="color:{roas_color}; font-size:9px; margin:4px 0 0; text-transform:uppercase; font-weight:700;">{roas_label}</p>
                    </div>
                </td>
            </tr>
        </table>
    </div>

    <!-- Products -->
    <div style="padding:24px 24px 0;">
        <p style="color:#e87c3e; font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; margin:0 0 16px; border-bottom:1px solid rgba(232,124,62,0.3); padding-bottom:8px;">PRODUTOS MAIS VENDIDOS</p>
        <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; overflow:hidden;">
            <table width="100%" cellpadding="0" cellspacing="0">
                {products_html}
            </table>
        </div>
    </div>

    <!-- Suggestions -->
    <div style="padding:24px;">
        <p style="color:#e87c3e; font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; margin:0 0 16px; border-bottom:1px solid rgba(232,124,62,0.3); padding-bottom:8px;">SUGESTOES DE MELHORIA</p>
        <div style="background:#112e33; border:1px solid rgba(26,122,138,0.2); border-radius:10px; padding:16px;">
            <ul style="list-style:none; padding:0; margin:0;">
                {suggestions_html}
            </ul>
        </div>
    </div>

    <!-- CTA -->
    <div style="padding:0 24px 24px; text-align:center;">
        <a href="{DASHBOARD_URL}" style="display:inline-block; background:#e87c3e; color:white; text-decoration:none; padding:14px 32px; border-radius:8px; font-size:14px; font-weight:700; text-transform:uppercase; letter-spacing:1px;">Ver Dashboard Completo</a>
    </div>

    <!-- WhatsApp Copy Text -->
    <div style="padding:0 24px 24px;">
        <p style="color:#e87c3e; font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; margin:0 0 16px; border-bottom:1px solid rgba(232,124,62,0.3); padding-bottom:8px;">COPIE E COLE NO WHATSAPP</p>
        <div style="background:#1a1a2e; border:1px solid rgba(37,211,102,0.3); border-radius:10px; padding:20px; position:relative;">
            <div style="position:absolute; top:8px; right:12px; background:rgba(37,211,102,0.15); color:#25d366; padding:3px 10px; border-radius:12px; font-size:10px; font-weight:700;">WhatsApp Ready</div>
            <pre style="color:#e0e0e0; font-family:monospace; font-size:12px; line-height:1.6; white-space:pre-wrap; word-wrap:break-word; margin:0;">{whatsapp_text}</pre>
        </div>
    </div>

    <!-- Footer -->
    <div style="padding:20px; text-align:center; border-top:1px solid rgba(26,122,138,0.2);">
        <p style="color:#7aa3ab; font-size:11px; margin:0;">Relatorio gerado automaticamente | ImagineBooks Dashboard</p>
        <p style="color:#7aa3ab; font-size:10px; margin:4px 0 0;">imaginebooks.com.br</p>
    </div>

    <!-- Belt Strip -->
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
    return html


# ==================== ENVIAR EMAIL ====================
def send_email(html, since, until, to_email=None, plain_text=None):
    since_fmt = datetime.strptime(since, "%Y-%m-%d").strftime("%d/%m")
    until_fmt = datetime.strptime(until, "%Y-%m-%d").strftime("%d/%m/%Y")

    recipient = to_email or EMAIL_TO

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"ImagineBooks - Relatorio {since_fmt} a {until_fmt}"
    msg["From"] = f"ImagineBooks Dashboard <{GMAIL_USER}>"
    msg["To"] = recipient

    msg.attach(MIMEText(plain_text or "Visualize este email em um cliente que suporte HTML.", "plain"))
    msg.attach(MIMEText(html, "html"))

    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.login(GMAIL_USER, GMAIL_PASS)
    server.sendmail(GMAIL_USER, recipient, msg.as_string())
    server.quit()

    print(f"Relatorio enviado para {recipient}!")


# ==================== MAIN ====================
def main(days=3, test_mode=False):
    print(f"Buscando dados dos ultimos {days} dias...")

    meta, since, until = fetch_meta_insights(days)
    orders = fetch_wc_orders(days)

    print(f"Meta Ads: {'OK' if meta else 'Sem dados'}")
    print(f"WooCommerce: {len(orders)} pedidos encontrados")

    stats = process_data(meta, orders)
    suggestions = generate_suggestions(stats)
    whatsapp_text = build_whatsapp_text(stats, since, until, suggestions)

    html = build_email_html(stats, since, until, suggestions, whatsapp_text)

    if test_mode:
        send_email(html, since, until, to_email=GMAIL_USER, plain_text=whatsapp_text)
        print("(Modo teste: enviado para voce mesmo)")
    else:
        send_email(html, since, until, plain_text=whatsapp_text)
        send_email(html, since, until, to_email=GMAIL_USER, plain_text=whatsapp_text)
        print("Enviado para o cliente e para voce!")


if __name__ == "__main__":
    import sys
    test = "--test" in sys.argv
    days = 3
    for arg in sys.argv[1:]:
        if arg.isdigit():
            days = int(arg)
    main(days=days, test_mode=test)
