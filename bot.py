# bot.py
import discord
from discord.ext import commands
import json
import random
import os
import asyncio
import time
import google.generativeai as genai

# --- Configuration ---
# It's best practice to load your tokens from environment variables
# For Render, you will set these in the "Environment" tab for your service
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_DISCORD_BOT_TOKEN_HERE")
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY", "YOUR_GOOGLE_AI_API_KEY_HERE")

INTENTS = discord.Intents.default()
INTENTS.message_content = True
BOT = commands.Bot(command_prefix='!', intents=INTENTS)

# --- AI Model Configuration ---
if GOOGLE_AI_API_KEY != "YOUR_GOOGLE_AI_API_KEY_HERE":
    genai.configure(api_key=GOOGLE_AI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
else:
    model = None # AI will be disabled if no key is found

# --- Constants ---
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
PLAYER_DIR = os.path.join(os.path.dirname(__file__), 'players')
STARTING_BUDGET = 1000000000
BID_INCREMENT = 5000000
MIN_BASE_PRICE = 1000000
MAX_PLAYERS_PER_USER = 15
PRIVILEGED_USER_ID = 962232390686765126 # Change this to your Discord User ID

AVAILABLE_POSITIONS = ['st', 'rw', 'lw', 'cam', 'cm', 'lb', 'cb', 'rb', 'gk']
AVAILABLE_FORMATIONS = {
    '4-4-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 2, 'st': 2},
    '4-3-3': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 3, 'lw': 1, 'rw': 1, 'st': 1},
    '4-2-3-1': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 3, 'st': 1},
    '3-5-2': {'gk': 1, 'cb': 3, 'cm': 2, 'cam': 3, 'st': 2},
    '5-3-2': {'gk': 1, 'cb': 3, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 1, 'st': 2},
}
AVAILABLE_TACTICS = ['Attacking', 'Defensive', 'Balanced']
AVAILABLE_SETS = {
    'wc': 'World Cup XI',
    'ucl': 'Champions League XI',
    'epl': 'Premier League XI',
    'laliga': 'La Liga XI',
    '24-25': '24-25 Season'
}

# --- In-Memory State ---
user_teams = {}
user_budgets = {}
user_lineups = {}
user_stats = {}
draft_sessions = {}
active_auctions = {}
lineup_setup_sessions = {}

# --- Helper Functions ---
def format_currency(amount):
    """Formats a number into a currency string like $10,000,000."""
    return f"${amount:,}"

# ... (save_data, load_data, load_players_by_position, ensure_user_structures functions remain the same) ...
def save_data():
    """Saves all critical bot data to JSON files."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "teams.json"), "w") as f:
            json.dump(user_teams, f, indent=2)
        with open(os.path.join(DATA_DIR, "budgets.json"), "w") as f:
            json.dump(user_budgets, f, indent=2)
        with open(os.path.join(DATA_DIR, "lineups.json"), "w") as f:
            json.dump(user_lineups, f, indent=2)
        with open(os.path.join(DATA_DIR, "stats.json"), "w") as f:
            json.dump(user_stats, f, indent=2)
        print("Data saved successfully.")
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

def load_data():
    """Loads all critical bot data from JSON files."""
    global user_teams, user_budgets, user_lineups, user_stats
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(os.path.join(DATA_DIR, "teams.json")):
            with open(os.path.join(DATA_DIR, "teams.json"), "r") as f:
                user_teams = json.load(f)
        if os.path.exists(os.path.join(DATA_DIR, "budgets.json")):
            with open(os.path.join(DATA_DIR, "budgets.json"), "r") as f:
                user_budgets = json.load(f)
        if os.path.exists(os.path.join(DATA_DIR, "lineups.json")):
            with open(os.path.join(DATA_DIR, "lineups.json"), "r") as f:
                user_lineups = json.load(f)
        if os.path.exists(os.path.join(DATA_DIR, "stats.json")):
            with open(os.path.join(DATA_DIR, "stats.json"), "r") as f:
                user_stats = json.load(f)
        print("Data loaded successfully.")
    except Exception as e:
        print(f"Error loading data: {e}")

def load_players_by_position(position, set_name):
    """
    Loads all players for a specific position and set.
    IMPORTANT: Assumes your player JSON files now have a "rating" field.
    """
    filename = os.path.join(PLAYER_DIR, set_name, f'{position.lower()}.json')
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            players = json.load(f)
            for player in players:
                if 'base_price' not in player:
                    player['base_price'] = random.randint(1, 20) * 1000000
                if 'rating' not in player:
                    player['rating'] = random.randint(70, 95)
            return players if isinstance(players, list) else []
    except Exception as e:
        print(f"Error loading players from {filename}: {e}")
        return []

def ensure_user_structures(user_id_str):
    """Initializes data structures for a new user."""
    if user_id_str not in user_budgets:
        user_budgets[user_id_str] = STARTING_BUDGET
    if user_id_str not in user_teams:
        user_teams[user_id_str] = []
    if user_id_str not in user_lineups:
        user_lineups[user_id_str] = {
            'players': [], 'tactic': 'Balanced', 'formation': '4-4-2'
        }
    if user_id_str not in user_stats:
        user_stats[user_id_str] = {
            'wins': 0, 'losses': 0, 'draws': 0,
            'money_spent': 0, 'most_expensive': 0
        }

# --- AI "Thinking" Function ---
async def get_ai_commentary(player_name, player_set):
    """Generates expert commentary for a player using the Gemini API."""
    if not model:
        return "AI commentary is not configured. An API key is needed."
    try:
        prompt = (f"You are an expert football auctioneer. "
                  f"Write 1-2 exciting, flavorful sentences of commentary for the player '{player_name}' "
                  f"in the context of the '{player_set}' set. "
                  f"Highlight one key strength. Keep it brief and punchy.")
        
        response = await model.generate_content_async(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating AI commentary: {e}")
        return "A true talent with a lot to prove." # Fallback text

async def start_auto_sold_timer(ctx):
    """Starts the 7-second countdown timer for selling a player."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state: return

    current_player = auction_state.get('current_player')
    if not auction_state.get('bidding') or not current_player:
        return

    try:
        await asyncio.sleep(7)
        if not auction_state.get('bidding') or auction_state.get('current_player') != current_player:
            return
        await ctx.send("⏳ Going once...")
        await asyncio.sleep(1)
        if not auction_state.get('bidding') or auction_state.get('current_player') != current_player:
            return
        await ctx.send("⏳ Going twice...")
        await asyncio.sleep(1)
        if not auction_state.get('bidding') or auction_state.get('current_player') != current_player:
            return
        await ctx.send("⏳ Final call...")
        await asyncio.sleep(1)
        if not auction_state.get('bidding') or auction_state.get('current_player') != current_player:
            return
        await _finalize_sold(ctx)
    except asyncio.CancelledError:
        pass

# --- Bot Events ---
@BOT.event
async def on_ready():
    """Event that fires when the bot successfully connects."""
    load_data()
    print(f'Logged in as {BOT.user}')

# ... (on_message, _finalize_sold, and other core functions remain the same) ...

@BOT.event
async def on_message(message):
    """Handles incoming messages for lineup setup."""
    if message.author.bot:
        return

    user_id = str(message.author.id)
    session = lineup_setup_sessions.get(user_id)

    if session and session['channel_id'] == message.channel.id:
        content = message.content.strip()
        
        if session['stage'] == 'formation':
            formation = content.replace(' ', '-')
            if formation in AVAILABLE_FORMATIONS:
                session['formation'] = formation
                session['required_counts'] = AVAILABLE_FORMATIONS[formation]
                session['stage'] = 'tactic'
                await message.channel.send(f"Formation set to **{formation}**. Now, choose a tactic: `Attacking`, `Defensive`, or `Balanced`.")
            else:
                await message.channel.send(f"❌ Invalid formation. Please choose from: {', '.join(AVAILABLE_FORMATIONS.keys())}")

        elif session['stage'] == 'tactic':
            tactic = content.capitalize()
            if tactic in AVAILABLE_TACTICS:
                session['tactic'] = tactic
                session['stage'] = 'players'
                await prompt_for_player(message.channel, message.author)
            else:
                await message.channel.send(f"❌ Invalid tactic. Please choose from: {', '.join(AVAILABLE_TACTICS)}")

        elif session['stage'] == 'players':
            player_name_input = content.lower()
            
            if player_name_input == 'done':
                user_lineups[user_id] = {
                    'players': session['selected_players'],
                    'tactic': session['tactic'],
                    'formation': session['formation']
                }
                save_data()
                await message.channel.send(f"✅ Lineup saved for {message.author.mention}!")
                del lineup_setup_sessions[user_id]
                return

            matched_player = None
            for p in user_teams.get(user_id, []):
                if p['name'].lower() == player_name_input and p not in session['selected_players']:
                    matched_player = p
                    break
            
            if not matched_player:
                await message.channel.send(f"❌ Player '{content}' not found in your team or already selected.")
                return

            pos = matched_player['position'].lower()
            needed = session['required_counts'].get(pos, 0)
            current = session['position_counts'].get(pos, 0)

            if current >= needed:
                await message.channel.send(f"❌ Your formation **{session['formation']}** doesn't require any more {pos.upper()} players.")
                return

            session['selected_players'].append(matched_player)
            session['position_counts'][pos] = current + 1
            
            if len(session['selected_players']) == 11:
                user_lineups[user_id] = {
                    'players': session['selected_players'],
                    'tactic': session['tactic'],
                    'formation': session['formation']
                }
                save_data()
                await message.channel.send(f"✅ Lineup complete and saved for {message.author.mention}!")
                del lineup_setup_sessions[user_id]
            else:
                await prompt_for_player(message.channel, message.author)
        return

    await BOT.process_commands(message)

async def _finalize_sold(ctx):
    """Helper function to finalize the sale of a player."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state or not auction_state['bidding']: return

    winner_id = auction_state['highest_bidder']
    player = auction_state['current_player']
    price = auction_state['current_price']

    if winner_id is None:
        auction_state['unsold_players'].add(player['name'])
        await ctx.send(f"🤷 No one bid for **{player['name']}**. They go unsold.")
    else:
        winner = await BOT.fetch_user(int(winner_id))
        user_budgets[winner_id] -= price
        entry = {
            "name": player['name'],
            "position": player.get('position', 'unknown'),
            "rating": player.get('rating', 75),
            "price": price,
            "set": AVAILABLE_SETS.get(auction_state.get('current_set'), 'Custom'),
        }
        user_teams[winner_id].append(entry)
        user_stats[winner_id]['money_spent'] += price
        if price > user_stats[winner_id]['most_expensive']:
            user_stats[winner_id]['most_expensive'] = price
        
        auction_state['last_sold_player'] = player
        auction_state['last_sold_buyer_id'] = winner_id
        auction_state['last_sold_price'] = price
        
        save_data()
        await ctx.send(f"✅ **{player['name']}** sold to **{winner.display_name}** for **{format_currency(price)}**!")

    auction_state['bidding'] = False
    auction_state['current_player'] = None
    auction_state['current_price'] = 0
    auction_state['highest_bidder'] = None
    auction_state['pass_votes'].clear()

def create_position_command(position):
    """Dynamically creates a command for each player position with AI commentary."""

    @BOT.command(name=position)
    async def _position_command(ctx):
        auction_state = active_auctions.get(ctx.channel.id)
        if not auction_state: return
        if ctx.author.id != auction_state['host'] and ctx.author.id != PRIVILEGED_USER_ID:
            return await ctx.send("Only the host can nominate players.")
        if auction_state['bidding']:
            return await ctx.send("A player is already being auctioned.")
        
        current_set = auction_state.get('current_set')
        if not current_set:
            return await ctx.send("The host has not selected a player set yet.")

        all_players_for_pos = load_players_by_position(position, current_set)
        
        sold_player_names = {p['name'].lower() for team in user_teams.values() for p in team}
        unsold_player_names = {p.lower() for p in auction_state['unsold_players']}
        
        available_players = [
            p for p in all_players_for_pos
            if p['name'].lower() not in sold_player_names and p['name'].lower() not in unsold_player_names
        ]

        if not available_players:
            return await ctx.send(f"No more {position.upper()} players available from the '{AVAILABLE_SETS[current_set]}' set.")

        available_players.sort(key=lambda p: p.get('rating', 0), reverse=True)
        player_to_auction = available_players[0]
        
        commentary = await get_ai_commentary(player_to_auction['name'], AVAILABLE_SETS[current_set])
        
        auction_state.update({
            'current_player': player_to_auction,
            'bidding': True,
            'current_price': player_to_auction.get('base_price', MIN_BASE_PRICE),
            'highest_bidder': None,
            'pass_votes': set()
        })

        embed = discord.Embed(title=f"🔥 Player Up for Auction: {player_to_auction['name']}", 
                              description=f"*{commentary}*",
                              color=discord.Color.gold())
        embed.add_field(name="Position", value=player_to_auction.get('position', 'N/A').upper())
        embed.add_field(name="Rating", value=player_to_auction.get('rating', 'N/A'))
        embed.add_field(name="Starting Price", value=format_currency(auction_state['current_price']), inline=False)
        embed.set_footer(text="Use !bid or !bid <amount> to bid. Use !pass to skip.")
        await ctx.send(embed=embed)
        
        if auction_state.get('timeout_task'):
            auction_state['timeout_task'].cancel()
        auction_state['timeout_task'] = BOT.loop.create_task(start_auto_sold_timer(ctx))

    BOT.add_command(_position_command)

for pos in AVAILABLE_POSITIONS:
    create_position_command(pos)
    
# ... (All other commands like !startauction, !bid, !sold, !setlineup, !myplayers, etc., are included here) ...
# The code for them is lengthy but assumed to be present and correct from the previous turns.
# I'll include the key ones again for a complete file.

@BOT.command()
async def startauction(ctx, *members: discord.Member):
    if ctx.channel.id in active_auctions:
        return await ctx.send("❌ An auction is already active in this channel.")

    participants = {str(m.id) for m in members}
    participants.add(str(ctx.author.id))

    for p_id in participants:
        ensure_user_structures(p_id)

    active_auctions[ctx.channel.id] = {
        "host": ctx.author.id, "participants": participants, "current_player": None,
        "bidding": False, "current_price": 0, "highest_bidder": None,
        "timeout_task": None, "pass_votes": set(), "unsold_players": set(),
        "last_sold_player": None, "last_sold_buyer_id": None, "last_sold_price": 0,
    }

    set_list = "\n".join([f"**{key}** - {name}" for key, name in AVAILABLE_SETS.items()])
    embed = discord.Embed(title="📖 Select Auction Set", description="The host must choose a player set by replying with the key (e.g., `wc`).", color=discord.Color.blue())
    embed.add_field(name="Available Sets", value=set_list)
    await ctx.send(embed=embed)

    try:
        msg = await BOT.wait_for('message', timeout=120.0, check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
        set_key = msg.content.lower().strip()
        if set_key in AVAILABLE_SETS:
            active_auctions[ctx.channel.id]['current_set'] = set_key
            await ctx.send(f"✅ Set selected: **{AVAILABLE_SETS[set_key]}**. Auction may begin! Use `!st`, `!gk`, etc.")
        else:
            await ctx.send("❌ Invalid set key. Auction setup failed."); del active_auctions[ctx.channel.id]
    except asyncio.TimeoutError:
        await ctx.send("⏰ Timed out. Auction setup failed."); del active_auctions[ctx.channel.id]

@BOT.command()
async def bid(ctx, amount: str = None):
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state or not auction_state['bidding']:
        return await ctx.send("No player is currently up for auction.")
    
    user_id = str(ctx.author.id)
    if user_id not in auction_state['participants']:
        return await ctx.send("You are not part of this auction.")
    if len(user_teams.get(user_id, [])) >= MAX_PLAYERS_PER_USER:
        return await ctx.send(f"You cannot have more than {MAX_PLAYERS_PER_USER} players.")

    new_price = 0
    if amount:
        try:
            val = float(amount.lower().replace('m', 'e6').replace('k', 'e3'))
            new_price = int(val)
        except ValueError:
            return await ctx.send("Invalid bid amount. Use `5000000` or `5m`.")
    else:
        new_price = auction_state['current_price'] + BID_INCREMENT
    
    if new_price <= auction_state['current_price']:
        return await ctx.send("Your bid must be higher than the current price.")
    if new_price > user_budgets.get(user_id, 0):
        return await ctx.send(f"You cannot afford this bid. Your budget is {format_currency(user_budgets.get(user_id, 0))}.")

    auction_state['current_price'] = new_price
    auction_state['highest_bidder'] = user_id
    await ctx.send(f"💰 {ctx.author.display_name} bids **{format_currency(new_price)}**!")

    if auction_state.get('timeout_task'):
        auction_state['timeout_task'].cancel()
    auction_state['timeout_task'] = BOT.loop.create_task(start_auto_sold_timer(ctx))

@BOT.command()
async def sold(ctx):
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state or (ctx.author.id != auction_state['host'] and ctx.author.id != PRIVILEGED_USER_ID): return
    if auction_state.get('timeout_task'): auction_state['timeout_task'].cancel()
    await _finalize_sold(ctx)

@BOT.command(name='pass')
async def pass_bid(ctx):
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state or not auction_state['bidding']: return
    user_id = str(ctx.author.id)
    if user_id in auction_state['participants']:
        auction_state['pass_votes'].add(user_id)
        
        active_bidders = auction_state['participants'] - {auction_state['highest_bidder']} if auction_state['highest_bidder'] else auction_state['participants']

        if auction_state['pass_votes'].issuperset(active_bidders):
            if auction_state.get('timeout_task'): auction_state['timeout_task'].cancel()
            await ctx.send("All active bidders have passed.")
            await _finalize_sold(ctx)
        else:
            await ctx.send(f"{ctx.author.display_name} has passed.")

@BOT.command()
async def endauction(ctx):
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state or (ctx.author.id != auction_state['host'] and ctx.author.id != PRIVILEGED_USER_ID): return
    if auction_state.get('timeout_task'): auction_state['timeout_task'].cancel()
    del active_auctions[ctx.channel.id]
    await ctx.send("✅ Auction has been ended by the host.")

async def prompt_for_player(channel, user):
    user_id = str(user.id)
    session = lineup_setup_sessions.get(user_id)
    if not session: return

    remaining_slots = 11 - len(session['selected_players'])
    embed = discord.Embed(title=f"Lineup Setup ({remaining_slots} slots left)", color=discord.Color.blue())
    
    if session['selected_players']:
        lineup_str = "\n".join([f"`{p['name']}` ({p['position'].upper()})" for p in session['selected_players']])
        embed.add_field(name="Current Lineup", value=lineup_str, inline=False)
    
    available_players = [p for p in user_teams.get(user_id, []) if p not in session['selected_players']]
    if available_players:
        player_list = "\n".join([f"`{p['name']}` ({p['position'].upper()})" for p in available_players[:15]])
        embed.add_field(name="Your Available Players", value=player_list, inline=False)
    
    embed.set_footer(text="Type a player's full name to add them. Type 'done' to save and exit.")
    await channel.send(f"{user.mention}, who do you want to add next?", embed=embed)

@BOT.command()
async def setlineup(ctx):
    user_id = str(ctx.author.id)
    if user_id in lineup_setup_sessions:
        return await ctx.send("You are already in a lineup setup session.")
    if not user_teams.get(user_id):
        return await ctx.send("You don't have any players yet!")

    lineup_setup_sessions[user_id] = {
        'channel_id': ctx.channel.id, 'stage': 'formation', 'formation': None, 'tactic': None,
        'required_counts': {}, 'position_counts': {pos: 0 for pos in AVAILABLE_POSITIONS},
        'selected_players': []
    }
    await ctx.send(f"Starting lineup setup for {ctx.author.mention}! First, choose a formation (e.g., `4-4-2`, `4-3-3`).")

@BOT.command()
async def viewlineup(ctx):
    user_id = str(ctx.author.id)
    lineup = user_lineups.get(user_id)
    if not lineup or not lineup.get('players'):
        return await ctx.send("You haven't set a lineup. Use `!setlineup`.")

    embed = discord.Embed(title=f"{ctx.author.display_name}'s Lineup", color=discord.Color.teal())
    embed.add_field(name="Formation", value=lineup.get('formation', 'N/A'))
    embed.add_field(name="Tactic", value=lineup.get('tactic', 'N/A'))
    player_list = "\n".join([f"{p['name']} ({p['position'].upper()})" for p in lineup['players']])
    embed.add_field(name="Players", value=player_list, inline=False)
    await ctx.send(embed=embed)

@BOT.command()
async def myplayers(ctx):
    team = user_teams.get(str(ctx.author.id))
    if not team:
        return await ctx.send("You haven't bought any players yet.")

    embed = discord.Embed(title=f"{ctx.author.display_name}'s Players", color=discord.Color.green())
    for p in team:
        embed.add_field(name=f"{p['name']} ({p['position'].upper()}) - Rating: {p.get('rating', 'N/A')}",
                        value=f"Bought for: {format_currency(p['price'])}",
                        inline=False)
    await ctx.send(embed=embed)

@BOT.command()
async def budget(ctx):
    user_id = str(ctx.author.id)
    b = user_budgets.get(user_id, STARTING_BUDGET)
    await ctx.send(f"💰 {ctx.author.display_name}, your remaining budget is: **{format_currency(b)}**")

@BOT.command()
async def footy(ctx):
    embed = discord.Embed(title="⚽ Football Auction Bot Commands", color=discord.Color.blue())
    auction_cmds = (
        "`!startauction @user...` - Starts an auction.\n"
        "`!endauction` - (Host) Ends the auction.\n"
        "`!st`, `!gk`, etc. - (Host) Nominates the best player for a position.\n"
        "`!bid <amount>` - Bids on a player (e.g., `!bid 10m`).\n"
        "`!pass` - Passes on the current player.\n"
        "`!sold` - (Host) Manually sells the player."
    )
    team_cmds = (
        "`!myplayers` - Shows your bought players.\n"
        "`!budget` - Displays your budget.\n"
        "`!setlineup` - Set your team lineup.\n"
        "`!viewlineup` - Shows your lineup."
    )
    embed.add_field(name="--- AUCTION ---", value=auction_cmds, inline=False)
    embed.add_field(name="--- TEAM MANAGEMENT ---", value=team_cmds, inline=False)
    await ctx.send(embed=embed)


if __name__ == "__main__":
    if DISCORD_BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("ERROR: Please set your DISCORD_BOT_TOKEN in the script or as an environment variable.")
    if GOOGLE_AI_API_KEY == "YOUR_GOOGLE_AI_API_KEY_HERE":
        print("WARNING: GOOGLE_AI_API_KEY is not set. AI features will be disabled.")
    
    if DISCORD_BOT_TOKEN != "YOUR_DISCORD_BOT_TOKEN_HERE":
        BOT.run(DISCORD_BOT_TOKEN)
