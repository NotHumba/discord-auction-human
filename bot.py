import discord

player_form = {} # {player_name: form_rating (0-10)}

from discord.ext import commands

import json

import random

import os

import asyncio

import uuid

import time

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

HOST_TIMEOUT = 300 # 5 minutes in seconds

available_positions = ['st', 'rw', 'lw', 'cam', 'cm', 'lb', 'cb', 'rb', 'gk']

available_tactics = ['Attacking', 'Defensive', 'Balanced']

available_formations = {
    '4-4-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 2, 'st': 2},
    '4-3-3': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 1, 'cam': 1, 'lw': 1, 'rw': 1, 'st': 1},
    '4-2-3-1': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 3, 'st': 1},
    '4-1-4-1': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 1, 'cam': 4, 'st': 1},
    '4-3-1-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 3, 'cam': 1, 'st': 2},
    '3-4-2-1': {'gk': 1, 'cb': 3, 'cm': 2, 'lw': 2, 'st': 1},
    '4-2-2-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 2, 'st': 2},
    '4-5-1': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 3, 'cam': 2, 'st': 1},
    '3-4-1-2': {'gk': 1, 'cb': 3, 'cm': 4, 'cam': 1, 'st': 2},
    '4-1-3-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 1, 'cam': 3, 'st': 2},
    '3-1-4-2': {'gk': 1, 'cb': 3, 'cm': 1, 'cam': 4, 'st': 2},
    '5-2-3': {'gk': 1, 'cb': 3, 'lb': 1, 'rb': 1, 'cm': 2, 'lw': 1, 'rw': 1, 'st': 1}
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

active_auctions = {}

lineup_setup_state = {
    'user_id': None,
    'channel_id': None,
    'stage': None,
    'formation': None,
    'tactic': None,
    'selected_players': [],
    'position_counts': {pos: 0 for pos in available_positions},
    'required_counts': None
}

user_teams = {}

user_budgets = {}

user_lineups = {}

user_stats = {} # tracks wins/losses/draws/money_spent/most_expensive/trades_made

pending_trades = {}

STARTING_BUDGET = 1000000000

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

# DRAFT related state and commands
draft_state = {
    "active": False,
    "participants": [],
    "picked_players": {},
    "current_turn": 0,
    "turn_order": []
}

def format_currency(amount):
    return f"${amount:,}"

def load_data():
    global user_teams, user_budgets, user_lineups, user_stats
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        teams_path = os.path.join(DATA_DIR, "teams.json")
        budgets_path = os.path.join(DATA_DIR, "budgets.json")
        lineups_path = os.path.join(DATA_DIR, "lineups.json")
        stats_path = os.path.join(DATA_DIR, "stats.json")

        if os.path.exists(teams_path):
            with open(teams_path, "r", encoding='utf-8') as f:
                user_teams.update(json.load(f))
        if os.path.exists(budgets_path):
            with open(budgets_path, "r", encoding='utf-8') as f:
                user_budgets.update(json.load(f))
        if os.path.exists(lineups_path):
            with open(lineups_path, "r", encoding='utf-8') as f:
                user_lineups.update(json.load(f))
        if os.path.exists(stats_path):
            with open(stats_path, "r", encoding='utf-8') as f:
                user_stats.update(json.load(f))
        return True
    except Exception as e:
        print(f"Error loading data: {e}")
        return False

def save_data():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "teams.json"), "w", encoding='utf-8') as f:
            json.dump(user_teams, f, indent=2)
        with open(os.path.join(DATA_DIR, "budgets.json"), "w", encoding='utf-8') as f:
            json.dump(user_budgets, f, indent=2)
        with open(os.path.join(DATA_DIR, "lineups.json"), "w", encoding='utf-8') as f:
            json.dump(user_lineups, f, indent=2)
        with open(os.path.join(DATA_DIR, "stats.json"), "w", encoding='utf-8') as f:
            json.dump(user_stats, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

load_data()

def ensure_user_structures(user_id_str):
    if user_id_str not in user_budgets:
        user_budgets[user_id_str] = STARTING_BUDGET
    if user_id_str not in user_teams:
        user_teams[user_id_str] = []
    if user_id_str not in user_lineups:
        user_lineups[user_id_str] = {'players': [], 'tactic': 'Balanced', 'formation': '4-4-2'}
    if user_id_str not in user_stats:
        user_stats[user_id_str] = {
            'wins': 0, 'losses': 0, 'draws': 0,
            'money_spent': 0, 'most_expensive': 0, 'trades_made': 0
        }

# ---- FOOTY command update with mode selection ----
@bot.command(name="footy")
async def footy_cmd(ctx):
    prompt_msg = await ctx.send("⚽ Please type `auction` or `draft` to view commands for that mode.")

    def check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and m.content.lower() in ['auction', 'draft']

    try:
        reply = await bot.wait_for('message', timeout=30.0, check=check)
        if reply.content.lower() == 'auction':
            embed = discord.Embed(
                title="📘 Football Auction Bot – Auction Commands",
                color=discord.Color.blue()
            )
            embed.add_field(name="🟢 !startauction @user1 @user2 ...", value="Start a new auction with the mentioned participants.", inline=False)
            embed.add_field(name="🎯 !sets", value="Show all available auction sets.", inline=False)
            embed.add_field(name="👤 !participants", value="List all registered participants in the current auction.", inline=False)
            embed.add_field(name="➕ !add @user", value="Add a new participant to the ongoing auction.", inline=False)
            embed.add_field(name="➖ !remove @user", value="Remove a participant from the ongoing auction.", inline=False)
            embed.add_field(name="⚽ !st / !rw / !lw / !cam / !cm / !lb / !cb / !rb / !gk", value="Start auctioning a player for the specified position.", inline=False)
            embed.add_field(name="💸 !bid / !bid [amount]", value="Place a bid on the current player.", inline=False)
            embed.add_field(name="✅ !sold", value="Manually sell the current player to the highest bidder.", inline=False)
            embed.add_field(name="🚫 !unsold", value="Mark the current player as unsold.", inline=False)
            embed.add_field(name="📊 !status", value="Show the current auction status.", inline=False)
            embed.add_field(name="📁 !myplayers", value="View the list of players you own.", inline=False)
            embed.add_field(name="⚽ !setlineup", value="Set your team’s lineup and tactics.", inline=False)
            embed.add_field(name="📋 !viewlineup", value="View your current lineup.", inline=False)
            embed.add_field(name="⚽ !battle @user1 @user2", value="Simulate a match between two teams.", inline=False)
            embed.add_field(name="🏆 !rankteams", value="Rank all participant teams based on lineup strength.", inline=False)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="📘 Football Auction Bot – Draft Commands",
                color=discord.Color.green()
            )
            embed.add_field(name="🟢 !draft start", value="Start the draft mode.", inline=False)
            embed.add_field(name="👤 !participants", value="List all registered participants in the draft.", inline=False)
            embed.add_field(name="➕ !add @user", value="Add a participant to the draft.", inline=False)
            embed.add_field(name="📁 !myplayers", value="View the players you have picked in the draft.", inline=False)
            embed.add_field(name="⚽ !setlineup", value="Set your team’s lineup and tactics.", inline=False)
            embed.add_field(name="📋 !viewlineup", value="View your draft lineup.", inline=False)
            embed.add_field(name="⚽ !battle @user1 @user2", value="Simulate a match between two drafted teams.", inline=False)
            embed.add_field(name="🏆 !rankteams", value="Rank all draft teams.", inline=False)
            await ctx.send(embed=embed)
    except asyncio.TimeoutError:
        await ctx.send("⏰ No response received. Please run !footy again.")

# ---- Setlineup command with expanded formations ----
@bot.command()
async def setlineup(ctx):
    user_id = str(ctx.author.id)
    if user_id not in user_teams or not user_teams[user_id]:
        await ctx.send("You haven't bought any players yet. Use !myplayers to check.")
        return
    if lineup_setup_state['user_id'] is not None:
        await ctx.send("Another lineup setup is in progress. Please wait or try again later.")
        return
    lineup_setup_state['user_id'] = user_id
    lineup_setup_state['channel_id'] = ctx.channel.id
    lineup_setup_state['stage'] = 'formation'
    embed = discord.Embed(title="🎯 Select Formation",
                          description="Please choose a formation for your lineup:",
                          color=discord.Color.blue())
    embed.add_field(name="Available Formations", value=", ".join(available_formations.keys()), inline=False)
    embed.set_footer(text="Type the formation (e.g., '4-3-3'). 600s timeout.")
    await ctx.send(embed=embed)
    def check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and lineup_setup_state['user_id'] == user_id
    try:
        reply = await bot.wait_for('message', check=check, timeout=600.0)
        formation = reply.content.replace(' ', '-')
        if formation not in available_formations:
            await ctx.send(f"❌ Invalid Formation. Please choose from: {', '.join(available_formations.keys())}")
            lineup_setup_state['user_id'] = None
            return
        lineup_setup_state['formation'] = formation
        lineup_setup_state['required_counts'] = available_formations[formation]
        lineup_setup_state['stage'] = 'tactic'
        embed = discord.Embed(title="🎯 Select Tactic",
                              description="Please choose a tactic:",
                              color=discord.Color.blue())
        embed.add_field(name="Available Tactics", value=", ".join(available_tactics), inline=False)
        embed.set_footer(text="Type the tactic (e.g., 'Attacking')")
        await ctx.send(embed=embed)
        tactic_msg = await bot.wait_for('message', check=check, timeout=600.0)
        tactic = tactic_msg.content.capitalize()
        if tactic not in available_tactics:
            await ctx.send(f"❌ Invalid Tactic. Please choose from: {', '.join(available_tactics)}")
            lineup_setup_state['user_id'] = None
            return
        lineup_setup_state['tactic'] = tactic

        # Start player selection for positions based on formation
        lineup_setup_state['stage'] = next(pos for pos in available_positions[::-1] if lineup_setup_state['required_counts'].get(pos, 0) > 0)

        await prompt_for_player(ctx.channel, ctx.author, lineup_setup_state['stage'])
    except asyncio.TimeoutError:
        await ctx.send("⏰ Lineup setup timed out. Please run !setlineup again.")
        lineup_setup_state['user_id'] = None

async def prompt_for_player(channel, user, position):
    """Prompts the user to select a player for a specific position."""
    user_id = str(user.id)
    available_players = [p for p in user_teams.get(user_id, []) if p['position'].lower() == position and p not in lineup_setup_state['selected_players']]
    count_needed = lineup_setup_state['required_counts'].get(position, 0) - lineup_setup_state['position_counts'][position]
    if not available_players:
        embed = discord.Embed(title="❌ No Players Available",
                              description=f"You have no available {position.upper()} players for your lineup.",
                              color=discord.Color.red())
        await channel.send(embed=embed)
        reset_lineup_setup_state()
        return

    embed = discord.Embed(title=f"📋 Select {position.upper()} ({count_needed} needed)",
                          description=f"Please type the name or initial of a {position.upper()} player:",
                          color=discord.Color.blue())
    player_list = "\n".join([f"{p['name']} ({p['position'].upper()})" for p in available_players])
    embed.add_field(name="Available Players", value=player_list or "None", inline=False)
    embed.set_footer(text="Type the player name or initial (e.g., 'Messi' or 'L'). 600s timeout.")
    await channel.send(embed=embed)

# The on_message event handles lineup stage, player selection interactions as usual (adapt logic similarly)
# ... Include your existing on_message code logic here with minimal changes ...

def reset_lineup_setup_state():
    lineup_setup_state['user_id'] = None
    lineup_setup_state['channel_id'] = None
    lineup_setup_state['stage'] = None
    lineup_setup_state['formation'] = None
    lineup_setup_state['tactic'] = None
    lineup_setup_state['selected_players'] = []
    lineup_setup_state['position_counts'] = {pos: 0 for pos in available_positions}
    lineup_setup_state['required_counts'] = None

# ---- Rankteams command updated ----
@bot.command()
async def rankteams(ctx, method: str = "by_score"):
    """Ranks all participant teams. Methods: by_score, random, by_players."""
    if not user_teams:
        await ctx.send("No teams have been formed yet to rank.")
        return

    if ctx.channel.id in active_auctions and active_auctions[ctx.channel.id]['host'] == ctx.author.id:
        active_auctions[ctx.channel.id]['last_host_activity'] = time.time()

    team_scores = []
    for user_id, team_players in user_teams.items():
        if team_players:
            attack_score, defense_score = calculate_team_score_based_on_lineup(user_id)
            total_score = attack_score + defense_score
            try:
                user = await bot.fetch_user(int(user_id))
                display_name = user.display_name
            except discord.NotFound:
                display_name = f"Unknown User ({user_id})"

            team_scores.append((display_name, total_score, user_id, len(team_players)))

    if not team_scores:
        await ctx.send("No players have been bought by any participant yet.")
        return

    if method == "by_score":
        team_scores.sort(key=lambda x: x[1], reverse=True)
        method_text = "Team Score (Attack + Defense)"
    elif method == "random":
        random.shuffle(team_scores)
        method_text = "Random Order"
    elif method == "by_players":
        team_scores.sort(key=lambda x: x[3], reverse=True)
        method_text = "Number of Players"
    else:
        team_scores.sort(key=lambda x: x[1], reverse=True)
        method_text = "Team Score (Default)"

    embed = discord.Embed(
        title=f"🏆 Team Rankings ({method_text})",
        color=discord.Color.gold()
    )
    description_list = []
    for i, (name, score, user_id, num_players_in_team) in enumerate(team_scores):
        description_list.append(f"**{i+1}.** {name}: {score} points, {num_players_in_team} players")
    embed.description = "\n".join(description_list)
    embed.set_footer(text="Use !rankteams [method] to choose ranking style. Ex: !rankteams by_players")
    await ctx.send(embed=embed)

# ---- Draft commands as a separate gamemode ----
@bot.group(invoke_without_command=True)
async def draft(ctx):
    """Draft mode base command."""
    await ctx.send("📋 Use `!draft start` to begin the draft, `!draft pick <player>`, or `!draft end` to finish.")

@draft.command()
async def start(ctx):
    if draft_state["active"]:
        await ctx.send("Draft is already in progress!")
        return
    draft_state["active"] = True
    draft_state["participants"] = [ctx.author.id]
    draft_state["turn_order"] = [ctx.author.id]
    draft_state["picked_players"] = {ctx.author.id: []}
    draft_state["current_turn"] = 0
    await ctx.send("📋 Draft mode started! Use `!draft pick <player>` on your turn.")

@draft.command()
async def add(ctx, member: discord.Member):
    if not draft_state["active"]:
        await ctx.send("No draft is started yet.")
        return
    if member.id not in draft_state["participants"]:
        draft_state["participants"].append(member.id)
        draft_state["turn_order"].append(member.id)
        draft_state["picked_players"][member.id] = []
        await ctx.send(f"✅ {member.mention} has been added to this draft.")
    else:
        await ctx.send(f"{member.mention} is already in the draft.")

@draft.command()
async def pick(ctx, *, player_name):
    if not draft_state["active"]:
        await ctx.send("No draft is currently in progress.")
        return
    current_user_id = draft_state["turn_order"][draft_state["current_turn"]]
    if ctx.author.id != current_user_id:
        await ctx.send("It's not your turn to pick.")
        return
    draft_state["picked_players"].setdefault(ctx.author.id, []).append(player_name)
    draft_state["current_turn"] = (draft_state["current_turn"] + 1) % len(draft_state["turn_order"])
    await ctx.send(f"✅ {ctx.author.mention} picked **{player_name}**.")

@draft.command()
async def end(ctx):
    if not draft_state["active"]:
        await ctx.send("No draft is currently in progress.")
        return
    draft_state["active"] = False
    draft_state["participants"] = []
    draft_state["picked_players"] = {}
    draft_state["turn_order"] = []
    draft_state["current_turn"] = 0
    await ctx.send("📋 Draft mode ended.")

# ---- Rest of auction commands unchanged ----
# (You can keep your existing auction commands like !startauction, !bid, !sold, etc.)

# Important: Your existing on_message event and other internal logic
# should minimally adapt for the lineup setup logic to use the upgraded formation list.

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
