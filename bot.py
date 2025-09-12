import discord

player_form = {}  # {player_name: form_rating (0-10)}
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
    '4-4-2': {
        'gk': 1,
        'cb': 2,
        'lb': 1,
        'rb': 1,
        'cm': 2,
        'cam': 2,
        'st': 2
    },
    '4-3-3': {
        'gk': 1,
        'cb': 2,
        'lb': 1,
        'rb': 1,
        'cm': 1,
        'cam': 1,
        'lw': 1,
        'rw': 1,
        'st': 1
    },
    '4-2-3-1': {
        'gk': 1,
        'cb': 2,
        'lb': 1,
        'rb': 1,
        'cm': 2,
        'cam': 3,
        'st': 1
    },
    '3-5-2': {
        'gk': 1,
        'cb': 3,
        'cm': 2,
        'cam': 3,
        'st': 2
    },
    '3-4-3': {
        'gk': 1,
        'cb': 3,
        'cm': 2,
        'lw': 1,
        'rw': 1,
        'st': 1
    },
    '5-4-1': {
        'gk': 1,
        'cb': 3,
        'lb': 1,
        'rb': 1,
        'cm': 2,
        'cam': 2,
        'st': 1
    },
    '5-3-2': {
        'gk': 1,
        'cb': 3,
        'lb': 1,
        'rb': 1,
        'cm': 2,
        'cam': 1,
        'st': 2
    }
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
    'position_counts': {
        pos: 0
        for pos in available_positions
    },
    'required_counts': None
}

user_teams = {}
user_budgets = {}
# Multiple lineups per user: user_lineups[user_id][lineup_name] = {...}
user_lineups = {}
# Track which lineup each user is currently using for battles
active_lineups = {}
user_stats = {
}  # new: tracks wins/losses/draws/money_spent/most_expensive/trades_made
tournaments = {}  # new: running tournaments (kept in-memory + saved)
pending_trades = {}  # new: trade proposals {trade_id: {...}}

# Additional game mode state variables
koth_state = {}  # King of the Hill state
draft_clash_sessions = {}  # Draft clash sessions
mystery_boxes = {}  # Mystery box system

# KoTH file paths
KOTH_AUCTION_FILE = "data/koth_auction.json"
KOTH_DRAFT_FILE = "data/koth_draft.json"

STARTING_BUDGET = 1000000000
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def format_currency(amount):
    """Formats a numerical amount into a currency string."""
    return f"${amount:,}"


def load_players_by_position(position, set_name):
    """Loads players from a specific set and position, assigning tiers."""
    base_dir = os.path.dirname(__file__)
    filename = os.path.join(base_dir, 'players', set_name,
                            f'{position.lower()}.json')

    print(f"Attempting to load: {filename}")

    if not os.path.exists(filename):
        print(f"File not found: {filename}")
        return {'A': [], 'B': [], 'C': []}

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            players = json.load(f)
            if not isinstance(players, list):
                print(f"Invalid data format in {filename}: Expected a list")
                return {'A': [], 'B': [], 'C': []}
            print(
                f"Loaded players for {position} from {set_name}: {len(players)} players"
            )
            tiered_players = {'A': [], 'B': [], 'C': []}
            for player in players:
                if not isinstance(
                        player, dict
                ) or 'name' not in player or 'position' not in player:
                    print(
                        f"Skipping invalid player data in {filename}: {player}"
                    )
                    continue

                if 'base_price' not in player:
                    tier = random.choice(['A', 'B', 'C'])
                    if tier == 'A':
                        player['base_price'] = random.randint(40, 50) * 1000000
                    elif tier == 'B':
                        player['base_price'] = random.randint(25, 39) * 1000000
                    else:  # tier == 'C'
                        player['base_price'] = random.randint(1, 24) * 1000000
                else:
                    base_price = player['base_price']
                    if not isinstance(
                            base_price, (int, float)
                    ) or base_price < MIN_BASE_PRICE or base_price > MAX_BASE_PRICE:
                        print(
                            f"Invalid base_price for {player.get('name', 'Unknown')} in {filename}: {base_price}"
                        )
                        tier = random.choice(['A', 'B', 'C'])
                        if tier == 'A':
                            player['base_price'] = random.randint(40,
                                                                  50) * 1000000
                        elif tier == 'B':
                            player['base_price'] = random.randint(25,
                                                                  39) * 1000000
                        else:  # tier == 'C'
                            player['base_price'] = random.randint(1,
                                                                  24) * 1000000
                    else:
                        if 40000000 <= base_price <= 50000000:
                            tier = 'A'
                        elif 25000000 <= base_price <= 39000000:
                            tier = 'B'
                        else:
                            tier = 'C'

                player['tier'] = tier
                tiered_players[tier].append(player)

            for tier in tiered_players:
                random.shuffle(tiered_players[tier])

            return tiered_players
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"Error loading {filename}: {e}")
        return {'A': [], 'B': [], 'C': []}
    except Exception as e:
        print(f"Unexpected error loading {filename}: {e}")
        return {'A': [], 'B': [], 'C': []}


def save_data():
    """Saves all game data."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Save core data
        data_files = {
            "teams.json": user_teams,
            "budgets.json": user_budgets, 
            "lineups.json": user_lineups,
            "stats.json": user_stats,
            "tournaments.json": tournaments
        }
        
        for filename, data in data_files.items():
            with open(os.path.join(DATA_DIR, filename), "w", encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                
        # Save gamemode data
        gamemode_files = {
            "koth.json": koth_state,
            "draftclash.json": draft_clash_sessions,
            "mystery_boxes.json": mystery_boxes
        }
        
        for filename, data in gamemode_files.items():
            with open(os.path.join(DATA_DIR, filename), "w", encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                
        return True
        
    except Exception as e:
        print(f"Error saving data: {e}")
        return False
    # --- Extra gamemodes persistence (added by patch) ---
    try:
        with open(os.path.join(DATA_DIR, "koth.json"), "w",
                  encoding='utf-8') as f:
            json.dump(koth_state, f, indent=2)
        with open(os.path.join(DATA_DIR, "draftclash.json"),
                  "w",
                  encoding='utf-8') as f:
            json.dump(draft_clash_sessions, f, indent=2)
        with open(os.path.join(DATA_DIR, "mystery_boxes.json"),
                  "w",
                  encoding='utf-8') as f:
            json.dump(mystery_boxes, f, indent=2)
    except Exception as e:
        print(f"Error saving extra data: {e}")

    return True


def load_data():
    """Loads user teams, budgets, lineups, stats, and tournaments from JSON files."""
    global user_teams, user_budgets, user_lineups, user_stats, tournaments
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        teams_path = os.path.join(DATA_DIR, "teams.json")
        budgets_path = os.path.join(DATA_DIR, "budgets.json")
        lineups_path = os.path.join(DATA_DIR, "lineups.json")
        stats_path = os.path.join(DATA_DIR, "stats.json")
        tournaments_path = os.path.join(DATA_DIR, "tournaments.json")
        if os.path.exists(teams_path):
            with open(teams_path, "r", encoding='utf-8') as f:
                user_teams = json.load(f)
        if os.path.exists(budgets_path):
            with open(budgets_path, "r", encoding='utf-8') as f:
                user_budgets = json.load(f)
        if os.path.exists(lineups_path):
            with open(lineups_path, "r", encoding='utf-8') as f:
                user_lineups = json.load(f)
        if os.path.exists(stats_path):
            with open(stats_path, "r", encoding='utf-8') as f:
                user_stats = json.load(f)
        if os.path.exists(tournaments_path):
            with open(tournaments_path, "r", encoding='utf-8') as f:
                tournaments = json.load(f)
    except Exception as e:
        print(f"Error loading data: {e}")
        return False
    # --- Load extra gamemodes persistence (added by patch) ---
    try:
        koth_path = os.path.join(DATA_DIR, "koth.json")
        if os.path.exists(koth_path):
            with open(koth_path, "r", encoding='utf-8') as f:
                tmp = json.load(f)
                if isinstance(tmp, dict):
                    koth_state.update(tmp)
        dc_path = os.path.join(DATA_DIR, "draftclash.json")
        if os.path.exists(dc_path):
            with open(dc_path, "r", encoding='utf-8') as f:
                tmp = json.load(f)
                if isinstance(tmp, dict):
                    draft_clash_sessions.update(tmp)
        mb_path = os.path.join(DATA_DIR, "mystery_boxes.json")
        if os.path.exists(mb_path):
            with open(mb_path, "r", encoding='utf-8') as f:
                tmp = json.load(f)
                if isinstance(tmp, dict):
                    mystery_boxes.update(tmp)
    except Exception as e:
        print(f"Error loading extra data: {e}")

    return True


load_data()


def ensure_user_structures(user_id_str):
    """Ensure minimal user keys exist across structures."""
    if user_id_str not in user_budgets:
        user_budgets[user_id_str] = STARTING_BUDGET
    if user_id_str not in user_teams:
        user_teams[user_id_str] = []
    if user_id_str not in user_lineups:
        user_lineups[user_id_str] = {}
        active_lineups[user_id_str] = 'main'
    if 'main' not in user_lineups[user_id_str]:
        user_lineups[user_id_str]['main'] = {
            'players': [],
            'tactic': 'Balanced',
            'formation': '4-4-2'
        }
    if user_id_str not in user_stats:
        user_stats[user_id_str] = {
            'wins': 0,
            'losses': 0,
            'draws': 0,
            'money_spent': 0,
            'most_expensive': 0,
            'trades_made': 0
        }


@bot.event
async def on_ready():
    """Event that fires when the bot successfully connects to Discord."""
    print(f'Logged in as {bot.user}')


@bot.event
async def on_message(message):
    """Handles incoming messages for set selection, lineup setup, and host activity."""
    if message.author.bot:
        return

    message_consumed = False

    # Update host last activity time if message is from host
    auction_state_for_channel = active_auctions.get(message.channel.id)
    if auction_state_for_channel and message.author.id == auction_state_for_channel[
            'host']:
        auction_state_for_channel['last_host_activity'] = time.time()

    if (auction_state_for_channel
            and auction_state_for_channel['awaiting_set_selection']
            and message.author.id
            == auction_state_for_channel['set_selection_author']):

        set_key = message.content.lower().strip()
        print(
            f"DEBUG (on_message): Awaiting set selection. Received set_key: '{set_key}'"
        )

        if set_key in available_sets:
            print(
                f"DEBUG (on_message): Set key '{set_key}' found in available_sets."
            )
            auction_state_for_channel['current_set'] = set_key
            auction_state_for_channel['awaiting_set_selection'] = False
            auction_state_for_channel['set_selection_author'] = None
            auction_state_for_channel['tier_counters'] = {
                pos: {
                    'A': 0,
                    'B': 0,
                    'C': 0
                }
                for pos in available_positions
            }

            all_positions_loaded_successfully = True
            error_positions = []
            for pos in available_positions:
                tiered_players = load_players_by_position(pos, set_key)
                auction_state_for_channel['player_queues'][
                    pos] = tiered_players
                if not any(tiered_players[tier] for tier in ['A', 'B', 'C']):
                    all_positions_loaded_successfully = False
                    error_positions.append(pos.upper())

            if all_positions_loaded_successfully:
                embed = discord.Embed(
                    title="🎉 Auction Started",
                    description=
                    f"**Set Selected:** {available_sets[set_key]}\n\nOnly the host or <@{PRIVILEGED_USER_ID}> can run position commands and !endauction.",
                    color=discord.Color.green())
                embed.set_footer(
                    text="Only registered users can bid. Good luck!")
                await message.channel.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="⚠️ Set Loaded with Warnings",
                    description=
                    f"**Set Selected:** {available_sets[set_key]}\n\nNo players available for positions: {', '.join(error_positions)}.",
                    color=discord.Color.orange())
                await message.channel.send(embed=embed)
            message_consumed = True
        else:
            print(f"DEBUG (on_message): Set key '{set_key}' NOT found.")
            embed = discord.Embed(
                title="❌ Invalid Set",
                description="Please choose from the available sets:",
                color=discord.Color.red())
            set_list = "\n".join([
                f"**{key}** - {name}" for key, name in available_sets.items()
            ])
            embed.add_field(name="Available Sets",
                            value=set_list,
                            inline=False)
            await message.channel.send(embed=embed)
            message_consumed = True

    if (lineup_setup_state['user_id'] == str(message.author.id)
            and message.channel.id == lineup_setup_state['channel_id']
            and lineup_setup_state['stage'] is not None):

        content = message.content.strip().lower()
        if lineup_setup_state['stage'] == 'formation':
            formation = content.replace(' ', '-')
            if formation in available_formations:
                lineup_setup_state['formation'] = formation
                lineup_setup_state['required_counts'] = available_formations[
                    formation]
                lineup_setup_state['stage'] = 'tactic'
                embed = discord.Embed(title="🎯 Select Tactic",
                                      description="Please choose a tactic:",
                                      color=discord.Color.blue())
                embed.add_field(name="Available Tactics",
                                value=", ".join(available_tactics),
                                inline=False)
                embed.set_footer(text="Type the tactic (e.g., 'Attacking')")
                await message.channel.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ Invalid Formation",
                    description=
                    f"Please choose from: {', '.join(available_formations.keys())}",
                    color=discord.Color.red())
                await message.channel.send(embed=embed)
            message_consumed = True

        elif lineup_setup_state['stage'] == 'tactic':
            tactic = content.capitalize()
            if tactic in available_tactics:
                lineup_setup_state['tactic'] = tactic
                lineup_setup_state['stage'] = available_positions[
                    -1]  # Start with 'gk'
                await prompt_for_player(message.channel, message.author,
                                        lineup_setup_state['stage'])
            else:
                embed = discord.Embed(
                    title="❌ Invalid Tactic",
                    description=
                    f"Please choose from: {', '.join(available_tactics)}",
                    color=discord.Color.red())
                await message.channel.send(embed=embed)
            message_consumed = True

        else:  # Stage is a position (st, rw, lw, cam, cm, lb, cb, rb, gk)
            pos = lineup_setup_state['stage']
            user_id = lineup_setup_state['user_id']
            player_name_input = content
            available_players = user_teams.get(user_id, [])

            matched_player = None
            for player in available_players:
                full_name = player['name'].lower()
                first_initial = full_name.split(
                )[0][0] if ' ' in full_name else full_name[0]
                last_initial = full_name.split(
                )[-1][0] if ' ' in full_name else full_name[0]

                if (full_name == player_name_input
                        or (len(player_name_input) == 1 and
                            (first_initial == player_name_input
                             or last_initial == player_name_input))
                        or any(part.lower().startswith(player_name_input)
                               for part in full_name.split())):
                    if player['position'].lower(
                    ) == pos and player not in lineup_setup_state[
                            'selected_players']:
                        matched_player = player
                        break

            if not matched_player:
                embed = discord.Embed(
                    title="❌ Invalid Player",
                    description=
                    f"Player '{content}' is not in your team or doesn't match the {pos.upper()} position. Use !myplayers to check.",
                    color=discord.Color.red())
                await message.channel.send(embed=embed)
                return

            if matched_player in lineup_setup_state['selected_players']:
                embed = discord.Embed(
                    title="❌ Player Already Selected",
                    description=
                    f"{matched_player['name']} is already in your lineup.",
                    color=discord.Color.red())
                await message.channel.send(embed=embed)
                return

            lineup_setup_state['selected_players'].append(matched_player)
            lineup_setup_state['position_counts'][pos] += 1

            next_pos = None
            for p in available_positions[::-1]:
                if lineup_setup_state['position_counts'][
                        p] < lineup_setup_state['required_counts'].get(p, 0):
                    next_pos = p
                    break

            if next_pos:
                lineup_setup_state['stage'] = next_pos
                await prompt_for_player(message.channel, message.author,
                                        next_pos)
            else:
                lineup_name = lineup_setup_state.get('lineup_name', 'main')
                if user_id not in user_lineups:
                    user_lineups[user_id] = {}
                    active_lineups[user_id] = 'main'
                user_lineups[user_id][lineup_name] = {
                    'players': lineup_setup_state['selected_players'],
                    'tactic': lineup_setup_state['tactic'],
                    'formation': lineup_setup_state['formation']
                }
                if not save_data():
                    await message.channel.send(
                        "⚠️ Error saving lineup data. Please try again.")
                embed = discord.Embed(title="✅ Lineup Set",
                                      color=discord.Color.green())
                embed.add_field(name="Formation",
                                value=lineup_setup_state['formation'].upper(),
                                inline=True)
                embed.add_field(name="Tactic",
                                value=lineup_setup_state['tactic'],
                                inline=True)
                embed.add_field(
                    name="Lineup",
                    value="\n".join([
                        f"{p['name']} ({p['position'].upper()})"
                        for p in lineup_setup_state['selected_players']
                    ]),
                    inline=False)
                embed.set_footer(
                    text=
                    "Use !viewlineup to check your lineup or !setlineup to change it."
                )
                await message.channel.send(embed=embed)
                reset_lineup_setup_state()
            message_consumed = True

    if not message_consumed:
        await bot.process_commands(message)


async def prompt_for_player(channel, user, position):
    """Prompts the user to select a player for a specific position."""
    user_id = str(user.id)
    available_players = [
        p for p in user_teams.get(user_id, [])
        if p['position'].lower() == position
        and p not in lineup_setup_state['selected_players']
    ]
    count_needed = lineup_setup_state['required_counts'].get(
        position, 0) - lineup_setup_state['position_counts'][position]

    if not available_players:
        embed = discord.Embed(
            title="❌ No Players Available",
            description=
            f"You have no available {position.upper()} players for your lineup.",
            color=discord.Color.red())
        await channel.send(embed=embed)
        reset_lineup_setup_state()
        return

    embed = discord.Embed(
        title=f"📋 Select {position.upper()} ({count_needed} needed)",
        description=
        f"Please type the name or initial of a {position.upper()} player:",
        color=discord.Color.blue())
    player_list = "\n".join(
        [f"{p['name']} ({p['position'].upper()})" for p in available_players])
    embed.add_field(name="Available Players",
                    value=player_list or "None",
                    inline=False)
    embed.set_footer(
        text=
        "Type the player name or initial (e.g., 'Messi' or 'L'). 600s timeout."
    )
    await channel.send(embed=embed)


def reset_lineup_setup_state():
    """Resets the lineup setup state."""
    lineup_setup_state['user_id'] = None
    lineup_setup_state['channel_id'] = None
    lineup_setup_state['stage'] = None
    lineup_setup_state['formation'] = None
    lineup_setup_state['tactic'] = None
    lineup_setup_state['selected_players'] = []
    lineup_setup_state['position_counts'] = {
        pos: 0
        for pos in available_positions
    }
    lineup_setup_state['required_counts'] = None
    lineup_setup_state['lineup_name'] = 'main'


@bot.event
async def on_reaction_add(reaction, user):
    """Handles reactions for bidding and passing."""
    if user.bot:
        return

    auction_state = active_auctions.get(reaction.message.channel.id)
    if not auction_state or not auction_state['bidding'] or not auction_state[
            'current_player']:
        return

    if str(user.id) not in auction_state['participants']:
        return

    if auction_state['host'] == user.id:
        auction_state['last_host_activity'] = time.time()

    if str(reaction.emoji) == '💰':
        fake_ctx = type(
            'obj', (object, ), {
                'author': user,
                'send': reaction.message.channel.send,
                'channel': reaction.message.channel
            })
        await bid(fake_ctx)
    elif str(reaction.emoji) == '❌':
        await handle_pass_reaction(user, reaction.message.channel)


async def handle_pass_reaction(user, channel):
    """Handles a user passing on a player."""
    auction_state = active_auctions.get(channel.id)
    if not auction_state:
        return

    user_id = str(user.id)
    if user_id not in auction_state['participants']:
        return

    if auction_state['host'] == user.id:
        auction_state['last_host_activity'] = time.time()

    auction_state['pass_votes'].add(user_id)

    remaining = auction_state['participants'] - auction_state['pass_votes']

    if not remaining:
        player = auction_state['current_player']
        auction_state['bidding'] = False
        auction_state['current_player'] = None
        auction_state['current_price'] = 0
        auction_state['highest_bidder'] = None
        if auction_state['timeout_task']:
            auction_state['timeout_task'].cancel()
        auction_state['pass_votes'].clear()
        auction_state['unsold_players'].add(player['name'])

        embed = discord.Embed(
            title="🚫 Player Unsold",
            description=
            f"**{player['name']}** received no bids and goes unsold.",
            color=discord.Color.red())
        await channel.send(embed=embed)
    else:
        embed = discord.Embed(
            title="⚠️ Player Passed",
            description=
            f"{user.display_name} passed. Waiting for {len(remaining)} more to pass.",
            color=discord.Color.orange())
        await channel.send(embed=embed)


async def check_host_activity(channel_id):
    """Checks if the host is inactive for too long and ends the auction."""
    while channel_id in active_auctions:
        auction_state = active_auctions.get(channel_id)
        if not auction_state:
            break

        current_time = time.time()
        last_activity = auction_state.get('last_host_activity', current_time)

        if current_time - last_activity > HOST_TIMEOUT:
            if auction_state['timeout_task']:
                auction_state['timeout_task'].cancel()

            participants = auction_state['participants'].copy()
            for user_id in participants:
                user_budgets[user_id] = STARTING_BUDGET
                user_teams[user_id] = []
                user_lineups[user_id] = {
                    'players': [],
                    'tactic': 'Balanced',
                    'formation': '4-4-2'
                }

            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(
                    "🔚 Auction ended due to host inactivity for 5 minutes. Participant budgets, teams, and lineups have been reset."
                )

            del active_auctions[channel_id]
            save_data()
            break

        await asyncio.sleep(60)  # Check every minute


@bot.command()
async def startauction(ctx, *members: discord.Member, timer: int = 30):
    """Starts a new auction without player limitations."""
    if ctx.channel.id in active_auctions:
        await ctx.send("❌ An auction is already active in this channel.")
        return

    active_auctions[ctx.channel.id] = {
        "current_player": None,
        "bidding": False,
        "bids": {},
        "player_queues": {},
        "timeout_task": None,
        "current_price": 0,
        "highest_bidder": None,
        "host": ctx.author.id,
        "participants": set(),
        "channel": ctx.channel.id,
        "current_set": None,
        "awaiting_set_selection": False,
        "set_selection_author": None,
        "pass_votes": set(),
        "tier_counters": {pos: {'A': 0, 'B': 0, 'C': 0} for pos in available_positions},
        "last_sold_player": None,
        "last_sold_buyer_id": None,
        "last_sold_price": 0,
        "unsold_players": set(),
        "last_host_activity": time.time()
    }

    auction_state = active_auctions[ctx.channel.id]
    auction_state['participants'].add(str(ctx.author.id))
    for m in members:
        auction_state['participants'].add(str(m.id))

    for participant_id in auction_state['participants']:
        ensure_user_structures(participant_id)

    embed = discord.Embed(
        title="🎯 Select Auction Set",
        description="Please choose which set you want to auction:",
        color=discord.Color.blue())

    set_list = "\n".join([f"**{key}** - {name}" for key, name in available_sets.items()])
    embed.add_field(name="Available Sets", value=set_list, inline=False)
    embed.set_footer(text="Type the set key (e.g., 'wc' for World Cup XI)")
    
    await ctx.send(embed=embed)
    
    auction_state['awaiting_set_selection'] = True
    auction_state['set_selection_author'] = ctx.author.id
    bot.loop.create_task(check_host_activity(ctx.channel.id))


@bot.command()
async def sets(ctx):
    """Shows all available auction sets."""
    embed = discord.Embed(title="🎯 Available Auction Sets",
                          description="Here are all the available sets:",
                          color=discord.Color.blue())

    set_list = "\n".join(
        [f"**{key}** - {name}" for key, name in available_sets.items()])
    embed.add_field(name="Sets", value=set_list, inline=False)
    embed.set_footer(text="Use these keys when starting an auction")

    await ctx.send(embed=embed)


@bot.command()
async def participants(ctx):
    """Lists all registered participants in the current auction."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if auction_state['host'] == ctx.author.id:
        auction_state['last_host_activity'] = time.time()

    users = []
    for uid in auction_state['participants']:
        try:
            user = await bot.fetch_user(int(uid))
            users.append(f"<@{uid}>")
        except:
            users.append(f"Unknown User ({uid})")

    current_set_name = available_sets.get(auction_state['current_set'],
                                          'No set selected')

    embed = discord.Embed(title="👥 Registered Participants",
                          description="\n".join(users),
                          color=discord.Color.green())
    embed.add_field(name="Current Set", value=current_set_name, inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def add(ctx, member: discord.Member):
    """Adds a new participant to the ongoing auction."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state[
            'host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send(
            "Only the auction host can add participants to this auction.")
        return

    if auction_state['host'] == ctx.author.id:
        auction_state['last_host_activity'] = time.time()

    if str(member.id) in auction_state['participants']:
        await ctx.send(f"❌ {member.display_name} is already a participant.")
        return

    auction_state['participants'].add(str(member.id))
    ensure_user_structures(str(member.id))

    await ctx.send(f"✅ {member.mention} has been added to this auction.")


@bot.command()
async def remove(ctx, member: discord.Member):
    """Removes a participant from the auction with confirmation."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state[
            'host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send(
            "Only the auction host can remove participants from this auction.")
        return

    if auction_state['host'] == ctx.author.id:
        auction_state['last_host_activity'] = time.time()

    if str(member.id) not in auction_state['participants']:
        await ctx.send(
            f"❌ {member.mention} is not a participant in this auction.")
        return

    confirm_msg = await ctx.send(
        f"⚠️ Are you sure you want to remove {member.mention} from this auction? React with ✅ to confirm."
    )
    await confirm_msg.add_reaction("✅")

    def check(reaction, user):
        return user == ctx.author and str(
            reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id

    try:
        await bot.wait_for('reaction_add', timeout=15.0, check=check)
        auction_state['participants'].remove(str(member.id))
        await ctx.send(
            f"❌ {member.mention} has been removed from this auction.")
    except asyncio.TimeoutError:
        await ctx.send("⏰ Removal cancelled. No confirmation received in time."
                       )


@bot.command()
async def setlineup(ctx, lineup_name: str = 'main'):
    """Starts an interactive process to set the user's lineup."""
    user_id = str(ctx.author.id)
    if user_id not in user_teams or not user_teams[user_id]:
        await ctx.send(
            "You haven't bought any players yet. Use !myplayers to check.")
        return

    if lineup_setup_state['user_id'] is not None:
        await ctx.send(
            "Another lineup setup is in progress. Please wait or try again later."
        )
        return

    lineup_setup_state['user_id'] = user_id
    lineup_setup_state['channel_id'] = ctx.channel.id
    lineup_setup_state['stage'] = 'formation'
    lineup_setup_state['lineup_name'] = lineup_name.lower()

    embed = discord.Embed(
        title="🎯 Select Formation",
        description="Please choose a formation for your lineup:",
        color=discord.Color.blue())
    embed.add_field(name="Available Formations",
                    value=", ".join(available_formations.keys()),
                    inline=False)
    embed.set_footer(text="Type the formation (e.g., '4-3-3'). 600s timeout.")
    await ctx.send(embed=embed)

    def check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and lineup_setup_state[
            'user_id'] == user_id

    try:
        await bot.wait_for('message', check=check, timeout=600.0)
    except asyncio.TimeoutError:
        if lineup_setup_state['user_id'] == user_id and lineup_setup_state[
                'stage'] is not None:
            await ctx.send(
                "⏰ Lineup setup timed out. Please run !setlineup again.")
            reset_lineup_setup_state()


@bot.command()
async def viewlineup(ctx):
    """Displays the user's current lineup, formation, and tactic."""
    user_id = str(ctx.author.id)
    if user_id not in user_lineups or not user_lineups[user_id]['players']:
        await ctx.send(
            "You haven't set a lineup yet. Use !setlineup to create one.")
        return

    lineup = user_lineups[user_id]
    embed = discord.Embed(title=f"📋 {ctx.author.display_name}'s Lineup",
                          color=discord.Color.teal())
    embed.add_field(name="Formation",
                    value=lineup['formation'].upper(),
                    inline=True)
    embed.add_field(name="Tactic", value=lineup['tactic'], inline=True)
    embed.add_field(name="Players",
                    value="\n".join([
                        f"{p['name']} ({p['position'].upper()})"
                        for p in lineup['players']
                    ]),
                    inline=False)
    await ctx.send(embed=embed)


def create_position_command(position):
    """Dynamically creates a command for each player position (e.g., !st, !rw)."""

    @bot.command(name=position)
    async def _position(ctx):
        auction_state = active_auctions.get(ctx.channel.id)
        if not auction_state:
            await ctx.send(
                "No auction is currently running in this channel. Please start one with `!startauction`."
            )
            return

        if ctx.author.id != auction_state[
                'host'] and ctx.author.id != PRIVILEGED_USER_ID:
            await ctx.send(
                "Only the auction host can run this command in this auction.")
            return

        if auction_state['host'] == ctx.author.id:
            auction_state['last_host_activity'] = time.time()

        if auction_state['current_set'] is None:
            await ctx.send(
                "❌ No set has been selected for this auction. The host needs to select a set first."
            )
            return

        tiered_queues = auction_state['player_queues'].get(position)
        if not tiered_queues or not any(tiered_queues[tier]
                                        for tier in ['A', 'B', 'C']):
            await ctx.send(
                f"No players left for **{position.upper()}** in the {available_sets[auction_state['current_set']]} set in this auction. Use !bid <player_name> <price> to auction a custom player."
            )
            return

        if auction_state['timeout_task']:
            auction_state['timeout_task'].cancel()

        auction_state['pass_votes'].clear()

        tier_counter = auction_state['tier_counters'][position]
        total_auctioned = sum(tier_counter.values())
        cycle_position = total_auctioned % 11  # 3A + 5B + 3C = 11 players per cycle

        if cycle_position < 3:
            tier = 'A'
        elif cycle_position < 8:
            tier = 'B'
        else:
            tier = 'C'

        if not tiered_queues[tier]:
            for fallback_tier in ['A', 'B', 'C']:
                if tiered_queues[fallback_tier]:
                    tier = fallback_tier
                    break
            else:
                await ctx.send(
                    f"No players left for **{position.upper()}** in the {available_sets[auction_state['current_set']]} set in this auction. Use !bid <player_name> <price> to auction a custom player."
                )
                return

        player = tiered_queues[tier].pop(0)
        tier_counter[tier] += 1
        auction_state['current_player'] = player
        auction_state['bidding'] = True
        auction_state['bids'] = {}
        auction_state['current_price'] = player.get('base_price',
                                                    MIN_BASE_PRICE)
        auction_state['highest_bidder'] = None

        embed = discord.Embed(title="🔨 Player Up for Auction",
                              color=discord.Color.gold())
        embed.add_field(name="Name", value=player['name'], inline=True)
        embed.add_field(name="Position",
                        value=player.get('position', 'Unknown').upper(),
                        inline=True)
        embed.add_field(name="League",
                        value=player.get('league', 'Unknown'),
                        inline=True)
        embed.add_field(name="Set",
                        value=available_sets[auction_state['current_set']],
                        inline=True)
        embed.add_field(name="Starting Price",
                        value=format_currency(auction_state['current_price']),
                        inline=False)
        embed.set_footer(
            text=
            "Use !bid or !bid [amount] to place a bid. React with 💰 to bid, ❌ to pass."
        )

        message = await ctx.send(embed=embed)
        await message.add_reaction("💰")
        await message.add_reaction("❌")

        async def auto_sold():
            try:
                if not auction_state.get('bidding',
                                         False) or auction_state.get(
                                             'current_player') != player:
                    return
                await asyncio.sleep(7)
                if not auction_state.get('bidding',
                                         False) or auction_state.get(
                                             'current_player') != player:
                    return
                await ctx.send("⌛ Going once...")
                await asyncio.sleep(1)
                if not auction_state.get('bidding',
                                         False) or auction_state.get(
                                             'current_player') != player:
                    return
                await ctx.send("⌛ Going twice...")
                await asyncio.sleep(1)
                if not auction_state.get('bidding',
                                         False) or auction_state.get(
                                             'current_player') != player:
                    return
                await ctx.send("⌛ Final call...")
                await asyncio.sleep(1)
                if not auction_state.get('bidding',
                                         False) or auction_state.get(
                                             'current_player') != player:
                    return
                await _finalize_sold(ctx)
            except asyncio.CancelledError:
                pass

        auction_state['timeout_task'] = bot.loop.create_task(auto_sold())


for pos in available_positions:
    create_position_command(pos)


@bot.command()
async def bid(ctx, *args):
    """Allows a participant to place a bid on the current player or start a custom player auction."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if auction_state['host'] == ctx.author.id:
        auction_state['last_host_activity'] = time.time()

    # Handle custom bid for a new player (e.g., !bid "Player Name" 10m)
    if len(args) >= 2:
        if ctx.author.id != auction_state[
                'host'] and ctx.author.id != PRIVILEGED_USER_ID:
            await ctx.send(
                "Only the auction host can start a custom player auction.")
            return

        if auction_state['bidding'] or auction_state['current_player']:
            await ctx.send(
                "A player is currently being auctioned. Please wait until the current auction ends."
            )
            return

        # Parse player name and price
        price_str = args[-1].strip().lower().replace(",", "")
        player_name = " ".join(args[:-1]).strip()

        multiplier = 1
        if price_str.endswith("m"):
            multiplier = 1_000_000
            price_str = price_str[:-1]
        elif price_str.endswith("k"):
            multiplier = 1_000
            price_str = price_str[:-1]

        try:
            start_price = int(float(price_str) * multiplier)
            if start_price < MIN_BASE_PRICE or start_price > MAX_BASE_PRICE:
                await ctx.send(
                    f"Starting price must be between {format_currency(MIN_BASE_PRICE)} and {format_currency(MAX_BASE_PRICE)}."
                )
                return
        except ValueError:
            await ctx.send(
                "❌ Invalid price format. Use numbers like 10m or 1000000.")
            return

        # Check if player has been sold or unsold
        for user_id, team in user_teams.items():
            for player in team:
                if player['name'].lower() == player_name.lower():
                    await ctx.send(
                        f"❌ Player **{player_name}** has already been sold.")
                    return

        if player_name.lower() in auction_state['unsold_players']:
            await ctx.send(
                f"❌ Player **{player_name}** was previously marked as unsold in this auction."
            )
            return

        # Create a custom player
        tier = 'C'  # Default to C-tier for custom players
        if start_price >= 40000000:
            tier = 'A'
        elif start_price >= 25000000:
            tier = 'B'

        custom_player = {
            'name': player_name,
            'position': 'unknown',  # Position not specified
            'league': 'Custom',
            'base_price': start_price,
            'tier': tier
        }

        auction_state['current_player'] = custom_player
        auction_state['bidding'] = True
        auction_state['bids'] = {}
        auction_state['current_price'] = start_price
        auction_state['highest_bidder'] = None
        auction_state['pass_votes'].clear()

        if auction_state['timeout_task']:
            auction_state['timeout_task'].cancel()

        embed = discord.Embed(title="🔨 Custom Player Up for Auction",
                              color=discord.Color.gold())
        embed.add_field(name="Name", value=custom_player['name'], inline=True)
        embed.add_field(name="Position", value="Custom", inline=True)
        embed.add_field(name="League", value="Custom", inline=True)
        embed.add_field(name="Set",
                        value=available_sets.get(auction_state['current_set'],
                                                 'Custom'),
                        inline=True)
        embed.add_field(name="Starting Price",
                        value=format_currency(start_price),
                        inline=False)
        embed.set_footer(
            text=
            "Use !bid or !bid [amount] to place a bid. React with 💰 to bid, ❌ to pass."
        )

        message = await ctx.send(embed=embed)
        await message.add_reaction("💰")
        await message.add_reaction("❌")

        async def auto_sold():
            try:
                if not auction_state.get(
                        'bidding', False) or auction_state.get(
                            'current_player') != custom_player:
                    return
                await asyncio.sleep(7)
                if not auction_state.get(
                        'bidding', False) or auction_state.get(
                            'current_player') != custom_player:
                    return
                await ctx.send("⌛ Going once...")
                await asyncio.sleep(1)
                if not auction_state.get(
                        'bidding', False) or auction_state.get(
                            'current_player') != custom_player:
                    return
                await ctx.send("⌛ Going twice...")
                await asyncio.sleep(1)
                if not auction_state.get(
                        'bidding', False) or auction_state.get(
                            'current_player') != custom_player:
                    return
                await ctx.send("⌛ Final call...")
                await asyncio.sleep(1)
                if not auction_state.get(
                        'bidding', False) or auction_state.get(
                            'current_player') != custom_player:
                    return
                await _finalize_sold(ctx)
            except asyncio.CancelledError:
                pass

        auction_state['timeout_task'] = bot.loop.create_task(auto_sold())
        return

    # Handle regular bid
    if not auction_state['bidding'] or not auction_state['current_player']:
        await ctx.send("No player is currently up for bidding in this channel."
                       )
        return

    user_id = str(ctx.author.id)
    if user_id not in auction_state['participants']:
        await ctx.send("You are not a registered participant in this auction.")
        return

    ensure_user_structures(user_id)

    if len(user_teams[user_id]) >= MAX_PLAYERS_PER_USER:
        await ctx.send(
            f"You have reached the {MAX_PLAYERS_PER_USER}-player limit for your team."
        )
        return

    new_price = 0
    if len(args) == 1:
        amount = args[0].strip().lower().replace(",", "")
        multiplier = 1
        if amount.endswith("m"):
            multiplier = 1_000_000
            amount = amount[:-1]
        elif amount.endswith("k"):
            multiplier = 1_000
            amount = amount[:-1]

        try:
            new_price = int(float(amount) * multiplier)
        except ValueError:
            await ctx.send(
                "❌ Invalid bid amount format. Use numbers like 50m or 1000000."
            )
            return

        if new_price <= auction_state['current_price']:
            await ctx.send("Your bid must be higher than the current bid.")
            return

        if new_price < auction_state[
                'current_price'] + MIN_BID_INCREMENT and new_price != auction_state[
                    'current_price']:
            await ctx.send(
                f"❌ Minimum bid increment is {format_currency(MIN_BID_INCREMENT)}."
            )
            return
    else:
        new_price = auction_state['current_price'] + BID_INCREMENT

    if new_price > user_budgets[user_id]:
        await ctx.send(
            f"You can't bid more than your remaining budget: {format_currency(user_budgets[user_id])}"
        )
        return

    auction_state['current_price'] = new_price
    auction_state['highest_bidder'] = user_id
    await ctx.send(
        f"🟡 {ctx.author.display_name} bids {format_currency(new_price)}!")

    if auction_state['timeout_task']:
        auction_state['timeout_task'].cancel()

    async def auto_sold():
        try:
            current_player = auction_state.get('current_player')
            if not auction_state.get('bidding', False) or not current_player:
                return
            await asyncio.sleep(7)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != current_player:
                return
            await ctx.send("⌛ Going once...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != current_player:
                return
            await ctx.send("⌛ Going twice...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != current_player:
                return
            await ctx.send("⌛ Final call...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != current_player:
                return
            await _finalize_sold(ctx)
        except asyncio.CancelledError:
            pass

    auction_state['timeout_task'] = bot.loop.create_task(auto_sold())


async def _finalize_sold(ctx):
    """Helper function to finalize the sale of a player."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state or not auction_state['bidding'] or not auction_state[
            'current_player']:
        return

    if auction_state['highest_bidder'] is None:
        player = auction_state['current_player']
        auction_state['bidding'] = False
        auction_state['unsold_players'].add(player['name'])
        auction_state['current_player'] = None
        auction_state['current_price'] = 0
        auction_state['highest_bidder'] = None
        auction_state['pass_votes'].clear()
        await ctx.send(
            f"❌ No one bid for **{player['name']}**. They go unsold.")
        return

    winner_id = auction_state['highest_bidder']
    price = auction_state['current_price']
    player = auction_state['current_player']

    try:
        winner = await bot.fetch_user(int(winner_id))
        winner_name = winner.display_name
    except:
        winner_name = f"User {winner_id}"

    # Deduct budget and add player
    user_budgets[winner_id] -= price
    entry = {
        "name": player['name'],
        "position": player.get('position', 'unknown'),
        "league": player.get('league', 'Unknown'),
        "price": price,
        "set": available_sets.get(auction_state['current_set'], 'Unknown Set'),
        "tier": player.get('tier', 'C')
    }
    user_teams[winner_id].append(entry)

    # Update stats: money spent and most expensive
    ensure_user_structures(winner_id)
    try:
        user_stats[winner_id]['money_spent'] = user_stats[winner_id].get(
            'money_spent', 0) + price
        if price > user_stats[winner_id].get('most_expensive', 0):
            user_stats[winner_id]['most_expensive'] = price
    except Exception as e:
        print(f"Error updating stats for user {winner_id}: {e}")

    auction_state['last_sold_player'] = player
    auction_state['last_sold_buyer_id'] = winner_id
    auction_state['last_sold_price'] = price

    auction_state['bidding'] = False
    auction_state['current_player'] = None
    auction_state['current_price'] = 0
    auction_state['highest_bidder'] = None
    auction_state['pass_votes'].clear()
    if not save_data():
        await ctx.send(
            "⚠️ Error saving data. Sale recorded but data may not persist.")
        return

    embed = discord.Embed(title="✅ Player Sold!", color=discord.Color.green())
    embed.add_field(name="Player", value=player['name'], inline=True)
    embed.add_field(name="Sold To",
                    value=f"<@{winner_id}> ({winner_name})",
                    inline=True)
    embed.add_field(name="Final Price",
                    value=format_currency(price),
                    inline=True)
    embed.add_field(name="Set",
                    value=available_sets.get(auction_state['current_set'],
                                             'Unknown Set'),
                    inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def rebid(ctx):
    """Re-auctions the last sold player, refunding the buyer and removing the player from their team."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state[
            'host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send(
            "Only the auction host can use this command in this auction.")
        return

    if auction_state['bidding'] or auction_state['current_player']:
        await ctx.send(
            "A player is currently being auctioned. Please wait until the current auction ends."
        )
        return

    if not auction_state['last_sold_player']:
        await ctx.send("No player has been sold yet in this auction.")
        return

    player = auction_state['last_sold_player']
    buyer_id = auction_state['last_sold_buyer_id']
    price = auction_state['last_sold_price']

    # Refund the buyer and remove the player
    user_budgets[buyer_id] += price
    user_teams[buyer_id] = [
        p for p in user_teams[buyer_id] if p['name'] != player['name']
    ]

    # Update lineups if the player was in any of them
    if buyer_id in user_lineups:
        for lineup_name, lineup_data in user_lineups[buyer_id].items():
            if lineup_data['players']:
                lineup_data['players'] = [
                    p for p in lineup_data['players']
                    if p['name'] != player['name']
                ]

    # Update stats for refund: reduce money_spent if possible (keeps simple)
    ensure_user_structures(buyer_id)
    user_stats[buyer_id]['money_spent'] = max(
        0, user_stats[buyer_id].get('money_spent', 0) - price)
    # Note: not rolling back most_expensive for simplicity

    if not save_data():
        await ctx.send(
            "⚠️ Error saving data. Rebid proceeding, but data may not persist."
        )

    # Start re-auction
    auction_state['current_player'] = player
    auction_state['bidding'] = True
    auction_state['bids'] = {}
    auction_state['current_price'] = player.get('base_price', MIN_BASE_PRICE)
    auction_state['highest_bidder'] = None
    auction_state['pass_votes'].clear()

    if auction_state['timeout_task']:
        auction_state['timeout_task'].cancel()

    embed = discord.Embed(title="🔨 Player Re-Auction",
                          color=discord.Color.gold())
    embed.add_field(name="Name", value=player['name'], inline=True)
    embed.add_field(name="Position",
                    value=player.get('position', 'Unknown').upper(),
                    inline=True)
    embed.add_field(name="League",
                    value=player.get('league', 'Unknown'),
                    inline=True)
    embed.add_field(name="Set",
                    value=available_sets.get(auction_state['current_set'],
                                             'Unknown Set'),
                    inline=True)
    embed.add_field(name="Starting Price",
                    value=format_currency(auction_state['current_price']),
                    inline=False)
    embed.set_footer(
        text=
        "Use !bid or !bid [amount] to place a bid. React with 💰 to bid, ❌ to pass."
    )

    message = await ctx.send(embed=embed)
    await message.add_reaction("💰")
    await message.add_reaction("❌")

    async def auto_sold():
        try:
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != player:
                return
            await asyncio.sleep(7)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != player:
                return
            await ctx.send("⌛ Going once...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != player:
                return
            await ctx.send("⌛ Going twice...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != player:
                return
            await ctx.send("⌛ Final call...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != player:
                return
            await _finalize_sold(ctx)
        except asyncio.CancelledError:
            pass

    auction_state['timeout_task'] = bot.loop.create_task(auto_sold())
    await ctx.send(
        f"✅ **{player['name']}** is being re-auctioned. Previous buyer <@{buyer_id}> has been refunded {format_currency(price)}."
    )


@bot.command()
async def sold(ctx):
    """Manually sells the current player to the highest bidder."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state[
            'host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send(
            "Only the auction host can use this command in this auction.")
        return

    if auction_state['host'] == ctx.author.id:
        auction_state['last_host_activity'] = time.time()

    if not auction_state['bidding'] or not auction_state['current_player']:
        await ctx.send(
            "No player is currently being auctioned in this channel.")
        return

    if auction_state['timeout_task']:
        auction_state['timeout_task'].cancel()

    await _finalize_sold(ctx)


@bot.command()
async def status(ctx):
    """Displays the current auction status."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if auction_state['host'] == ctx.author.id:
        auction_state['last_host_activity'] = time.time()

    if not auction_state['bidding'] or not auction_state['current_player']:
        await ctx.send(
            "⚠️ No player is currently being auctioned in this channel.")
        return

    player = auction_state['current_player']
    price = auction_state['current_price']
    bidder_id = auction_state['highest_bidder']
    bidder = f"<@{bidder_id}>" if bidder_id else "None"

    embed = discord.Embed(title="📢 Current Auction Status",
                          color=discord.Color.blue())
    embed.add_field(name="Player", value=player['name'], inline=True)
    embed.add_field(name="Position",
                    value=player.get('position', 'Unknown').upper(),
                    inline=True)
    embed.add_field(name="League",
                    value=player.get('league', 'Unknown'),
                    inline=True)
    embed.add_field(name="Set",
                    value=available_sets.get(auction_state['current_set'],
                                             'Unknown Set'),
                    inline=True)
    embed.add_field(name="Highest Bid",
                    value=format_currency(price),
                    inline=True)
    embed.add_field(name="Highest Bidder", value=bidder, inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def unsold(ctx):
    """Marks the current player as unsold."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state[
            'host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send(
            "Only the auction host can use this command in this auction.")
        return

    if auction_state['host'] == ctx.author.id:
        auction_state['last_host_activity'] = time.time()

    if not auction_state['bidding'] or not auction_state['current_player']:
        await ctx.send(
            "No player is currently being auctioned in this channel.")
        return

    player = auction_state['current_player']
    auction_state['bidding'] = False
    auction_state['unsold_players'].add(player['name'])
    auction_state['current_player'] = None
    auction_state['current_price'] = 0
    auction_state['highest_bidder'] = None
    auction_state['pass_votes'].clear()

    if auction_state['timeout_task']:
        auction_state['timeout_task'].cancel()

    await ctx.send(
        f"❌ Player **{player['name']}** goes unsold in this auction.")


@bot.command()
async def myplayers(ctx):
    """Displays the list of players bought by the command issuer."""
    user_id = str(ctx.author.id)
    if user_id not in user_teams or not user_teams[user_id]:
        await ctx.send("You haven't bought any players yet.")
        return

    if ctx.channel.id in active_auctions and active_auctions[
            ctx.channel.id]['host'] == ctx.author.id:
        active_auctions[ctx.channel.id]['last_host_activity'] = time.time()

    team = user_teams[user_id]
    embed = discord.Embed(title=f"📋 {ctx.author.display_name}'s Players",
                          color=discord.Color.teal())

    for p in team:
        set_info = f" ({p.get('set', 'Unknown Set')})" if 'set' in p else ""
        embed.add_field(
            name=f"{p['name']} ({p['position'].upper()})",
            value=
            f"{p.get('league', 'Unknown')}{set_info} - {format_currency(p['price'])}",
            inline=False)

    await ctx.send(embed=embed)


@bot.command()
async def budget(ctx):
    """Displays the remaining budget of the command issuer."""
    user_id = str(ctx.author.id)
    budget = user_budgets.get(user_id, STARTING_BUDGET)

    if ctx.channel.id in active_auctions and active_auctions[
            ctx.channel.id]['host'] == ctx.author.id:
        active_auctions[ctx.channel.id]['last_host_activity'] = time.time()

    await ctx.send(f"💰 Your remaining budget: {format_currency(budget)}")


def calculate_team_score_based_on_lineup(user_id, lineup_name=None):
    """Calculates a score for a team based on its lineup, tactic, and formation."""
    # Get the active lineup if no specific lineup name is provided
    if lineup_name is None:
        lineup_name = active_lineups.get(user_id, 'main')
    
    user_lineup_dict = user_lineups.get(user_id, {})
    lineup_data = user_lineup_dict.get(lineup_name, {
        'players': [],
        'tactic': 'Balanced',
        'formation': '4-4-2'
    })
    players = lineup_data['players']
    tactic = lineup_data['tactic']
    formation = lineup_data['formation']

    if not players:
        players = user_teams.get(user_id, [])[:MAX_LINEUP_PLAYERS]
        tactic = 'Balanced'
        formation = '4-4-2'

    if not players:
        return 0, 0

    attack_score = 0
    defense_score = 0
    positions_filled = {pos: False for pos in available_positions}
    position_counts = {pos: 0 for pos in available_positions}
    set_counts = {}

    for player in players:
        pos = player['position'].lower()
        if pos in positions_filled:
            positions_filled[pos] = True
            position_counts[pos] += 1
        player_set = player.get('set')
        if player_set:
            set_counts[player_set] = set_counts.get(player_set, 0) + 1
        tier = player.get('tier', 'C')
        tier_multiplier = {'A': 1.5, 'B': 1.2, 'C': 1.0}
        score_boost = tier_multiplier[tier]

        if pos == 'gk':
            defense_score += position_counts[pos] * 60 * score_boost
        elif pos in ['cb', 'lb', 'rb']:
            defense_score += position_counts[pos] * 40 * score_boost
        elif pos == 'cm':
            defense_score += position_counts[pos] * 30 * score_boost
            attack_score += position_counts[pos] * 10 * score_boost
        elif pos == 'cam':
            attack_score += position_counts[pos] * 30 * score_boost
            defense_score += position_counts[pos] * 10 * score_boost
        elif pos in ['lw', 'rw', 'st']:
            attack_score += position_counts[pos] * 40 * score_boost

    attack_score += len(players) * 15
    defense_score += len(players) * 15

    for set_name, count in set_counts.items():
        if count >= 3:
            attack_score += count * 20
            defense_score += count * 20
        elif count == 2:
            attack_score += 5
            defense_score += 5

    if tactic == 'Attacking':
        attack_score += 20
        defense_score -= 10
    elif tactic == 'Defensive':
        attack_score -= 10
        defense_score += 20
    elif tactic == 'Balanced':
        attack_score += 10
        defense_score += 10

    if formation in ['5-4-1', '5-3-2']:
        defense_score += 30
        attack_score -= 10
    elif formation in ['4-3-3', '3-4-3']:
        attack_score += 30
        defense_score -= 10
    else:
        attack_score += 15
        defense_score += 15

    return max(0, attack_score), max(0, defense_score)


def simulate_match(team1_id, team2_id, team1, team2):
    """Simulates a football match between two teams' lineups."""
    team1_lineup = user_lineups.get(team1_id, {
        'players': [],
        'tactic': 'Balanced',
        'formation': '4-4-2'
    })
    team2_lineup = user_lineups.get(team2_id, {
        'players': [],
        'tactic': 'Balanced',
        'formation': '4-4-2'
    })

    team1_players = team1_lineup['players'] or user_teams.get(
        team1_id, [])[:MAX_LINEUP_PLAYERS]
    team2_players = team2_lineup['players'] or user_teams.get(
        team2_id, [])[:MAX_LINEUP_PLAYERS]
    team1_tactic = team1_lineup['tactic'] if team1_lineup[
        'players'] else 'Balanced'
    team2_tactic = team2_lineup['tactic'] if team2_lineup[
        'players'] else 'Balanced'
    team1_formation = team1_lineup['formation'] if team1_lineup[
        'players'] else '4-4-2'
    team2_formation = team2_lineup['formation'] if team2_lineup[
        'players'] else '4-4-2'

    if not team1_players or not team2_players:
        return None, "One or both teams have no players.", None

    team1_attack, team1_defense = calculate_team_score_based_on_lineup(
        team1_id)
    team2_attack, team2_defense = calculate_team_score_based_on_lineup(
        team2_id)

    team1_attack += random.randint(-15, 15)
    team1_defense += random.randint(-15, 15)
    team2_attack += random.randint(-15, 15)
    team2_defense += random.randint(-15, 15)

    team1_goals = 0
    team2_goals = 0
    score_diff = abs((team1_attack - team2_defense) -
                     (team2_attack - team1_defense))

    if score_diff < 20:
        team1_goals = random.randint(0, 3)
        team2_goals = random.randint(max(0, team1_goals - 1), team1_goals + 1)
    elif score_diff < 50:
        if team1_attack - team2_defense > team2_attack - team1_defense:
            team1_goals = random.randint(2, 4)
            team2_goals = random.randint(0, 2)
        else:
            team1_goals = random.randint(0, 2)
            team2_goals = random.randint(2, 4)
    else:
        if team1_attack - team2_defense > team2_attack - team1_defense:
            team1_goals = random.randint(3, 6)
            team2_goals = random.randint(0, 2)
        else:
            team1_goals = random.randint(0, 2)
            team2_goals = random.randint(3, 6)

    narrative = []
    events = random.randint(3, 5)
    event_types = ['goal', 'save', 'chance', 'tackle', 'assist']

    for _ in range(events):
        team = random.choice([1, 2])
        event = random.choice(event_types)
        players = team1_players if team == 1 else team2_players
        tactic = team1_tactic if team == 1 else team2_tactic
        formation = team1_formation if team == 1 else team2_formation
        team_name_display = team1.display_name if team == 1 else team2.display_name
        if players:
            player = random.choice(players)
            player_name = player['name']
            pos = player['position'].upper()
        else:
            player_name = f"Team {team} player"
            pos = "Unknown"

        if event == 'goal':
            if pos in ['ST', 'LW', 'RW', 'CAM']:
                narrative.append(
                    f"⚽ {player_name} ({pos}) scores a {random.choice(['stunning', 'clinical', 'brilliant'])} goal for {team_name_display}!"
                )
            else:
                narrative.append(
                    f"⚽ {player_name} ({pos}) scores a rare goal for {team_name_display}!"
                )
        elif event == 'save':
            if pos == 'GK':
                narrative.append(
                    f"🧤 {player_name} ({pos}) makes a fantastic save to deny {team_name_display}'s opponent!"
                )
            else:
                narrative.append(
                    f"🧤 {team_name_display}'s goalkeeper makes a crucial save!"
                )
        elif event == 'chance':
            if pos in ['ST', 'LW', 'RW', 'CAM']:
                narrative.append(
                    f"🎯 {player_name} ({pos}) misses a golden opportunity for {team_name_display}!"
                )
            else:
                narrative.append(
                    f"🎯 {player_name} ({pos}) creates a chance for {team_name_display}!"
                )
        elif event == 'tackle':
            if pos in ['CB', 'LB', 'RB', 'CM']:
                narrative.append(
                    f"💪 {player_name} ({pos}) makes a crunching tackle to stop {team_name_display}'s opponent!"
                )
            else:
                narrative.append(
                    f"💪 {player_name} ({pos}) makes a key defensive play for {team_name_display}!"
                )
        elif event == 'assist':
            if pos in ['CAM', 'LW', 'RW', 'CM']:
                narrative.append(
                    f"🎁 {player_name} ({pos}) delivers a perfect assist for {team_name_display}!"
                )
            else:
                narrative.append(
                    f"🎁 {player_name} ({pos}) sets up a goal for {team_name_display}!"
                )

    if team1_tactic == 'Attacking' and team1_goals > team2_goals:
        narrative.append(
            f"{team1.display_name}'s attacking style overwhelmed the opposition's defense!"
        )
    elif team2_tactic == 'Defensive' and team2_goals <= team1_goals:
        narrative.append(
            f"{team2.display_name}'s defensive solidity frustrated their opponents!"
        )
    elif team1_formation in ['5-4-1', '5-3-2'] and team1_goals <= team2_goals:
        narrative.append(
            f"{team1.display_name}'s defensive {team1_formation} formation held strong!"
        )
    elif team2_formation in ['4-3-3', '3-4-3'] and team2_goals > team1_goals:
        narrative.append(
            f"{team2.display_name}'s attacking {team2_formation} formation overwhelmed the opposition!"
        )

    return (team1_goals,
            team2_goals), "\n".join(narrative), (team1_attack, team1_defense,
                                                 team2_attack, team2_defense,
                                                 team1_formation,
                                                 team2_formation)


@bot.command()
async def battle(ctx, team1: discord.Member, team2: discord.Member):
    """Simulates a football match between two participants' lineups."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send(
            "No auction is currently running in this channel, so battle commands are not available here."
        )
        return

    if ctx.author.id != auction_state[
            'host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send(
            "Only the auction host can run this command in this auction.")
        return

    if auction_state['host'] == ctx.author.id:
        auction_state['last_host_activity'] = time.time()

    team1_id = str(team1.id)
    team2_id = str(team2.id)

    if team1_id not in user_teams or not user_teams[team1_id]:
        await ctx.send(f"{team1.display_name} has no players to field a team.")
        return
    if team2_id not in user_teams or not user_teams[team2_id]:
        await ctx.send(f"{team2.display_name} has no players to field a team.")
        return

    scoreline, narrative, scores = simulate_match(team1_id, team2_id, team1,
                                                  team2)

    if scoreline is None:
        await ctx.send(narrative)
        return

    team1_goals, team2_goals = scoreline
    team1_attack, team1_defense, team2_attack, team2_defense, team1_formation, team2_formation = scores

    team1_lineup = user_lineups.get(team1_id, {
        'players': [],
        'tactic': 'Balanced',
        'formation': '4-4-2'
    })
    team2_lineup = user_lineups.get(team2_id, {
        'players': [],
        'tactic': 'Balanced',
        'formation': '4-4-2'
    })
    team1_players = team1_lineup['players'] or user_teams.get(
        team1_id, [])[:MAX_LINEUP_PLAYERS]
    team2_players = team2_lineup['players'] or user_teams.get(
        team2_id, [])[:MAX_LINEUP_PLAYERS]
    team1_tactic = team1_lineup['tactic'] if team1_lineup[
        'players'] else 'Balanced'
    team2_tactic = team2_lineup['tactic'] if team2_lineup[
        'players'] else 'Balanced'
    team1_formation = team1_lineup['formation'] if team1_lineup[
        'players'] else '4-4-2'
    team2_formation = team2_lineup['formation'] if team2_lineup[
        'players'] else '4-4-2'

    embed = discord.Embed(title="⚽ Match Result", color=discord.Color.purple())
    embed.add_field(name="Teams",
                    value=f"{team1.display_name} vs {team2.display_name}",
                    inline=False)
    embed.add_field(name="Scoreline",
                    value=f"{team1_goals} - {team2_goals}",
                    inline=False)
    embed.add_field(
        name="Team Strengths",
        value=
        f"{team1.display_name}: Attack {team1_attack}, Defense {team1_defense}\n"
        f"{team2.display_name}: Attack {team2_attack}, Defense {team2_defense}",
        inline=False)
    embed.add_field(
        name="Tactics and Formations",
        value=f"{team1.display_name}: {team1_tactic}, {team1_formation}\n"
        f"{team2.display_name}: {team2_tactic}, {team2_formation}",
        inline=False)
    embed.add_field(name="Match Summary", value=narrative, inline=False)

    team1_lineup_str = "\n".join(
        [f"{p['name']} ({p['position'].upper()})"
         for p in team1_players]) or "No lineup set"
    team2_lineup_str = "\n".join(
        [f"{p['name']} ({p['position'].upper()})"
         for p in team2_players]) or "No lineup set"
    embed.add_field(name=f"{team1.display_name}'s Lineup",
                    value=team1_lineup_str,
                    inline=True)
    embed.add_field(name=f"{team2.display_name}'s Lineup",
                    value=team2_lineup_str,
                    inline=True)

    if team1_goals > team2_goals:
        embed.add_field(name="Winner",
                        value=f"{team1.display_name} 🏆",
                        inline=False)
    elif team2_goals > team1_goals:
        embed.add_field(name="Winner",
                        value=f"{team2.display_name} 🏆",
                        inline=False)
    else:
        embed.add_field(name="Result", value="Draw 🤝", inline=False)

    embed.set_footer(
        text="Use !battle @user1 @user2 to simulate another match!")
    await ctx.send(embed=embed)


@bot.command()
async def rankteams(ctx):
    """Ranks all participant teams based on their lineup composition."""
    if not user_teams:
        await ctx.send("No teams have been formed yet to rank.")
        return

    if ctx.channel.id in active_auctions and active_auctions[
            ctx.channel.id]['host'] == ctx.author.id:
        active_auctions[ctx.channel.id]['last_host_activity'] = time.time()

    team_scores = []
    for user_id, team_players in user_teams.items():
        if team_players:
            attack_score, defense_score = calculate_team_score_based_on_lineup(
                user_id)
            total_score = attack_score + defense_score
            try:
                user = await bot.fetch_user(int(user_id))
                team_scores.append((user.display_name, total_score, user_id,
                                    len(team_players)))
            except discord.NotFound:
                team_scores.append(
                    (f"Unknown User ({user_id})", total_score, user_id,
                     len(team_players)))
            except Exception as e:
                print(f"Error fetching user {user_id}: {e}")
                team_scores.append(
                    (f"Error User ({user_id})", total_score, user_id,
                     len(team_players)))

    if not team_scores:
        await ctx.send("No players have been bought by any participant yet.")
        return

    team_scores.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(title="🏆 Team Rankings (Based on Lineup)",
                          color=discord.Color.gold())
    description_list = []

    for i, (name, score, user_id,
            num_players_in_team) in enumerate(team_scores):
        lineup_data = user_lineups.get(user_id, {
            'players': [],
            'tactic': 'Balanced',
            'formation': '4-4-2'
        })
        players_in_lineup = lineup_data['players'] if lineup_data[
            'players'] else user_teams.get(user_id, [])[:MAX_LINEUP_PLAYERS]

        positions_covered = set(p['position'].lower()
                                for p in players_in_lineup)

        set_distribution = {}
        tier_distribution = {'A': 0, 'B': 0, 'C': 0}
        for p in players_in_lineup:
            player_set_name = p.get('set', 'Unknown Set')
            display_set_name = available_sets.get(player_set_name,
                                                  player_set_name)
            set_distribution[display_set_name] = set_distribution.get(
                display_set_name, 0) + 1
            tier = p.get('tier', 'C')
            tier_distribution[tier] += 1

        set_info_parts = [
            f"{count} {key}" for key, count in set_distribution.items()
        ]
        set_summary = f"Sets: {', '.join(set_info_parts)}" if set_info_parts else "No Sets"
        tier_summary = f"Tiers: A: {tier_distribution['A']}, B: {tier_distribution['B']}, C: {tier_distribution['C']}"
        tactic = lineup_data['tactic'] if lineup_data['players'] else 'Balanced'
        formation = lineup_data['formation'] if lineup_data[
            'players'] else '4-4-2'

        description_list.append(
            f"**{i+1}.** <@{user_id}> ({name}): **{score} Team Score** ({len(players_in_lineup)} players in lineup)\n"
            f"  Positions: {', '.join(p.upper() for p in positions_covered) if positions_covered else 'None'}\n"
            f"  Tactic: {tactic}, Formation: {formation}\n"
            f"  {set_summary}\n"
            f"  {tier_summary}\n")

    embed.description = "\n".join(description_list)
    embed.set_footer(
        text="Higher Team Score indicates a more complete and cohesive lineup."
    )
    await ctx.send(embed=embed)


@bot.command()
async def endauction(ctx):
    """Ends the current auction in this channel and resets its data and participant data (host or privileged user only)."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state[
            'host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send(
            "Only the auction host or the privileged user can end this auction."
        )
        return

    if auction_state['timeout_task']:
        auction_state['timeout_task'].cancel()

    participants = auction_state['participants'].copy()
    for user_id in participants:
        user_budgets[user_id] = STARTING_BUDGET
        user_teams[user_id] = []
        user_lineups[user_id] = {
            'main': {
                'players': [],
                'tactic': 'Balanced',
                'formation': '4-4-2'
            }
        }
        active_lineups[user_id] = 'main'

    del active_auctions[ctx.channel.id]

    if not save_data():
        await ctx.send(
            "⚠️ Error saving data. Auction ended, but data may not persist.")
        return

    await ctx.send(
        "🔚 Auction in this channel has been ended. Participant budgets, teams, and lineups have been reset."
    )

@bot.command()
async def footy(ctx, category: str = None):
    """Shows categorized help for the bot."""
    embed = discord.Embed(title="📘 Football Auction Bot Commands",
                          color=discord.Color.blue())

    if category is None:
        embed.description = (
            "Use `!footy <category>` to view commands in that category.\n\n"
            "Available categories:\n"
            "⚽ auction, 👥 team, 🎮 gamemodes, 📊 leaderboards")
    elif category.lower() == "auction":
        embed.add_field(
            name="Auction Commands",
            value="\n".join([
                "`!startauction @users...` – Start a new auction",
                "`!sets` – Show all available sets",
                "`!participants` – List participants",
                "`!bid [amount]` – Place a bid",
                "`!sold / !unsold` – Resolve auction",
                "`!status` – Current auction status",
                "`!endauction` – End current auction"
        ]),
        inline=False)
    elif category.lower() == "team":
        embed.add_field(name="Team Commands",
                        value="\n".join([
                            "`!myplayers` – View your bought players",
                            "`!budget` – Show your budget",
                            "`!setlineup [name]` – Setup/edit a lineup",
                            "`!lineups` – View all your lineups",
                            "`!switchlineup <name>` – Switch active lineup",
                            "`!deletelineup <name>` – Delete a lineup",
                            "`!viewlineup` – View your active lineup",
                            "`!battle @user1 @user2` – Simulate a match"
                        ]),
                        inline=False)
    elif category.lower() == "gamemodes":
        embed.add_field(
            name="Gamemodes",
            value="\n".join([
                "`!koth start` – Start King of the Hill (max 6 players)",
                "`!draftclash start` – Start Draft Clash (max 8 players)",
                "`!draftclash koth` – Enter KoTH with drafted team",
                "`!challenge @user` – Challenge for the throne",
                "`!end <gamemode>` – End active game sessions"
            ]),
            inline=False)
    elif category.lower() == "leaderboards":
        embed.add_field(
            name="Leaderboards",
            value="\n".join([
                "`!leaderboard auction` – Auction stats",
                "`!leaderboard gamemodes` – KoTH & Draft Clash stats",
                "`!draftclashleaderboard` – Draft Clash wins"
            ]),
            inline=False)
    else:
        embed.description = "❌ Unknown category. Try: auction, team, gamemodes, leaderboards."

    await ctx.send(embed=embed)


import os
from keep_alive import keep_alive

keep_alive()

import random


@bot.command()
async def market(ctx):
    """Show free agent players available to bid on."""
    free_agents = ["Player A", "Player B", "Player C", "Player D", "Player E"]
    embed = discord.Embed(title="🛒 Free Agent Market",
                          color=discord.Color.gold())
    for p in free_agents:
        form = player_form.get(p, 5)
        embed.add_field(
            name=p,
            value=f"Form: {form}/10 | Starting bid: {random.randint(5, 50)}M",
            inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def events(ctx):
    """Trigger or show random events."""
    events_list = [
        "🚑 Injury – One of your players is out for 2 matches!",
        "⚡ Form Boost – Random player gains +2 form for 3 matches!",
        "🔄 Transfer Rumor – Random player may be swapped with the market!",
    ]
    event = random.choice(events_list)
    await ctx.send(f"🎲 Random Event: {event}")

@bot.command()
async def draft(ctx, action: str = None):
    """Draft command system."""
    if action is None:
        await ctx.send("Usage: !draft start|pick <player>")
        return
        
    if action.lower() == "start":
        # Implement draft start logic
        await ctx.send("📋 Draft mode started! Turn order will be assigned.")
        return
        
    elif action.lower() == "pick":
        # Implement pick logic 
        player_name = ctx.message.content.split(None, 2)[2]
        await ctx.send(f"✅ {ctx.author.mention} picked **{player_name}**.")
        return
        
    await ctx.send("Unknown draft action. Use start or pick.")


# -------------------- Added Gamemodes: KoTH, Draft Clash, Mystery Box --------------------
# Note: Integrates with user_teams, user_budgets, user_lineups, user_stats, save_data(), load_data(), ensure_user_structures(), simulate_match().

koth_state = {
    'current_king_id': None,
    'king_streak': 0,
    'longest_reigns': {},
    'history': []
}

draft_clash_sessions = {}
draft_clash_wins = {}


# Modify draftclash command for no player limits
@bot.command()
async def draftclash(ctx, action: str = None):
    """Draft Clash command without player limitations."""
    ch = ctx.channel.id
    if action is None:
        await ctx.send("Usage: !draftclash start|join|begin|status|pick <1-3>|koth")
        return
        
    action = action.lower()
    if action == 'start':
        if ch in draft_clash_sessions and draft_clash_sessions[ch].get('state') in ('lobby', 'drafting'):
            await ctx.send("A draft is already in this channel.")
            return
            
        draft_clash_sessions[ch] = {
            'host': str(ctx.author.id),
            'players': [str(ctx.author.id)],
            'state': 'lobby', 
            'round': 0,
            'picks': {},
            'available_pool': [],
            'set_key': None
        }
        save_data()
        await ctx.send(f"Draft Clash lobby created by {ctx.author.mention}. Others use `!draftclash join`. Host uses `!draftclash begin <set_key>` to start.")
        return

    session = draft_clash_sessions.get(ch)
    if not session:
        await ctx.send("No active draft lobby. Start with `!draftclash start`.")
        return

    if action == 'join':
        if session['state'] != 'lobby':
            await ctx.send("Draft already in progress.")
            return
            
        session['players'].append(str(ctx.author.id))
        save_data()
        await ctx.send(f"{ctx.author.mention} joined the draft! ({len(session['players'])} players)")
        return
    if action == 'begin':
        if str(ctx.author.id) != session['host']:
            await ctx.send("Only host can begin.")
            return
        # optional set key
        parts = ctx.message.content.strip().split()
        set_key = None
        if len(parts) > 2: set_key = parts[2].strip().lower()
        session['set_key'] = set_key or '24-25'
        session['state'] = 'drafting'
        session['round'] = 1
        session['picks'] = {uid: [] for uid in session['players']}
        # Build pool from available players
        pool = []
        for pos in available_positions:
            tiered_players = load_players_by_position(pos, session['set_key'])
            for tier in ['A', 'B', 'C']:
                pool.extend(tiered_players[tier])
        random.shuffle(pool)
        session['available_pool'] = pool[:60]
        await _draft_offer(ctx, session)
        save_data()
        return
    if action == 'status':
        await ctx.send(
            f"Draft status: {session['state']}, players: {', '.join(session['players'])}, round: {session['round']}"
        )
        return
    if action == 'pick':
        parts = ctx.message.content.strip().split()
        if len(parts) < 3:
            await ctx.send("Use `!draftclash pick <1|2|3>`")
            return
        try:
            idx = int(parts[2])
        return
    if action == 'status':
        await ctx.send(
            f"Draft status: {session['state']}, players: {', '.join(session['players'])}, round: {session['round']}"
        )
        return
    if action == 'pick':
        parts = ctx.message.content.strip().split()
        if len(parts) < 3:
            await ctx.send("Use `!draftclash pick <1|2|3>`")
            return
        try:
            idx = int(parts[2])
            assert idx in (1, 2, 3)
        except:
            await ctx.send("Choice must be 1,2 or 3")
            return
        await _draft_pick(ctx, session, idx - 1)
        save_data()
        return
    if action == 'koth':
        # Check if user participated in a completed draft and has a lineup
        user_id = str(ctx.author.id)
        if user_id not in user_lineups or not user_lineups[user_id]:
            await ctx.send("❌ You don't have any lineups yet. Complete a draft first!")
            return
        
        active_lineup_name = active_lineups.get(user_id, 'main')
        if active_lineup_name not in user_lineups[user_id] or not user_lineups[user_id][active_lineup_name].get('players'):
            await ctx.send("❌ You don't have a draft lineup yet. Complete a draft first!")
            return
            
        # Check if user was in this channel's draft session
        if session and user_id not in session.get('players', []):
            await ctx.send("❌ You didn't participate in this channel's draft session.")
            return
            
        # If no current king, user becomes king
        if koth_state['current_king_id'] is None:
            koth_state['current_king_id'] = user_id
            koth_state['king_streak'] = 0
            save_data()
            await ctx.send(f"👑 {ctx.author.mention} claims the throne as the new King of the Hill with their drafted lineup!")
            return
            
        # Challenge the current king
        current_king = koth_state['current_king_id']
        if current_king == user_id:
            await ctx.send("👑 You're already the King! Defend your throne against challengers.")
            return

        # Simulate battle between challenger and king
        try:
            king_user = await bot.fetch_user(int(current_king))
            challenger_user = ctx.author
            
            class MockUser:
                def __init__(self, display_name):
                    self.display_name = display_name
            
            king_mock = MockUser(king_user.display_name)
            challenger_mock = MockUser(challenger_user.display_name)
            
            result = simulate_match(current_king, user_id, king_mock, challenger_mock)
            
            if isinstance(result, tuple):
                scoreline, narrative, scores = result
                king_score, challenger_score = scoreline
                
                embed = discord.Embed(title="🏆 King of the Hill Battle", 
                                     description=narrative, 
                                     color=discord.Color.gold())
                embed.add_field(name=f"👑 {king_user.display_name} (King)", 
                               value=f"Score: {king_score}", inline=True)
                embed.add_field(name=f"⚔️ {challenger_user.display_name} (Challenger)", 
                               value=f"Score: {challenger_score}", inline=True)
                
                if challenger_score > king_score:
                    # Challenger wins, becomes new king
                    old_streak = koth_state['king_streak']
                    koth_state['longest_reigns'][current_king] = max(
                        koth_state['longest_reigns'].get(current_king, 0), old_streak)
                    
                    koth_state['current_king_id'] = user_id
                    koth_state['king_streak'] = 0
                    koth_state['history'].append({
                        'old_king': current_king,
                        'new_king': user_id,
                        'streak_ended': old_streak
                    })
                    
                    embed.add_field(name="🏆 Result", 
                                   value=f"{challenger_user.mention} defeats the king and claims the throne!", 
                                   inline=False)
                    
                    # Update user stats
                    ensure_user_structures(user_id)
                    ensure_user_structures(current_king)
                    user_stats[user_id]['wins'] = user_stats[user_id].get('wins', 0) + 1
                    user_stats[current_king]['losses'] = user_stats[current_king].get('losses', 0) + 1
                    
                else:
                    # King defends successfully
                    koth_state['king_streak'] += 1
                    embed.add_field(name="🛡️ Result", 
                                   value=f"{king_user.display_name} successfully defends the throne! Streak: {koth_state['king_streak']}", 
                                   inline=False)
                    
                    # Update user stats
                    ensure_user_structures(user_id)
                    ensure_user_structures(current_king)
                    user_stats[current_king]['wins'] = user_stats[current_king].get('wins', 0) + 1
                    user_stats[user_id]['losses'] = user_stats[user_id].get('losses', 0) + 1
                
                save_data()
                await ctx.send(embed=embed)
                
            else:
                await ctx.send("❌ Error simulating the battle. Please try again.")
                
        except Exception as e:
            await ctx.send(f"❌ Error during KoTH battle: {str(e)}")
        
        return
    await ctx.send("Unknown action for draftclash.")


async def _draft_offer(ctx, session):
    """Handles draft picks."""
    players = session['players']
    round_no = session['round']
    
    # Use snake draft order
    order = players if round_no % 2 == 1 else list(reversed(players))
    
    for uid in order:
        if len(session['picks'].get(uid, [])) >= round_no:
            continue
            
        pool = session['available_pool']
        if not pool:
            session['state'] = 'completed'
            await ctx.send("Pool exhausted; draft ended.")
            return
            
        # Offer 3 choices
        choices = []
        for _ in range(min(3, len(pool))):
            choices.append(pool.pop(0))
            
        session.setdefault('current_offer', {})[uid] = choices
        
        embed = discord.Embed(
            title=f"Draft Round {round_no} — Pick for <@{uid}>",
            color=discord.Color.blue())
            
        for i, p in enumerate(choices, start=1):
            embed.add_field(
                name=f"{i}. {p.get('name','Unknown')}",
                value=f"{p.get('position','?').upper()} - {p.get('league','?')}",
                inline=False)
                
        embed.set_footer(text="Type `!draftclash pick <1|2|3>`")
        await ctx.send(embed=embed)
        return
        
    # Advance round if everyone has picked
    session['round'] += 1
    if session['round'] > 11:
        session['state'] = 'completed'
        await ctx.send("Draft complete! Running knockout...")
        await _draft_run_knockout(ctx, session)
        return
        
    await _draft_offer(ctx, session)


async def _draft_pick(ctx, session, idx):
    uid = str(ctx.author.id)
    if 'current_offer' not in session or uid not in session['current_offer']:
        await ctx.send("No offer.")
        return
    choices = session['current_offer'].pop(uid)
    if idx < 0 or idx >= len(choices):
        await ctx.send("Invalid index")
        return
    picked = choices[idx]
    session['picks'].setdefault(uid, []).append(picked)
    await ctx.send(
        f"{ctx.author.mention} picked **{picked.get('name','Unknown')}** for round {session['round']}"
    )
    await _draft_offer(ctx, session)


async def _draft_run_knockout(ctx, session):
    players = session['players'][:]
    for uid in players:
        picks = session['picks'].get(uid, [])
        lineup = picks[:11]
        if len(lineup) < 11:
            extra = user_teams.get(uid, [])[:11 - len(lineup)]
            lineup.extend(extra)
        if uid not in user_lineups:
            user_lineups[uid] = {}
            active_lineups[uid] = 'draft'
        user_lineups[uid]['draft'] = {
            'players': lineup,
            'tactic': 'Balanced',
            'formation': '4-4-2'
        }
        active_lineups[uid] = 'draft'
    bracket = players[:]
    random.shuffle(bracket)
    round_no = 1
    while len(bracket) > 1:
        nxt = []
        for i in range(0, len(bracket), 2):
            if i + 1 >= len(bracket):
                nxt.append(bracket[i])
                continue
            a = bracket[i]
            b = bracket[i + 1]

            class L:
                pass

            ma = L()
            ma.display_name = (await bot.fetch_user(int(a))).name
            mb = L()
            mb.display_name = (await bot.fetch_user(int(b))).name
            res = simulate_match(a, b, ma, mb)
            if isinstance(res, tuple):
                scoreline, narrative, scores = res
                if scoreline[0] >= scoreline[1]: winner = a
                else: winner = b
            else:
                winner = a
            nxt.append(winner)
            await ctx.send(
                f"Round {round_no}: <@{a}> vs <@{b}> — Winner: <@{winner}>")
        bracket = nxt
        round_no += 1
    champ = bracket[0] if bracket else None
    if champ: 
        await ctx.send(f"🏁 Draft Clash Champion: <@{champ}>")
        # Announce KoTH integration
        await ctx.send("🎯 **Draft lineups are now ready for King of the Hill!** All participants can use `!draftclash koth` to enter KoTH battles with their drafted teams.")
    draft_clash_wins[str(champ)] = draft_clash_wins.get(str(champ), 0) + 1
    save_data()
    ensure_user_structures(champ)
    user_stats[champ]['wins'] = user_stats[champ].get('wins', 0) + 1
    save_data()


# ----------------------------------------------------------------------------------------
# End of added gamemode code


# -------------------- Added Leaderboards for Draft Clash --------------------
@bot.command()
async def draftclashleaderboard(ctx):
    if not draft_clash_wins:
        await ctx.send("No Draft Clash wins recorded yet.")
        return
    items = sorted(draft_clash_wins.items(), key=lambda x: x[1],
                   reverse=True)[:10]
    desc = "\n".join([f"<@{uid}> — {wins} wins" for uid, wins in items])
    embed = discord.Embed(title="⚡ Draft Clash Leaderboard",
                          description=desc,
                          color=discord.Color.blue())
    await ctx.send(embed=embed)




@bot.command()
async def lineups(ctx):
    """Show all your saved lineups."""
    user_id = str(ctx.author.id)
    if user_id not in user_lineups or not user_lineups[user_id]:
        await ctx.send("❌ You don't have any lineups yet. Use `!setlineup` to create one!")
        return
    
    active_name = active_lineups.get(user_id, 'main')
    embed = discord.Embed(title="🎯 Your Lineups", color=discord.Color.blue())
    
    for lineup_name, lineup_data in user_lineups[user_id].items():
        player_count = len(lineup_data.get('players', []))
        formation = lineup_data.get('formation', '4-4-2')
        tactic = lineup_data.get('tactic', 'Balanced')
        
        status = "🟢 ACTIVE" if lineup_name == active_name else "⚪"
        value = f"{status}\n{player_count}/11 players\n{formation} ({tactic})"
        
        embed.add_field(name=f"📋 {lineup_name.title()}", value=value, inline=True)
    
    embed.set_footer(text="Use !switchlineup <name> to change active lineup | !setlineup <name> to create/edit")
    await ctx.send(embed=embed)

@bot.command()
async def switchlineup(ctx, lineup_name: str = None):
    """Switch to a different lineup for battles."""
    if lineup_name is None:
        await ctx.send("❌ Please specify a lineup name: `!switchlineup <name>`")
        return
    
    user_id = str(ctx.author.id)
    lineup_name = lineup_name.lower()
    
    if user_id not in user_lineups or lineup_name not in user_lineups[user_id]:
        await ctx.send(f"❌ Lineup '{lineup_name}' doesn't exist. Use `!lineups` to see available lineups.")
        return
    
    active_lineups[user_id] = lineup_name
    save_data()
    
    lineup_data = user_lineups[user_id][lineup_name]
    player_count = len(lineup_data.get('players', []))
    formation = lineup_data.get('formation', '4-4-2')
    tactic = lineup_data.get('tactic', 'Balanced')
    
    await ctx.send(f"✅ Switched to lineup: **{lineup_name.title()}**\n"
                  f"📋 {player_count}/11 players | {formation} ({tactic})")

@bot.command()
async def deletelineup(ctx, lineup_name: str = None):
    """Delete a saved lineup."""
    if lineup_name is None:
        await ctx.send("❌ Please specify a lineup name: `!deletelineup <name>`")
        return
    
    user_id = str(ctx.author.id)
    lineup_name = lineup_name.lower()
    
    if lineup_name == 'main':
        await ctx.send("❌ Cannot delete the main lineup!")
        return
    
    if user_id not in user_lineups or lineup_name not in user_lineups[user_id]:
        await ctx.send(f"❌ Lineup '{lineup_name}' doesn't exist.")
        return
    
    del user_lineups[user_id][lineup_name]
    
    # If this was the active lineup, switch to main
    if active_lineups.get(user_id) == lineup_name:
        active_lineups[user_id] = 'main'
    
    save_data()
    await ctx.send(f"🗑️ Deleted lineup: **{lineup_name.title()}**")

@bot.command()
async def end(ctx, gamemode: str = None):
    """End a specific game mode: koth or draftclash."""
    if gamemode is None:
        await ctx.send("Usage: `!end <gamemode>` where gamemode is: koth or draftclash")
        return
    
    gamemode = gamemode.lower()
    ch = ctx.channel.id
    
    if gamemode == "koth":
        if koth_state['current_king_id'] is None:
            await ctx.send("No active King of the Hill session.")
            return
        
        # Reset KoTH state
        koth_state['current_king_id'] = None
        koth_state['king_streak'] = 0
        save_data()
        await ctx.send("👑 King of the Hill session has been ended.")
        
    elif gamemode == "draftclash":
        if ch not in draft_clash_sessions:
            await ctx.send("No active Draft Clash session in this channel.")
            return
        
        # Only host can end
        session = draft_clash_sessions[ch]
        if str(ctx.author.id) != session.get('host') and ctx.author.id != PRIVILEGED_USER_ID:
            await ctx.send("Only the session host or privileged user can end Draft Clash.")
            return
            
        del draft_clash_sessions[ch]
        save_data()
        await ctx.send("⚡ Draft Clash session has been ended.")
        
    else:
        await ctx.send("❌ Unknown game mode. Available: koth, draftclash")

def load_koth(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

def save_koth(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

koth_auction = load_koth(KOTH_AUCTION_FILE)
koth_draft = load_koth(KOTH_DRAFT_FILE)

@bot.command()
async def koth(ctx, action: str = None, mode: str = None):
    """Manage KoTH sessions without player limits.
    Usage:
      !koth start auction
      !koth start draftclash  
      !koth add <session_id?> @user1 @user2
    """
    chan = str(ctx.channel.id)
    if action == "start":
     if mode == "auction":
        session_id = str(uuid.uuid4())[:8]
        koth_auction.setdefault(chan, {})
        koth_auction[chan][session_id] = {
            "id": session_id,
            "king": None,
            "streak": 0,
            "players": [],
            "active": True,
            "created_by": str(ctx.author.id),
            "created_at": time.time()
        }
        _save_json(KOTH_AUCTION_FILE, koth_auction)
        await ctx.send(f"🏟️ Auction KoTH started (ID `{session_id}`)")
        return
    elif mode == "draftclash":
            if chan in koth_draft and koth_draft[chan].get("active"):
                await ctx.send("⚠️ A Draft Clash KoTH is already running in this channel!")
                return
            koth_draft[chan] = {
                "id": str(uuid.uuid4())[:8],
                "king": None,
                "streak": 0,
                "players": [],
                "active": True,
                "created_by": str(ctx.author.id),
                "created_at": time.time()
            }
            _save_json(KOTH_DRAFT_FILE, koth_draft)
            await ctx.send("🏆 Draft Clash KoTH started! Use `!koth add @user1 @user2` to add players.")
            return
    elif action == "add":
        # ... rest of add logic stays the same but remove lineup requirement checks
        if not args:
            await ctx.send("Usage: `!koth add <session_id?> @user1 @user2`")
            return
            
        # ... rest of the add logic stays the same but without lineup checks ...
        
        for m in ctx.message.mentions:
            uid = str(m.id)
            if uid not in target_session["players"]:
                target_session["players"].append(uid)
                added.append(m.mention)
                
        if target_mode=="draft":
            _save_json(KOTH_DRAFT_FILE, koth_draft)
        else:
            _save_json(KOTH_AUCTION_FILE, koth_auction)
            
        await ctx.send(f"Added to KoTH: {', '.join(added)}")
        return
    else:
        await ctx.send("Use `!koth start` or `!koth add`.")
        return
    elif action == "add":
        # syntax: !koth add [session_id] @user1 @user2...
        parts = ctx.message.content.split()
        args = parts[2:]
        if not args:
            await ctx.send("Usage: `!koth add <session_id?> @user1 @user2`")
            return
        session_id = None
        if not args[0].startswith("<@") and not args[0].startswith("@") and not args[0].isdigit():
            session_id = args[0]
            mention_args = args[1:]
        else:
            mention_args = args
        # resolve target session: prefer draft if exists
        target_session = None
        target_mode = None
        if chan in koth_draft and koth_draft[chan].get("active"):
            target_session = koth_draft[chan]; target_mode="draft"
        else:
            auction_sessions = koth_auction.get(chan, {})
            if session_id:
                target_session = auction_sessions.get(session_id); target_mode="auction"
                if not target_session:
                    await ctx.send("No such Auction KoTH session id in this channel.")
                    return
            else:
                for sid,sess in auction_sessions.items():
                    if sess.get("active"):
                        target_session=sess; target_mode="auction"; break
        if not target_session:
            await ctx.send("No active KoTH session found to add players.")
            return
        added=[]
        for m in ctx.message.mentions:
            uid=str(m.id)
            # check lineup existence
            if uid not in user_lineups:
                await ctx.send(f"⚠️ {m.display_name} has no lineup set. They must set a lineup first.")
                continue
            # For draft mode, ideally check draft-specific lineup; here we assume users set distinct lineup
            if uid not in target_session["players"]:
                target_session["players"].append(uid)
                added.append(m.mention)
        if target_mode=="draft":
            _save_json(KOTH_DRAFT_FILE, koth_draft)
        else:
            _save_json(KOTH_AUCTION_FILE, koth_auction)
        await ctx.send(f"Added to KoTH: {', '.join(added)}")
        return
    else:
        await ctx.send("Use `!koth start` or `!koth add`.")
        return

@bot.command()
async def challenge(ctx, opponent: discord.Member = None):
    """Challenge someone in the active KoTH session. Use: !challenge @user"""
    if opponent is None:
        await ctx.send("⚠️ You must mention someone to challenge. Usage: `!challenge @user`")
        return

    chan = str(ctx.channel.id)

    # select target session: prefer draft session (only 1 allowed per channel), else pick first active auction session
    target = None
    mode = None
    session_id = None

    if chan in koth_draft and koth_draft[chan].get("active"):
        target = koth_draft[chan]
        mode = "draft"
        session_id = target.get("id")
    else:
        auction_sessions = koth_auction.get(chan, {})
        for sid, sess in (auction_sessions.items() if auction_sessions else []):
            if sess.get("active"):
                target = sess
                mode = "auction"
                session_id = sid
                break

    if not target:
        await ctx.send("⚠️ No active KoTH session in this channel. Start one with `!koth start auction` or `!koth start draftclash`.")
        return

    # membership check
    challenger_id = str(ctx.author.id)
    opponent_id = str(opponent.id)
    players = target.get("players", [])

    if challenger_id not in players or opponent_id not in players:
        await ctx.send("⚠️ Both challenger and opponent must be added to the KoTH session via `!koth add`.")
        return

    # lineup checks (require a saved lineup)
    if challenger_id not in user_lineups:
        await ctx.send(f"⚠️ {ctx.author.display_name}, you don't have a lineup set. Use `!setlineup` first.")
        return
    if opponent_id not in user_lineups:
        await ctx.send(f"⚠️ {opponent.display_name} doesn't have a lineup set. They must set a lineup with `!setlineup`.")
        return

    # helper to build member-like object needed by simulate_match display
    async def _get_member_like(uid):
        try:
            m = ctx.guild.get_member(int(uid))
            if m:
                return m
            u = await bot.fetch_user(int(uid))
            class L: pass
            o = L()
            o.display_name = getattr(u, "display_name", getattr(u, "name", str(u)))
            return o
        except Exception:
            class L: pass
            o = L()
            o.display_name = f"User {uid}"
            return o

    member1 = await _get_member_like(challenger_id)
    member2 = await _get_member_like(opponent_id)

    # run simulation - handle different possible return formats robustly
    try:
        sim = simulate_match(challenger_id, opponent_id, member1, member2)
    except Exception as e:
        await ctx.send(f"⚠️ Error running match simulation: {e}")
        return

    if not sim:
        await ctx.send("⚠️ Match could not be simulated.")
        return

    # expected: ( (goals_a, goals_b), narrative, scores )
    # but be defensive
    try:
        if isinstance(sim[0], (list, tuple)) and len(sim[0]) == 2:
            scoreline = sim[0]
            narrative = sim[1] if len(sim) > 1 else ""
            scores = sim[2] if len(sim) > 2 else None
        else:
            # fallback try: sim == ((a,b), narrative, scores)
            scoreline, narrative, scores = sim
            scoreline = tuple(scoreline)
    except Exception:
        # last attempt: try unpack simple
        try:
            scoreline = tuple(sim[0])
            narrative = sim[1] if len(sim) > 1 else ""
            scores = sim[2] if len(sim) > 2 else None
        except Exception:
            await ctx.send("⚠️ Simulation returned unexpected format; cannot parse result.")
            return

    a_goals, b_goals = int(scoreline[0]), int(scoreline[1])

    # create rich embed
    session_label = f" (session {session_id})" if session_id else ""
    title = f"⚔️ KoTH{session_label} — {ctx.author.display_name} vs {opponent.display_name}"
    embed = discord.Embed(title=title, color=discord.Color.blurple())
    embed.add_field(name="Score", value=f"**{a_goals} - {b_goals}**", inline=False)
    if narrative:
        # truncate if too long
        summary = narrative if len(narrative) <= 1000 else (narrative[:980] + "…")
        embed.add_field(name="Match Summary", value=summary, inline=False)

    # determine winner
    if a_goals > b_goals:
        winner = challenger_id
    elif b_goals > a_goals:
        winner = opponent_id
    else:
        winner = None

    # update KoTH state with safe logic
    if target.get("king") is None:
        if winner:
            target["king"] = winner
            target["streak"] = 1
            result_msg = f"👑 | **A New King is Crowned!** <@{winner}> wins the first battle! 🏆 Streak: 1"
        else:
            result_msg = "🤝 It's a draw — no King yet."
    else:
        current_king = target.get("king")
        if winner is None:
            result_msg = "🤝 It's a draw! No change to the throne."
        elif winner == current_king:
            target["streak"] = target.get("streak", 0) + 1
            result_msg = f"👑 | **The King Defends the Throne!** <@{winner}> wins again! 🔥 Streak: {target['streak']}"
        else:
            prev = current_king
            target["king"] = winner
            target["streak"] = 1
            result_msg = f"👑 | **A New King is Crowned!** <@{winner}> dethrones <@{prev}>! 🏆 Streak: 1"

    # persist
    try:
        if mode == "draft":
            _save_json(KOTH_DRAFT_FILE, koth_draft)
        else:
            _save_json(KOTH_AUCTION_FILE, koth_auction)
    except Exception as e:
        # saving failed but state updated in memory; warn
        await ctx.send(f"⚠️ Warning: could not save KoTH state: {e}")

    # send embed + result
    await ctx.send(embed=embed)
    await ctx.send(result_msg)
    return


@bot.command()
async def kingstatus(ctx):
    """Show current KoTH king(s) in this channel."""
    chan = str(ctx.channel.id)
    # Prefer draft session info (only one allowed per channel)
    if chan in koth_draft and koth_draft[chan].get("active"):
        s = koth_draft[chan]
        if s.get("king"):
            await ctx.send(f"👑 Current Draft KoTH King: <@{s['king']}> | 🔥 Streak: {s.get('streak', 0)}")
        else:
            await ctx.send("No Draft KoTH King yet. Add players and challenge!")
        return

    # Show auction sessions (can be multiple)
    auction_sessions = koth_auction.get(chan, {})
    active = {sid: ses for sid, ses in (auction_sessions.items() if auction_sessions else []) if ses.get("active")}
    if not active:
        await ctx.send("No active KoTH sessions in this channel.")
        return

    lines = []
    for sid, s in active.items():
        king = f"<@{s['king']}>" if s.get("king") else "— No King yet —"
        lines.append(f"• ID `{sid}` — King: {king} — Streak: {s.get('streak', 0)} — Players: {len(s.get('players', []))}")

    # chunk message if very long
    msg = "\n".join(lines)
    await ctx.send(msg)


@bot.command()
async def kothleaderboard(ctx):
    """Show a simple KoTH leaderboard based on current recorded streaks."""
    boards = {}
    # auction: flatten sessions
    for chan, sessions in (koth_auction.items() if isinstance(koth_auction, dict) else []):
        for sid, s in (sessions.items() if isinstance(sessions, dict) else []):
            if s.get("king"):
                uid = s.get("king")
                boards[uid] = max(boards.get(uid, 0), s.get("streak", 0))
    # draft:
    for chan, s in (koth_draft.items() if isinstance(koth_draft, dict) else []):
        if s.get("king"):
            target["king"] = winner
            target["streak"] = 1
            result_msg = f"👑 | **A New King is Crowned!** <@{winner}> wins the first battle! 🏆 Streak: 1"
        else:
            result_msg = "🤝 It's a draw — no King yet."
    else:
        current_king = target.get("king")
        if winner is None:
            result_msg = "🤝 It's a draw! No change to the throne."
        elif winner == current_king:
            target["streak"] = target.get("streak", 0) + 1
            result_msg = f"👑 | **The King Defends the Throne!** <@{winner}> wins again! 🔥 Streak: {target['streak']}"
        else:
            prev = current_king
            target["king"] = winner
            target["streak"] = 1
            result_msg = f"👑 | **A New King is Crowned!** <@{winner}> dethrones <@{prev}>! 🏆 Streak: 1"

    # persist
    try:
        if mode == "draft":
            _save_json(KOTH_DRAFT_FILE, koth_draft)
        else:
            _save_json(KOTH_AUCTION_FILE, koth_auction)
    except Exception as e:
        # saving failed but state updated in memory; warn
        await ctx.send(f"⚠️ Warning: could not save KoTH state: {e}")

    # send embed + result
    await ctx.send(embed=embed)
    await ctx.send(result_msg)
    return


@bot.command()
async def kingstatus(ctx):
    """Show current KoTH king(s) in this channel."""
    chan = str(ctx.channel.id)
    # Prefer draft session info (only one allowed per channel)
    if chan in koth_draft and koth_draft[chan].get("active"):
        s = koth_draft[chan]
        if s.get("king"):
            await ctx.send(f"👑 Current Draft KoTH King: <@{s['king']}> | 🔥 Streak: {s.get('streak', 0)}")
        else:
            await ctx.send("No Draft KoTH King yet. Add players and challenge!")
        return

    # Show auction sessions (can be multiple)
    auction_sessions = koth_auction.get(chan, {})
    active = {sid: ses for sid, ses in (auction_sessions.items() if auction_sessions else []) if ses.get("active")}
    if not active:
        await ctx.send("No active KoTH sessions in this channel.")
        return

    lines = []
    for sid, s in active.items():
        king = f"<@{s['king']}>" if s.get("king") else "— No King yet —"
        lines.append(f"• ID `{sid}` — King: {king} — Streak: {s.get('streak', 0)} — Players: {len(s.get('players', []))}")

    # chunk message if very long
    msg = "\n".join(lines)
    await ctx.send(msg)


@bot.command()
async def kothleaderboard(ctx):
    """Show a simple KoTH leaderboard based on current recorded streaks."""
    boards = {}
    # auction: flatten sessions
    for chan, sessions in (koth_auction.items() if isinstance(koth_auction, dict) else []):
        for sid, s in (sessions.items() if isinstance(sessions, dict) else []):
            if s.get("king"):
                uid = s.get("king")
                boards[uid] = max(boards.get(uid, 0), s.get("streak", 0))
    # draft:
    for chan, s in (koth_draft.items() if isinstance(koth_draft, dict) else []):
        if s.get("king"):
            uid = s.get("king")
            boards[uid] = max(boards.get(uid, 0), s.get("streak", 0))

    if not boards:
        await ctx.send("No KoTH reigns recorded yet.")
        return

    items = sorted(boards.items(), key=lambda x: x[1], reverse=True)[:10]
    desc = "\n".join([f"{i+1}. <@{uid}> — {streak} defenses" for i, (uid, streak) in enumerate(items)])
    embed = discord.Embed(title="🏆 KoTH Leaderboard", description=desc, color=discord.Color.gold())
    await ctx.send(embed=embed)


@bot.command(name="koth_list")
async def koth_list(ctx, mode: str = None):
    """List active KoTH sessions. Usage: !koth_list auction | draftclash"""
    chan = str(ctx.channel.id)
    if mode == "auction":
        sessions = koth_auction.get(chan, {})
        # filter only active sessions
        active = {sid: ses for sid, ses in (sessions.items() if sessions else []) if ses.get("active")}
        if not active:
            await ctx.send("⚠️ No active Auction KoTH sessions in this channel.")
            return
        lines = []
        for sid, s in active.items():
            king = f"<@{s['king']}>" if s.get("king") else "No King yet"
            lines.append(f"• `{sid}` — King: {king} — Streak: {s.get('streak', 0)} — Players: {len(s.get('players', []))}")
        await ctx.send("**Active Auction KoTH sessions:**\n" + "\n".join(lines))
        return
    elif mode == "draftclash":
        s = koth_draft.get(chan)
        if not s or not s.get("active"):
            await ctx.send("⚠️ No active Draft Clash KoTH session in this channel.")
            return
        king = f"<@{s['king']}>" if s.get("king") else "No King yet"
        await ctx.send(f"**Draft Clash KoTH:** ID `{s.get('id')}` — King: {king} — Streak: {s.get('streak', 0)} — Players: {len(s.get('players', []))}")
        return
    else:
        await ctx.send("Usage: `!koth_list auction` or `!koth_list draftclash`")


keep_alive()

# Start the bot
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_BOT_TOKEN"))
