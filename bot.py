import discord
from discord.ext import commands
import json
import random
import os
import asyncio
import uuid

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

available_positions = ['st', 'rw', 'lw', 'cam', 'cm', 'lb', 'cb', 'rb', 'gk']
available_tactics = ['Attacking', 'Defensive', 'Balanced']
available_formations = {
    '4-4-2': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 2, 'st': 2},
    '4-3-3': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 1, 'cam': 1, 'lw': 1, 'rw': 1, 'st': 1},
    '4-2-3-1': {'gk': 1, 'cb': 2, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 3, 'st': 1},
    '3-5-2': {'gk': 1, 'cb': 3, 'cm': 2, 'cam': 3, 'st': 2},
    '3-4-3': {'gk': 1, 'cb': 3, 'cm': 2, 'lw': 1, 'rw': 1, 'st': 1},
    '5-4-1': {'gk': 1, 'cb': 3, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 2, 'st': 1},
    '5-3-2': {'gk': 1, 'cb': 3, 'lb': 1, 'rb': 1, 'cm': 2, 'cam': 1, 'st': 2}
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
STARTING_BUDGET = 1000000000
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

def format_currency(amount):
    """Formats a numerical amount into a currency string."""
    return f"${amount:,}"

def load_players_by_position(position, set_name):
    """Loads players from a specific set and position, assigning tiers."""
    base_dir = os.path.dirname(__file__)
    filename = os.path.join(base_dir, 'players', set_name, f'{position.lower()}.json')
    
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
            print(f"Loaded players for {position} from {set_name}: {len(players)} players")
            tiered_players = {'A': [], 'B': [], 'C': []}
            for player in players:
                if not isinstance(player, dict) or 'name' not in player or 'position' not in player:
                    print(f"Skipping invalid player data in {filename}: {player}")
                    continue
                
                if 'base_price' not in player:
                    # Assign deterministic price based on tier
                    tier = random.choice(['A', 'B', 'C'])
                    if tier == 'A':
                        player['base_price'] = random.randint(40, 50) * 1000000
                    elif tier == 'B':
                        player['base_price'] = random.randint(25, 39) * 1000000
                    else:  # tier == 'C'
                        player['base_price'] = random.randint(1, 24) * 1000000
                else:
                    base_price = player['base_price']
                    # Validate and adjust base_price to fit tier ranges
                    if not isinstance(base_price, (int, float)) or base_price < MIN_BASE_PRICE or base_price > MAX_BASE_PRICE:
                        print(f"Invalid base_price for {player.get('name', 'Unknown')} in {filename}: {base_price}")
                        tier = random.choice(['A', 'B', 'C'])
                        if tier == 'A':
                            player['base_price'] = random.randint(40, 50) * 1000000
                        elif tier == 'B':
                            player['base_price'] = random.randint(25, 39) * 1000000
                        else:  # tier == 'C'
                            player['base_price'] = random.randint(1, 24) * 1000000
                    else:
                        if 40000000 <= base_price <= 50000000:
                            tier = 'A'
                        elif 25000000 <= base_price <= 39000000:
                            tier = 'B'
                        else:
                            tier = 'C'
                
                player['tier'] = tier
                tiered_players[tier].append(player)
            
            # Shuffle each tier
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
    """Saves user teams, budgets, and lineups to JSON files."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "teams.json"), "w") as f:
            json.dump(user_teams, f, indent=2)
        with open(os.path.join(DATA_DIR, "budgets.json"), "w") as f:
            json.dump(user_budgets, f, indent=2)
        with open(os.path.join(DATA_DIR, "lineups.json"), "w") as f:
            json.dump(user_lineups, f, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")
        return False
    return True

def load_data():
    """Loads user teams, budgets, and lineups from JSON files."""
    global user_teams, user_budgets, user_lineups
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        teams_path = os.path.join(DATA_DIR, "teams.json")
        budgets_path = os.path.join(DATA_DIR, "budgets.json")
        lineups_path = os.path.join(DATA_DIR, "lineups.json")
        if os.path.exists(teams_path):
            with open(teams_path, "r") as f:
                user_teams = json.load(f)
        if os.path.exists(budgets_path):
            with open(budgets_path, "r") as f:
                user_budgets = json.load(f)
        if os.path.exists(lineups_path):
            with open(lineups_path, "r") as f:
                user_lineups = json.load(f)
    except Exception as e:
        print(f"Error loading data: {e}")
        return False
    return True

load_data()

def is_user_in_any_auction(user_id):
    user_id_str = str(user_id)
    for auction_id, auction_data in active_auctions.items():
        if auction_data['host'] == user_id or user_id_str in auction_data['participants']:
            return True
    return False

@bot.event
async def on_ready():
    """Event that fires when the bot successfully connects to Discord."""
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    """Handles incoming messages for set selection and lineup setup."""
    if message.author.bot:
        return

    message_consumed = False

    auction_state_for_channel = active_auctions.get(message.channel.id)
    if (auction_state_for_channel and
        auction_state_for_channel['awaiting_set_selection'] and 
        message.author.id == auction_state_for_channel['set_selection_author']):
        
        set_key = message.content.lower().strip()
        print(f"DEBUG (on_message): Awaiting set selection. Received set_key: '{set_key}'")
        
        if set_key in available_sets:
            print(f"DEBUG (on_message): Set key '{set_key}' found in available_sets.")
            auction_state_for_channel['current_set'] = set_key
            auction_state_for_channel['awaiting_set_selection'] = False
            auction_state_for_channel['set_selection_author'] = None
            auction_state_for_channel['tier_counters'] = {pos: {'A': 0, 'B': 0, 'C': 0} for pos in available_positions}
            
            all_positions_loaded_successfully = True
            error_positions = []
            for pos in available_positions:
                tiered_players = load_players_by_position(pos, set_key)
                auction_state_for_channel['player_queues'][pos] = tiered_players
                if not any(tiered_players[tier] for tier in ['A', 'B', 'C']):
                    all_positions_loaded_successfully = False
                    error_positions.append(pos.upper())
            
            if all_positions_loaded_successfully:
                embed = discord.Embed(title="🎉 Auction Started", 
                                     description=f"**Set Selected:** {available_sets[set_key]}\n\nOnly the host or <@{PRIVILEGED_USER_ID}> can run position commands, !rebid, !custombid, and !endauction.", 
                                     color=discord.Color.green())
                embed.set_footer(text="Only registered users can bid. Good luck!")
                await message.channel.send(embed=embed)
            else:
                embed = discord.Embed(title="⚠️ Set Loaded with Warnings", 
                                     description=f"**Set Selected:** {available_sets[set_key]}\n\nNo players available for positions: {', '.join(error_positions)}. Use !custombid <name> <price> <position> to auction custom players.", 
                                     color=discord.Color.orange())
                await message.channel.send(embed=embed)
            message_consumed = True
        else:
            print(f"DEBUG (on_message): Set key '{set_key}' NOT found.")
            embed = discord.Embed(title="❌ Invalid Set", 
                                 description="Please choose from the available sets:", 
                                 color=discord.Color.red())
            set_list = "\n".join([f"**{key}** - {name}" for key, name in available_sets.items()])
            embed.add_field(name="Available Sets", value=set_list, inline=False)
            await message.channel.send(embed=embed)
            message_consumed = True

    if (lineup_setup_state['user_id'] == str(message.author.id) and 
        message.channel.id == lineup_setup_state['channel_id'] and 
        lineup_setup_state['stage'] is not None):
        
        content = message.content.strip().lower()
        if lineup_setup_state['stage'] == 'formation':
            formation = content.replace(' ', '-')
            if formation in available_formations:
                lineup_setup_state['formation'] = formation
                lineup_setup_state['required_counts'] = available_formations[formation]
                lineup_setup_state['stage'] = 'tactic'
                embed = discord.Embed(title="🎯 Select Tactic", 
                                     description="Please choose a tactic:", 
                                     color=discord.Color.blue())
                embed.add_field(name="Available Tactics", value=", ".join(available_tactics), inline=False)
                embed.set_footer(text="Type the tactic (e.g., 'Attacking')")
                await message.channel.send(embed=embed)
            else:
                embed = discord.Embed(title="❌ Invalid Formation", 
                                     description=f"Please choose from: {', '.join(available_formations.keys())}", 
                                     color=discord.Color.red())
                await message.channel.send(embed=embed)
            message_consumed = True
        
        elif lineup_setup_state['stage'] == 'tactic':
            tactic = content.capitalize()
            if tactic in available_tactics:
                lineup_setup_state['tactic'] = tactic
                lineup_setup_state['stage'] = available_positions[-1]  # Start with 'gk'
                await prompt_for_player(message.channel, message.author, lineup_setup_state['stage'])
            else:
                embed = discord.Embed(title="❌ Invalid Tactic", 
                                     description=f"Please choose from: {', '.join(available_tactics)}", 
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
                first_initial = full_name.split()[0][0] if ' ' in full_name else full_name[0]
                last_initial = full_name.split()[-1][0] if ' ' in full_name else full_name[0]
                
                if (full_name == player_name_input or
                    (len(player_name_input) == 1 and (first_initial == player_name_input or last_initial == player_name_input)) or
                    any(part.lower().startswith(player_name_input) for part in full_name.split())):
                    if player['position'].lower() == pos and player not in lineup_setup_state['selected_players']:
                        matched_player = player
                        break
            
            if not matched_player:
                embed = discord.Embed(title="❌ Invalid Player", 
                                     description=f"Player '{content}' is not in your team or doesn't match the {pos.upper()} position. Use !myplayers to check.", 
                                     color=discord.Color.red())
                await message.channel.send(embed=embed)
                return
            
            if matched_player in lineup_setup_state['selected_players']:
                embed = discord.Embed(title="❌ Player Already Selected", 
                                     description=f"{matched_player['name']} is already in your lineup.", 
                                     color=discord.Color.red())
                await message.channel.send(embed=embed)
                return
            
            lineup_setup_state['selected_players'].append(matched_player)
            lineup_setup_state['position_counts'][pos] += 1
            
            next_pos = None
            for p in available_positions[::-1]:
                if lineup_setup_state['position_counts'][p] < lineup_setup_state['required_counts'].get(p, 0):
                    next_pos = p
                    break
            
            if next_pos:
                lineup_setup_state['stage'] = next_pos
                await prompt_for_player(message.channel, message.author, next_pos)
            else:
                user_lineups[user_id] = {
                    'players': lineup_setup_state['selected_players'],
                    'tactic': lineup_setup_state['tactic'],
                    'formation': lineup_setup_state['formation']
                }
                if not save_data():
                    await message.channel.send("⚠️ Error saving lineup data. Please try again.")
                embed = discord.Embed(title="✅ Lineup Set", color=discord.Color.green())
                embed.add_field(name="Formation", value=lineup_setup_state['formation'].upper(), inline=True)
                embed.add_field(name="Tactic", value=lineup_setup_state['tactic'], inline=True)
                embed.add_field(name="Lineup", 
                                value="\n".join([f"{p['name']} ({p['position'].upper()})" for p in lineup_setup_state['selected_players']]), 
                                inline=False)
                embed.set_footer(text="Use !viewlineup to check your lineup or !setlineup to change it.")
                await message.channel.send(embed=embed)
                reset_lineup_setup_state()
            message_consumed = True

    if not message_consumed:
        await bot.process_commands(message)

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

def reset_lineup_setup_state():
    """Resets the lineup setup state."""
    lineup_setup_state['user_id'] = None
    lineup_setup_state['channel_id'] = None
    lineup_setup_state['stage'] = None
    lineup_setup_state['formation'] = None
    lineup_setup_state['tactic'] = None
    lineup_setup_state['selected_players'] = []
    lineup_setup_state['position_counts'] = {pos: 0 for pos in available_positions}
    lineup_setup_state['required_counts'] = None

@bot.event
async def on_reaction_add(reaction, user):
    """Handles reactions for bidding and passing."""
    if user.bot:
        return
    
    auction_state = active_auctions.get(reaction.message.channel.id)
    if not auction_state or not auction_state['bidding'] or not auction_state['current_player']:
        return
    
    if str(user.id) not in auction_state['participants']:
        return
    
    if str(reaction.emoji) == '💰':
        fake_ctx = type('obj', (object,), {
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
        
        # Add to unsold players
        if 'unsold_players' not in auction_state:
            auction_state['unsold_players'] = []
        auction_state['unsold_players'].append(player)
        
        embed = discord.Embed(title="🚫 Player Unsold", 
                            description=f"**{player['name']}** received no bids and goes unsold.", 
                            color=discord.Color.red())
        await channel.send(embed=embed)
    else:
        embed = discord.Embed(title="⚠️ Player Passed", 
                            description=f"{user.display_name} passed. Waiting for {len(remaining)} more to pass.", 
                            color=discord.Color.orange())
        await channel.send(embed=embed)

@bot.command()
async def startauction(ctx, *members: discord.Member, timer: int = 30):
    """Starts a new auction, registers participants, and prompts for set selection."""
    if ctx.channel.id in active_auctions:
        await ctx.send("❌ An auction is already active in this channel. Please use a different channel or end the current auction first.")
        return
    
    if is_user_in_any_auction(ctx.author.id):
        await ctx.send(f"❌ {ctx.author.display_name}, you are already participating in another auction.")
        return

    for member in members:
        if is_user_in_any_auction(member.id):
            await ctx.send(f"❌ {member.display_name} is already participating in another auction.")
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
        "last_sold_price": 0,
        "last_sold_winner_id": None,
        "unsold_players": []
    }
    
    auction_state = active_auctions[ctx.channel.id]

    auction_state['participants'].add(str(ctx.author.id))
    for m in members:
        auction_state['participants'].add(str(m.id))
    
    for participant_id in auction_state['participants']:
        if participant_id not in user_budgets:
            user_budgets[participant_id] = STARTING_BUDGET
        if participant_id not in user_teams:
            user_teams[participant_id] = []
        if participant_id not in user_lineups:
            user_lineups[participant_id] = {'players': [], 'tactic': 'Balanced', 'formation': '4-4-2'}
    
    embed = discord.Embed(title="🎯 Select Auction Set", 
                         description="Please choose which set you want to auction:", 
                         color=discord.Color.blue())
    
    set_list = "\n".join([f"**{key}** - {name}" for key, name in available_sets.items()])
    embed.add_field(name="Available Sets", value=set_list, inline=False)
    embed.set_footer(text="Type the set key (e.g., 'wc' for World Cup XI)")
    
    await ctx.send(embed=embed)
    
    auction_state['awaiting_set_selection'] = True
    auction_state['set_selection_author'] = ctx.author.id

@bot.command()
async def sets(ctx):
    """Shows all available auction sets."""
    embed = discord.Embed(title="🎯 Available Auction Sets", 
                         description="Here are all the available sets:", 
                         color=discord.Color.blue())
    
    set_list = "\n".join([f"**{key}** - {name}" for key, name in available_sets.items()])
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
    
    users = []
    for uid in auction_state['participants']:
        try:
            user = await bot.fetch_user(int(uid))
            users.append(f"<@{uid}>")
        except:
            users.append(f"Unknown User ({uid})")
    
    current_set_name = available_sets.get(auction_state['current_set'], 'No set selected')
    
    embed = discord.Embed(title="👥 Registered Participants", 
                         description="\n".join(users), 
                         color=discord.Color.green())
    embed.add_field(name="Current Set", value=current_set_name, inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def add(ctx, member: discord.Member):
    """Adds a new participant to the ongoing auction (host or privileged user only)."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state['host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send("Only the auction host or the privileged user can add participants to this auction.")
        return
    
    if is_user_in_any_auction(member.id):
        await ctx.send(f"❌ {member.display_name} is already participating in another auction.")
        return

    auction_state['participants'].add(str(member.id))
    if str(member.id) not in user_budgets:
        user_budgets[str(member.id)] = STARTING_BUDGET
    if str(member.id) not in user_teams:
        user_teams[str(member.id)] = []
    if str(member.id) not in user_lineups:
        user_lineups[str(member.id)] = {'players': [], 'tactic': 'Balanced', 'formation': '4-4-2'}
    
    await ctx.send(f"✅ {member.mention} has been added to this auction.")

@bot.command()
async def remove(ctx, member: discord.Member):
    """Removes a participant from the auction with confirmation (host or privileged user only)."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state['host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send("Only the auction host or the privileged user can remove participants from this auction.")
        return
    
    if str(member.id) not in auction_state['participants']:
        await ctx.send(f"❌ {member.mention} is not a participant in this auction.")
        return
    
    confirm_msg = await ctx.send(f"⚠️ Are you sure you want to remove {member.mention} from this auction? React with ✅ to confirm.")
    await confirm_msg.add_reaction("✅")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id

    try:
        await bot.wait_for('reaction_add', timeout=15.0, check=check)
        auction_state['participants'].remove(str(member.id))
        await ctx.send(f"❌ {member.mention} has been removed from this auction.")
    except asyncio.TimeoutError:
        await ctx.send("⏰ Removal cancelled. No confirmation received in time.")

@bot.command()
async def setlineup(ctx):
    """Starts an interactive process to set the user's lineup."""
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
        await bot.wait_for('message', check=check, timeout=600.0)
    except asyncio.TimeoutError:
        if lineup_setup_state['user_id'] == user_id and lineup_setup_state['stage'] is not None:
            await ctx.send("⏰ Lineup setup timed out. Please run !setlineup again.")
            reset_lineup_setup_state()

@bot.command()
async def viewlineup(ctx):
    """Displays the user's current lineup, formation, and tactic."""
    user_id = str(ctx.author.id)
    if user_id not in user_lineups or not user_lineups[user_id]['players']:
        await ctx.send("You haven't set a lineup yet. Use !setlineup to create one.")
        return

    lineup = user_lineups[user_id]
    embed = discord.Embed(title=f"📋 {ctx.author.display_name}'s Lineup", color=discord.Color.teal())
    embed.add_field(name="Formation", value=lineup['formation'].upper(), inline=True)
    embed.add_field(name="Tactic", value=lineup['tactic'], inline=True)
    embed.add_field(name="Players", 
                    value="\n".join([f"{p['name']} ({p['position'].upper()})" for p in lineup['players']]), 
                    inline=False)
    await ctx.send(embed=embed)

def create_position_command(position):
    """Dynamically creates a command for each player position (e.g., !st, !rw)."""
    @bot.command(name=position)
    async def _position(ctx):
        auction_state = active_auctions.get(ctx.channel.id)
        if not auction_state:
            await ctx.send("No auction is currently running in this channel. Please start one with `!startauction`.")
            return

        if ctx.author.id != auction_state['host'] and ctx.author.id != PRIVILEGED_USER_ID:
            await ctx.send("Only the auction host or the privileged user can run this command in this auction.")
            return
        
        if auction_state['current_set'] is None:
            await ctx.send("❌ No set has been selected for this auction. The host needs to select a set first.")
            return
        
        tiered_queues = auction_state['player_queues'].get(position)
        if not tiered_queues or not any(tiered_queues[tier] for tier in ['A', 'B', 'C']):
            await ctx.send(f"No players left for **{position.upper()}** in the {available_sets[auction_state['current_set']]} set in this auction. Use !custombid <name> <price> {position} to auction a custom player.")
            return
        
        # Determine the next tier to auction (3 A, 5 B, 3 C, repeat)
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
            # If the desired tier is empty, try the next available tier
            for fallback_tier in ['A', 'B', 'C']:
                if tiered_queues[fallback_tier]:
                    tier = fallback_tier
                    break
            else:
                await ctx.send(f"No players left for **{position.upper()}** in the {available_sets[auction_state['current_set']]} set in this auction. Use !custombid <name> <price> {position} to auction a custom player.")
                return
        
        if auction_state['timeout_task']:
            auction_state['timeout_task'].cancel()
        
        auction_state['pass_votes'].clear()
        
        player = tiered_queues[tier].pop(0)
        tier_counter[tier] += 1
        auction_state['current_player'] = player
        auction_state['bidding'] = True
        auction_state['bids'] = {}
        auction_state['current_price'] = player.get('base_price', MIN_BASE_PRICE)
        auction_state['highest_bidder'] = None
        
        embed = discord.Embed(title="🔨 Player Up for Auction", color=discord.Color.gold())
        embed.add_field(name="Name", value=player['name'], inline=True)
        embed.add_field(name="Position", value=player.get('position', 'Unknown').upper(), inline=True)
        embed.add_field(name="League", value=player.get('league', 'Unknown'), inline=True)
        embed.add_field(name="Set", value=available_sets[auction_state['current_set']], inline=True)
        embed.add_field(name="Starting Price", value=format_currency(auction_state['current_price']), inline=False)
        embed.set_footer(text="Use !bid or !bid [amount] to place a bid. React with 💰 to bid, ❌ to pass.")
        
        message = await ctx.send(embed=embed)
        await message.add_reaction("💰")
        await message.add_reaction("❌")
        
        async def auto_sold():
            try:
                if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                    return
                await asyncio.sleep(7)
                if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                    return
                await ctx.send("⌛ Going once...")
                await asyncio.sleep(1)
                if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                    return
                await ctx.send("⌛ Going twice...")
                await asyncio.sleep(1)
                if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                    return
                await ctx.send("⌛ Final call...")
                await asyncio.sleep(1)
                if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                    return
                await _finalize_sold(ctx)
            except asyncio.CancelledError:
                pass
        
        auction_state['timeout_task'] = bot.loop.create_task(auto_sold())

for pos in available_positions:
    create_position_command(pos)

@bot.command()
async def bid(ctx, *, amount: str = None):
    """Allows a participant to place a bid on the current player."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state or not auction_state['bidding'] or not auction_state['current_player']:
        await ctx.send("No player is currently up for bidding in this channel.")
        return
    
    user_id = str(ctx.author.id)
    if user_id not in auction_state['participants']:
        await ctx.send("You are not a registered participant in this auction.")
        return
    
    if user_id not in user_budgets:
        user_budgets[user_id] = STARTING_BUDGET
        user_teams[user_id] = []
        user_lineups[user_id] = {'players': [], 'tactic': 'Balanced', 'formation': '4-4-2'}
    
    if len(user_teams[user_id]) >= MAX_PLAYERS_PER_USER:
        await ctx.send(f"You have reached the {MAX_PLAYERS_PER_USER}-player limit for your team.")
        return
    
    new_price = 0
    if amount is not None:
        amount = amount.strip().lower().replace(",", "")
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
            await ctx.send("❌ Invalid bid amount format. Use numbers like 50m or 1000000.")
            return
        
        if new_price <= auction_state['current_price']:
            await ctx.send("Your bid must be higher than the current bid.")
            return
        
        if new_price < auction_state['current_price'] + MIN_BID_INCREMENT and new_price != auction_state['current_price']:
            await ctx.send(f"❌ Minimum bid increment is {format_currency(MIN_BID_INCREMENT)}.")
            return
        
    else:
        new_price = auction_state['current_price'] + BID_INCREMENT
    
    if new_price > user_budgets[user_id]:
        await ctx.send(f"You can't bid more than your remaining budget: {format_currency(user_budgets[user_id])}")
        return
    
    auction_state['current_price'] = new_price
    auction_state['highest_bidder'] = user_id
    await ctx.send(f"🟡 {ctx.author.display_name} bids {format_currency(new_price)}!")

    if auction_state['timeout_task']:
        auction_state['timeout_task'].cancel()

    async def auto_sold():
        try:
            current_player = auction_state.get('current_player')
            if not auction_state.get('bidding', False) or not current_player:
                return
            await asyncio.sleep(7)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != current_player:
                return
            await ctx.send("⌛ Going once...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != current_player:
                return
            await ctx.send("⌛ Going twice...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != current_player:
                return
            await ctx.send("⌛ Final call...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != current_player:
                return
            await _finalize_sold(ctx)
        except asyncio.CancelledError:
            pass

    auction_state['timeout_task'] = bot.loop.create_task(auto_sold())

async def _finalize_sold(ctx):
    """Helper function to finalize the sale of a player."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state or not auction_state['bidding'] or not auction_state['current_player']:
        return

    if auction_state['highest_bidder'] is None:
        player = auction_state['current_player']
        auction_state['bidding'] = False
        auction_state['current_player'] = None
        auction_state['current_price'] = 0
        auction_state['highest_bidder'] = None
        auction_state['pass_votes'].clear()
        
        # Add to unsold players
        if 'unsold_players' not in auction_state:
            auction_state['unsold_players'] = []
        auction_state['unsold_players'].append(player)
        
        await ctx.send(f"❌ No one bid for **{player['name']}**. They go unsold.")
        return

    winner_id = auction_state['highest_bidder']
    price = auction_state['current_price']
    player = auction_state['current_player']

    try:
        winner = await bot.fetch_user(int(winner_id))
        winner_name = winner.display_name
    except:
        winner_name = f"User {winner_id}"

    user_budgets[winner_id] -= price
    user_teams[winner_id].append({
        "name": player['name'],
        "position": player['position'],
        "league": player.get('league', 'Unknown'),
        "price": price,
        "set": available_sets.get(auction_state['current_set'], 'Custom') if player.get('set', 'Custom') == 'Custom' else player.get('set', 'Unknown Set'),
        "tier": player.get('tier', 'C')
    })

    # Store the last sold player details
    auction_state['last_sold_player'] = player
    auction_state['last_sold_price'] = price
    auction_state['last_sold_winner_id'] = winner_id

    auction_state['bidding'] = False
    auction_state['current_player'] = None
    auction_state['current_price'] = 0
    auction_state['highest_bidder'] = None
    auction_state['pass_votes'].clear()
    if not save_data():
        await ctx.send("⚠️ Error saving data. Sale recorded but data may not persist.")
        return

    embed = discord.Embed(title="✅ Player Sold!", color=discord.Color.green())
    embed.add_field(name="Player", value=player['name'], inline=True)
    embed.add_field(name="Sold To", value=f"<@{winner_id}> ({winner_name})", inline=True)
    embed.add_field(name="Final Price", value=format_currency(price), inline=True)
    embed.add_field(name="Set", value=available_sets.get(auction_state['current_set'], 'Custom') if player.get('set', 'Custom') == 'Custom' else player.get('set', 'Unknown Set'), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def rebid(ctx):
    """Rebids the last sold player, removing them from the winner's team and refunding the money."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state['host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send("Only the auction host or the privileged user can use this command in this auction.")
        return

    if not auction_state['last_sold_player']:
        await ctx.send("No player has been sold yet in this auction to rebid.")
        return

    # Get the last sold player details
    player = auction_state['last_sold_player']
    price = auction_state['last_sold_price']
    winner_id = auction_state['last_sold_winner_id']

    # Remove the player from the winner's team
    if winner_id in user_teams:
        user_teams[winner_id] = [p for p in user_teams[winner_id] if p['name'] != player['name'] or p['position'] != player['position'] or p['price'] != price]

    # Refund the money
    if winner_id in user_budgets:
        user_budgets[winner_id] += price

    # Remove the player from the winner's lineup if present
    if winner_id in user_lineups and user_lineups[winner_id]['players']:
        user_lineups[winner_id]['players'] = [p for p in user_lineups[winner_id]['players'] if p['name'] != player['name'] or p['position'] != player['position'] or p['price'] != price]

    # Save the updated data
    if not save_data():
        await ctx.send("⚠️ Error saving data. Rebid initiated but data may not persist.")
        return

    # Add the player back to the appropriate tier queue
    position = player['position'].lower()
    tier = player['tier']
    if position in auction_state['player_queues'] and tier in auction_state['player_queues'][position]:
        auction_state['player_queues'][position][tier].append(player)
        # Decrement the tier counter to maintain the correct cycle
        auction_state['tier_counters'][position][tier] -= 1

    # Cancel any ongoing auction
    if auction_state['timeout_task']:
        auction_state['timeout_task'].cancel()
    auction_state['bidding'] = False
    auction_state['current_player'] = None
    auction_state['current_price'] = 0
    auction_state['highest_bidder'] = None
    auction_state['pass_votes'].clear()

    # Start the rebid
    auction_state['current_player'] = player
    auction_state['bidding'] = True
    auction_state['bids'] = {}
    auction_state['current_price'] = player.get('base_price', MIN_BASE_PRICE)
    auction_state['highest_bidder'] = None

    embed = discord.Embed(title="🔄 Player Rebid", color=discord.Color.gold())
    embed.add_field(name="Name", value=player['name'], inline=True)
    embed.add_field(name="Position", value=player.get('position', 'Unknown').upper(), inline=True)
    embed.add_field(name="League", value=player.get('league', 'Unknown'), inline=True)
    embed.add_field(name="Set", value=available_sets[auction_state['current_set']] if player.get('set') != 'Custom' else 'Custom', inline=True)
    embed.add_field(name="Starting Price", value=format_currency(auction_state['current_price']), inline=False)
    embed.set_footer(text="Use !bid or !bid [amount] to place a bid. React with 💰 to bid, ❌ to pass.")
    
    message = await ctx.send(embed=embed)
    await message.add_reaction("💰")
    await message.add_reaction("❌")

    async def auto_sold():
        try:
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                return
            await asyncio.sleep(7)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                return
            await ctx.send("⌛ Going once...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                return
            await ctx.send("⌛ Going twice...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                return
            await ctx.send("⌛ Final call...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                return
            await _finalize_sold(ctx)
        except asyncio.CancelledError:
            pass

    auction_state['timeout_task'] = bot.loop.create_task(auto_sold())

@bot.command()
async def custombid(ctx, name: str, price: str, position: str):
    """Auctions a custom player with specified name, starting price, and position."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state['host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send("Only the auction host or the privileged user can use this command in this auction.")
        return

    if auction_state['current_set'] is None:
        await ctx.send("❌ No set has been selected for this auction. The host needs to select a set first.")
        return

    if auction_state['bidding']:
        await ctx.send("An auction is already in progress. Please wait until it concludes or use !sold/!unsold.")
        return

    position = position.lower()
    if position not in available_positions:
        await ctx.send(f"Invalid position. Choose from: {', '.join(available_positions)}")
        return

    # Parse and validate price
    price = price.strip().lower().replace(",", "")
    multiplier = 1
    if price.endswith("m"):
        multiplier = 1_000_000
        price = price[:-1]
    elif price.endswith("k"):
        multiplier = 1_000
        price = price[:-1]
    
    try:
        start_price = int(float(price) * multiplier)
    except ValueError:
        await ctx.send("❌ Invalid price format. Use numbers like 50m or 1000000.")
        return

    if start_price < MIN_BASE_PRICE or start_price > MAX_BASE_PRICE:
        await ctx.send(f"Starting price must be between {format_currency(MIN_BASE_PRICE)} and {format_currency(MAX_BASE_PRICE)}.")
        return

    # Check if the player has been sold or marked unsold
    for user_id, team in user_teams.items():
        for player in team:
            if player['name'].lower() == name.lower() and player['position'].lower() == position:
                await ctx.send(f"❌ Player '{name}' ({position.upper()}) has already been sold in this auction.")
                return

    if 'unsold_players' in auction_state:
        for player in auction_state['unsold_players']:
            if player['name'].lower() == name.lower() and player['position'].lower() == position:
                await ctx.send(f"❌ Player '{name}' ({position.upper()}) was previously marked unsold in this auction.")
                return

    # Determine tier based on price
    if 40000000 <= start_price <= 50000000:
        tier = 'A'
    elif 25000000 <= start_price <= 39000000:
        tier = 'B'
    else:
        tier = 'C'

    # Create custom player
    player = {
        'name': name,
        'position': position,
        'league': 'Custom',
        'base_price': start_price,
        'tier': tier,
        'set': 'Custom'
    }

    # Cancel any ongoing auction
    if auction_state['timeout_task']:
        auction_state['timeout_task'].cancel()
    auction_state['bidding'] = False
    auction_state['current_player'] = None
    auction_state['current_price'] = 0
    auction_state['highest_bidder'] = None
    auction_state['pass_votes'].clear()

    # Start the custom bid
    auction_state['current_player'] = player
    auction_state['bidding'] = True
    auction_state['bids'] = {}
    auction_state['current_price'] = start_price
    auction_state['highest_bidder'] = None

    embed = discord.Embed(title="🔨 Custom Player Up for Auction", color=discord.Color.gold())
    embed.add_field(name="Name", value=player['name'], inline=True)
    embed.add_field(name="Position", value=player['position'].upper(), inline=True)
    embed.add_field(name="League", value='Custom', inline=True)
    embed.add_field(name="Set", value='Custom', inline=True)
    embed.add_field(name="Starting Price", value=format_currency(start_price), inline=False)
    embed.set_footer(text="Use !bid or !bid [amount] to place a bid. React with 💰 to bid, ❌ to pass.")

    message = await ctx.send(embed=embed)
    await message.add_reaction("💰")
    await message.add_reaction("❌")

    async def auto_sold():
        try:
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                return
            await asyncio.sleep(7)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                return
            await ctx.send("⌛ Going once...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                return
            await ctx.send("⌛ Going twice...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                return
            await ctx.send("⌛ Final call...")
            await asyncio.sleep(1)
            if not auction_state.get('bidding', False) or auction_state.get('current_player') != player:
                return
            await _finalize_sold(ctx)
        except asyncio.CancelledError:
            pass

    auction_state['timeout_task'] = bot.loop.create_task(auto_sold())

@bot.command()
async def sold(ctx):
    """Manually sells the current player to the highest bidder (host or privileged user only)."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state['host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send("Only the auction host or the privileged user can use this command in this auction.")
        return
    
    if not auction_state['bidding'] or not auction_state['current_player']:
        await ctx.send("No player is currently being auctioned in this channel.")
        return
    
    if auction_state['timeout_task']:
        auction_state['timeout_task'].cancel()
    
    await _finalize_sold(ctx)

@bot.command()
async def status(ctx):
    """Displays the current auction status."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state or not auction_state['bidding'] or not auction_state['current_player']:
        await ctx.send("⚠️ No player is currently being auctioned in this channel.")
        return
    
    player = auction_state['current_player']
    price = auction_state['current_price']
    bidder_id = auction_state['highest_bidder']
    bidder = f"<@{bidder_id}>" if bidder_id else "None"
    
    embed = discord.Embed(title="📢 Current Auction Status", color=discord.Color.blue())
    embed.add_field(name="Player", value=player['name'], inline=True)
    embed.add_field(name="Position", value=player.get('position', 'Unknown').upper(), inline=True)
    embed.add_field(name="League", value=player.get('league', 'Unknown'), inline=True)
    embed.add_field(name="Set", value=available_sets.get(auction_state['current_set'], 'Custom') if player.get('set', 'Custom') == 'Custom' else player.get('set', 'Unknown Set'), inline=True)
    embed.add_field(name="Highest Bid", value=format_currency(price), inline=True)
    embed.add_field(name="Highest Bidder", value=bidder, inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def unsold(ctx):
    """Marks the current player as unsold (host or privileged user only)."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel.")
        return

    if ctx.author.id != auction_state['host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send("Only the auction host or the privileged user can use this command in this auction.")
        return
    
    if not auction_state['bidding'] or not auction_state['current_player']:
        await ctx.send("No player is currently being auctioned in this channel.")
        return
    
    player = auction_state['current_player']
    auction_state['bidding'] = False
    auction_state['current_player'] = None
    auction_state['current_price'] = 0
    auction_state['highest_bidder'] = None
    auction_state['pass_votes'].clear()
    
    if auction_state['timeout_task']:
        auction_state['timeout_task'].cancel()
    
    # Add to unsold players
    if 'unsold_players' not in auction_state:
        auction_state['unsold_players'] = []
    auction_state['unsold_players'].append(player)
    
    await ctx.send(f"❌ Player **{player['name']}** goes unsold in this auction.")

@bot.command()
async def myplayers(ctx):
    """Displays the list of players bought by the command issuer."""
    user_id = str(ctx.author.id)
    if user_id not in user_teams or not user_teams[user_id]:
        await ctx.send("You haven't bought any players yet.")
        return
    
    team = user_teams[user_id]
    embed = discord.Embed(title=f"📋 {ctx.author.display_name}'s Players", color=discord.Color.teal())
    
    for p in team:
        set_info = f" ({p.get('set', 'Unknown Set')})" if 'set' in p else ""
        embed.add_field(name=f"{p['name']} ({p['position'].upper()})", 
                       value=f"{p.get('league', 'Unknown')}{set_info} - {format_currency(p['price'])}", 
                       inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def budget(ctx):
    """Displays the remaining budget of the command issuer."""
    user_id = str(ctx.author.id)
    budget = user_budgets.get(user_id, STARTING_BUDGET)
    await ctx.send(f"💰 Your remaining budget: {format_currency(budget)}")

def calculate_team_score_based_on_lineup(user_id):
    """Calculates a score for a team based on its lineup, tactic, and formation."""
    lineup_data = user_lineups.get(user_id, {'players': [], 'tactic': 'Balanced', 'formation': '4-4-2'})
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
        # Adjust score based on tier
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
    team1_lineup = user_lineups.get(team1_id, {'players': [], 'tactic': 'Balanced', 'formation': '4-4-2'})
    team2_lineup = user_lineups.get(team2_id, {'players': [], 'tactic': 'Balanced', 'formation': '4-4-2'})

    team1_players = team1_lineup['players'] or user_teams.get(team1_id, [])[:MAX_LINEUP_PLAYERS]
    team2_players = team2_lineup['players'] or user_teams.get(team2_id, [])[:MAX_LINEUP_PLAYERS]
    team1_tactic = team1_lineup['tactic'] if team1_lineup['players'] else 'Balanced'
    team2_tactic = team2_lineup['tactic'] if team2_lineup['players'] else 'Balanced'
    team1_formation = team1_lineup['formation'] if team1_lineup['players'] else '4-4-2'
    team2_formation = team2_lineup['formation'] if team2_lineup['players'] else '4-4-2'

    if not team1_players or not team2_players:
        return None, "One or both teams have no players.", None

    team1_attack, team1_defense = calculate_team_score_based_on_lineup(team1_id)
    team2_attack, team2_defense = calculate_team_score_based_on_lineup(team2_id)

    team1_attack += random.randint(-15, 15)
    team1_defense += random.randint(-15, 15)
    team2_attack += random.randint(-15, 15)
    team2_defense += random.randint(-15, 15)

    team1_goals = 0
    team2_goals = 0
    score_diff = abs((team1_attack - team2_defense) - (team2_attack - team1_defense))
    
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
                narrative.append(f"⚽ {player_name} ({pos}) scores a {random.choice(['stunning', 'clinical', 'brilliant'])} goal for {team_name_display}!")
            else:
                narrative.append(f"⚽ {player_name} ({pos}) scores a rare goal for {team_name_display}!")
        elif event == 'save':
            if pos == 'GK':
                narrative.append(f"🧤 {player_name} ({pos}) makes a fantastic save to deny {team_name_display}'s opponent!")
            else:
                narrative.append(f"🧤 {team_name_display}'s goalkeeper makes a crucial save!")
        elif event == 'chance':
            if pos in ['ST', 'LW', 'RW', 'CAM']:
                narrative.append(f"🎯 {player_name} ({pos}) misses a golden opportunity for {team_name_display}!")
            else:
                narrative.append(f"🎯 {player_name} ({pos}) creates a chance for {team_name_display}!")
        elif event == 'tackle':
            if pos in ['CB', 'LB', 'RB', 'CM']:
                narrative.append(f"💪 {player_name} ({pos}) makes a crunching tackle to stop {team_name_display}'s opponent!")
            else:
                narrative.append(f"💪 {player_name} ({pos}) makes a key defensive play for {team_name_display}!")
        elif event == 'assist':
            if pos in ['CAM', 'LW', 'RW', 'CM']:
                narrative.append(f"🎁 {player_name} ({pos}) delivers a perfect assist for {team_name_display}!")
            else:
                narrative.append(f"🎁 {player_name} ({pos}) sets up a goal for {team_name_display}!")

    if team1_tactic == 'Attacking' and team1_goals > team2_goals:
        narrative.append(f"{team1.display_name}'s attacking style overwhelmed the opposition's defense!")
    elif team2_tactic == 'Defensive' and team2_goals <= team1_goals:
        narrative.append(f"{team2.display_name}'s defensive solidity frustrated their opponents!")
    elif team1_formation in ['5-4-1', '5-3-2'] and team1_goals <= team2_goals:
        narrative.append(f"{team1.display_name}'s defensive {team1_formation} formation held strong!")
    elif team2_formation in ['4-3-3', '3-4-3'] and team2_goals > team1_goals:
        narrative.append(f"{team2.display_name}'s attacking {team2_formation} formation overwhelmed the opposition!")

    return (team1_goals, team2_goals), "\n".join(narrative), (team1_attack, team1_defense, team2_attack, team2_defense, team1_formation, team2_formation)

@bot.command()
async def battle(ctx, team1: discord.Member, team2: discord.Member):
    """Simulates a football match between two participants' lineups (host or privileged user only)."""
    auction_state = active_auctions.get(ctx.channel.id)
    if not auction_state:
        await ctx.send("No auction is currently running in this channel, so battle commands are not available here.")
        return

    if ctx.author.id != auction_state['host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send("Only the auction host or the privileged user can run this command in this auction.")
        return
    
    team1_id = str(team1.id)
    team2_id = str(team2.id)

    if team1_id not in user_teams or not user_teams[team1_id]:
        await ctx.send(f"{team1.display_name} has no players to field a team.")
        return
    if team2_id not in user_teams or not user_teams[team2_id]:
        await ctx.send(f"{team2.display_name} has no players to field a team.")
        return

    scoreline, narrative, scores = simulate_match(team1_id, team2_id, team1, team2)
    
    if scoreline is None:
        await ctx.send(narrative)
        return

    team1_goals, team2_goals = scoreline
    team1_attack, team1_defense, team2_attack, team2_defense, team1_formation, team2_formation = scores

    team1_lineup = user_lineups.get(team1_id, {'players': [], 'tactic': 'Balanced', 'formation': '4-4-2'})
    team2_lineup = user_lineups.get(team2_id, {'players': [], 'tactic': 'Balanced', 'formation': '4-4-2'})
    team1_players = team1_lineup['players'] or user_teams.get(team1_id, [])[:MAX_LINEUP_PLAYERS]
    team2_players = team2_lineup['players'] or user_teams.get(team2_id, [])[:MAX_LINEUP_PLAYERS]
    team1_tactic = team1_lineup['tactic'] if team1_lineup['players'] else 'Balanced'
    team2_tactic = team2_lineup['tactic'] if team2_lineup['players'] else 'Balanced'
    team1_formation = team1_lineup['formation'] if team1_lineup['players'] else '4-4-2'
    team2_formation = team2_lineup['formation'] if team2_lineup['players'] else '4-4-2'

    embed = discord.Embed(title="⚽ Match Result", color=discord.Color.purple())
    embed.add_field(name="Teams", value=f"{team1.display_name} vs {team2.display_name}", inline=False)
    embed.add_field(name="Scoreline", value=f"{team1_goals} - {team2_goals}", inline=False)
    embed.add_field(name="Team Strengths", 
                    value=f"{team1.display_name}: Attack {team1_attack}, Defense {team1_defense}\n"
                          f"{team2.display_name}: Attack {team2_attack}, Defense {team2_defense}", 
                    inline=False)
    embed.add_field(name="Tactics and Formations", 
                    value=f"{team1.display_name}: {team1_tactic}, {team1_formation}\n"
                          f"{team2.display_name}: {team2_tactic}, {team2_formation}", 
                    inline=False)
    embed.add_field(name="Match Summary", value=narrative, inline=False)
    
    team1_lineup_str = "\n".join([f"{p['name']} ({p['position'].upper()})" for p in team1_players]) or "No lineup set"
    team2_lineup_str = "\n".join([f"{p['name']} ({p['position'].upper()})" for p in team2_players]) or "No lineup set"
    embed.add_field(name=f"{team1.display_name}'s Lineup", value=team1_lineup_str, inline=True)
    embed.add_field(name=f"{team2.display_name}'s Lineup", value=team2_lineup_str, inline=True)
    
    if team1_goals > team2_goals:
        embed.add_field(name="Winner", value=f"{team1.display_name} 🏆", inline=False)
    elif team2_goals > team1_goals:
        embed.add_field(name="Winner", value=f"{team2.display_name} 🏆", inline=False)
    else:
        embed.add_field(name="Result", value="Draw 🤝", inline=False)
    
    embed.set_footer(text="Use !battle @user1 @user2 to simulate another match!")
    await ctx.send(embed=embed)

@bot.command()
async def rankteams(ctx):
    """Ranks all participant teams based on their lineup composition."""
    if not user_teams:
        await ctx.send("No teams have been formed yet to rank.")
        return

    team_scores = []
    for user_id, team_players in user_teams.items():
        if team_players:
            attack_score, defense_score = calculate_team_score_based_on_lineup(user_id)
            total_score = attack_score + defense_score
            try:
                user = await bot.fetch_user(int(user_id))
                team_scores.append((user.display_name, total_score, user_id, len(team_players)))
            except discord.NotFound:
                team_scores.append((f"Unknown User ({user_id})", total_score, user_id, len(team_players)))
            except Exception as e:
                print(f"Error fetching user {user_id}: {e}")
                team_scores.append((f"Error User ({user_id})", total_score, user_id, len(team_players)))

    if not team_scores:
        await ctx.send("No players have been bought by any participant yet.")
        return

    team_scores.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(title="🏆 Team Rankings (Based on Lineup)", color=discord.Color.gold())
    description_list = []

    for i, (name, score, user_id, num_players_in_team) in enumerate(team_scores):
        lineup_data = user_lineups.get(user_id, {'players': [], 'tactic': 'Balanced', 'formation': '4-4-2'})
        players_in_lineup = lineup_data['players'] if lineup_data['players'] else user_teams.get(user_id, [])[:MAX_LINEUP_PLAYERS]
        
        positions_covered = set(p['position'].lower() for p in players_in_lineup)
        
        set_distribution = {}
        tier_distribution = {'A': 0, 'B': 0, 'C': 0}
        for p in players_in_lineup:
            player_set_name = p.get('set', 'Unknown Set')
            display_set_name = available_sets.get(player_set_name, player_set_name)
            set_distribution[display_set_name] = set_distribution.get(display_set_name, 0) + 1
            tier = p.get('tier', 'C')
            tier_distribution[tier] += 1
        
        set_info_parts = [f"{count} {key}" for key, count in set_distribution.items()]
        set_summary = f"Sets: {', '.join(set_info_parts)}" if set_info_parts else "No Sets"
        tier_summary = f"Tiers: A: {tier_distribution['A']}, B: {tier_distribution['B']}, C: {tier_distribution['C']}"
        tactic = lineup_data['tactic'] if lineup_data['players'] else 'Balanced'
        formation = lineup_data['formation'] if lineup_data['players'] else '4-4-2'

        description_list.append(f"**{i+1}.** <@{user_id}> ({name}): **{score} Team Score** ({len(players_in_lineup)} players in lineup)\n"
                               f"  Positions: {', '.join(p.upper() for p in positions_c
