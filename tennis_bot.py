import os

import asyncio

import logging

from datetime import datetime

import httpx

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Bot

# =========================

# CONFIG

# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

CHAT_ID = os.getenv("CHAT_ID")

ODDS_API_KEY = os.getenv("ODDS_API_KEY")

SEND_HOUR = 8

SEND_MINUTE = 0

MIN_VALUE = 3

# =========================

# LOGS

# =========================

logging.basicConfig(level=logging.INFO)

log = logging.getLogger(__name__)

# =========================

# TELEGRAM BOT

# =========================

bot = Bot(token=TELEGRAM_TOKEN)

# =========================

# MATHS

# =========================

def implied_prob(odd):

    return 1 / odd if odd > 0 else 0

def value_percent(fair_prob, odd):

    return round((fair_prob * odd - 1) * 100, 1)

# =========================

# ANALYSE MATCH

# =========================

def analyze_match(match):

    home = match.get("home_team", "?")

    away = match.get("away_team", "?")

    tournament = match.get("sport_title", "Tennis")

    bookmakers = match.get("bookmakers", [])

    if not bookmakers:

        return None

    all_odds_home = []

    all_odds_away = []

    for bk in bookmakers:

        for market in bk.get("markets", []):

            if market.get("key") != "h2h":

                continue

            for outcome in market.get("outcomes", []):

                if outcome["name"] == home:

                    all_odds_home.append(outcome["price"])

                elif outcome["name"] == away:

                    all_odds_away.append(outcome["price"])

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

    pick_prob = round(

        fair_home * 100 if val_home >= val_away else fair_away * 100,

        1

    )

    score = min(100, int(50 + pick_val * 2))

    level = (

        "🔥 FORTE VALUE"

        if pick_val >= 8

        else "⚡ BONNE VALUE"

        if pick_val >= 4

        else "✅ VALUE CORRECTE"

    )

    return {

        "home": home,

        "away": away,

        "tournament": tournament,

        "pick": pick,

        "odd": pick_odd,

        "value": pick_val,

        "prob": pick_prob,

        "score": score,

        "level": level,

    }

# =========================

# API ODDS

# =========================

async def fetch_matches():

    url = (

        "https://api.the-odds-api.com/v4/sports/tennis/odds/"

        f"?apiKey={ODDS_API_KEY}"

        "&regions=eu"

        "&markets=h2h"

        "&oddsFormat=decimal"

    )

    async with httpx.AsyncClient(timeout=20) as client:

        response = await client.get(url)

        response.raise_for_status()

        return response.json()

# =========================

# MESSAGE TELEGRAM

# =========================

def build_message(picks):

    today = datetime.now().strftime("%d/%m/%Y")

    lines = [

        f"🎾 *TENNIS VALUE BETS — {today}*",

        "━━━━━━━━━━━━━━━━━━━━━━",

        f"📊 {len(picks)} value bet(s) détecté(s)\n",

    ]

    for i, p in enumerate(picks, 1):

        lines.extend([

            f"*Match {i}*",

            f"🏆 {p['tournament']}",

            f"👤 {p['home']} vs {p['away']}",

            f"✅ *Pick : {p['pick']}*",

            f"💰 Cote : *{p['odd']}*",

            f"📈 Value : *+{p['value']}%*",

            f"🎯 Probabilité : {p['prob']}%",

            f"⚡ Score : {p['score']}/100",

            f"{p['level']}",

            "━━━━━━━━━━━━━━━━━━━━━━",

        ])

    lines.append("⚠️ _Parie de façon responsable._")

    return "\n".join(lines)

# =========================

# ENVOI

# =========================

async def send_picks():

    try:

        log.info("Récupération des matchs...")

        matches = await fetch_matches()

        picks = sorted(

            [

                result

                for match in matches

                if (result := analyze_match(match))

            ],

            key=lambda x: x["value"],

            reverse=True,

        )

        if picks:

            message = build_message(picks)

        else:

            message = "🎾 Aucune value bet trouvée aujourd'hui."

        await bot.send_message(

            chat_id=CHAT_ID,

            text=message,

            parse_mode="Markdown",

        )

        log.info("Message envoyé avec succès")

    except Exception as e:

        log.error(f"Erreur : {e}")

# =========================

# MAIN

# =========================

async def main():

    log.info("Bot démarré")

    # Envoi immédiat au lancement

    await send_picks()

    scheduler = AsyncIOScheduler()

    scheduler.add_job(

        send_picks,

        "cron",

        hour=SEND_HOUR,

        minute=SEND_MINUTE,

    )

    scheduler.start()

    while True:

        await asyncio.sleep(3600)

# =========================

# START

# =========================

if __name__ == "__main__":

    asyncio.run(main())
