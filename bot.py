#!/usr/bin/env python3
import requests, os, time, threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

TG_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TG_CHAT = os.environ['TELEGRAM_CHAT_ID']
META_TOKEN = os.environ['META_ACCESS_TOKEN']
META_ACCOUNT = os.environ['META_AD_ACCOUNT']
ADSET_ID = '120246373074310177'

TELEGRAM_API = f'https://api.telegram.org/bot{TG_TOKEN}'

# ── Meta helpers ──────────────────────────────────────────────────────────────

def meta_insights(adset_id, preset):
    r = requests.get(f'https://graph.facebook.com/v21.0/{adset_id}/insights',
        params={
            'access_token': META_TOKEN,
            'fields': 'spend,impressions,reach,clicks,ctr,cpc,cpm,frequency,actions,action_values,cost_per_action_type',
            'date_preset': preset,
        }, timeout=15)
    data = r.json().get('data', [{}])
    return data[0] if data else {}

def parse(d):
    actions = {a['action_type']: float(a['value']) for a in d.get('actions', [])}
    av      = {a['action_type']: float(a['value']) for a in d.get('action_values', [])}
    costs   = {a['action_type']: float(a['value']) for a in d.get('cost_per_action_type', [])}
    spend   = float(d.get('spend', 0))
    clicks  = int(d.get('clicks', 0))
    lpv     = int(actions.get('landing_page_views', 0))
    purchases = int(actions.get('purchase', 0))
    revenue = av.get('purchase', 0)
    cpp     = costs.get('purchase', 0)
    return {
        'spend': spend,
        'impressions': int(d.get('impressions', 0)),
        'reach': int(d.get('reach', 0)),
        'freq': float(d.get('frequency', 0)),
        'clicks': clicks,
        'ctr': float(d.get('ctr', 0)),
        'cpc': float(d.get('cpc', 0)),
        'cpm': float(d.get('cpm', 0)),
        'lpv': lpv,
        'click_lpv': f"{lpv/clicks*100:.0f}%" if clicks else "—",
        'atc': int(actions.get('add_to_cart', 0)),
        'ic': int(actions.get('initiate_checkout', 0)),
        'purchases': purchases,
        'revenue': revenue,
        'cpp': cpp,
        'roas': revenue / spend if spend > 0 else 0,
    }

def flag(val, metric):
    if metric == 'ctr':
        return '✅' if val >= 4 else ('⚠️' if val >= 2 else '🔴')
    if metric == 'cpp':
        if val == 0: return '⏳'
        return '✅' if val <= 25 else ('⚠️' if val <= 50 else '🔴')
    if metric == 'roas':
        return '✅' if val >= 2 else ('⚠️' if val >= 1 else '🔴')
    return ''

# ── Report builder ────────────────────────────────────────────────────────────

def build_report(label='📊 Report'):
    now = datetime.utcnow()
    cairo_hour = (now.hour + 3) % 24
    cairo_str = f"{cairo_hour:02d}:{now.minute:02d} Cairo"

    today = parse(meta_insights(ADSET_ID, 'today'))
    yest  = parse(meta_insights(ADSET_ID, 'yesterday'))

    return f"""🧶 <b>Nile Yarn — {label}</b>
🕐 {cairo_str}

<b>TODAY</b>
💰 Spend: ${today['spend']:.2f} / $120
👁 Impressions: {today['impressions']:,} | Reach: {today['reach']:,}
🖱 Clicks: {today['clicks']:,} | CTR: {today['ctr']:.2f}% {flag(today['ctr'],'ctr')}
💵 CPC: ${today['cpc']:.2f} | CPM: ${today['cpm']:.2f}
🔗 LPV: {today['lpv']:,} ({today['click_lpv']} of clicks)
🛒 ATC: {today['atc']} | IC: {today['ic']} | Purchases: {today['purchases']}
💳 Revenue: ${today['revenue']:.2f}
📦 CPP: ${today['cpp']:.2f} {flag(today['cpp'],'cpp')}
📈 ROAS: {today['roas']:.2f}x {flag(today['roas'],'roas')}

<b>YESTERDAY</b>
💰 Spend: ${yest['spend']:.2f} | CTR: {yest['ctr']:.2f}% {flag(yest['ctr'],'ctr')}
🛒 ATC: {yest['atc']} | IC: {yest['ic']} | Purchases: {yest['purchases']}
💳 Revenue: ${yest['revenue']:.2f} | CPP: ${yest['cpp']:.2f} {flag(yest['cpp'],'cpp')}
📈 ROAS: {yest['roas']:.2f}x {flag(yest['roas'],'roas')}"""

# ── Telegram helpers ──────────────────────────────────────────────────────────

def send(text, chat_id=None):
    requests.post(f'{TELEGRAM_API}/sendMessage', data={
        'chat_id': chat_id or TG_CHAT,
        'text': text,
        'parse_mode': 'HTML'
    }, timeout=10)

def send_typing(chat_id):
    requests.post(f'{TELEGRAM_API}/sendChatAction',
        data={'chat_id': chat_id, 'action': 'typing'}, timeout=5)

# ── Command handler ───────────────────────────────────────────────────────────

def handle(text, chat_id):
    t = text.lower().strip()

    if any(k in t for k in ['pull', 'report', 'analyze', 'analysis', 'stats', 'data']):
        send_typing(chat_id)
        send(build_report('On-Demand Report'), chat_id)

    elif any(k in t for k in ['spend', 'spent', 'budget']):
        send_typing(chat_id)
        d = parse(meta_insights(ADSET_ID, 'today'))
        remaining = max(0, 120 - d['spend'])
        send(f"💰 Spent today: <b>${d['spend']:.2f}</b>\n🎯 Remaining: <b>${remaining:.2f}</b>", chat_id)

    elif any(k in t for k in ['purchase', 'sale', 'order', 'conversion']):
        send_typing(chat_id)
        d = parse(meta_insights(ADSET_ID, 'today'))
        y = parse(meta_insights(ADSET_ID, 'yesterday'))
        send(f"🛍 <b>Purchases</b>\nToday: {d['purchases']} (${d['revenue']:.2f})\nYesterday: {y['purchases']} (${y['revenue']:.2f})\nCPP today: ${d['cpp']:.2f} {flag(d['cpp'],'cpp')}", chat_id)

    elif any(k in t for k in ['atc', 'add to cart', 'cart']):
        send_typing(chat_id)
        d = parse(meta_insights(ADSET_ID, 'today'))
        send(f"🛒 <b>Today's Funnel</b>\nATC: {d['atc']} | IC: {d['ic']} | Purchases: {d['purchases']}", chat_id)

    elif any(k in t for k in ['ctr', 'click']):
        send_typing(chat_id)
        d = parse(meta_insights(ADSET_ID, 'today'))
        send(f"🖱 <b>Clicks today</b>: {d['clicks']:,}\nCTR: {d['ctr']:.2f}% {flag(d['ctr'],'ctr')}\nCPC: ${d['cpc']:.2f}\nLPV: {d['lpv']:,} ({d['click_lpv']} of clicks)", chat_id)

    elif any(k in t for k in ['roas', 'return', 'revenue']):
        send_typing(chat_id)
        d = parse(meta_insights(ADSET_ID, 'today'))
        send(f"📈 <b>ROAS today</b>: {d['roas']:.2f}x {flag(d['roas'],'roas')}\nRevenue: ${d['revenue']:.2f} on ${d['spend']:.2f} spend", chat_id)

    elif any(k in t for k in ['cpp', 'cost per']):
        send_typing(chat_id)
        d = parse(meta_insights(ADSET_ID, 'today'))
        send(f"📦 <b>CPP today</b>: ${d['cpp']:.2f} {flag(d['cpp'],'cpp')}\nTarget: $15–25", chat_id)

    elif any(k in t for k in ['help', 'menu', 'commands', '/start']):
        send("""🧶 <b>Nile Yarn Ads Bot</b>

You can ask me anything, for example:
• "pull" / "report" → full report
• "spend" → today's spend & remaining budget
• "purchases" → sales today vs yesterday
• "ATC" → funnel breakdown
• "CTR" → click metrics
• "ROAS" → return on ad spend
• "CPP" → cost per purchase
• "help" → this menu

Reports auto-send at 9AM, 5PM, midnight Cairo 🕐""", chat_id)

    else:
        send("I didn't understand that. Send <b>help</b> to see what I can do 🧶", chat_id)

# ── Polling loop ──────────────────────────────────────────────────────────────

def poll():
    offset = None
    print("Bot is running...")
    while True:
        try:
            params = {'timeout': 30, 'allowed_updates': ['message']}
            if offset:
                params['offset'] = offset
            r = requests.get(f'{TELEGRAM_API}/getUpdates', params=params, timeout=35)
            updates = r.json().get('result', [])
            for u in updates:
                offset = u['update_id'] + 1
                msg = u.get('message', {})
                text = msg.get('text', '')
                chat_id = msg.get('chat', {}).get('id')
                if text and chat_id:
                    handle(text, str(chat_id))
        except Exception as e:
            print(f"Poll error: {e}")
            time.sleep(5)

# ── Scheduler ─────────────────────────────────────────────────────────────────

def scheduled_report(label):
    try:
        send(build_report(label))
    except Exception as e:
        print(f"Scheduled report error: {e}")

def start_scheduler():
    scheduler = BackgroundScheduler(timezone='Africa/Cairo')
    scheduler.add_job(lambda: scheduled_report('Morning Report ☀️'),  'cron', hour=9,  minute=0)
    scheduler.add_job(lambda: scheduled_report('Afternoon Report 🌤'),  'cron', hour=17, minute=0)
    scheduler.add_job(lambda: scheduled_report('Night Report 🌙'),      'cron', hour=0,  minute=0)
    scheduler.start()

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    send("🟢 Nile Ads Bot is online and listening!")
    start_scheduler()
    poll()
