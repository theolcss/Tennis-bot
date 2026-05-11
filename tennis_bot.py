import os
import asyncio
import logging
import requests
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8783177635:AAFdsz2X3Myp8mnweuT6gRrvjpNW3558FJ4")
CHAT_ID = os.getenv("CHAT_ID", "8507279948")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "00ba40654da2cc8a63aa56b513d46b18")
SEND_HOUR = 8
SEND_MINUTE = 0
MIN_VALUE = 3

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def implied_prob(odd):
    return 1 / odd if odd > 0 else 0

def value_percent(fair_prob, odd):
    return round((fair_prob * odd - 1) * 100, 1)

def analyze_match(match):
    home = match.get("home_team", "?")
    away = match.get("away_team", "?")
    tournament = match.get("sport_title", "Tennis")
    bookmakers = match.get("bookmakers", [])
    if not bookmakers:
        return None
    all_odds_home, all_odds_away = [], []
    for bk in bookmakers:
        for market in bk.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for o in market.get("outcomes", []):
                if o["name"] == home:
                    all_odds_home.append(o["price"])
                elif o["name"] == away:
                    all_odds_away.append(o["price"])
    if not all_odds_home or not all_odds_away:
        return None
    avg_home = sum(all_odds_home) / len(all_odds_home)
    avg_away = sum(all_odds_away) / len(all_odds_away)
    margin = implied_prob(avg_home) + implied_prob(avg_away)
    fair_home = implied_prob(avg_home) / margin
    fair_away = implied_prob(avg_away) / margin
    best_home = max(all_odds_home)
    best_away = max(all_odds_away)
    val_home = value_percent(fair_home, best_home)
    val_away = value_percent(fair_away, best_away)
    best_val = max(val_home, val_away)
    if best_val < MIN_VALUE:
        return None
    pick = home if val_home >= val_away else away
    pick_odd = best_home if val_home >= val_away else best_away
    pick_val = val_home if val_home >= val_away else val_away
    pick_prob = round(fair_home * 100 if val_home >= val_away else fair_away * 100, 1)
    score = min(100, int(50 + pick_val * 2))
    level = "FORTE VALUE" if pick_val >= 8 else "BONNE VALUE" if pick_val >= 4 else "VALUE CORRECTE"
    return {"home": home, "away": away, "tournament": tournament, "pick": pick, "odd": pick_odd, "value": pick_val, "prob": pick_prob, "score": score, "level": level}

def fetch_matches():
    url = f"https://api.the-odds-api.com/v4/sports/tennis/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=h2h&oddsFormat=decimal"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()

def build_message(picks):
    today = datetime.now().strftime("%d/%m/%Y")
    lines = [f"TENNIS VALUE BETS - {today}", "="*30, f"{len(picks)} value bet(s) detecte(s)\n"]
    for i, p in enumerate(picks, 1):
        lines += [
            f"Match {i}",
            f"Tournoi: {p['tournament']}",
            f"{p['home']} vs {p['away']}",
            f"Pick: {p['pick']}",
            f"Cote: {p['odd']}",
            f"Value: +{p['value']}%",
            f"Prob reelle: {p['prob']}%",
            f"Score: {p['score']}/100 - {p['level']}",
            "="*30
        ]
    lines.append("Joue de facon responsable.")
    return "\n".join(lines)

async def send_picks():
    try:
        matches = fetch_matches()
    except Exception as e:
        log.error(f"Erreur fetch: {e}")
        return
    picks = []
    for m in matches:
        r = analyze_match(m)
        if r:
            picks.append(r)
    picks.sort(key=lambda x: x["value"], reverse=True)
    msg = build_message(picks) if picks else "Aucune value bet aujourd'hui."
    bot = Bot(TELEGRAM_TOKEN)
    await bot.send_message(chat_id=CHAT_ID, text=msg)
    log.info(f"Message envoye - {len(picks)} picks")

async def main():
    log.info("Bot demarre")
    await send_picks()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_picks, "cron", hour=SEND_HOUR, minute=SEND_MINUTE)
    scheduler.start()
    log.info(f"Planifie a {SEND_HOUR}h{SEND_MINUTE:02d} UTC")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
