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
    """Simulate a match and produce commentary.
    Returns: ( (goals1, goals2), narrative_string, events_dict )
    """
    try:
        # compute attack/defense using existing helper
        attack1, defense1 = calculate_team_score_based_on_lineup(team1_id)
        attack2, defense2 = calculate_team_score_based_on_lineup(team2_id)
    except Exception:
        # fallback to simple values
        attack1 = random.randint(50, 120)
        defense1 = random.randint(50, 120)
        attack2 = random.randint(50, 120)
        defense2 = random.randint(50, 120)

    # determine goals by comparing attacks vs defenses, with randomness
    diff1 = max(0, attack1 - defense2)
    diff2 = max(0, attack2 - defense1)

    # base goal expectation scaled down
    g1 = int(round(diff1 / 60.0)) + random.randint(0,2)
    g2 = int(round(diff2 / 60.0)) + random.randint(0,2)

    # adjust slightly for randomness
    if random.random() < 0.12:
        g1 += 1
    if random.random() < 0.12:
        g2 += 1

    # clamp
    g1 = max(0, min(6, g1))
    g2 = max(0, min(6, g2))

    # create commentary events
    commentary = []
    commentary.append("⚽ Kick-off!")

    total_goals = g1 + g2
    # number of other events
    other_events = max(3, 6 - total_goals + random.randint(0,3))
    num_events = total_goals + other_events

    minutes = sorted(random.sample(range(1, 90), min(15, max(5, num_events))))
    goal_minutes = []
    # assign goal minutes for team1 and team2
    goal_minutes_team1 = sorted(random.sample(minutes, g1)) if g1>0 else []
    remaining_minutes = [m for m in minutes if m not in goal_minutes_team1]
    goal_minutes_team2 = sorted(random.sample(remaining_minutes, g2)) if g2>0 else []

    # helper to pick random player name from lineup
    def pick_name(team_id):
        try:
            lineup = user_lineups.get(team_id, {}).get(active_lineups.get(team_id,'main'), {})
            players = lineup.get('players') or user_teams.get(team_id, [])
            if players:
                p = random.choice(players)
                return p.get('name', 'Player')
        except Exception:
            pass
        return "Player"

    for minute in minutes:
        if minute in goal_minutes_team1:
            scorer = pick_name(team1_id)
            commentary.append(f"🔥 {minute}’ — GOAL! {scorer} finishes coolly for {team1.display_name}. ({g1}-{g2})")
        elif minute in goal_minutes_team2:
            scorer = pick_name(team2_id)
            commentary.append(f"🔥 {minute}’ — GOAL! {scorer} nets one for {team2.display_name}. ({g1}-{g2})")
        else:
            ev = random.choice(["shot", "save", "miss", "foul", "counter", "chance"])
            if ev == "shot":
                commentary.append(f"⚡ {minute}’ — A thunderous shot from distance that tests the keeper.")
            elif ev == "save":
                commentary.append(f"🧤 {minute}’ — Brilliant save from the keeper to keep the scoreline level.")
            elif ev == "miss":
                commentary.append(f"❌ {minute}’ — Close! The chance drifts wide.")
            elif ev == "foul":
                commentary.append(f"🟨 {minute}’ — A cynical challenge; the referee reaches for a card.")
            elif ev == "counter":
                commentary.append(f"⚡ {minute}’ — Rapid counter-attack — almost a goal!")
            else:
                commentary.append(f"🔁 {minute}’ — A tense moment in midfield.")

    commentary.append(f"🏁 Full time: {team1.display_name} {g1}–{g2} {team2.display_name}")

    narrative = "\n".join(commentary)
    events = {"goals": {"team1": g1, "team2": g2}, "commentary": commentary}

    return (g1, g2), narrative, events

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
async def koth_add(ctx, *members: discord.Member):
    mode = None
    if ctx.channel.id in koth_draft and koth_draft[ctx.channel.id]["active"]:
        mode = "draft"; session = koth_draft[ctx.channel.id]
    elif ctx.channel.id in koth_auction and koth_auction[ctx.channel.id]["active"]:
        mode = "auction"; session = koth_auction[ctx.channel.id]
    else:
        await ctx.send("⚠️ No active KoTH session in this channel!"); return

    for m in members:
        if m.id not in session["players"]:
            session["players"].append(m.id)

    if mode == "draft": save_koth(KOTH_DRAFT_FILE, koth_draft)
    else: save_koth(KOTH_AUCTION_FILE, koth_auction)

    await ctx.send(f"Players added: {', '.join([m.mention for m in members])}")




# -------------------- KoTH System (Merged) --------------------

def _load_json(path):
    try:
        if os.path.exists(path):
            with open(path,"r",encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print("Error loading",path,e)
    return {}

def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path,"w",encoding="utf-8") as f:
            json.dump(data,f,indent=2)
    except Exception as e:
        print("Error saving",path,e)

koth_auction = _load_json(KOTH_AUCTION_FILE)
koth_draft = _load_json(KOTH_DRAFT_FILE)

@bot.command()
async def koth(ctx, action: str = None, mode: str = None):
    """Manage KoTH sessions.
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
            await ctx.send(f"🏟️ Auction KoTH started (ID `{session_id}`). Use `!koth add {session_id} @user1 @user2` to add players. Multiple Auction KoTH allowed in this channel.")
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
            await ctx.send("🏆 Draft Clash KoTH started! Use `!koth add @user1 @user2` to add players. (Draft Clash KoTH uses Draft Clash squads only.)")
            return
        else:
            await ctx.send("Usage: `!koth start auction` or `!koth start draftclash`")
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
    """Challenge someone in KoTH — open to anyone with a lineup."""
    if opponent is None:
        await ctx.send("⚠️ You must mention someone to challenge. Usage: `!challenge @user`")
        return

    challenger_id = str(ctx.author.id)
    opponent_id = str(opponent.id)

    # lineup checks
    if challenger_id not in user_lineups:
        await ctx.send(f"⚠️ {ctx.author.display_name}, you don’t have a lineup. Use `!setlineup` first.")
        return
    if opponent_id not in user_lineups:
        await ctx.send(f"⚠️ {opponent.display_name} doesn’t have a lineup yet. They must set one with `!setlineup`.")
        return

    # pick session (prefer draft if active in channel else auction default)
    chan = str(ctx.channel.id)
    target = None
    mode = None
    session_id = None
    if chan in koth_draft and koth_draft[chan].get("active"):
        target = koth_draft[chan]; mode="draft"; session_id = target.get("id")
    else:
        # pick or create default auction session for channel
        auction_sessions = koth_auction.setdefault(chan, {})
        if auction_sessions:
            # pick first active session
            found = None
            for sid,sess in auction_sessions.items():
                if sess.get("active"):
                    found = sess; session_id = sid; break
            if found:
                target = found; mode="auction"
            else:
                # create a default auction session entry
                sid = "default"
                target = auction_sessions.setdefault(sid, {"id":sid,"king":None,"streak":0,"players":[],"active":True})
                session_id = sid; mode="auction"
        else:
            # create default session
            sid = "default"
            auction_sessions[sid] = {"id":sid,"king":None,"streak":0,"players":[],"active":True}
            target = auction_sessions[sid]; session_id = sid; mode="auction"

    # run simulation
    member1 = ctx.author
    member2 = opponent
    try:
        scoreline, narrative, events = simulate_match(challenger_id, opponent_id, member1, member2)
    except Exception as e:
        await ctx.send(f"⚠️ Error simulating match: {e}")
        return

    a_goals, b_goals = scoreline

    # send commentary instantly
    await ctx.send(narrative)

    # determine winner & update KoTH
    if target.get("king") is None:
        if a_goals > b_goals:
            winner = challenger_id
        elif b_goals > a_goals:
            winner = opponent_id
        else:
            winner = None

        if winner:
            target["king"] = winner
            target["streak"] = 1
            await ctx.send(f"👑 | **A New King is Crowned!** <@{winner}> wins the first battle! 🏆 Streak: 1")
        else:
            await ctx.send("🤝 It's a draw! No King yet.")
    else:
        current = target.get("king")
        if a_goals == b_goals:
            await ctx.send("🤝 It's a draw! The King stays on the throne.")
        else:
            winner = challenger_id if a_goals > b_goals else opponent_id
            if winner == current:
                target["streak"] = target.get("streak",0) + 1
                await ctx.send(f"👑 | **The King Defends the Throne!** <@{winner}> wins again! 🔥 Streak: {target['streak']}")
            else:
                prev = current
                target["king"] = winner
                target["streak"] = 1
                await ctx.send(f"👑 | **A New King is Crowned!** <@{winner}> dethrones <@{prev}>! 🏆 Streak: 1")

    # persist
    try:
        if mode == "draft":
            _save_json(KOTH_DRAFT_FILE, koth_draft)
        else:
            _save_json(KOTH_AUCTION_FILE, koth_auction)
    except Exception:
        pass

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
