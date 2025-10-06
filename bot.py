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
        '4-4-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 2, 'st': 2},
    '4-3-3': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 1, 'cam': 1, 'lw': 1, 'rw': 1, 'st': 1},
    '4-2-3-1': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 3, 'st': 1},
    '3-5-2': {'gk': 1, 'cb': 3, 'cm': 2, 'cam': 3, 'st': 2},
    '3-4-3': {'gk': 1, 'cb': 3, 'cm': 2, 'lw': 1, 'rw': 1, 'st': 1},
    '5-4-1': {'gk': 1, 'cb': 3, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 2, 'st': 1},
    '5-3-2': {'gk': 1, 'cb': 3, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 1, 'st': 2},
    '4-1-4-1': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 1, 'cam': 2, 'lw': 1, 'rw': 1, 'st': 1},
    '4-5-1': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 3, 'lw': 1, 'rw': 1, 'st': 1},
    '4-3-1-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 3, 'cam': 1, 'st': 2},
    '3-4-1-2': {'gk': 1, 'cb': 3, 'cm': 2, 'cam': 1, 'lw': 1, 'rw': 1, 'st': 2},
    '3-1-4-2': {'gk': 1, 'cb': 3, 'cm': 1, 'cam': 2, 'lw': 1, 'rw': 1, 'st': 2},
    '4-2-2-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 2, 'st': 2},
    '4-1-2-1-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 1, 'st': 2},
    '4-3-2-1': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 3, 'cam': 2, 'st': 1},
    '3-2-3-2': {'gk': 1, 'cb': 3, 'cm': 2, 'cam': 3, 'st': 2},
    '3-6-1': {'gk': 1, 'cb': 3, 'cm': 3, 'cam': 2, 'st': 1},
    '4-2-4': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'lw': 1, 'rw': 1, 'st': 2},
    '4-4-1-1': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 1, 'st': 1},
    '4-1-3-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 1, 'cam': 2, 'st': 2},
    '3-3-3-1': {'gk': 1, 'cb': 3, 'cm': 3, 'cam': 3, 'st': 1},
    '3-2-4-1': {'gk': 1, 'cb': 3, 'cm': 2, 'cam': 2, 'lw': 1, 'rw': 1, 'st': 1
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
# Track which lineup each user is currently using
active_lineups = {}
user_stats = {}  # tracks wins/losses/draws/money_spent/most_expensive/trades_made
tournaments = {}  # running tournaments (kept in-memory + saved)
pending_trades = {}  # trade proposals {trade_id: {...}}

# Draft system state variables
draft_sessions = {}
draft_wins = {}

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
    """Saves user teams, budgets, lineups, stats, and tournaments to JSON files."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "teams.json"), "w",
                  encoding='utf-8') as f:
            json.dump(user_teams, f, indent=2)
        with open(os.path.join(DATA_DIR, "budgets.json"),
                  "w",
                  encoding='utf-8') as f:
            json.dump(user_budgets, f, indent=2)
        with open(os.path.join(DATA_DIR, "lineups.json"),
                  "w",
                  encoding='utf-8') as f:
            json.dump(user_lineups, f, indent=2)
        with open(os.path.join(DATA_DIR, "stats.json"), "w",
                  encoding='utf-8') as f:
            json.dump(user_stats, f, indent=2)
        with open(os.path.join(DATA_DIR, "tournaments.json"),
                  "w",
                  encoding='utf-8') as f:
            json.dump(tournaments, f, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")
        return False
    # Draft persistence
    try:
        with open(os.path.join(DATA_DIR, "draft.json"),
                  "w",
                  encoding='utf-8') as f:
            json.dump(draft_sessions, f, indent=2)
    except Exception as e:
        print(f"Error saving draft data: {e}")

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
    # Load draft persistence
    try:
        draft_path = os.path.join(DATA_DIR, "draft.json")
        if os.path.exists(draft_path):
            with open(draft_path, "r", encoding='utf-8') as f:
                tmp = json.load(f)
                if isinstance(tmp, dict):
                    draft_sessions.update(tmp)
    except Exception as e:
        print(f"Error loading draft data: {e}")

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


def is_user_in_any_auction(user_id):
    user_id_str = str(user_id)
    for auction_id, auction_data in active_auctions.items():
        if auction_data['host'] == user_id or user_id_str in auction_data[
                'participants']:
            return True
    return False


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
                    title="⚽ Auction Started",
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
                    "⏰ Auction ended due to host inactivity for 5 minutes. Participant budgets, teams, and lineups have been reset."
                )

            del active_auctions[channel_id]
            save_data()
            break

        await asyncio.sleep(60)  # Check every minute


@bot.command()
async def startauction(ctx, *members: discord.Member, timer: int = 30):
    """Starts a new auction, registers participants, and prompts for set selection."""
    if ctx.channel.id in active_auctions:
        await ctx.send(
            "❌ An auction is already active in this channel. Please use a different channel or end the current auction first."
        )
        return

    if is_user_in_any_auction(
            ctx.author.id) and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send(
            f"❌ {ctx.author.display_name}, you are already participating in another auction."
        )
        return

    for member in members:
        if is_user_in_any_auction(
                member.id) and member.id != PRIVILEGED_USER_ID:
            await ctx.send(
                f"❌ {member.display_name} is already participating in another auction."
            )
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
        "tier_counters": {
            pos: {
                'A': 0,
                'B': 0,
                'C': 0
            }
            for pos in available_positions
        },
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

    set_list = "\n".join(
        [f"**{key}** - {name}" for key, name in available_sets.items()])
    embed.add_field(name="Available Sets", value=set_list, inline=False)
    embed.set_footer(text="Type the set key (e.g., 'wc' for World Cup XI)")

    await ctx.send(embed=embed)

    auction_state['awaiting_set_selection'] = True
    auction_state['set_selection_author'] = ctx.author.id

    # Start host activity check
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

    if is_user_in_any_auction(member.id) and member.id != PRIVILEGED_USER_ID:
        await ctx.send(
            f"❌ {member.display_name} is already participating in another auction."
        )
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

        embed = discord.Embed(title="🎨 Player Up for Auction",
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
                await ctx.send("⏳ Going once...")
                await asyncio.sleep(1)
                if not auction_state.get('bidding',
                                         False) or auction_state.get(
                                             'current_player') != player:
                    return
                await ctx.send("⏳ Going twice...")
                await asyncio.sleep(1)
                if not auction_state.get('bidding',
                                         False) or auction_state.get(
                                             'current_player') != player:
                    return
                await ctx.send("⏳ Final call...")
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

        embed = discord.Embed(title="🎨 Custom Player Up for Auction",
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
                await ctx.send("⏳ Going once...")
                await asyncio.sleep(1)
                if not auction_state.get(
                        'bidding', False) or auction_state.get(
                            'current_player') != custom_player:
                    return
                await ctx.send("⏳ Going twice...")
                await asyncio.sleep(1)
                if not auction_state.get(
                        'bidding', False) or auction_state.get(
                            'current_player') != custom_player:
                    return
                await ctx.send("⏳ Final call...")
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
        f"🏡 {ctx.author.display_name} bids {format_currency(new_price)}!")

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
            await ctx.send("⏳ Going once...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != current_player:
                return
            await ctx.send("⏳ Going twice...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != current_player:
                return
            await ctx.send("⏳ Final call...")
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

    if auction_state['host'] == ctx.author.id:
        auction_state['last_host_activity'] = time.time()

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

    embed = discord.Embed(title="🎨 Player Re-Auction",
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
            await ctx.send("⏳ Going once...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != player:
                return
            await ctx.send("⏳ Going twice...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get(
                    'current_player') != player:
                return
            await ctx.send("⏳ Final call...")
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
            # Simple scoring based on number of players
            total_score = len(team_players) * 10
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

    embed = discord.Embed(title="🏆 Team Rankings",
                          color=discord.Color.gold())
    description_list = []

    for i, (name, score, user_id, num_players) in enumerate(team_scores):
        description_list.append(
            f"**{i+1}.** <@{user_id}> ({name}): **{score} Team Score** ({num_players} players)\n"
        )

    embed.description = "\n".join(description_list)
    embed.set_footer(text="Rankings based on squad size and composition.")
    await ctx.send(embed=embed)


@bot.command()
async def endauction(ctx):
    """Ends the current auction in this channel and resets its data and participant data."""
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
        "⏰ Auction in this channel has been ended. Participant budgets, teams, and lineups have been reset."
    )


@bot.command()
async def lineups(ctx):
    """Show all your saved lineups."""
    user_id = str(ctx.author.id)
    if user_id not in user_lineups or not user_lineups[user_id]:
        await ctx.send("You don't have any lineups yet. Use `!setlineup` to create one!")
        return
    
    active_name = active_lineups.get(user_id, 'main')
    embed = discord.Embed(title="🎯 Your Lineups", color=discord.Color.blue())
    
    for lineup_name, lineup_data in user_lineups[user_id].items():
        player_count = len(lineup_data.get('players', []))
        formation = lineup_data.get('formation', '4-4-2')
        tactic = lineup_data.get('tactic', 'Balanced')
        
        status = "🏆 ACTIVE" if lineup_name == active_name else "⚪"
        value = f"{status}\n{player_count}/11 players\n{formation} ({tactic})"
        
        embed.add_field(name=f"📋 {lineup_name.title()}", value=value, inline=True)
    
    embed.set_footer(text="Use !switchlineup <name> to change active lineup | !setlineup <name> to create/edit")
    await ctx.send(embed=embed)


@bot.command()
async def switchlineup(ctx, lineup_name: str = None):
    """Switch to a different lineup."""
    if lineup_name is None:
        await ctx.send("Please specify a lineup name: `!switchlineup <name>`")
        return
    
    user_id = str(ctx.author.id)
    lineup_name = lineup_name.lower()
    
    if user_id not in user_lineups or lineup_name not in user_lineups[user_id]:
        await ctx.send(f"Lineup '{lineup_name}' doesn't exist. Use `!lineups` to see available lineups.")
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
        await ctx.send("Please specify a lineup name: `!deletelineup <name>`")
        return
    
    user_id = str(ctx.author.id)
    lineup_name = lineup_name.lower()
    
    if lineup_name == 'main':
        await ctx.send("Cannot delete the main lineup!")
        return
    
    if user_id not in user_lineups or lineup_name not in user_lineups[user_id]:
        await ctx.send(f"Lineup '{lineup_name}' doesn't exist.")
        return
    
    del user_lineups[user_id][lineup_name]
    
    # If this was the active lineup, switch to main
    if active_lineups.get(user_id) == lineup_name:
        active_lineups[user_id] = 'main'
    
    save_data()
    await ctx.send(f"🗑️ Deleted lineup: **{lineup_name.title()}**")


@bot.command()
async def footy(ctx, category: str = None):
    """Shows categorized help for the bot."""
    embed = discord.Embed(title="📖 Football Auction Bot Commands",
                          color=discord.Color.blue())

    if category is None:
        embed.description = (
            "Use `!footy <category>` to view commands in that category.\n\n"
            "Available categories:\n"
            "⚽ auction, 👥 team, 📊 leaderboards")
    elif category.lower() == "auction":
        embed.add_field(
            name="Auction Commands",
            value="\n".join([
                "`!startauction @users...` - Start a new auction",
                "`!sets` - Show all available sets",
                "`!participants` - List participants",
                "`!bid [amount]` - Place a bid",
                "`!sold / !unsold` - Resolve auction",
                "`!status` - Current auction status",
                "`!endauction` - End current auction"
        ]),
        inline=False)
    elif category.lower() == "team":
        embed.add_field(name="Team Commands",
                        value="\n".join([
                            "`!myplayers` - View your bought players",
                            "`!budget` - Show your budget",
                            "`!setlineup [name]` - Setup/edit a lineup",
                            "`!lineups` - View all your lineups",
                            "`!switchlineup <name>` - Switch active lineup",
                            "`!deletelineup <name>` - Delete a lineup",
                            "`!viewlineup` - View your active lineup"
                        ]),
                        inline=False)
    elif category.lower() == "leaderboards":
        embed.add_field(
            name="Leaderboards",
            value="\n".join([
                "`!rankteams` - Team rankings"
            ]),
            inline=False)
    else:
        embed.description = "Unknown category. Try: auction, team, leaderboards."

    await ctx.send(embed=embed)


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
        "🚑 Injury - One of your players is out for 2 matches!",
        "⚡ Form Boost - Random player gains +2 form for 3 matches!",
        "📰 Transfer Rumor - Random player may be swapped with the market!",
    ]
    event = random.choice(events_list)
    await ctx.send(f"🎲 Random Event: {event}")


@bot.group(invoke_without_command=True)
async def draft(ctx):
    """Draft mode base command."""
    await ctx.send(
        "📋 Use `!draft start` to begin the draft or check draft commands with !footy."
    )


@draft.command()
async def start(ctx):
    await ctx.send("📋 Draft mode started! Turn order will be assigned.")


@draft.command()
async def pick(ctx, *, player_name):
    await ctx.send(f"✅ {ctx.author.mention} picked **{player_name}**.")


# -------------------- Who Am I? Game Mode --------------------
whoami_sessions = {}

@bot.command()
async def whoami(ctx, action: str = None):
    """Start a 'Who Am I?' guessing game.
    Usage: !whoami start <set_key> - Host starts the game
           !whoami join - Players join the lobby
           !whoami begin - Host begins after players join
           !whoami reveal - Reveal your assigned player
           !whoami end - End the game
    """
    ch = ctx.channel.id
    
    if action is None:
        await ctx.send(
            "**Who Am I? Game Mode**\n"
            "Commands:\n"
            "`!whoami start <set>` - Start a new game (e.g., !whoami start 24-25)\n"
            "`!whoami join` - Join the game lobby\n"
            "`!whoami begin` - Begin the game (host only)\n"
            "`!whoami reveal` - Reveal your player identity\n"
            "`!whoami end` - End the game\n\n"
            "**How to Play:**\n"
            "Each player gets assigned a footballer. Everyone else knows who you are except YOU!\n"
            "Ask yes/no questions to figure out your identity. First to guess wins!"
        )
        return
    
    action = action.lower()
    
    if action == "start":
        if ch in whoami_sessions and whoami_sessions[ch].get('state') in ['lobby', 'playing']:
            await ctx.send("A Who Am I game is already active in this channel. Use `!whoami end` to end it first.")
            return
        
        # Parse set key from command
        parts = ctx.message.content.split()
        set_key = parts[2].lower() if len(parts) > 2 else '24-25'
        
        if set_key not in available_sets:
            await ctx.send(f"Invalid set key. Available sets: {', '.join(available_sets.keys())}")
            return
        
        whoami_sessions[ch] = {
            'host': str(ctx.author.id),
            'players': [str(ctx.author.id)],
            'state': 'lobby',
            'set_key': set_key,
            'assignments': {},  # {user_id: player_dict}
            'revealed': set()  # users who revealed their identity
        }
        
        embed = discord.Embed(
            title="🎭 Who Am I? - Lobby Open",
            description=f"**Set:** {available_sets[set_key]}\n\nHost: {ctx.author.mention}\n\nReact with ✅ to join!",
            color=discord.Color.green()
        )
        embed.set_footer(text="Host uses !whoami begin to start the game")
        
        join_msg = await ctx.send(embed=embed)
        await join_msg.add_reaction("✅")
        
        def check(reaction, user):
            return str(reaction.emoji) == "✅" and reaction.message.id == join_msg.id and not user.bot
        
        async def wait_for_joins():
            while whoami_sessions.get(ch, {}).get('state') == 'lobby':
                try:
                    reaction, user = await bot.wait_for('reaction_add', timeout=300, check=check)
                    uid = str(user.id)
                    if uid not in whoami_sessions[ch]['players']:
                        whoami_sessions[ch]['players'].append(uid)
                        await ctx.send(f"{user.mention} joined the game! Total players: {len(whoami_sessions[ch]['players'])}")
                except asyncio.TimeoutError:
                    break
        
        bot.loop.create_task(wait_for_joins())
        return
    
    elif action == "join":
        if ch not in whoami_sessions or whoami_sessions[ch].get('state') != 'lobby':
            await ctx.send("No Who Am I lobby is open. Host must use `!whoami start <set>` first.")
            return
        
        uid = str(ctx.author.id)
        if uid in whoami_sessions[ch]['players']:
            await ctx.send("You've already joined!")
            return
        
        whoami_sessions[ch]['players'].append(uid)
        await ctx.send(f"{ctx.author.mention} joined! Total players: {len(whoami_sessions[ch]['players'])}")
        return
    
    elif action == "begin":
        if ch not in whoami_sessions or whoami_sessions[ch].get('state') != 'lobby':
            await ctx.send("No lobby to begin. Use `!whoami start <set>` first.")
            return
        
        session = whoami_sessions[ch]
        if str(ctx.author.id) != session['host']:
            await ctx.send("Only the host can begin the game.")
            return
        
        if len(session['players']) < 2:
            await ctx.send("Need at least 2 players to start!")
            return
        
        if len(session['players']) > 10:
            await ctx.send("Maximum 10 players allowed!")
            return
        
        # Collect all players from the chosen set
        all_players = []
        for pos in available_positions:
            tiered_players = load_players_by_position(pos, session['set_key'])
            for tier in ['A', 'B', 'C']:
                all_players.extend(tiered_players[tier])
        
        if len(all_players) < len(session['players']):
            await ctx.send("Not enough players in this set for all participants!")
            return
        
        # Randomly assign unique players to each participant
        selected_players = random.sample(all_players, len(session['players']))
        for i, uid in enumerate(session['players']):
            session['assignments'][uid] = selected_players[i]
        
        session['state'] = 'playing'
        
        # Send DMs to each player with everyone's assignments EXCEPT their own
        for uid in session['players']:
            try:
                user = await bot.fetch_user(int(uid))
                embed = discord.Embed(
                    title="🎭 Who Am I? - Game Started!",
                    description="**Your mission:** Figure out which player YOU are!\n\nHere's what everyone else got:",
                    color=discord.Color.blue()
                )
                
                for other_uid in session['players']:
                    if other_uid != uid:
                        other_user = await bot.fetch_user(int(other_uid))
                        player_info = session['assignments'][other_uid]
                        embed.add_field(
                            name=f"{other_user.display_name}",
                            value=f"**{player_info['name']}** ({player_info.get('position', 'Unknown').upper()})",
                            inline=False
                        )
                
                embed.add_field(
                    name="🤔 Your Player",
                    value="**??? - THIS IS WHAT YOU NEED TO GUESS!**",
                    inline=False
                )
                embed.set_footer(text="Ask yes/no questions in the channel to figure out your identity!\nUse !whoami reveal when you think you know!")
                
                await user.send(embed=embed)
            except discord.Forbidden:
                await ctx.send(f"⚠️ Couldn't DM {user.display_name}. Make sure DMs are enabled!")
            except Exception as e:
                print(f"Error sending DM to {uid}: {e}")
        
        # Announce in channel
        announce_embed = discord.Embed(
            title="🎭 Who Am I? - Game Started!",
            description=f"**{len(session['players'])} players** are in the game!\n\n"
                       f"**Set:** {available_sets[session['set_key']]}\n\n"
                       "Each player has been assigned a footballer. Check your DMs to see everyone else's players!\n\n"
                       "**Rules:**\n"
                       "• Ask yes/no questions to figure out YOUR player\n"
                       "• You can see everyone else's players but not your own\n"
                       "• Use `!whoami reveal` when you think you know!\n"
                       "• First to guess correctly wins!",
            color=discord.Color.gold()
        )
        await ctx.send(embed=announce_embed)
        return
    
    elif action == "reveal":
        if ch not in whoami_sessions or whoami_sessions[ch].get('state') != 'playing':
            await ctx.send("No active Who Am I game in this channel.")
            return
        
        session = whoami_sessions[ch]
        uid = str(ctx.author.id)
        
        if uid not in session['assignments']:
            await ctx.send("You're not in this game!")
            return
        
        if uid in session['revealed']:
            await ctx.send("You've already revealed your player!")
            return
        
        # Reveal their player
        player = session['assignments'][uid]
        session['revealed'].add(uid)
        
        embed = discord.Embed(
            title="🎭 Player Revealed!",
            description=f"{ctx.author.mention}'s player was:",
            color=discord.Color.purple()
        )
        embed.add_field(
            name=player['name'],
            value=f"**Position:** {player.get('position', 'Unknown').upper()}\n"
                  f"**League:** {player.get('league', 'Unknown')}\n"
                  f"**Tier:** {player.get('tier', 'C')}",
            inline=False
        )
        
        if len(session['revealed']) == len(session['players']):
            embed.add_field(
                name="🏆 Game Over!",
                value="All players have been revealed!",
                inline=False
            )
            session['state'] = 'finished'
        
        await ctx.send(embed=embed)
        return
    
    elif action == "end":
        if ch not in whoami_sessions:
            await ctx.send("No Who Am I game in this channel.")
            return
        
        session = whoami_sessions[ch]
        if str(ctx.author.id) != session['host'] and ctx.author.id != PRIVILEGED_USER_ID:
            await ctx.send("Only the host can end the game.")
            return
        
        del whoami_sessions[ch]
        await ctx.send("🎭 Who Am I game has been ended.")
        return
    
    else:
        await ctx.send("Unknown action. Use: start, join, begin, reveal, or end")


@bot.command()
async def guess(ctx, *, player_name: str):
    """Make a guess for your Who Am I player.
    Usage: !guess <player name>
    """
    ch = ctx.channel.id
    
    if ch not in whoami_sessions or whoami_sessions[ch].get('state') != 'playing':
        await ctx.send("No active Who Am I game in this channel.")
        return
    
    session = whoami_sessions[ch]
    uid = str(ctx.author.id)
    
    if uid not in session['assignments']:
        await ctx.send("You're not in this game!")
        return
    
    if uid in session['revealed']:
        await ctx.send("You've already revealed your player!")
        return
    
    # Check if guess is correct
    actual_player = session['assignments'][uid]
    
    if player_name.lower().strip() == actual_player['name'].lower().strip():
        session['revealed'].add(uid)
        
        embed = discord.Embed(
            title="🏆 CORRECT GUESS!",
            description=f"{ctx.author.mention} guessed correctly!",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Their Player",
            value=f"**{actual_player['name']}** ({actual_player.get('position', 'Unknown').upper()})",
            inline=False
        )
        
        if len(session['revealed']) == len(session['players']):
            embed.add_field(
                name="🎮 Game Over!",
                value="All players have been revealed!",
                inline=False
            )
            session['state'] = 'finished'
        
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ Wrong! **{player_name}** is not your player. Keep guessing!")


# -------------------- Among Us Game Mode --------------------
amongus_sessions = {}

@bot.command()
async def amongus(ctx, action: str = None):
    """Start an Among Us style impostor game.
    Usage: !amongus start <set_key> - Host starts the game
           !amongus join - Players join the lobby
           !amongus begin - Host begins after players join
           !amongus end - End the game
    """
    ch = ctx.channel.id
    
    if action is None:
        await ctx.send(
            "**Among Us - Impostor Game Mode**\n"
            "Commands:\n"
            "`!amongus start <set>` - Start a new game (e.g., !amongus start 24-25)\n"
            "`!amongus join` - Join the game lobby\n"
            "`!amongus begin` - Begin the game (host only)\n"
            "`!vote @player` - Vote to eject a player\n"
            "`!amongus end` - End the game\n\n"
            "**How to Play:**\n"
            "Everyone gets the same footballer EXCEPT one impostor who gets a different one!\n"
            "Discuss and vote to find the impostor. Majority vote ejects a player!"
        )
        return
    
    action = action.lower()
    
    if action == "start":
        if ch in amongus_sessions and amongus_sessions[ch].get('state') in ['lobby', 'playing']:
            await ctx.send("An Among Us game is already active in this channel. Use `!amongus end` to end it first.")
            return
        
        # Parse set key from command
        parts = ctx.message.content.split()
        set_key = parts[2].lower() if len(parts) > 2 else '24-25'
        
        if set_key not in available_sets:
            await ctx.send(f"Invalid set key. Available sets: {', '.join(available_sets.keys())}")
            return
        
        amongus_sessions[ch] = {
            'host': str(ctx.author.id),
            'players': [str(ctx.author.id)],
            'state': 'lobby',
            'set_key': set_key,
            'impostor': None,
            'crewmate_player': None,
            'impostor_player': None,
            'votes': {},  # {voter_id: voted_for_id}
            'ejected': []
        }
        
        embed = discord.Embed(
            title="🔴 Among Us - Lobby Open",
            description=f"**Set:** {available_sets[set_key]}\n\nHost: {ctx.author.mention}\n\nReact with ✅ to join!",
            color=discord.Color.red()
        )
        embed.set_footer(text="Host uses !amongus begin to start the game")
        
        join_msg = await ctx.send(embed=embed)
        await join_msg.add_reaction("✅")
        
        def check(reaction, user):
            return str(reaction.emoji) == "✅" and reaction.message.id == join_msg.id and not user.bot
        
        async def wait_for_joins():
            while amongus_sessions.get(ch, {}).get('state') == 'lobby':
                try:
                    reaction, user = await bot.wait_for('reaction_add', timeout=300, check=check)
                    uid = str(user.id)
                    if uid not in amongus_sessions[ch]['players']:
                        amongus_sessions[ch]['players'].append(uid)
                        await ctx.send(f"{user.mention} joined the game! Total players: {len(amongus_sessions[ch]['players'])}")
                except asyncio.TimeoutError:
                    break
        
        bot.loop.create_task(wait_for_joins())
        return
    
    elif action == "join":
        if ch not in amongus_sessions or amongus_sessions[ch].get('state') != 'lobby':
            await ctx.send("No Among Us lobby is open. Host must use `!amongus start <set>` first.")
            return
        
        uid = str(ctx.author.id)
        if uid in amongus_sessions[ch]['players']:
            await ctx.send("You've already joined!")
            return
        
        amongus_sessions[ch]['players'].append(uid)
        await ctx.send(f"{ctx.author.mention} joined! Total players: {len(amongus_sessions[ch]['players'])}")
        return
    
    elif action == "begin":
        if ch not in amongus_sessions or amongus_sessions[ch].get('state') != 'lobby':
            await ctx.send("No lobby to begin. Use `!amongus start <set>` first.")
            return
        
        session = amongus_sessions[ch]
        if str(ctx.author.id) != session['host']:
            await ctx.send("Only the host can begin the game.")
            return
        
        if len(session['players']) < 3:
            await ctx.send("Need at least 3 players to start!")
            return
        
        if len(session['players']) > 10:
            await ctx.send("Maximum 10 players allowed!")
            return
        
        # Collect all players from the chosen set
        all_players = []
        for pos in available_positions:
            tiered_players = load_players_by_position(pos, session['set_key'])
            for tier in ['A', 'B', 'C']:
                all_players.extend(tiered_players[tier])
        
        if len(all_players) < 2:
            await ctx.send("Not enough players in this set!")
            return
        
        # Select 2 random players: one for crewmates, one for impostor
        selected_players = random.sample(all_players, 2)
        session['crewmate_player'] = selected_players[0]
        session['impostor_player'] = selected_players[1]
        
        # Randomly select impostor
        session['impostor'] = random.choice(session['players'])
        
        session['state'] = 'playing'
        
        # Send DMs to each player
        for uid in session['players']:
            try:
                user = await bot.fetch_user(int(uid))
                
                if uid == session['impostor']:
                    # Impostor gets different player
                    embed = discord.Embed(
                        title="🔴 You are the IMPOSTOR!",
                        description="Everyone else has a different player. Blend in and don't get caught!",
                        color=discord.Color.red()
                    )
                    embed.add_field(
                        name="Your Player",
                        value=f"**{session['impostor_player']['name']}**\n"
                              f"Position: {session['impostor_player'].get('position', 'Unknown').upper()}\n"
                              f"League: {session['impostor_player'].get('league', 'Unknown')}",
                        inline=False
                    )
                    embed.set_footer(text="Don't reveal your player! Vote others out to win!")
                else:
                    # Crewmates get the same player
                    embed = discord.Embed(
                        title="🔵 You are a CREWMATE!",
                        description="You and other crewmates have the same player. Find the impostor!",
                        color=discord.Color.blue()
                    )
                    embed.add_field(
                        name="Your Player",
                        value=f"**{session['crewmate_player']['name']}**\n"
                              f"Position: {session['crewmate_player'].get('position', 'Unknown').upper()}\n"
                              f"League: {session['crewmate_player'].get('league', 'Unknown')}",
                        inline=False
                    )
                    embed.set_footer(text="Discuss with others and vote out the impostor!")
                
                await user.send(embed=embed)
            except discord.Forbidden:
                await ctx.send(f"⚠️ Couldn't DM {user.display_name}. Make sure DMs are enabled!")
            except Exception as e:
                print(f"Error sending DM to {uid}: {e}")
        
        # Announce in channel
        announce_embed = discord.Embed(
            title="🔴 Among Us - Game Started!",
            description=f"**{len(session['players'])} players** are in the game!\n\n"
                       f"**Set:** {available_sets[session['set_key']]}\n\n"
                       "One player is the IMPOSTOR with a different footballer!\n"
                       "Everyone else has the SAME player.\n\n"
                       "**Rules:**\n"
                       "• Discuss and figure out who has a different player\n"
                       "• Use `!vote @player` to vote someone out\n"
                       "• Majority vote ejects the player\n"
                       "• Find the impostor to win!",
            color=discord.Color.red()
        )
        announce_embed.add_field(
            name="Players",
            value=", ".join([f"<@{uid}>" for uid in session['players']]),
            inline=False
        )
        await ctx.send(embed=announce_embed)
        return
    
    elif action == "end":
        if ch not in amongus_sessions:
            await ctx.send("No Among Us game in this channel.")
            return
        
        session = amongus_sessions[ch]
        if str(ctx.author.id) != session['host'] and ctx.author.id != PRIVILEGED_USER_ID:
            await ctx.send("Only the host can end the game.")
            return
        
        del amongus_sessions[ch]
        await ctx.send("🔴 Among Us game has been ended.")
        return
    
    else:
        await ctx.send("Unknown action. Use: start, join, begin, or end")


@bot.command()
async def vote(ctx, target: discord.Member = None):
    """Vote to eject a player in Among Us game.
    Usage: !vote @player
    """
    ch = ctx.channel.id
    
    if ch not in amongus_sessions or amongus_sessions[ch].get('state') != 'playing':
        await ctx.send("No active Among Us game in this channel.")
        return
    
    if target is None:
        await ctx.send("You must mention a player to vote! Usage: `!vote @player`")
        return
    
    session = amongus_sessions[ch]
    voter_id = str(ctx.author.id)
    target_id = str(target.id)
    
    if voter_id not in session['players']:
        await ctx.send("You're not in this game!")
        return
    
    if voter_id in session['ejected']:
        await ctx.send("You've been ejected and cannot vote!")
        return
    
    if target_id not in session['players']:
        await ctx.send("That player is not in the game!")
        return
    
    if target_id in session['ejected']:
        await ctx.send("That player has already been ejected!")
        return
    
    # Record vote
    session['votes'][voter_id] = target_id
    await ctx.send(f"✅ {ctx.author.mention} voted for {target.mention}")
    
    # Count active players (not ejected)
    active_players = [p for p in session['players'] if p not in session['ejected']]
    
    # Check if all active players have voted
    active_voters = [v for v in session['votes'].keys() if v in active_players]
    
    if len(active_voters) >= len(active_players):
        # Tally votes
        vote_counts = {}
        for voted_for in session['votes'].values():
            if voted_for in active_players:
                vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1
        
        if not vote_counts:
            await ctx.send("No valid votes cast. Voting reset.")
            session['votes'].clear()
            return
        
        # Find player(s) with most votes
        max_votes = max(vote_counts.values())
        top_voted = [uid for uid, count in vote_counts.items() if count == max_votes]
        
        if len(top_voted) > 1:
            # Tie - no ejection
            await ctx.send(f"🤝 Tie vote! No one was ejected. Players with {max_votes} votes: {', '.join([f'<@{uid}>' for uid in top_voted])}")
            session['votes'].clear()
            return
        
        # Eject the player with most votes
        ejected_id = top_voted[0]
        session['ejected'].append(ejected_id)
        session['votes'].clear()
        
        try:
            ejected_user = await bot.fetch_user(int(ejected_id))
            
            # Check if they were the impostor
            if ejected_id == session['impostor']:
                # Crewmates win!
                embed = discord.Embed(
                    title="🎉 CREWMATES WIN!",
                    description=f"{ejected_user.mention} was ejected with {max_votes} votes.",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="Result",
                    value=f"**{ejected_user.display_name} WAS the impostor!**\n"
                          f"Impostor's Player: **{session['impostor_player']['name']}**\n"
                          f"Crewmate's Player: **{session['crewmate_player']['name']}**",
                    inline=False
                )
                session['state'] = 'finished'
            else:
                # Wrong person ejected
                embed = discord.Embed(
                    title="❌ Wrong Person Ejected!",
                    description=f"{ejected_user.mention} was ejected with {max_votes} votes.",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="Result",
                    value=f"**{ejected_user.display_name} was NOT the impostor!**\n"
                          f"Their Player: **{session['crewmate_player']['name']}**\n\n"
                          f"The impostor is still among you! Continue voting.",
                    inline=False
                )
                
                # Check if impostor wins (only 2 or fewer active players left)
                remaining_active = [p for p in session['players'] if p not in session['ejected']]
                if len(remaining_active) <= 2:
                    impostor_user = await bot.fetch_user(int(session['impostor']))
                    embed = discord.Embed(
                        title="🔴 IMPOSTOR WINS!",
                        description="Not enough players left to vote out the impostor!",
                        color=discord.Color.red()
                    )
                    embed.add_field(
                        name="Result",
                        value=f"**{impostor_user.display_name} was the impostor!**\n"
                              f"Impostor's Player: **{session['impostor_player']['name']}**\n"
                              f"Crewmate's Player: **{session['crewmate_player']['name']}**",
                        inline=False
                    )
                    session['state'] = 'finished'
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Error processing ejection: {e}")
            await ctx.send(f"<@{ejected_id}> was ejected with {max_votes} votes!")


keep_alive()

# Start the bot
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_BOT_TOKEN"))
