import discord
from discord.ext import commands
import requests
import json
import os
from collections import defaultdict, Counter

# API key and bot token — keep these secure!
API_KEY = '89cffdca189608777591aa1afac88ac6'
BOT_TOKEN = 'YOUR_DISCORD_BOT_TOKEN_HERE'

# API settings
SPORT = 'upcoming'
REGIONS = 'us'
MARKETS = 'h2h,spreads'
ODDS_FORMAT = 'decimal'
DATE_FORMAT = 'iso'
STREAKS_FILE = 'streaks.json'

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# === LIVE ODDS COMMAND ===
def get_live_odds():
    headers = {'X-API-KEY': API_KEY}
    response = requests.get(
        f'https://api.the-odds-api.com/v4/sports/upcoming/odds/?regions={REGIONS}&markets={MARKETS}&oddsFormat={ODDS_FORMAT}&dateFormat={DATE_FORMAT}&apiKey={API_KEY}'
    )
    if response.status_code != 200:
        return f"Error: Unable to fetch data from API. Status Code: {response.status_code}. Message: {response.text}"

    data = response.json()
    if not data:
        return "No odds data available."

    odds_info = []
    for game in data:
        sport_title = game['sport_title']
        home_team = game['home_team']
        away_team = game['away_team']
        commence_time = game['commence_time']

        odds_text = f"**{sport_title}:** {home_team} vs {away_team}\n"
        odds_text += f"  **Start Time:** {commence_time}\n"

        if 'bookmakers' in game:
            for bookmaker in game['bookmakers']:
                bookmaker_name = bookmaker['title']
                odds_text += f"\n  **{bookmaker_name}:**\n"
                for market in bookmaker['markets']:
                    if market['key'] == 'h2h':
                        odds_text += f"    Head-to-Head: \n"
                        for outcome in market['outcomes']:
                            odds_text += f"    {outcome['name']}: {outcome['price']} \n"

        odds_info.append(odds_text)

    return "\n".join(odds_info)

# === STREAKS FUNCTIONS ===
def load_streaks():
    if os.path.exists(STREAKS_FILE):
        with open(STREAKS_FILE, 'r') as f:
            return json.load(f)
    else:
        return {
            'moneyline': {}, 'moneyline_losses': {},
            'runline': {}, 'runline_misses': {}
        }

def save_streaks(data):
    with open(STREAKS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_recent_results():
    url = f'https://api.the-odds-api.com/v4/sports/baseball_mlb/odds-history/?regions=us&markets=h2h,spreads&apiKey={API_KEY}'
    response = requests.get(url)
    if response.status_code != 200:
        print("Failed to fetch data:", response.status_code)
        return []
    return response.json()

def update_streaks(stored_streaks, games):
    ml_wins = defaultdict(lambda: 0, stored_streaks.get("moneyline", {}))
    ml_losses = defaultdict(lambda: 0, stored_streaks.get("moneyline_losses", {}))
    rl_covers = defaultdict(lambda: 0, stored_streaks.get("runline", {}))
    rl_misses = defaultdict(lambda: 0, stored_streaks.get("runline_misses", {}))

    for game in games:
        if not game.get('completed'):
            continue

        home = game['home_team']
        away = game['away_team']
        scores = game.get('scores', {})
        if not scores:
            continue

        home_score = scores.get('home_score')
        away_score = scores.get('away_score')
        if home_score is None or away_score is None:
            continue

        # ====== MONEYLINE OUTCOME TALLY ACROSS BOOKS ======
        ml_votes = []
        for bookmaker in game.get("bookmakers", []):
            market = next((m for m in bookmaker.get("markets", []) if m["key"] == "h2h"), None)
            if market:
                if home_score > away_score:
                    ml_votes.append(home)
                elif away_score > home_score:
                    ml_votes.append(away)

        if ml_votes:
            most_common_winner, count = Counter(ml_votes).most_common(1)[0]
            ml_wins[most_common_winner] += 1
            loser = away if most_common_winner == home else home
            ml_losses[loser] += 1
            ml_losses[most_common_winner] = 0
            ml_wins[loser] = 0

        # ====== RUNLINE OUTCOME TALLY ACROSS BOOKS ======
        rl_results = []

        for bookmaker in game.get("bookmakers", []):
            market = next((m for m in bookmaker.get("markets", []) if m["key"] == "spreads"), None)
            if market:
                for outcome in market.get("outcomes", []):
                    team = outcome["name"]
                    point = outcome["point"]
                    if team == home:
                        covered = (home_score - away_score) > point
                    elif team == away:
                        covered = (away_score - home_score) > point
                    else:
                        continue

                    rl_results.append((team, covered))

        if rl_results:
            teams = set([home, away])
            for team in teams:
                votes = [covered for t, covered in rl_results if t == team]
                if not votes:
                    continue
                most_common = Counter(votes).most_common(1)[0][0]
                if most_common:
                    rl_covers[team] += 1
                    rl_misses[team] = 0
                else:
                    rl_misses[team] += 1
                    rl_covers[team] = 0

    return {
        "moneyline": dict(ml_wins),
        "moneyline_losses": dict(ml_losses),
        "runline": dict(rl_covers),
        "runline_misses": dict(rl_misses)
    }

def get_streak_report(streaks):
    report = ""

    report += "**🏆 Moneyline Win Streaks (2+):**\n"
    for team, streak in streaks['moneyline'].items():
        if streak >= 2:
            report += f"- {team}: {streak} ML wins in a row\n"
    if not any(v >= 2 for v in streaks['moneyline'].values()):
        report += "None\n"

    report += "\n**❌ Moneyline Loss Streaks (2+):**\n"
    for team, streak in streaks['moneyline_losses'].items():
        if streak >= 2:
            report += f"- {team}: {streak} ML losses in a row\n"
    if not any(v >= 2 for v in streaks['moneyline_losses'].values()):
        report += "None\n"

    report += "\n**📈 Run Line Cover Streaks (2+):**\n"
    for team, streak in streaks['runline'].items():
        if streak >= 2:
            report += f"- {team}: Covered RL in {streak} straight games\n"
    if not any(v >= 2 for v in streaks['runline'].values()):
        report += "None\n"

    report += "\n**📉 Run Line Miss Streaks (2+):**\n"
    for team, streak in streaks['runline_misses'].items():
        if streak >= 2:
            report += f"- {team}: Missed RL in {streak} straight games\n"
    if not any(v >= 2 for v in streaks['runline_misses'].values()):
        report += "None\n"

    return report

# === SEND LONG MESSAGE HELPER ===
async def send_large_message(ctx, message):
    while len(message) > 1999:
        await ctx.send(message[:1999])
        message = message[1999:]
    await ctx.send(message)

# === BOT EVENTS & COMMANDS ===
@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')

@bot.command()
async def odds(ctx):
    await ctx.send("📡 Pulling current odds...")
    odds_data = get_live_odds()
    await send_large_message(ctx, f"**Live Sports Odds:**\n{odds_data}")

@bot.command()
async def streaks(ctx):
    await ctx.send("📊 Fetching updated MLB streaks...")
    saved_streaks = load_streaks()
    games = get_recent_results()
    updated_streaks = update_streaks(saved_streaks, games)
    save_streaks(updated_streaks)
    report = get_streak_report(updated_streaks)
    await send_large_message(ctx, report)

# === START THE BOT ===
bot.run('MTQwMTM1MTQ5MDQ1ODg3ODAxNQ.GKyX2B._Kcc_8BTquTLkedeqltyc4PRPMcOtAa9rP-Ud4')