import os
import asyncio
import logging
from datetime import datetime

import requests
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ======================
# VARIABLES
# ======================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

SEND_HOUR = 8
SEND_MINUTE = 0
MIN_VALUE = 3

# ======================
# LOGS
# ======================

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ======================
# BOT
# ======================

bot = Bot(token=TELEGRAM_TOKEN)

# ======================
# UTILS
# ======================

def implied_prob(odd):
    return 1 / odd if odd > 0 else 0


def value_percent(prob, odd):
    return round((prob * odd - 1) * 100, 1)

# ======================
# API ODDS
# ======================

def fetch_matches():

    url = (
        f"https://api.the-odds-api.com/v4/sports/tennis/odds/"
        f"?apiKey={ODDS_API_KEY}"
        "&regions=eu"
        "&markets=h2h"
        "&oddsFormat=decimal"
    )

    response = requests.get(url, timeout=20)

    response.raise_for_status()

    return response.json()

# ======================
# ANALYSE
# ======================

def analyze_match(match):

    home = match.get("home_team", "?")
    away = match.get("away_team", "?")

    bookmakers = match.get("bookmakers", [])

    if not bookmakers:
        return None

    home_odds = []
    away_odds = []

    for bookmaker in bookmakers:

        for market in bookmaker.get("markets", []):

            if market.get("key") != "h2h":
                continue

            for outcome in market.get("outcomes", []):

                if outcome["name"] == home:
                    home_odds.append(outcome["price"])

                elif outcome["name"] == away:
                    away_odds.append(outcome["price"])

    if not home_odds or not away_odds:
        return None

    avg_home = sum(home_odds) / len(home_odds)
    avg_away = sum(away_odds) / len(away_odds)

    margin = implied_prob(avg_home) + implied_prob(avg_away)

    fair_home = implied_prob(avg_home) / margin
    fair_away = implied_prob(avg_away) / margin

    best_home = max(home_odds)
    best_away = max(away_odds)

    value_home = value_percent(fair_home, best_home)
    value_away = value_percent(fair_away, best_away)

    if max(value_home, value_away) < MIN_VALUE:
        return None

    if value_home >= value_away:

        return {
            "pick": home,
            "opponent": away,
            "odd": best_home,
            "value": value_home,
        }

    else:

        return {
            "pick": away,
            "opponent": home,
            "odd": best_away,
            "value": value_away,
        }

# ======================
# MESSAGE
# ======================

def build_message(picks):

    today = datetime.now().strftime("%d/%m/%Y")

    lines = [
        f"🎾 TENNIS VALUE BETS - {today}",
        "",
    ]

    for i, pick in enumerate(picks, 1):

        lines.extend([
            f"Match {i}",
            f"Pick : {pick['pick']}",
            f"Contre : {pick['opponent']}",
            f"Cote : {pick['odd']}",
            f"Value : +{pick['value']}%",
            "",
        ])

    lines.append("⚠️ Parie de façon responsable.")

    return "\n".join(lines)

# ======================
# ENVOI
# ======================

async def send_picks():

    try:

        log.info("Analyse des matchs...")

        matches = fetch_matches()

        picks = []

        for match in matches:

            result = analyze_match(match)

            if result:
                picks.append(result)

        picks.sort(
            key=lambda x: x["value"],
            reverse=True,
        )

        if picks:
            message = build_message(picks)
        else:
            message = "🎾 Aucune value bet aujourd'hui."

        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
        )

        log.info("Message envoyé")

    except Exception as e:

        log.error(f"Erreur : {e}")

# ======================
# MAIN
# ======================

async def main():

    log.info("Bot démarré")

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

# ======================
# START
# ======================

if __name__ == "__main__":
    asyncio.run(main())
