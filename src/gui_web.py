# this file only fetches data (through player.py) and hands it to the page.
import json, os, sys, threading
from types import SimpleNamespace

# In the .exe, the page files are unpacked to a temporary folder (sys._MEIPASS) while
# settings.json stays next to the .exe; player.py reads settings.json from the working directory.
HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, 'frozen', False)
APP_DIR = os.path.dirname(sys.executable) if FROZEN else HERE
WEB_DIR = os.path.join(getattr(sys, '_MEIPASS', HERE), 'web')
os.chdir(APP_DIR)

if not os.path.exists('settings.json'):
    # when you first launch of the .exe: the region is asked in the window
    with open('settings.json', 'w') as f:
        json.dump({"region": "eu", "stateInterval": 30, "ran": False, "henrikApiKey": ""}, f, indent=4)

import webview
from valclient.client import Client
from player import (
    Player, agentMap, agentIcons, tierNames, tierIcons, parse_scoreboard, fetch_names,
    fetch_player_by_name, fetch_henrik_matches
)

with open('settings.json', 'r') as f:
    data = json.load(f)
    ranBefore = data['ran']
    region = data['region']
    stateInterval = data['stateInterval']

DEMO = "--demo" in sys.argv

PLAYER_FIELDS = ['puuid', 'full_name', 'agent', 'agentIcon', 'incognito', 'team', 'level', 'tier', 'rank', 'rankIcon',
                 'peakTier', 'peak', 'rankedGames', 'actGames', 'actWinRate', 'avgWinRR', 'recentWinRate',
                 'smurfScore', 'smurfReasons', 'isSelf', 'inMyParty']


class Api:
    # Methods are called from the page (window.pywebview.api.*), each in its own thread.
    # Attributes start with _ so pywebview does not expose them to the page.

    def __init__(self):
        self._window = None
        self._players = {}   # puuid -> Player (or search result)
        self._matches = {}   # match id -> parsed match with Riot's raw details
        self._matchNames = {}  # match id -> {puuid: Riot ID or None}, from the scoreboard
        self._details = {}   # puuid -> last matches, cached
        self._me = None      # your own Player, for the Career tab
        self._client = None  # Riot client for searches made before the Career tab is opened
        self._checkNow = threading.Event()
        self._started = False

    # ---- helpers ----

    def _push(self, event):
        if self._window:
            self._window.run_js(f"window.onEvent({json.dumps(event)})")

    def _player_out(self, p):
        self._players[p.puuid] = p
        out = {k: getattr(p, k, None) for k in PLAYER_FIELDS}
        out['hasHistory'] = bool(getattr(p, 'client', None)) or bool(getattr(p, 'region', None))
        return out

    def _match_out(self, m):
        matchID = m['raw']['matchInfo']['matchId'] if m.get('raw') else None
        if matchID:
            self._matches[matchID] = m
        out = {k: v for k, v in m.items() if k != 'raw'}
        out['id'] = matchID
        return out

    def _details_out(self, d):
        if 'error' in d:
            return d
        return {'total': d.get('total', 0), 'summary': d.get('summary'), 'xp': d.get('xp'),
                'matches': [self._match_out(m) for m in d.get('matches', [])]}

    # ---- called by the page ----

    def init(self):
        return {'region': region, 'needsRegion': not ranBefore and not DEMO, 'demo': DEMO}

    def ready(self):
        # the page is loaded: start watching for matches (once)
        if self._started or (not ranBefore and not DEMO):
            return
        self._started = True
        if DEMO:
            threading.Thread(target=demo_worker, args=(self,), daemon=True).start()
        else:
            threading.Thread(target=self._worker, args=(region,), daemon=True).start()

    def set_region(self, value):
        global region, ranBefore
        region, ranBefore = value.strip().lower(), True
        data['ran'], data['region'] = True, region
        with open('settings.json', 'w') as f:
            json.dump(data, f, indent=4)
        self.ready()

    def check_now(self):
        self._checkNow.set()

    def player_details(self, puuid):
        p = self._players.get(puuid)
        if p is None:
            return {'error': "player not found"}
        try:
            if puuid not in self._details:
                if hasattr(p, 'load_details'):
                    self._details[puuid] = p.load_details(isSelf=getattr(p, 'isSelf', False))
                elif getattr(p, 'region', None):
                    self._details[puuid] = fetch_henrik_matches(p.puuid, p.region)
                else:
                    return {'error': "match history is not available in demo mode"}
            return self._details_out(self._details[puuid])
        except Exception as e:
            return {'error': str(e)}

    def match_details(self, puuid, matchID):
        m = self._matches.get(matchID)
        if not m:
            return {'error': "the full scoreboard is only available for matches loaded from the Riot client"}
        try:
            client = getattr(self._players.get(puuid), 'client', None)
            try:
                names = fetch_names(client, [p['subject'] for p in m['raw']['players']]) if client else {}
            except Exception as e:
                print("Could not load names:", e)
                names = {}
            board = parse_scoreboard(m['raw'], puuid, names)
            board['won'], board['scoreLine'] = m['won'], m['scoreLine']
            self._matchNames[matchID] = {p['subject']: p['name'] for p in board['players']}
            return board
        except Exception as e:
            return {'error': str(e)}

    def match_player(self, matchID, subject):
        # a player clicked in a match scoreboard: same profile and smurf rating as a search
        known = self._players.get(subject)
        if hasattr(known, 'load_details'):
            return self._player_out(known)
        m = self._matches.get(matchID)
        if not m:
            return {'error': "match not found"}
        try:
            raw = next(p for p in m['raw']['players'] if p['subject'] == subject)
            name = self._matchNames.get(matchID, {}).get(subject) or "Name withheld by Riot"
            # level stays unknown: match details also give the level of players who hide it
            found = Player.from_search(self._riot_client(), subject, name, None, agentIcons.get(raw['characterId']))
            found.agent = agentMap.get(raw['characterId'], "Profile")
            return self._player_out(found)
        except Exception as e:
            return {'error': str(e)}

    def career(self, start=0):
        try:
            if self._me is None:
                client = Client(region=region)
                client.activate()
                me = Player(client=client, puuid=client.puuid, agentID='', incognito=False, team='Blue')
                me.isSelf = True
                me.full_name = f"{client.player_name}#{client.player_tag}"
                self._me = me
            me = self._me
            details = me.load_details(count=20 if start == 0 else 10, isSelf=start == 0, start=start)
            if details['xp'] and not me.level:
                # the level comes from account XP here, so the smurf rating matches the live-match one
                me.level = details['xp']['level']
                me.smurfScore, me.smurfReasons = me.smurf_score()
            if start == 0:
                self._details[me.puuid] = details
            return {'me': self._player_out(me), **self._details_out(details)}
        except Exception as e:
            return {'error': str(e)}

    def career_reload(self):
        self._me = None
        self._details.clear()

    def search(self, query):
        if "#" not in query:
            return {'error': "use the Name#TAG format (ex: TenZ#0001)"}
        name, tag = (part.strip() for part in query.split("#", 1))
        if not name or not tag:
            return {'error': "use the Name#TAG format (ex: TenZ#0001)"}
        p, err = fetch_player_by_name(name, tag, region)
        if err or not p:
            return {'error': "player not found" if not err or "404" in err else err}
        known = self._players.get(p.puuid)
        if hasattr(known, 'load_details'):
            # already loaded from the Riot client (you, or a player in your match): its data is more complete
            return self._player_out(known)
        try:
            # HenrikDev only finds the account; rank, smurf rating and match history come from Riot
            found = Player.from_search(self._riot_client(), p.puuid, p.full_name, p.level, p.agentIcon)
            return self._player_out(found)
        except Exception as e:
            # Riot client not running: HenrikDev profile and matches only, no smurf rating
            print("Could not load the player from Riot:", e)
            p.smurfReasons = ["Smurf rating needs the Riot Client to be open"]
            return self._player_out(p)

    def _riot_client(self):
        if self._me is not None:
            return self._me.client
        if self._client is None:
            client = Client(region=region)
            client.activate()
            self._client = client
        return self._client

    # ---- live match watcher ----

    def _worker(self, region):
        client = None
        seenMatches = []
        forced = False

        while True:
            try:
                if client is None:
                    self._push({'type': 'status', 'kind': 'idle', 'text': "Connecting to the Riot Client..."})
                    client = Client(region=region)
                    client.activate()
                    self._push({'type': 'status', 'kind': 'ok',
                                'text': f"Connected as {client.player_name}#{client.player_tag} · waiting for a match"})

                # raises "You are not in a core-game" until the match has loaded
                matchID = client.coregame_fetch_player()['MatchID']

                if (matchID not in seenMatches) or forced:
                    self._push({'type': 'status', 'kind': 'match', 'text': "Match detected · checking every player..."})
                    if matchID not in seenMatches:
                        seenMatches.append(matchID)
                    matchInfo = client.coregame_fetch_match(matchID)
                    players = []

                    for player in matchInfo['Players']:
                        p = Player(
                            client=client,
                            puuid=player['Subject'].lower(),
                            agentID=player['CharacterID'].lower(),
                            incognito=player['PlayerIdentity']['Incognito'],
                            team=player['TeamID'],
                            accountLevel=player['PlayerIdentity'].get('AccountLevel')
                        )
                        p.isSelf = client.puuid == player['Subject']
                        if p.isSelf:
                            p.full_name = f"{client.player_name}#{client.player_tag}"
                        players.append(p)

                    # Riot only answers the party endpoint for your own account,
                    # so in a live match only your own party can be shown
                    try:
                        members = {m['Subject'].lower() for m in client.fetch_party()['Members']}
                    except Exception as e:
                        print("Could not load your party:", e)
                        members = set()
                    for p in players:
                        p.inMyParty = len(members) > 1 and p.puuid in members and not p.isSelf

                    self._push({'type': 'players', 'players': [self._player_out(p) for p in players]})
                    self._push({'type': 'status', 'kind': 'match', 'text': match_status(players)})

            except Exception as e:
                if "activate" in str(e):
                    client = None
                    self._push({'type': 'status', 'kind': 'error', 'text': "Riot Client not found or not signed in · retrying"})
                elif ("core" not in str(e)) and ("NoneType" not in str(e)):
                    self._push({'type': 'status', 'kind': 'error', 'text': f"An error occurred: {e}"})

            forced = self._checkNow.wait(stateInterval)
            self._checkNow.clear()


def match_status(players):
    others = [p for p in players if not getattr(p, 'isSelf', False)]
    hidden = sum(1 for p in others if p.incognito)
    smurfs = sum(1 for p in others if (p.smurfScore or 0) >= 60)
    return f"In match · {hidden} hidden player{'s' if hidden != 1 else ''} · {smurfs} likely smurf{'s' if smurfs != 1 else ''}"


def demo_worker(api):
    agents = list(agentMap.items())[:9]
    rows = [  # name, hidden, level, tier, peak, ranked games, act games, act wins, RR/win, recent WR, score, reasons
        ("Name withheld by Riot", True, 24, 18, 19, 22, 14, 11, 28, 80, 95, ["very low level (24)", "only 22 ranked games", "+28 RR per win"]),
        ("Kirito#0001", False, 212, 15, 17, 640, 41, 21, 19, 50, 5, []),
        ("Name withheld by Riot", True, None, 16, 16, 95, 20, 12, 24, 60, 28, ["+24 RR per win", "60% recent win rate"]),
        ("Nyx#777", False, 88, 14, 16, 310, 33, 15, 17, 40, 5, []),
        ("Baguette#CROIS", False, 41, 17, 17, 61, 25, 17, 25, 70, 64, ["low level (41)", "61 ranked games", "+25 RR per win", "70% recent win rate"]),
        ("Mochi#2222", False, 156, 15, 18, 520, 38, 19, 18, 50, 2, []),
        ("Name withheld by Riot", True, 70, 12, 14, 180, 30, 14, 21, 40, 10, []),
        ("Apex#999", False, 301, 16, 19, 900, 50, 26, 20, 60, 13, ["60% recent win rate"]),
        ("Lumen#4040", False, 133, 15, 15, 205, 22, 10, 18, 30, 5, []),
    ]
    players = []
    for i, ((uuid, agent), row) in enumerate(zip(agents, rows)):
        name, hidden, level, tier, peak, ranked, actGames, actWins, rr, wr, score, reasons = row
        players.append(SimpleNamespace(
            puuid=f"demo-{i}", full_name=name, agent=agent, agentIcon=agentIcons.get(uuid), incognito=hidden,
            team="Attacking" if i < 4 else "Defending", level=level, tier=tier, rank=tierNames.get(tier),
            peakTier=peak, peak=tierNames.get(peak), rankIcon=tierIcons.get(tier), rankedGames=ranked,
            actGames=actGames, actWinRate=round(100 * actWins / actGames), avgWinRR=rr, recentWinRate=wr,
            smurfScore=score, smurfReasons=reasons, isSelf=False, inMyParty=i == 1))
    api._push({'type': 'players', 'players': [api._player_out(p) for p in players]})
    api._push({'type': 'status', 'kind': 'match', 'text': "Demo mode · " + match_status(players)})


if __name__ == '__main__':
    api = Api()
    api._window = webview.create_window(
        "ValScope", url=os.path.join(WEB_DIR, 'index.html'), js_api=api,
        width=1280, height=860, min_size=(980, 560), background_color='#0f1923')
    webview.start(debug="--debug" in sys.argv)
