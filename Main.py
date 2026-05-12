import os
import asyncio
import logging
import requests
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

TELEGRAM_TOKEN = os.getenv(“TELEGRAM_TOKEN”, “8783177635:AAFdsz2X3Myp8mnweuT6gRrvjpNW3558FJ4”)
CHAT_ID        = os.getenv(“CHAT_ID”, “8507279948”)
TENNIS_API_KEY = os.getenv(“TENNIS_API_KEY”, “ebc982da8e20da6428c182641a2318c6bc1d366db0417fa8a7f5dc013f6934ce”)
GROQ_KEY       = os.getenv(“GROQ_KEY”, “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”)
GEMINI_KEY     = os.getenv(“GEMINI_KEY”, “AIzaSyC0i7ePT6Idz_dSIHlGAWiT2LUKxnZdyo4”)
COHERE_KEY     = os.getenv(“COHERE_KEY”, “UHufQ8lDHphL7x18k4WrKdRQALasfSq3VAcvEXtt”)
MISTRAL_KEY    = os.getenv(“MISTRAL_KEY”, “hUqO16TLqbrdEEerVFBKhrCC7Jain33G”)
HF_KEY         = os.getenv(“HF_KEY”, “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”)
SEND_HOUR      = 8
SEND_MINUTE    = 0
MIN_CONSENSUS  = 3

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(**name**)

def get_todays_matches():
today = datetime.now().strftime(”%Y-%m-%d”)
r = requests.get(
“https://v1.tennis.api-sports.io/games”,
headers={“x-apisports-key”: TENNIS_API_KEY},
params={“date”: today},
timeout=15
)
r.raise_for_status()
return r.json().get(“response”, [])

def get_player_stats(player_id):
try:
r = requests.get(
“https://v1.tennis.api-sports.io/games”,
headers={“x-apisports-key”: TENNIS_API_KEY},
params={“player”: player_id, “last”: 10},
timeout=10
)
games = r.json().get(“response”, [])
if not games:
return None
wins = sum(
1 for g in games
if (g.get(“players”, {}).get(“home”, {}).get(“id”) == player_id and g.get(“winner”) == “home”)
or (g.get(“players”, {}).get(“away”, {}).get(“id”) == player_id and g.get(“winner”) == “away”)
)
return round(wins / len(games) * 100)
except Exception:
return None

def build_prompt(home, away, home_form, away_form, tournament):
form_text = “”
if home_form is not None:
form_text = f”Recent form: {home} wins {home_form}% of matches, {away} wins {away_form}% of matches.”
return (
f”Tennis match: {home} vs {away} - Tournament: {tournament}. {form_text} “
f”Who will win? Reply ONLY with the exact player name, either ‘{home}’ or ‘{away}’, nothing else.”
)

def ask_groq(prompt):
try:
r = requests.post(
“https://api.groq.com/openai/v1/chat/completions”,
headers={“Authorization”: f”Bearer {GROQ_KEY}”, “Content-Type”: “application/json”},
json={“model”: “llama3-8b-8192”, “messages”: [{“role”: “user”, “content”: prompt}], “max_tokens”: 20},
timeout=15
)
return r.json()[“choices”][0][“message”][“content”].strip()
except Exception as e:
log.warning(f”Groq: {e}”)
return None

def ask_gemini(prompt):
try:
r = requests.post(
f”https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}”,
json={“contents”: [{“parts”: [{“text”: prompt}]}]},
timeout=15
)
return r.json()[“candidates”][0][“content”][“parts”][0][“text”].strip()
except Exception as e:
log.warning(f”Gemini: {e}”)
return None

def ask_cohere(prompt):
try:
r = requests.post(
“https://api.cohere.ai/v1/generate”,
headers={“Authorization”: f”Bearer {COHERE_KEY}”, “Content-Type”: “application/json”},
json={“model”: “command”, “prompt”: prompt, “max_tokens”: 20},
timeout=15
)
return r.json()[“generations”][0][“text”].strip()
except Exception as e:
log.warning(f”Cohere: {e}”)
return None

def ask_mistral(prompt):
try:
r = requests.post(
“https://api.mistral.ai/v1/chat/completions”,
headers={“Authorization”: f”Bearer {MISTRAL_KEY}”, “Content-Type”: “application/json”},
json={“model”: “mistral-small-latest”, “messages”: [{“role”: “user”, “content”: prompt}], “max_tokens”: 20},
timeout=15
)
return r.json()[“choices”][0][“message”][“content”].strip()
except Exception as e:
log.warning(f”Mistral: {e}”)
return None

def ask_huggingface(prompt):
try:
r = requests.post(
“https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3”,
headers={“Authorization”: f”Bearer {HF_KEY}”},
json={“inputs”: prompt, “parameters”: {“max_new_tokens”: 20}},
timeout=20
)
result = r.json()
if isinstance(result, list):
return result[0].get(“generated_text”, “”).replace(prompt, “”).strip()
return None
except Exception as e:
log.warning(f”HuggingFace: {e}”)
return None

def get_consensus(home, away, home_form, away_form, tournament):
prompt = build_prompt(home, away, home_form, away_form, tournament)
responses = {
“Groq”: ask_groq(prompt),
“Gemini”: ask_gemini(prompt),
“Cohere”: ask_cohere(prompt),
“Mistral”: ask_mistral(prompt),
“HuggingFace”: ask_huggingface(prompt),
}
votes_home, votes_away = 0, 0
ai_picks = {}
for ai_name, response in responses.items():
if response is None:
ai_picks[ai_name] = “?”
continue
resp_lower = response.lower()
home_lower = home.lower()
away_lower = away.lower()
if home_lower in resp_lower and away_lower not in resp_lower:
votes_home += 1
ai_picks[ai_name] = home
elif away_lower in resp_lower and home_lower not in resp_lower:
votes_away += 1
ai_picks[ai_name] = away
elif home_lower in resp_lower:
votes_home += 1
ai_picks[ai_name] = home
elif away_lower in resp_lower:
votes_away += 1
ai_picks[ai_name] = away
else:
ai_picks[ai_name] = “?”
if votes_home >= votes_away:
return home, votes_home, ai_picks
else:
return away, votes_away, ai_picks

def build_message(results):
today = datetime.now().strftime(”%d/%m/%Y”)
lines = [f”TENNIS PICKS - {today}”, “=”*32, f”{len(results)} pick(s) valide(s)”, “”]
for i, r in enumerate(results, 1):
c = r[“consensus”]
if c == 5: confidence, emoji = “MAXIMALE”, “🔥”
elif c == 4: confidence, emoji = “TRES ELEVEE”, “✅”
else: confidence, emoji = “CORRECTE”, “⚡”
lines += [
f”MATCH {i} - {r[‘tournament’]}”,
f”{r[‘home’]} vs {r[‘away’]}”,
f””,
f”PICK : {r[‘pick’]}”,
f”{emoji} Confiance : {confidence} ({c}/5 IA)”,
f””,
f”Votes IA :”,
]
for ai_name, vote in r[“ai_picks”].items():
icon = “✅” if vote == r[“pick”] else “❌” if vote != “?” else “⚠️”
lines.append(f”  {icon} {ai_name} : {vote}”)
if r.get(“home_form”) is not None:
lines += [
f””,
f”Forme recente :”,
f”  {r[‘home’].split()[-1]} : {r[‘home_form’]}% victoires”,
f”  {r[‘away’].split()[-1]} : {r[‘away_form’]}% victoires”,
]
lines += [”=”*32, “”]
lines.append(“Joue de facon responsable.”)
return “\n”.join(lines)

async def send_picks():
log.info(“Analyse en cours…”)
try:
matches = get_todays_matches()
log.info(f”{len(matches)} matchs trouves”)
except Exception as e:
log.error(f”Erreur matchs: {e}”)
return
results = []
for m in matches:
try:
players = m.get(“players”, {})
home = players.get(“home”, {}).get(“name”, “?”)
away = players.get(“away”, {}).get(“name”, “?”)
tournament = m.get(“league”, {}).get(“name”, “Tennis”)
home_id = players.get(“home”, {}).get(“id”)
away_id = players.get(“away”, {}).get(“id”)
home_form = get_player_stats(home_id) if home_id else None
away_form = get_player_stats(away_id) if away_id else None
pick, consensus, ai_picks = get_consensus(home, away, home_form, away_form, tournament)
if consensus >= MIN_CONSENSUS:
results.append({
“home”: home, “away”: away, “tournament”: tournament,
“pick”: pick, “consensus”: consensus, “ai_picks”: ai_picks,
“home_form”: home_form, “away_form”: away_form,
})
except Exception as e:
log.warning(f”Erreur: {e}”)
results.sort(key=lambda x: x[“consensus”], reverse=True)
msg = build_message(results) if results else f”Aucun pick valide aujourd’hui (moins de {MIN_CONSENSUS}/5 IA en accord).”
await Bot(TELEGRAM_TOKEN).send_message(chat_id=CHAT_ID, text=msg)
log.info(f”Envoye - {len(results)} picks”)

async def main():
log.info(“Bot demarre”)
await send_picks()
scheduler = AsyncIOScheduler()
scheduler.add_job(send_picks, “cron”, hour=SEND_HOUR, minute=SEND_MINUTE)
scheduler.start()
while True:
await asyncio.sleep(3600)

if **name** == “**main**”:
asyncio.run(main())
