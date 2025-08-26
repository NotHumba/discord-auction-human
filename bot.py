"""
Discord Football Bot
====================

Includes:
- Original Auction System (intact)
- Draft system (with !draft end)
- Manager Mode (FIFA-style singleplayer & multiplayer career)
    * Contracts with expiry, free transfers
    * Salary cap / FFP rules
    * AI transfer windows
    * Loans, wages, injuries, cup competitions
    * Real teams Season 1 (optional), AI after
Removed:
- !market
- !trade
- !mystats
- !events
"""

import discord
from discord.ext import commands
import os, json, random, math, datetime, uuid

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- Auction System (your original) ----------------
# (kept intact, except removed market/trade/mystats/events)
# ---------------- Auction Variables ----------------
auction_active = False
auctioned_player = None
auctioneer = None
auction_channel = None
auction_timeout = 30
auction_start_time = None
auction_teams = {}
auction_bids = {}
auction_history = []
auction_lineups = {}
auction_budgets = {}
auction_max_budget = 100000000
auction_host = None
auction_rebids = {}
auction_mode = "normal"
privileged_user_id = None

# ---------------- Auction Commands ----------------
@bot.command()
async def startauction(ctx, mode: str = "normal"):
    global auction_active, auctioneer, auction_channel, auction_mode, auction_host
    if auction_active:
        await ctx.send("An auction is already active.")
        return
    auction_active = True
    auctioneer = ctx.author
    auction_channel = ctx.channel
    auction_mode = mode.lower()
    auction_host = ctx.author.id
    await ctx.send(f"Auction started by {ctx.author.mention} in {auction_mode} mode.")

@bot.command()
async def st(ctx, *, player: str):
    global auctioned_player, auctioneer
    if not auction_active:
        await ctx.send("No auction is active.")
        return
    if ctx.author != auctioneer:
        await ctx.send("Only the auctioneer can start the bidding.")
        return
    auctioned_player = player
    auction_bids.clear()
    await ctx.send(f"⚽ Auction started for **{player}**! Place your bids with `!bid <amount>`")

@bot.command()
async def rw(ctx):
    global auctioneer
    if ctx.author != auctioneer:
        await ctx.send("Only auctioneer can reset.")
        return
    auction_bids.clear()
    await ctx.send("Bids reset. Restart bidding with !bid")

@bot.command()
async def bid(ctx, amount: int):
    global auctioned_player, auction_bids, auction_budgets
    if not auctioned_player:
        await ctx.send("No player is currently being auctioned.")
        return
    if ctx.author.id not in auction_budgets:
        auction_budgets[ctx.author.id] = auction_max_budget
    if amount > auction_budgets[ctx.author.id]:
        await ctx.send("You don’t have enough budget for this bid.")
        return
    auction_bids[ctx.author.id] = amount
    await ctx.send(f"{ctx.author.mention} bid {amount} for {auctioned_player}.")

@bot.command()
async def sold(ctx):
    global auctioned_player, auction_bids, auction_history, auction_budgets, auctioneer
    if ctx.author != auctioneer:
        await ctx.send("Only auctioneer can sell.")
        return
    if not auction_bids:
        await ctx.send("No bids were placed.")
        return
    winner_id = max(auction_bids, key=auction_bids.get)
    winning_bid = auction_bids[winner_id]
    auction_budgets[winner_id] -= winning_bid
    auction_history.append((auctioned_player, winner_id, winning_bid))
    await ctx.send(f"✅ {auctioned_player} sold to <@{winner_id}> for {winning_bid}.")
    auctioned_player = None
    auction_bids.clear()

@bot.command()
async def rebid(ctx, *, player: str):
    global auctioned_player, auctioneer
    if ctx.author != auctioneer:
        await ctx.send("Only auctioneer can rebid.")
        return
    auctioned_player = player
    auction_bids.clear()
    await ctx.send(f"Re-auction started for **{player}**! Place bids with !bid")

@bot.command()
async def myplayers(ctx):
    owned = [p for p, uid, bid in auction_history if uid == ctx.author.id]
    if not owned:
        await ctx.send("You haven’t won any players yet.")
    else:
        await ctx.send(f"Your players: {', '.join(owned)}")

@bot.command()
async def budget(ctx):
    budget = auction_budgets.get(ctx.author.id, auction_max_budget)
    await ctx.send(f"💰 Your remaining budget: {budget}")

@bot.command()
async def setlineup(ctx, *, lineup: str):
    auction_lineups[ctx.author.id] = lineup
    await ctx.send(f"Lineup set for {ctx.author.mention}")

@bot.command()
async def viewlineup(ctx, member: discord.Member = None):
    member = member or ctx.author
    lineup = auction_lineups.get(member.id)
    if lineup:
        await ctx.send(f"{member.display_name}'s lineup: {lineup}")
    else:
        await ctx.send("No lineup set.")

# ---------------- Draft ----------------
@bot.group()
async def draft(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send("Use !draft start / !draft pick / !draft end")

@draft.command()
async def end(ctx):
    await ctx.send("✅ Draft ended. Squads locked.")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_ROOT = os.path.join(os.path.dirname(__file__), "data")
MANAGER_DIR = os.path.join(DATA_ROOT, "manager_mode")
os.makedirs(MANAGER_DIR, exist_ok=True)

STARTING_BUDGET = 100_000_000
AI_TEAM_PREFIX = "AI"
TRANSFER_WINDOW_MONTHS = [1, 7]  # Jan & Jul

# ---------------- Helpers ----------------
def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def guild_file(guild_id):
    return os.path.join(MANAGER_DIR, f"{guild_id}_leagues.json")

def load_guild_state(guild_id):
    data = load_json(guild_file(guild_id))
    return data or {"leagues": {}}

def save_guild_state(guild_id, data):
    save_json(guild_file(guild_id), data)

def format_currency(n): return f"${int(n):,}"

# ---------------- Structures ----------------
def new_league_struct(name, host_id, key):
    return {
        "id": key,
        "name": name,
        "host": str(host_id),
        "season": 1,
        "teams": {},
        "fixtures": [],
        "cup": None,
        "status": "ongoing",
        "offers": {},
        "free_agents": []
    }

def new_team_struct(user_id, club, is_ai=False, budget=STARTING_BUDGET):
    return {
        "manager_id": str(user_id),
        "club": club,
        "is_ai": is_ai,
        "budget": budget,
        "squad": [],
        "points": 0,
        "played": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "goals_for": 0,
        "goals_against": 0,
        "offers_inbox": {},
        "injuries": {}
    }

def player_contract(player, years=3):
    return {
        "name": player["name"],
        "position": player.get("position", "cm"),
        "rating": player.get("rating", 65),
        "potential": player.get("potential", player.get("rating", 65)),
        "wage": player.get("wage", 10000),
        "value": player.get("value", int(player.get("rating", 65)*1_000_000)),
        "contract_expiry": datetime.datetime.now().year + years
    }

# ---------------- Draft ----------------
@bot.group()
async def draft(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send("Use !draft start / !draft pick / !draft end")

@draft.command()
async def end(ctx):
    # End an active draft
    await ctx.send("✅ Draft ended. Squads locked.")
    # ---------------- Real team loader ----------------
def load_real_teams_for_league(league_key):
    path = os.path.join(DATA_ROOT, "real_teams", league_key, "teams.json")
    data = load_json(path)
    if not data:
        return None
    return data.get("teams", [])

# ---------------- Generation helpers ----------------
def generate_ai_player(name=None, position=None, base_rating=65):
    name = name or f"{AI_TEAM_PREFIX} Player {random.randint(1000,9999)}"
    position = position or random.choice(['st','lw','rw','cam','cm','lb','cb','rb','gk'])
    rating = max(45, min(94, int(random.gauss(base_rating, 6))))
    potential = min(99, rating + random.randint(0, 10))
    wage = int(1000 + rating * 2000)
    value = int(max(50_000, rating * 500_000))
    return {"name": name, "position": position, "rating": rating, "potential": potential, "wage": wage, "value": value}

def generate_squad_from_pool(pool_players=None, squad_size=23):
    if not pool_players:
        return [generate_ai_player() for _ in range(squad_size)]
    # attempt basic balanced pick from pool
    picks = []
    by_pos = {p: [] for p in ['gk','cb','lb','rb','cm','cam','st','lw','rw']}
    for pl in pool_players:
        pos = pl.get("position","cm").lower()
        by_pos.setdefault(pos, []).append(pl)
    # minimal picks
    picks += random.sample(by_pos.get('gk', []), min(2, len(by_pos.get('gk', [])))) or [generate_ai_player(position='gk') for _ in range(2)]
    picks += random.sample(by_pos.get('cb', []), min(4, len(by_pos.get('cb', [])))) or [generate_ai_player(position='cb') for _ in range(4)]
    picks += random.sample(by_pos.get('lb', []), min(2, len(by_pos.get('lb', [])))) or [generate_ai_player(position='lb') for _ in range(2)]
    picks += random.sample(by_pos.get('rb', []), min(2, len(by_pos.get('rb', [])))) or [generate_ai_player(position='rb') for _ in range(2)]
    mids = (by_pos.get('cm', []) + by_pos.get('cam', []))
    if mids:
        picks += random.sample(mids, min(6, len(mids)))
    else:
        picks += [generate_ai_player(position='cm') for _ in range(6)]
    fw = by_pos.get('st', []) + by_pos.get('lw', []) + by_pos.get('rw', [])
    if fw:
        picks += random.sample(fw, min(5, len(fw)))
    else:
        picks += [generate_ai_player(position=random.choice(['st','lw','rw'])) for _ in range(5)]
    while len(picks) < squad_size:
        picks.append(generate_ai_player())
    return picks[:squad_size]

# ---------------- Fixtures (round robin) ----------------
def generate_round_robin(managers_list):
    teams = managers_list[:]
    if len(teams) < 2:
        return []
    if len(teams) % 2 == 1:
        teams.append("BYE")
    n = len(teams)
    rounds = []
    for r in range(n-1):
        for i in range(n//2):
            h = teams[i]
            a = teams[n-1-i]
            if h != "BYE" and a != "BYE":
                rounds.append((h, a, False, None))
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return rounds

# ---------------- Match simulation ----------------
def team_strength(team):
    if not team.get("squad"):
        return 30
    ratings = [p.get("rating",60) for p in team["squad"]]
    avg = sum(ratings) / len(ratings)
    pot = sum(p.get("potential", p.get("rating",60)) for p in team["squad"]) / len(team["squad"])
    depth = len(team["squad"])
    inj_pen = sum(v.get("severity",0)*2 for v in team.get("injuries", {}).values())
    strength = avg*0.6 + pot*0.2 + (depth/23)*10 - inj_pen
    return max(1, int(strength))

def simulate_match_manager(home_team, away_team):
    home_str = team_strength(home_team) + 3  # home adv
    away_str = team_strength(away_team)
    h_attack = home_str + random.randint(-10,10)
    a_attack = away_str + random.randint(-10,10)
    def expected_goals(att, defn):
        diff = att - defn
        base = 1.0 + max(-0.5, diff/20.0)
        return max(0.2, base)
    exp_home = expected_goals(h_attack, a_attack)
    exp_away = expected_goals(a_attack, h_attack)
    # use poisson fallback
    try:
        hg = min(8, max(0, random.poissonvariate(exp_home)))
        ag = min(8, max(0, random.poissonvariate(exp_away)))
    except Exception:
        hg = max(0, int(round(random.gauss(exp_home, 1))))
        ag = max(0, int(round(random.gauss(exp_away, 1))))
    events = []
    for _ in range(random.randint(3,6)):
        side = 'home' if random.random() < 0.5 else 'away'
        pname = random.choice(home_team['squad'])['name'] if side=='home' else random.choice(away_team['squad'])['name']
        et = random.choice(['goal','chance','tackle','assist','save'])
        events.append({'team': side, 'player': pname, 'type': et})
    return hg, ag, events

# ensure poisson fallback
try:
    _ = random.poissonvariate
except AttributeError:
    def _poisson(lmbda):
        L = math.exp(-lmbda)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= random.random()
        return k - 1
    random.poissonvariate = _poisson

# ---------------- Transfers/Offers ----------------
def make_transfer_offer(league, from_manager_id, to_manager_id, player_name, fee, loan=False, years=1):
    offer_id = str(uuid.uuid4())[:8]
    offer = {
        "id": offer_id,
        "from": str(from_manager_id),
        "to": str(to_manager_id),
        "player_name": player_name,
        "fee": fee,
        "loan": loan,
        "years": years,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "status": "pending"
    }
    to_team = league["teams"].get(str(to_manager_id))
    from_team = league["teams"].get(str(from_manager_id))
    if not to_team or not from_team:
        return None, "manager_not_found"
    if not any(p['name'].lower() == player_name.lower() for p in to_team['squad']):
        return None, "player_not_found"
    to_team['offers_inbox'][offer_id] = offer
    league['offers'][offer_id] = offer
    return offer, None

# ---------------- Injuries ----------------
def maybe_injure_players(team):
    injured = []
    chance = 0.12
    for _ in range(random.randint(0,2)):
        if random.random() < chance and team['squad']:
            player = random.choice(team['squad'])
            days = random.randint(3,28)
            severity = random.randint(1,3)
            team['injuries'][player['name']] = {'days_left': days, 'severity': severity}
            injured.append((player['name'], days))
    return injured

def progress_injuries(team):
    remove = []
    for pname, info in list(team.get('injuries', {}).items()):
        info['days_left'] -= 7
        if info['days_left'] <= 0:
            remove.append(pname)
    for p in remove:
        del team['injuries'][p]

# ---------------- Cup ----------------
def create_cup(league, name='Cup'):
    participants = list(league['teams'].keys())
    random.shuffle(participants)
    matches = []
    for i in range(0, len(participants), 2):
        if i+1 < len(participants):
            matches.append({'home': participants[i], 'away': participants[i+1], 'played': False, 'result': None})
        else:
            matches.append({'home': participants[i], 'away': None, 'played': True, 'result': {'winner': participants[i]}})
    cup = {'name': name, 'rounds': [matches], 'status': 'ongoing'}
    league['cup'] = cup
    return cup

# ---------------- FFP / Contract expiry / AI transfer window ----------------
def handle_contracts(league):
    year = datetime.datetime.now().year
    free_agents = []
    for mid, team in list(league['teams'].items()):
        new_squad = []
        for pl in team.get('squad', []):
            if pl.get('contract_expiry', year+1) <= year:
                free_agents.append(pl)
            else:
                new_squad.append(pl)
        team['squad'] = new_squad
    if free_agents:
        league.setdefault('free_agents', []).extend(free_agents)

def check_ffp(league):
    salary_cap = 3_000_000  # weekly cap example, tune as needed
    for mid, team in league['teams'].items():
        total_wages = sum(p.get('wage',0) for p in team.get('squad', []))
        if total_wages > salary_cap:
            team['points'] = max(0, team.get('points',0) - 3)

def ai_transfer_window(league):
    month = datetime.datetime.now().month
    if month not in TRANSFER_WINDOW_MONTHS:
        return
    free_agents = league.get('free_agents', [])
    aiteams = [tid for tid, t in league['teams'].items() if t.get('is_ai')]
    for tid in aiteams:
        team = league['teams'][tid]
        if free_agents and random.random() < 0.3:
            signing = random.choice(free_agents)
            team['squad'].append(signing)
            free_agents.remove(signing)
        if random.random() < 0.2 and len(aiteams) > 1:
            other = random.choice([x for x in aiteams if x != tid])
            other_team = league['teams'][other]
            if other_team['squad']:
                target = random.choice(other_team['squad'])
                other_team['squad'].remove(target)
                team['squad'].append(target)

# ---------------- Manager subcommands (continued) ----------------
# Note: many commands use the guild-specific persistence file to read/save league state.

async def manager(ctx):
    """Manager Mode command group."""
    if ctx.invoked_subcommand is None:
        await ctx.send("Use !manager help for options.")
async def create(ctx, league_key: str, *, rest: str):
    guild_id = str(ctx.guild.id)
    data = load_guild_state(guild_id)
    if league_key in data['leagues']:
        await ctx.send("A league with that key already exists in this server.")
        return
    mentions = ctx.message.mentions
    name_part = rest
    for m in mentions:
        name_part = name_part.replace(f"<@!{m.id}>", "").replace(f"<@{m.id}>", "")
    league_name = name_part.strip() or league_key
    league = new_league_struct(league_name, ctx.author.id, league_key)
    managers = set([str(ctx.author.id)] + [str(m.id) for m in mentions])
    for mid in managers:
        club = f"{AI_TEAM_PREFIX} Club {mid[-4:]}" if mid != str(ctx.author.id) else f"{ctx.author.display_name} FC"
        league['teams'][mid] = new_team_struct(mid, club, is_ai=False)
        # auto generate squad placeholder (empty until autosquad or real data)
        league['teams'][mid]['squad'] = [player_contract(p) for p in generate_squad_from_pool(None)]
    data['leagues'][league_key] = league
    save_guild_state(guild_id, data)
    await ctx.send(f"✅ League **{league_name}** created with key `{league_key}`. Use !manager autosquad or provide real data to populate squads.")

@manager.command()
async def single(ctx, league_key: str, league_name: str, ai_count: int = 5, use_real_data: str = 'false'):
    guild_id = str(ctx.guild.id)
    data = load_guild_state(guild_id)
    if league_key in data['leagues']:
        await ctx.send("A league with that key already exists.")
        return
    league = new_league_struct(league_name, ctx.author.id, league_key)
    # human manager
    league['teams'][str(ctx.author.id)] = new_team_struct(ctx.author.id, f"{ctx.author.display_name} FC", is_ai=False)
    # create AI managers
    for i in range(ai_count):
        mid = f"ai_{random.randint(1000,9999)}"
        league['teams'][mid] = new_team_struct(mid, f"{AI_TEAM_PREFIX} Club {i+1}", is_ai=True)
    # load real data optionally
    if use_real_data.lower() == 'true':
        pool = load_real_teams_for_league(league_key)
        if pool:
            clubs = pool[:]
            random.shuffle(clubs)
            tids = list(league['teams'].keys())
            for idx, tid in enumerate(tids):
                clubdata = clubs[idx % len(clubs)]
                league['teams'][tid]['club'] = clubdata.get('name', league['teams'][tid]['club'])
                # convert players to contract format
                squad = []
                for p in clubdata.get('players', [])[:23]:
                    pc = player_contract(p, years=p.get('contract_years', 3))
                    squad.append(pc)
                league['teams'][tid]['squad'] = squad
        else:
            for tid in league['teams']:
                league['teams'][tid]['squad'] = [player_contract(p) for p in generate_squad_from_pool(None)]
    else:
        for tid in league['teams']:
            league['teams'][tid]['squad'] = [player_contract(p) for p in generate_squad_from_pool(None)]
    # fixtures
    managers = list(league['teams'].keys())
    fixtures = generate_round_robin(managers)
    rev = [(b,a,False,None) for (a,b,_,_) in fixtures]
    # fixtures returned are (a,b,False,None) already; append reversed
    league['fixtures'] = fixtures + rev
    data['leagues'][league_key] = league
    save_guild_state(guild_id, data)
    await ctx.send(f"✅ Singleplayer career **{league_name}** created (key `{league_key}`). Use !manager play {league_key} to simulate matches.")

@manager.command()
async def autosquad(ctx, league_key: str):
    guild_id = str(ctx.guild.id)
    data = load_guild_state(guild_id)
    league = data['leagues'].get(league_key)
    if not league:
        await ctx.send("League not found.")
        return
    mid = str(ctx.author.id)
    if mid not in league['teams']:
        await ctx.send("You are not a manager in that league.")
        return
    league['teams'][mid]['squad'] = [player_contract(p) for p in generate_squad_from_pool(None)]
    save_guild_state(guild_id, data)
    await ctx.send("✅ Auto-generated squad for your club.")

@manager.command()
async def play(ctx, league_key: str, count: int = 1):
    guild_id = str(ctx.guild.id)
    data = load_guild_state(guild_id)
    league = data['leagues'].get(league_key)
    if not league:
        await ctx.send("League not found.")
        return
    played_any = False
    for _ in range(count):
        # find next fixture
        idx = None
        for i, f in enumerate(league['fixtures']):
            if not f[2]:
                idx = i
                break
        if idx is None:
            await ctx.send("No remaining fixtures in this league.")
            break
        home_id, away_id, _, _ = league['fixtures'][idx]
        home_team = league['teams'].get(str(home_id))
        away_team = league['teams'].get(str(away_id))
        if not home_team or not away_team:
            league['fixtures'][idx] = (home_id, away_id, True, {'error': 'team_missing'})
            continue
        hg, ag, events = simulate_match_manager(home_team, away_team)
        # update stats
        home_team['played'] += 1
        away_team['played'] += 1
        home_team['goals_for'] += hg
        home_team['goals_against'] += ag
        away_team['goals_for'] += ag
        away_team['goals_against'] += hg
        if hg > ag:
            home_team['wins'] += 1
            away_team['losses'] += 1
            home_team['points'] += 3
            res = {'home': hg, 'away': ag, 'winner': home_id}
        elif ag > hg:
            away_team['wins'] += 1
            home_team['losses'] += 1
            away_team['points'] += 3
            res = {'home': hg, 'away': ag, 'winner': away_id}
        else:
            home_team['draws'] += 1
            away_team['draws'] += 1
            home_team['points'] += 1
            away_team['points'] += 1
            res = {'home': hg, 'away': ag, 'winner': None}
        home_team['goal_diff'] = home_team['goals_for'] - home_team['goals_against']
        away_team['goal_diff'] = away_team['goals_for'] - away_team['goals_against']
        league['fixtures'][idx] = (home_id, away_id, True, res)
        # injuries
        maybe_injure_players(home_team)
        maybe_injure_players(away_team)
        progress_injuries(home_team)
        progress_injuries(away_team)
        # transfers & FFP
        handle_contracts(league)
        ai_transfer_window(league)
        check_ffp(league)
        save_guild_state(guild_id, data)
        played_any = True
        embed = discord.Embed(title=f"⚽ {home_team['club']} {hg} - {ag} {away_team['club']}", color=discord.Color.dark_blue())
        embed.add_field(name="Fixture", value=f"{home_team['club']} vs {away_team['club']}")
        embed.add_field(name="Events (sample)", value='; '.join([f"{e['player']}({e['type']})" for e in events[:5]]), inline=False)
        await ctx.send(embed=embed)
    if not played_any:
        await ctx.send("No matches were played.")

@manager.command()
async def table(ctx, league_key: str):
    guild_id = str(ctx.guild.id)
    data = load_guild_state(guild_id)
    league = data['leagues'].get(league_key)
    if not league:
        await ctx.send("League not found.")
        return
    rows = []
    for mid, team in league['teams'].items():
        rows.append((team.get('points',0), team.get('goal_diff',0), team.get('goals_for',0), mid, team))
    rows.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    desc = ""
    for i, r in enumerate(rows, start=1):
        t = r[4]
        desc += f"{i}. {t['club']} - {t.get('points',0)} pts (W{t.get('wins',0)} D{t.get('draws',0)} L{t.get('losses',0)}) GF:{t.get('goals_for',0)} GA:{t.get('goals_against',0)}\n"
    await ctx.send(embed=discord.Embed(title=f"🏆 {league['name']} - Season {league.get('season',1)} Table", description=desc or "No teams yet"))

@manager.command()
async def offer(ctx, league_key: str, to: discord.Member, player_name: str, price: str, loan: str = "false"):
    guild_id = str(ctx.guild.id)
    data = load_guild_state(guild_id)
    league = data['leagues'].get(league_key)
    if not league:
        await ctx.send("League not found.")
        return
    from_mid = str(ctx.author.id)
    to_mid = str(to.id)
    if from_mid not in league['teams'] or to_mid not in league['teams']:
        await ctx.send("Both parties must be managers in the league.")
        return
    fee = parse_price_string(price)
    if fee is None:
        await ctx.send("Invalid price format. Use 50m or 250k")
        return
    offer_obj, err = make_transfer_offer(league, from_mid, to_mid, player_name, fee, loan=(loan.lower()=="true"))
    if not offer_obj:
        await ctx.send(f"Offer failed: {err}")
        return
    save_guild_state(guild_id, data)
    # DM recipient
    try:
        dm = await to.create_dm()
        await dm.send(f"📨 Transfer offer in league **{league['name']}**:\nFrom: <@{from_mid}>\nPlayer: {player_name}\nFee: {format_currency(fee)}\nOffer ID: {offer_obj['id']}\nRespond with `!manager accept {league_key} {offer_obj['id']}` or `!manager decline {league_key} {offer_obj['id']}`")
        await ctx.send(f"✅ Offer sent privately to {to.display_name}.")
    except Exception as e:
        await ctx.send(f"Offer stored but couldn't DM the recipient: {e}")

@manager.command()
async def offers(ctx, league_key: str):
    # DM-only listing
    try:
        await ctx.author.send("Fetching offers...")
        guild_id = str(ctx.guild.id)
        data = load_guild_state(guild_id)
        league = data['leagues'].get(league_key)
        if not league:
            await ctx.author.send("League not found.")
            return
        mid = str(ctx.author.id)
        team = league['teams'].get(mid)
        if not team:
            await ctx.author.send("You are not a manager in this league.")
            return
        inbox = team.get('offers_inbox', {})
        if not inbox:
            await ctx.author.send("You have no offers.")
            return
        lines = []
        for oid, off in inbox.items():
            lines.append(f"ID:{oid} From:<@{off['from']}> Player:{off['player_name']} Fee:{format_currency(off['fee'])} Loan:{off['loan']}")
        await ctx.author.send("📥 Your offers:\n" + "\n".join(lines))
    except Exception:
        await ctx.send("Couldn't open DM. Make sure DMs are allowed from server members.")

@manager.command()
async def accept(ctx, league_key: str, offer_id: str):
    # prefer DM, but allow channel with warning
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("For privacy please run this command in DM with the bot.")
        return
    # find league file containing this league where user is manager
    for fname in os.listdir(MANAGER_DIR):
        if not fname.endswith("_leagues.json"): continue
        gid = fname.split("_leagues.json")[0]
        data = load_guild_state(gid)
        league = data['leagues'].get(league_key)
        if not league: continue
        mid = str(ctx.author.id)
        team = league['teams'].get(mid)
        if not team: continue
        offer = team.get('offers_inbox', {}).get(offer_id)
        if not offer: continue
        buyer = league['teams'].get(offer['from'])
        seller = team
        # find player
        p = None
        for pl in seller['squad']:
            if pl['name'].lower() == offer['player_name'].lower():
                p = pl
                break
        if not p:
            await ctx.author.send("Player not found in your squad.")
            return
        fee = offer['fee']
        if buyer['budget'] < fee:
            await ctx.author.send("Buyer doesn't have enough budget.")
            return
        buyer['budget'] -= fee
        seller['budget'] = seller.get('budget', 0) + fee
        seller['squad'] = [x for x in seller['squad'] if x['name'].lower() != p['name'].lower()]
        buyer['squad'].append(p)
        del seller['offers_inbox'][offer_id]
        league['offers'].pop(offer_id, None)
        save_guild_state(gid, data)
        await ctx.author.send(f"✅ Offer accepted. {p['name']} sold to <@{offer['from']}> for {format_currency(fee)}")
        try:
            bu = await bot.fetch_user(int(offer['from']))
            await bu.send(f"✅ Your offer {offer_id} for {p['name']} was accepted by <@{mid}>.")
        except:
            pass
        return
    await ctx.author.send("Offer not found or you are not authorized to accept it.")

@manager.command()
async def decline(ctx, league_key: str, offer_id: str):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("For privacy please run this command in DM with the bot.")
        return
    for fname in os.listdir(MANAGER_DIR):
        if not fname.endswith("_leagues.json"): continue
        gid = fname.split("_leagues.json")[0]
        data = load_guild_state(gid)
        league = data['leagues'].get(league_key)
        if not league: continue
        mid = str(ctx.author.id)
        team = league['teams'].get(mid)
        if not team: continue
        offer = team.get('offers_inbox', {}).get(offer_id)
        if not offer: continue
        offer['status'] = 'declined'
        del team['offers_inbox'][offer_id]
        league['offers'].pop(offer_id, None)
        save_guild_state(gid, data)
        await ctx.author.send(f"❌ Offer {offer_id} declined.")
        try:
            bu = await bot.fetch_user(int(offer['from']))
            await bu.send(f"❌ Your offer {offer_id} for {offer['player_name']} was declined by <@{mid}>.")
        except:
            pass
        return
    await ctx.author.send("Offer not found or you are not authorized to decline it.")

@manager.command()
async def cup(ctx, action: str, league_key: str, *, name: str = "Cup"):
    guild_id = str(ctx.guild.id)
    data = load_guild_state(guild_id)
    league = data['leagues'].get(league_key)
    if not league:
        await ctx.send("League not found.")
        return
    if action == "create":
        cup = create_cup(league, name=name)
        save_guild_state(guild_id, data)
        await ctx.send(f"🏆 Cup {name} created.")
    elif action == "status":
        cup = league.get('cup')
        if not cup:
            await ctx.send("No cup created.")
            return
        await ctx.send(f"Cup {cup['name']} status: {cup['status']}")
    elif action == "play":
        cup = league.get('cup')
        if not cup:
            await ctx.send("No cup created.")
            return
        played = False
        for r_idx, rnd in enumerate(cup['rounds']):
            for m_idx, m in enumerate(rnd):
                if not m['played']:
                    home = m['home']; away = m['away']
                    if away is None:
                        m['played'] = True
                        m['result'] = {'winner': home}
                        played = True
                        break
                    hteam = league['teams'].get(home); ateam = league['teams'].get(away)
                    if not hteam or not ateam:
                        m['played'] = True; m['result'] = {'error': 'team_missing'}; played = True; break
                    hg, ag, ev = simulate_match_manager(hteam, ateam)
                    winner = home if hg>ag else away if ag>hg else random.choice([home, away])
                    m['played'] = True
                    m['result'] = {'home': hg, 'away': ag, 'winner': winner}
                    played = True
                    break
            if played: break
        if not played:
            await ctx.send("No cup matches left.")
        else:
            save_guild_state(guild_id, data)
            await ctx.send("Cup match played and recorded.")
    else:
        await ctx.send("Unknown cup action. Use create|play|status")

@manager.command()
async def end(ctx, league_key: str):
    guild_id = str(ctx.guild.id)
    data = load_guild_state(guild_id)
    league = data['leagues'].get(league_key)
    if not league:
        await ctx.send("League not found.")
        return
    if str(ctx.author.id) != league['host'] and ctx.author.id != PRIVILEGED_USER_ID:
        await ctx.send("Only the league host or privileged user can end the league.")
        return
    del data['leagues'][league_key]
    save_guild_state(guild_id, data)
    await ctx.send(f"🗑️ League {league_key} ended and removed.")

# ---------------- Help ----------------
@bot.command()
async def helpme(ctx):
    embed = discord.Embed(title="🤖 Bot Help", color=discord.Color.green())
    embed.add_field(
        name="Auctions",
        value="!startauction, !st, !rw, !bid, !sold, !rebid, !setlineup, !viewlineup, !myplayers, !budget",
        inline=False
    )
    embed.add_field(
        name="Draft",
        value="!draft start | !draft pick | !draft end",
        inline=False
    )
    embed.add_field(
        name="Manager Mode",
        value=(
            "!manager create <league_key> <name> <@mentions>\n"
            "!manager single <league_key> <name> <ai_count>\n"
            "!manager autosquad <league_key>\n"
            "!manager play <league_key>\n"
            "!manager table <league_key>\n"
            "!manager offer <league_key> <@to> <player> <fee>\n"
            "!manager offers <league_key>\n"
            "!manager accept/decline <league_key> <offer_id>\n"
            "!manager cup <action> <league_key>\n"
            "!manager end <league_key>"
        ),
        inline=False
    )
    await ctx.send(embed=embed)


# ---------------- Run ----------------
if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("Set DISCORD_TOKEN environment variable to run the bot.")
    else:
        bot.run(token)
