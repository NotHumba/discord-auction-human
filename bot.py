import discord
from discord.ext import commands
import json
import random
import os
import asyncio
import uuid
import time
from keep_alive import keep_alive

# Create alias for random module
_r = random

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

BID_INCREMENT = 5000000
MIN_BID_INCREMENT = 5000000
MAX_BASE_PRICE = 50000000
MIN_BASE_PRICE = 1000000
MAX_PLAYERS_PER_USER = 15
MAX_LINEUP_PLAYERS = 11
PRIVILEGED_USER_ID = 962232390686765126
HOST_TIMEOUT = 300  # 5 minutes in seconds

available_positions = ['st', 'rw', 'lw', 'cam', 'cm', 'lb', 'cb', 'rb', 'gk']
available_tactics = ['Attacking', 'Defensive', 'Balanced']
available_formations = {
    '4-4-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 2, 'st': 2},
    '4-3-3': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 1, 'cam': 1, 'lw': 1, 'rw': 1, 'st': 1},
    '4-2-3-1': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 3, 'st': 1},
    '3-5-2': {'gk': 1, 'cb': 3, 'cm': 2, 'cam': 3, 'st': 2},
    '3-4-3': {'gk': 1, 'cb': 3, 'cm': 2, 'lw': 1, 'rw': 1, 'st': 1},
    '5-4-1': {'gk': 1, 'cb': 3, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 2, 'st': 1},
    '5-3-2': {'gk': 1, 'cb': 3, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 1, 'st': 2},
    # ... Add more formations as needed
}

available_sets = {
    'wc': 'World Cup XI',
    'ucl': 'Champions League XI',
    'epl': 'Premier League XI',
    'laliga': 'La Liga XI',
    'bundesliga': 'Bundesliga XI',
    'seriea': 'Serie A XI',
    '2010-2025': '2010-2025 Legends',
    '24-25': '24-25 Season'
}

STARTING_BUDGET = 1000000000
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

player_form = {}
active_auctions = {}
lineup_setup_state = {
    'user_id': None,
    'channel_id': None,
    'stage': None,
    'formation': None,
    'tactic': None,
    'selected_players': [],
    'position_counts': {pos: 0 for pos in available_positions},
    'required_counts': None,
    'lineup_name': 'main'
}
user_teams = {}
user_budgets = {}
user_lineups = {}
active_lineups = {}
user_stats = {}
tournaments = {}
pending_trades = {}
mystery_boxes = {}

# Drafts mode - replacing draftclash with drafts
drafts_sessions = {}
drafts_wins = {}

def save_data(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w') as f:
        json.dump(data, f)

def load_data(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}

# Core load/save for drafts mode
drafts_sessions = load_data("drafts_sessions.json")
drafts_wins = load_data("drafts_wins.json")
user_teams = load_data("user_teams.json")
user_budgets = load_data("user_budgets.json")
user_lineups = load_data("user_lineups.json")
active_lineups = load_data("active_lineups.json")
user_stats = load_data("user_stats.json")
tournaments = load_data("tournaments.json")
pending_trades = load_data("pending_trades.json")
mystery_boxes = load_data("mystery_boxes.json")

@bot.command()
async def drafts(ctx):
    """Start a new drafts session, or join if one is active in this channel."""
    channel_id = str(ctx.channel.id)
    user_id = str(ctx.author.id)

    if channel_id in drafts_sessions:
        if user_id in drafts_sessions[channel_id]['players']:
            await ctx.send("You are already in this drafts session!")
            return
        drafts_sessions[channel_id]['players'].append(user_id)
        save_data("drafts_sessions.json", drafts_sessions)
        await ctx.send(f"{ctx.author.mention} joined the ongoing drafts session!")
    else:
        # Start new session
        drafts_sessions[channel_id] = {
            "host": user_id,
            "players": [user_id],
            "status": "waiting"
        }
        save_data("drafts_sessions.json", drafts_sessions)
        await ctx.send(f"New Drafts session started by {ctx.author.mention}! Type `!drafts` to join.")

@bot.command()
async def draftsleaderboard(ctx):
    """Show the all-time drafts wins leaderboard."""
    if not drafts_wins:
        await ctx.send("No drafts wins recorded yet!")
        return
    sorted_leaderboard = sorted(drafts_wins.items(), key=lambda x: x[1], reverse=True)
    msg = "**Drafts Leaderboard:**\n"
    for i, (user_id, wins) in enumerate(sorted_leaderboard[:10], 1):
        user = await bot.fetch_user(int(user_id))
        username = user.name if user else f"User {user_id}"
        msg += f"{i}. {username}: {wins} wins\n"
    await ctx.send(msg)

@bot.command()
async def mydraftswins(ctx):
    """Check your total wins in Drafts mode."""
    user_id = str(ctx.author.id)
    wins = drafts_wins.get(user_id, 0)
    await ctx.send(f"{ctx.author.mention}, you have {wins} Drafts wins!")

# All storage, session save/load, and other bot references to "draftclash" should be renamed accordingly!
# --- LINEUP LOGIC ---

def validate_lineup(formation, selected_players):
    """Ensure all positions are filled as per the chosen formation."""
    req = available_formations.get(formation, {})
    pos_counts = {pos: 0 for pos in available_positions}
    for p in selected_players:
        pos_counts[p['position']] += 1
    for pos, count in req.items():
        if pos_counts[pos] != count:
            return False
    return True

@bot.command()
async def setlineup(ctx, lineup_name: str):
    """Set your active lineup by name."""
    user_id = str(ctx.author.id)
    if user_id not in user_lineups or lineup_name not in user_lineups[user_id]:
        await ctx.send(f"Lineup `{lineup_name}` not found. Make sure you saved it first!")
        return
    active_lineups[user_id] = lineup_name
    save_data("active_lineups.json", active_lineups)
    await ctx.send(f"{ctx.author.mention}, your active lineup is now `{lineup_name}`.")

@bot.command()
async def savelineup(ctx, lineup_name: str):
    """Save your current lineup under a custom name."""
    user_id = str(ctx.author.id)
    current = user_teams.get(user_id)
    if not current:
        await ctx.send("You have no players to save yet!")
        return
    if user_id not in user_lineups:
        user_lineups[user_id] = {}
    user_lineups[user_id][lineup_name] = current
    save_data("user_lineups.json", user_lineups)
    await ctx.send(f"Lineup saved as `{lineup_name}`.")

# --- AUCTION LOGIC ---

@bot.command()
async def startauction(ctx):
    """Start a new auction round for the channel."""
    channel_id = str(ctx.channel.id)
    if channel_id in active_auctions:
        await ctx.send("An auction is already live in this channel!")
        return
    active_auctions[channel_id] = {
        "host": str(ctx.author.id),
        "players": [],
        "stage": "setup"
    }
    await ctx.send(f"Auction started by {ctx.author.mention}! Type `!joinauction` to participate.")

@bot.command()
async def joinauction(ctx):
    """Join an active auction."""
    channel_id = str(ctx.channel.id)
    user_id = str(ctx.author.id)
    if channel_id not in active_auctions:
        await ctx.send("No auction is currently running in this channel.")
        return
    if user_id in active_auctions[channel_id]['players']:
        await ctx.send("You are already in this auction!")
        return
    active_auctions[channel_id]['players'].append(user_id)
    await ctx.send(f"{ctx.author.mention} joined the auction!")

# Additional auction stages, player bid handling, and result finalization routines go here.
@bot.command()
async def myteam(ctx):
    """Show your current squad lineup."""
    user_id = str(ctx.author.id)
    team = user_teams.get(user_id)
    if not team:
        await ctx.send("You have no team yet!")
        return
    msg = f"**{ctx.author.name}'s Team:**\n"
    for player in team:
        msg += f"- {player['name']} ({player['position']})\n"
    await ctx.send(msg)

@bot.command()
async def mybudget(ctx):
    """Show your remaining budget."""
    user_id = str(ctx.author.id)
    budget = user_budgets.get(user_id, STARTING_BUDGET)
    await ctx.send(f"{ctx.author.mention}, your budget is: {budget:,}")

@bot.command()
async def stats(ctx):
    """Show your football bot milestones and stats."""
    user_id = str(ctx.author.id)
    stats = user_stats.get(user_id, {})
    if not stats:
        await ctx.send("You have no stats recorded yet.")
        return
    msg = f"**Stats for {ctx.author.name}:**\n"
    for k, v in stats.items():
        msg += f"{k}: {v}\n"
    await ctx.send(msg)

@bot.command()
async def addstats(ctx, key: str, value: int):
    """Admin-only: Add to a user's stats."""
    if ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send("No permission.")
        return
    user_id = str(ctx.author.id)
    user_stats.setdefault(user_id, {})
    user_stats[user_id][key] = user_stats[user_id].get(key, 0) + value
    save_data("user_stats.json", user_stats)
    await ctx.send(f"Stat updated: {key} -> {user_stats[user_id][key]}")

@bot.command()
async def tournaments(ctx):
    """Show current tournaments."""
    if not tournaments:
        await ctx.send("No tournaments live right now.")
        return
    msg = "**Current Tournaments:**\n"
    for tname, tinfo in tournaments.items():
        msg += f"{tname}: {tinfo['status']}\n"
    await ctx.send(msg)

@bot.command()
async def trade(ctx, other_user: discord.User, give_player: str, receive_player: str):
    """Propose a player trade with another user."""
    user_id = str(ctx.author.id)
    other_id = str(other_user.id)
    pending_trades.setdefault(user_id, {})
    pending_trades[user_id][other_id] = {
        "give": give_player,
        "receive": receive_player
    }
    save_data("pending_trades.json", pending_trades)
    await ctx.send(f"Trade proposed to {other_user.mention}: {give_player} for {receive_player}")

@bot.command()
async def mysterybox(ctx):
    """Open a mystery box for a random reward."""
    user_id = str(ctx.author.id)
    reward = random.choice(["bonus budget", "star player", "formation boost"])
    mystery_boxes.setdefault(user_id, [])
    mystery_boxes[user_id].append(reward)
    save_data("mystery_boxes.json", mystery_boxes)
    await ctx.send(f"Congrats, {ctx.author.mention}! You earned: {reward}")

@bot.event
async def on_ready():
    print(f"Bot is live as {bot.user}.")

if __name__ == "__main__":
    keep_alive()
    bot.run(os.getenv('DISCORD_TOKEN'))
