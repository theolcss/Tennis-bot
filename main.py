import os
import asyncio
import logging
import requests
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

TELEGRAM_TOKEN = os.getenv(“TELEGRAM_TOKEN”, “8783177635:AAFdsz2X3Myp8mnweuT6gRrvjpNW3558FJ4”)
CHAT_ID = os.getenv(“CHAT_ID”, “8507279948”)
ODDS_API_KEY = os.getenv(“ODDS_API_KEY”, “00ba40654da2cc8a63aa56b513d46b18”)
TENNIS_API_KEY = os.getenv(“TENNIS_API_KEY”, “ebc982da8e20da6428c182641a2318c6bc1d366db0417fa8a7f5dc013f6934ce”)
SEND_HOUR = 8
SEND_MINUTE = 0
MIN_VALUE = 2

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(**name**)

TENNIS_BASE = “https://v1.tennis.api-sports.io”
TENNIS_HEADERS = {“x-apisports-key”: TENNIS_API_KEY}

def fetch_odds():
url = f”https://api.the-odds-api.com/v4/sports/tennis/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=h2h&oddsFormat=decimal”
r = requests.get(url, timeout=15)
r.raise_for_status()
return r.json()

def search_player(name):
try:
r = requests.get(f”{TENNIS_BASE}/players”, headers=TENNIS_HEADERS, params={“search”: name}, timeout=10)
data = r.json().get(“response”, [])
return data[0][“id”] if data else None
except Exception:
return None

def get_player_form(player_id):
try:
r = requests.get(f”{TENNIS_BASE}/games”, headers=TENNIS_HEADERS, params={“player”: player_id, “last”: 10}, timeout=10)
games = r.json().get(“response”, [])
if not games:
return None
wins = 0
for g in games:
players = g.get(“players”, {})
home_id = players.get(“home”, {}).get(“id”)
winner = g.get(“winner”)
if (home_id == player_id and winner == “home”) or (home_id != player_id and winner == “away”):
wins += 1
return round(wins / len(games) * 100, 1)
except Exception:
return None

def get_h2h(p1_id, p2_id):
try:
r = requests.get(f”{TENNIS_BASE}/games”, headers=TENNIS_HEADERS,
params={“h2h”: f”{p1_id}-{p2_id}”, “last”: 10}, timeout=10)
games = r.json().get(“response”, [])
if not games:
return None, None
w1, w2 = 0, 0
for g in games:
home_id = g.get(“players”, {}).get(“home”, {}).get(“id”)
winner = g.get(“winner”)
if winner == “home”:
if home_id == p1_id: w1 += 1
else: w2 += 1
elif winner == “away”:
if home_id == p1_id: w2 += 1
else: w1 += 1
return w1, w2
except Exception:
return None, None

def implied_prob(odd):
return 1 / odd if odd > 0 else 0

def value_percent(fair_prob, odd):
return round((fair_prob * odd - 1) * 100, 1)

def analyze_match(match):
home = match.get(“home_team”, “?”)
away = match.get(“away_team”, “?”)
tournament = match.get(“sport_title”, “Tennis”)
bookmakers = match.get(“bookmakers”, [])
if not bookmakers:
return None

```
all_home, all_away = [], []
for bk in bookmakers:
    for mkt in bk.get("markets", []):
        if mkt.get("key") != "h2h":
            continue
        for o in mkt.get("outcomes", []):
            if o["name"] == home: all_home.append(o["price"])
            elif o["name"] == away: all_away.append(o["price"])

if not all_home or not all_away:
    return None

avg_home = sum(all_home) / len(all_home)
avg_away = sum(all_away) / len(all_away)
margin = implied_prob(avg_home) + implied_prob(avg_away)
fair_home = implied_prob(avg_home) / margin
fair_away = implied_prob(avg_away) / margin
best_home = max(all_home)
best_away = max(all_away)

prob_home = fair_home * 100
prob_away = fair_away * 100

form_home = form_away = h2h_home = h2h_away = None
id_home = search_player(home)
id_away = search_player(away)

if id_home: form_home = get_player_form(id_home)
if id_away: form_away = get_player_form(id_away)
if id_home and id_away: h2h_home, h2h_away = get_h2h(id_home, id_away)

adj_home = prob_home
adj_away = prob_away

if form_home is not None and form_away is not None:
    form_diff = (form_home - form_away) * 0.1
    adj_home += form_diff
    adj_away -= form_diff

if h2h_home is not None and h2h_away is not None:
    total_h2h = h2h_home + h2h_away
    if total_h2h > 0:
        h2h_diff = ((h2h_home / total_h2h) - 0.5) * 10
        adj_home += h2h_diff
        adj_away -= h2h_diff

total = adj_home + adj_away
adj_home = round(adj_home / total * 100, 1)
adj_away = round(adj_away / total * 100, 1)

val_home = value_percent(adj_home / 100, best_home)
val_away = value_percent(adj_away / 100, best_away)
best_val = max(val_home, val_away)

if best_val < MIN_VALUE:
    return None

is_home_pick = val_home >= val_away
pick = home if is_home_pick else away
opponent = away if is_home_pick else home
pick_odd = best_home if is_home_pick else best_away
pick_val = val_home if is_home_pick else val_away
pick_prob = adj_home if is_home_pick else adj_away
opp_prob = adj_away if is_home_pick else adj_home

score = min(100, int(50 + pick_val * 2))
if form_home is not None: score = min(100, score + 2)
if h2h_home is not None: score = min(100, score + 3)
level = "FORTE VALUE" if pick_val >= 8 else "BONNE VALUE" if pick_val >= 4 else "VALUE CORRECTE"

return {
    "home": home, "away": away, "tournament": tournament,
    "pick": pick, "opponent": opponent,
    "odd": pick_odd, "value": pick_val,
    "pick_prob": pick_prob, "opp_prob": opp_prob,
    "form_home": form_home, "form_away": form_away,
    "h2h_home": h2h_home, "h2h_away": h2h_away,
    "score": score, "level": level
}
```

def build_message(picks):
today = datetime.now().strftime(”%d/%m/%Y”)
lines = [f”TENNIS VALUE BETS - {today}”, “=”*32, f”{len(picks)} value bet(s)”, “”]
for i, p in enumerate(picks, 1):
pn = p[‘pick’].split()[-1]
on = p[‘opponent’].split()[-1]
hn = p[‘home’].split()[-1]
an = p[‘away’].split()[-1]
lines += [
f”MATCH {i} - {p[‘tournament’]}”,
f”{p[‘home’]} vs {p[‘away’]}”,
f””,
f”PICK : {p[‘pick’]}”,
f”Cote : {p[‘odd’]}”,
f”Value : +{p[‘value’]}%”,
f””,
f”CHANCES DE VICTOIRE :”,
f”  {pn} : {p[‘pick_prob’]}%”,
f”  {on} : {p[‘opp_prob’]}%”,
]
if p[‘form_home’] is not None:
lines += [
f””,
f”FORME (10 derniers matchs) :”,
f”  {hn} : {p[‘form_home’]}% victoires”,
f”  {an} : {p[‘form_away’]}% victoires”,
]
if p[‘h2h_home’] is not None:
lines += [f””, f”H2H : {hn} {p[‘h2h_home’]} - {p[‘h2h_away’]} {an}”]
lines += [f””, f”Confiance : {p[‘score’]}/100 - {p[‘level’]}”, “=”*32, “”]
lines.append(“Joue de facon responsable.”)
return “\n”.join(lines)

async def send_picks():
log.info(“Analyse en cours…”)
try:
matches = fetch_odds()
except Exception as e:
log.error(f”Erreur odds: {e}”)
return
picks = []
for m in matches:
try:
r = analyze_match(m)
if r: picks.append(r)
except Exception as e:
log.warning(f”Erreur: {e}”)
picks.sort(key=lambda x: x[“value”], reverse=True)
msg = build_message(picks) if picks else “Aucune value bet aujourd’hui.”
await Bot(TELEGRAM_TOKEN).send_message(chat_id=CHAT_ID, text=msg)
log.info(f”Envoye - {len(picks)} picks”)

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
