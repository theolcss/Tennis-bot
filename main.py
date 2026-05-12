import os
import asyncio
import logging
import requests
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

# =========================
# VARIABLES
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TENNIS_API_KEY = os.getenv("TENNIS_API_KEY")

GROQ_KEY = os.getenv("GROQ_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")
COHERE_KEY = os.getenv("COHERE_KEY")
MISTRAL_KEY = os.getenv("MISTRAL_KEY")
HF_KEY = os.getenv("HF_KEY")

SEND_HOUR = 8
SEND_MINUTE = 0
MIN_CONSENSUS = 3

# =========================
# LOGS
# =========================

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# =========================
# TELEGRAM
# =========================

bot = Bot(token=TELEGRAM_TOKEN)

# =========================
# TENNIS API
# =========================

def get_todays_matches():

    today = datetime.now().strftime("%Y-%m-%d")

    response = requests.get(
        "https://v1.tennis.api-sports.io/games",
        headers={
            "x-apisports-key": TENNIS_API_KEY
        },
        params={
            "date": today
        },
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    return data.get("response", [])

# =========================
# PLAYER FORM
# =========================

def get_player_form(player_id):

    try:

        response = requests.get(
            "https://v1.tennis.api-sports.io/games",
            headers={
                "x-apisports-key": TENNIS_API_KEY
            },
            params={
                "player": player_id,
                "last": 10
            },
            timeout=15
        )

        games = response.json().get("response", [])

        if not games:
            return None

        wins = 0

        for game in games:

            players = game.get("players", {})

            home_id = players.get("home", {}).get("id")
            away_id = players.get("away", {}).get("id")

            winner = game.get("winner")

            if home_id == player_id and winner == "home":
                wins += 1

            elif away_id == player_id and winner == "away":
                wins += 1

        return round((wins / len(games)) * 100)

    except Exception as e:

        log.warning(f"Erreur forme joueur : {e}")

        return None

# =========================
# PROMPT IA
# =========================

def build_prompt(home, away, tournament, home_form, away_form):

    form_text = ""

    if home_form is not None and away_form is not None:

        form_text = (
            f"{home} gagne {home_form}% de ses matchs récents. "
            f"{away} gagne {away_form}% de ses matchs récents."
        )

    prompt = (
        f"Match de tennis : {home} contre {away}. "
        f"Tournoi : {tournament}. "
        f"{form_text} "
        f"Qui va gagner ? "
        f"Réponds uniquement par le nom exact du joueur."
    )

    return prompt

# =========================
# IA REQUEST
# =========================

def ask_groq(prompt):

    try:

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-8b-8192",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 20
            },
            timeout=20
        )

        data = response.json()

        return data["choices"][0]["message"]["content"].strip()

    except Exception as e:

        log.warning(f"Groq erreur : {e}")

        return None

# =========================
# CONSENSUS
# =========================

def get_consensus(home, away, tournament, home_form, away_form):

    prompt = build_prompt(
        home,
        away,
        tournament,
        home_form,
        away_form
    )

    responses = {
        "Groq": ask_groq(prompt)
    }

    votes_home = 0
    votes_away = 0

    ai_votes = {}

    for ai_name, response in responses.items():

        if response is None:

            ai_votes[ai_name] = "?"

            continue

        response_lower = response.lower()

        if home.lower() in response_lower:

            votes_home += 1

            ai_votes[ai_name] = home

        elif away.lower() in response_lower:

            votes_away += 1

            ai_votes[ai_name] = away

        else:

            ai_votes[ai_name] = "?"

    if votes_home >= votes_away:

        return home, votes_home, ai_votes

    return away, votes_away, ai_votes

# =========================
# MESSAGE
# =========================

def build_message(results):

    today = datetime.now().strftime("%d/%m/%Y")

    lines = [
        f"🎾 TENNIS PICKS - {today}",
        "==============================",
        ""
    ]

    for i, result in enumerate(results, 1):

        lines.extend([
            f"MATCH {i}",
            f"{result['home']} vs {result['away']}",
            "",
            f"✅ PICK : {result['pick']}",
            f"🔥 Consensus IA : {result['consensus']}",
            "",
            "Votes IA :"
        ])

        for ai_name, vote in result["ai_votes"].items():

            lines.append(f"- {ai_name} : {vote}")

        if result["home_form"] is not None:

            lines.extend([
                "",
                "Forme récente :",
                f"- {result['home']} : {result['home_form']}%",
                f"- {result['away']} : {result['away_form']}%"
            ])

        lines.extend([
            "",
            "==============================",
            ""
        ])

    if not results:

        lines.append("❌ Aucun pick valide aujourd'hui.")

    lines.append("⚠️ Parie de façon responsable.")

    return "\n".join(lines)

# =========================
# SEND PICKS
# =========================

async def send_picks():

    try:

        log.info("Analyse des matchs...")

        matches = get_todays_matches()

        results = []

        for match in matches:

            try:

                players = match.get("players", {})

                home = players.get("home", {}).get("name", "?")
                away = players.get("away", {}).get("name", "?")

                tournament = match.get(
                    "league",
                    {}
                ).get("name", "Tennis")

                home_id = players.get("home", {}).get("id")
                away_id = players.get("away", {}).get("id")

                home_form = (
                    get_player_form(home_id)
                    if home_id else None
                )

                away_form = (
                    get_player_form(away_id)
                    if away_id else None
                )

                pick, consensus, ai_votes = get_consensus(
                    home,
                    away,
                    tournament,
                    home_form,
                    away_form
                )

                if consensus >= MIN_CONSENSUS:

                    results.append({
                        "home": home,
                        "away": away,
                        "pick": pick,
                        "consensus": consensus,
                        "ai_votes": ai_votes,
                        "home_form": home_form,
                        "away_form": away_form
                    })

            except Exception as e:

                log.warning(f"Erreur match : {e}")

        message = build_message(results)

        await bot.send_message(
            chat_id=CHAT_ID,
            text=message
        )

        log.info("Message envoyé")

    except Exception as e:

        log.error(f"Erreur globale : {e}")

# =========================
# MAIN
# =========================

async def main():

    log.info("Bot démarré")

    await send_picks()

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        send_picks,
        "cron",
        hour=SEND_HOUR,
        minute=SEND_MINUTE
    )

    scheduler.start()

    while True:

        await asyncio.sleep(3600)

# =========================
# START
# =========================

if __name__ == "__main__":

    asyncio.run(main())
