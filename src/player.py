import io, json, os, requests, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

agentMap = {}
agentIcons = {}
tierNames = {}
tierIcons = {}
mapNames = {}
weaponNames = {}
currentActID = None
queueNames = {
    'competitive': "Competitive", 'unrated': "Unrated", 'swiftplay': "Swiftplay",
    'spikerush': "Spike Rush", 'deathmatch': "Deathmatch", 'ggteam': "Escalation",
    'hurm': "Team Deathmatch", 'premier': "Premier", 'onefa': "Replication",
    'snowball': "Snowball Fight", '': "Custom"
}

# Clé API HenrikDev (lue depuis settings.json ou fallback ici)
HENRIK_API_KEY = ""  # set "henrikApiKey" in settings.json; keep keys out of the code
if os.path.exists('settings.json'):
    try:
        with open('settings.json', 'r') as f:
            settings_data = json.load(f)
            HENRIK_API_KEY = settings_data.get('henrikApiKey', HENRIK_API_KEY)
    except Exception:
        pass

# Cache mémoire pour éviter de spammer l'API HenrikDev sur les mêmes PUUIDs
HENRIK_NAME_CACHE = {}


def resolve_henrik_name(puuid):
    if not puuid:
        return None
    if puuid in HENRIK_NAME_CACHE:
        return HENRIK_NAME_CACHE[puuid]

    url = f"https://api.henrikdev.xyz/valorant/v2/by-puuid/account/{puuid}"
    headers = {
        "Authorization": HENRIK_API_KEY,
        "User-Agent": "Valorant-Tool/1.0"
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json().get('data', {})
            name = data.get('name')
            tag = data.get('tag')
            if name and tag:
                resolved = f"{name}#{tag}"
                HENRIK_NAME_CACHE[puuid] = resolved
                return resolved
    except Exception as e:
        print(f"Erreur HenrikDev ({puuid}):", e)

    HENRIK_NAME_CACHE[puuid] = None
    return None


try:
    reqAgents = requests.get("https://valorant-api.com/v1/agents?isPlayableCharacter=true")
    reqAgents = reqAgents.json()
    Agents = reqAgents['data']
    for agent in Agents:
        agentMap[agent['uuid']] = agent['displayName']
        agentIcons[agent['uuid']] = agent['displayIcon']
    print("Finished Updating Agents")
except Exception as e:
    print(e)

try:
    tiers = requests.get("https://valorant-api.com/v1/competitivetiers").json()['data'][-1]['tiers']
    for tier in tiers:
        tierNames[tier['tier']] = tier['tierName'].title()
        tierIcons[tier['tier']] = tier['smallIcon']

    now = datetime.now(timezone.utc).isoformat()
    for season in requests.get("https://valorant-api.com/v1/seasons").json()['data']:
        if season['parentUuid'] and season['startTime'] <= now <= season['endTime']:
            currentActID = season['uuid']

    for gameMap in requests.get("https://valorant-api.com/v1/maps").json()['data']:
        mapNames[gameMap['mapUrl']] = gameMap['displayName']

    for weapon in requests.get("https://valorant-api.com/v1/weapons").json()['data']:
        weaponNames[weapon['uuid'].lower()] = weapon['displayName']
except Exception as e:
    print(e)


class Player:
    def __init__(self, client, puuid, agentID, incognito, team, accountLevel=None):
        self.client = client
        self.puuid = puuid
        self.agent = agentMap.get(agentID, "Unknown agent")
        self.agentIcon = agentIcons.get(agentID)
        self.incognito = incognito
        self.team = self.side(team)
        self.full_name = self.set_name(puuid)
        self.level = accountLevel or None  # 0 means the player hides their level
        self.load_stats()
        self.smurfScore, self.smurfReasons = self.smurf_score()

    @classmethod
    def from_search(cls, client, puuid, full_name, level=None, icon=None):
        # a player found by Riot ID: the name is already known, so no name lookup;
        # rank and RR come from Riot like for players in a match, so the smurf rating is the same
        p = cls.__new__(cls)
        p.client, p.puuid, p.full_name, p.level = client, puuid, full_name, level
        p.agent, p.agentIcon, p.incognito, p.team = "Profile", icon, False, None
        p.load_stats()
        p.smurfScore, p.smurfReasons = p.smurf_score()
        return p

    def side(self, color):
        if color == "Blue":
            return "Defending"
        else:
            return "Attacking"

    def set_name(self, puuid):
        riot_name = None
        try:
            playerData = self.client.put(
                endpoint="/name-service/v2/players",
                endpoint_type="pd",
                json_data=[puuid]
            )[0]
            if playerData.get('GameName'):
                riot_name = f"{playerData['GameName']}#{playerData['TagLine']}"
        except Exception as e:
            print(f"Erreur name-service local ({puuid}):", e)

        # Si le joueur n'est pas masqué, on garde le nom local
        if riot_name:
            return riot_name

        # En mode Incognito / Privacy, récupération du pseudo réel via HenrikDev
        henrik_name = resolve_henrik_name(puuid)
        if henrik_name:
            return henrik_name

        return "Name withheld by Riot"

    def fetch_retry(self, endpoint):
        # Riot answers rate limits with an error body instead of an exception
        # (valclient returns None or raises "NoneType" for those)
        for wait in (2, 4, 8, 0):
            try:
                data = self.client.fetch(endpoint, "pd")
                if isinstance(data, dict) and 'errorCode' not in data:
                    return data
            except Exception:
                pass
            time.sleep(wait)
        raise Exception("no data after 4 tries")

    def load_stats(self):
        self.tier = self.peakTier = 0
        self.rankedGames = self.actGames = self.actWins = 0
        self.recentRR = []
        self.statsLoaded = True

        try:
            mmr = self.fetch_retry(f"/mmr/v1/players/{self.puuid}")
            seasons = (((mmr.get('QueueSkills') or {}).get('competitive') or {}).get('SeasonalInfoBySeasonID')) or {}
            for seasonID, season in seasons.items():
                self.rankedGames += season.get('NumberOfGames', 0)
                tiers = [int(t) for t in (season.get('WinsByTier') or {})] + [season.get('CompetitiveTier', 0)]
                self.peakTier = max([self.peakTier] + tiers)
                if seasonID == currentActID:
                    self.actGames = season.get('NumberOfGames', 0)
                    self.actWins = season.get('NumberOfWinsWithPlacements', 0)
            self.tier = (mmr.get('LatestCompetitiveUpdate') or {}).get('TierAfterUpdate') or 0
            self.peakTier = max(self.peakTier, self.tier)
        except Exception as e:
            self.statsLoaded = False
            print("Could not load rank:", e)

        try:
            updates = self.fetch_retry(
                f"/mmr/v1/players/{self.puuid}/competitiveupdates?startIndex=0&endIndex=10&queue=competitive")
            # 0 RR = placement game, says nothing about win or loss
            self.recentRR = [u['RankedRatingEarned'] for u in updates.get('Matches', []) if u.get('RankedRatingEarned')]
        except Exception as e:
            self.statsLoaded = False
            print("Could not load match history:", e)

        self.rank = tierNames.get(self.tier, "Unranked") if self.tier else "Unranked"
        self.peak = tierNames.get(self.peakTier, "Unranked") if self.peakTier else "Unranked"
        self.rankIcon = tierIcons.get(self.tier)
        wins = [rr for rr in self.recentRR if rr > 0]
        self.avgWinRR = round(sum(wins) / len(wins)) if len(wins) >= 2 else None
        self.recentWinRate = round(100 * len(wins) / len(self.recentRR)) if len(self.recentRR) >= 5 else None
        self.actWinRate = round(100 * self.actWins / self.actGames) if self.actGames >= 5 else None

    def smurf_score(self):
        score, reasons = 0, []
        if not self.statsLoaded:
            return None, ["Riot did not return this player's stats (rate limit?) · press Check now"]

        if self.level is not None:
            if self.level <= 30: score += 25; reasons.append(f"very low level ({self.level})")
            elif self.level <= 60: score += 15; reasons.append(f"low level ({self.level})")
            elif self.level <= 100: score += 5

        if self.rankedGames == 0: score += 10; reasons.append("no ranked games")
        elif self.rankedGames < 30: score += 20; reasons.append(f"only {self.rankedGames} ranked games")
        elif self.rankedGames < 80: score += 12; reasons.append(f"{self.rankedGames} ranked games")
        elif self.rankedGames < 150: score += 5

        if self.avgWinRR is not None:
            if self.avgWinRR >= 27: score += 25; reasons.append(f"+{self.avgWinRR} RR per win")
            elif self.avgWinRR >= 23: score += 15; reasons.append(f"+{self.avgWinRR} RR per win")
            elif self.avgWinRR >= 20: score += 5

        if self.recentWinRate is not None:
            if self.recentWinRate >= 70: score += 15; reasons.append(f"{self.recentWinRate}% recent win rate")
            elif self.recentWinRate >= 60: score += 8; reasons.append(f"{self.recentWinRate}% recent win rate")

        if self.peakTier >= 18 and self.rankedGames < 100:
            score += 15; reasons.append(f"{self.peak} peak in {self.rankedGames} games")

        return max(2, min(95, score)), reasons

    def load_details(self, count=10, isSelf=False, start=0):
        history = self.fetch_retry(f"/match-history/v1/history/{self.puuid}?startIndex={start}&endIndex={start + count}")
        def load(entry):
            try:
                return self.parse_match(self.fetch_retry(f"/match-details/v1/matches/{entry['MatchID']}"))
            except Exception as e:
                print("Could not load match:", e)

        # a few matches at a time instead of one by one; map() keeps the order
        with ThreadPoolExecutor(max_workers=5) as pool:
            matches = [m for m in pool.map(load, history.get('History', [])) if m]

        summary = summarize(matches)

        xp = None
        if isSelf:
            try:
                data = self.fetch_retry(f"/account-xp/v1/players/{self.puuid}")
                xp = {'level': data['Progress']['Level'], 'xp': data['Progress']['XP'],
                      'recent': [h['XPDelta'] for h in data.get('History', [])]}
            except Exception as e:
                print("Could not load account XP:", e)

        return {'total': history.get('Total', 0), 'matches': matches, 'summary': summary, 'xp': xp}

    def parse_match(self, details):
        info = details['matchInfo']
        me = next((p for p in details['players'] if p['subject'] == self.puuid), None)
        if me is None:
            return None
        stats = me['stats'] or {}
        # deathmatch modes count as a single round, so per-round stats (ACS, ADR) make no sense there
        rounds = 0 if info.get('queueID') in ('deathmatch', 'hurm') else stats.get('roundsPlayed') or 0

        teams = {t['teamId']: t for t in details.get('teams') or []}
        myTeam = teams.get(me['teamId'])
        others = [t for tid, t in teams.items() if tid != me['teamId']]
        won = myTeam['won'] if myTeam and len(teams) == 2 else None
        scoreLine = f"{myTeam['roundsWon']}-{others[0]['roundsWon']}" if myTeam and len(teams) == 2 else None

        shots = {'headshots': 0, 'bodyshots': 0, 'legshots': 0}
        for rnd in details.get('roundResults') or []:
            for ps in rnd.get('playerStats') or []:
                if ps['subject'] == self.puuid:
                    for dmg in ps.get('damage') or []:
                        for key in shots:
                            shots[key] += dmg.get(key, 0)
        totalShots = sum(shots.values())
        damage = sum(d['damage'] for d in me.get('roundDamage') or [])

        return {
            'raw': details,
            'start': info['gameStartMillis'],
            'queue': queueNames.get(info.get('queueID'), info.get('queueID') or "Custom"),
            'map': mapNames.get(info['mapId'], info['mapId'].split('/')[-1]),
            'agent': agentMap.get(me['characterId'], "Unknown"),
            'agentIcon': agentIcons.get(me['characterId']),
            'tier': tierNames.get(me.get('competitiveTier')) if info.get('isRanked') and me.get('competitiveTier') else None,
            'won': won, 'scoreLine': scoreLine,
            'kills': stats.get('kills', 0), 'deaths': stats.get('deaths', 0), 'assists': stats.get('assists', 0),
            'acs': round(stats.get('score', 0) / rounds) if rounds else None,
            'adr': round(damage / rounds) if rounds and me.get('roundDamage') is not None else None,
            'hs': round(100 * shots['headshots'] / totalShots) if totalShots else None,
        }


def summarize(matches):
    # Averages over a list of parsed matches
    def average(key):
        values = [m[key] for m in matches if m[key] is not None]
        return round(sum(values) / len(values)) if values else None

    kills, deaths = sum(m['kills'] for m in matches), sum(m['deaths'] for m in matches)
    decided = [m for m in matches if m['won'] is not None]
    return {
        'kd': round(kills / max(deaths, 1), 2) if matches else None,
        'acs': average('acs'),
        'adr': average('adr'),
        'hs': average('hs'),
        'winRate': round(100 * sum(m['won'] for m in decided) / len(decided)) if decided else None,
    }


def fetch_names(client, puuids):
    data = client.put(endpoint="/name-service/v2/players", endpoint_type="pd", json_data=puuids)
    names = {}
    for d in data:
        subject = d['Subject']
        if d.get('GameName'):
            names[subject] = f"{d['GameName']}#{d['TagLine']}"
        else:
            # Si vide via Riot name-service, fallback HenrikDev
            names[subject] = resolve_henrik_name(subject)
    return names


def parse_scoreboard(details, puuid, names=None):
    names = names or {}
    info = details['matchInfo']
    rounds = details.get('roundResults') or []
    shots, firstBloods = {}, {}

    for rnd in rounds:
        if rnd.get('firstBloodPlayer'):
            firstBloods[rnd['firstBloodPlayer']] = firstBloods.get(rnd['firstBloodPlayer'], 0) + 1
        for ps in rnd.get('playerStats') or []:
            s = shots.setdefault(ps['subject'], [0, 0])
            for dmg in ps.get('damage') or []:
                s[0] += dmg.get('headshots', 0)
                s[1] += dmg.get('headshots', 0) + dmg.get('bodyshots', 0) + dmg.get('legshots', 0)

    players = []
    for p in details['players']:
        stats = p.get('stats') or {}
        n = stats.get('roundsPlayed') or 0
        damage = sum(d['damage'] for d in p.get('roundDamage') or [])
        hs = shots.get(p['subject'], [0, 0])
        players.append({
            'subject': p['subject'], 'team': p['teamId'], 'isTarget': p['subject'] == puuid,
            'name': f"{p['gameName']}#{p['tagLine']}" if p.get('gameName') else names.get(p['subject']),
            'agent': agentMap.get(p['characterId'], "Unknown"), 'agentIcon': agentIcons.get(p['characterId']),
            'tier': tierNames.get(p.get('competitiveTier')) if info.get('isRanked') and p.get('competitiveTier') else None,
            'tierIcon': tierIcons.get(p.get('competitiveTier')) if info.get('isRanked') and p.get('competitiveTier') else None,
            'kills': stats.get('kills', 0), 'deaths': stats.get('deaths', 0), 'assists': stats.get('assists', 0),
            'acs': round(stats.get('score', 0) / n) if n else 0,
            'adr': round(damage / n) if n else 0,
            'hs': round(100 * hs[0] / hs[1]) if hs[1] else None,
            'firstBloods': firstBloods.get(p['subject'], 0),
        })
    players.sort(key=lambda p: -p['acs'])

    # parties of 2+ players get a number (1, 2, ...); solo players get None
    partySizes = {}
    for p in details['players']:
        if p.get('partyId'):
            partySizes[p['partyId']] = partySizes.get(p['partyId'], 0) + 1
    partyNumbers = {pid: i + 1 for i, pid in enumerate(pid for pid, size in partySizes.items() if size > 1)}
    partyIDs = {p['subject']: p.get('partyId') for p in details['players']}
    for p in players:
        p['party'] = partyNumbers.get(partyIDs[p['subject']])
        p['partySize'] = partySizes.get(partyIDs[p['subject']], 1)

    targetTeam = next((p['team'] for p in players if p['isTarget']), None)
    timeline, myRounds = [], []
    for rnd in rounds:
        timeline.append({'num': rnd['roundNum'] + 1, 'won': rnd.get('winningTeam') == targetTeam,
                         'result': rnd.get('roundResult') or "", 'site': rnd.get('plantSite') or ""})
        ps = next((x for x in rnd.get('playerStats') or [] if x['subject'] == puuid), None)
        if ps:
            economy = ps.get('economy') or {}
            myRounds.append({
                'num': rnd['roundNum'] + 1, 'won': rnd.get('winningTeam') == targetTeam,
                'result': rnd.get('roundResult') or "",
                'kills': len(ps.get('kills') or []),
                'damage': sum(d.get('damage', 0) for d in ps.get('damage') or []),
                'weapon': weaponNames.get((economy.get('weapon') or "").lower(), "-"),
                'loadout': economy.get('loadoutValue', 0), 'spent': economy.get('spent', 0),
                'firstBlood': rnd.get('firstBloodPlayer') == puuid,
                'died': any(k.get('victim') == puuid for x in rnd.get('playerStats') or [] for k in x.get('kills') or []),
            })

    teams = {t['teamId']: t for t in details.get('teams') or []}
    return {
        'map': mapNames.get(info['mapId'], info['mapId'].split('/')[-1]),
        'queue': queueNames.get(info.get('queueID'), info.get('queueID') or "Custom"),
        'start': info['gameStartMillis'], 'length': info.get('gameLengthMillis', 0),
        'targetTeam': targetTeam, 'teams': teams, 'players': players,
        'timeline': timeline, 'myRounds': myRounds,
    }

def fetch_player_by_name(name, tag, default_region="eu"):
    from types import SimpleNamespace
    url = f"https://api.henrikdev.xyz/valorant/v2/account/{name}/{tag}"
    headers = {"Authorization": HENRIK_API_KEY, "User-Agent": "Valorant-Tool/1.0"}
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code != 200:
            return None, f"Status HTTP {res.status_code}"
        d = res.json().get('data', {})
        puuid = d.get('puuid')
        player_region = d.get('region', default_region)

        # Récupération du rang MMR v2
        mmr_url = f"https://api.henrikdev.xyz/valorant/v2/by-puuid/mmr/{player_region}/{puuid}"
        res_mmr = requests.get(mmr_url, headers=headers, timeout=8)
        tier, peak_tier = 0, 0
        if res_mmr.status_code == 200:
            mmr_data = res_mmr.json().get('data', {})
            current_data = mmr_data.get('current_data', {})
            tier = current_data.get('currenttier', 0)
            peak_tier = mmr_data.get('highest_rank', {}).get('tier', tier)

        p = SimpleNamespace(
            full_name=f"{d.get('name')}#{d.get('tag')}",
            puuid=puuid,
            region=player_region,
            agent="Profile",
            # in account v2, card is just the card ID (it was an object in v1)
            agentIcon=f"https://media.valorant-api.com/playercards/{d['card']}/smallart.png" if d.get('card') else None,
            level=d.get('account_level'),
            tier=tier,
            rank=tierNames.get(tier, "Unranked"),
            peakTier=peak_tier,
            peak=tierNames.get(peak_tier, "Unranked"),
            rankIcon=tierIcons.get(tier),
            smurfScore=None,
            smurfReasons=[],
            incognito=False,
            client=None
        )
        return p, None
    except Exception as e:
        return None, str(e)


def fetch_henrik_matches(puuid, region="eu", count=10):
    url = f"https://api.henrikdev.xyz/valorant/v3/by-puuid/matches/{region}/{puuid}?size={count}"
    headers = {"Authorization": HENRIK_API_KEY, "User-Agent": "Valorant-Tool/1.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return {'error': f"HTTP {res.status_code}"}

        matches_raw = res.json().get('data', [])
        matches = []
        kills_total, deaths_total = 0, 0
        wins_count, decided_count = 0, 0
        acs_list, adr_list, hs_list = [], [], []

        for m in matches_raw:
            metadata = m.get('metadata', {})
            all_players = m.get('players', {}).get('all_players', [])
            me = next((p for p in all_players if p.get('puuid') == puuid), None)
            if not me:
                continue

            stats = me.get('stats', {})
            k = stats.get('kills', 0)
            d = stats.get('deaths', 0)
            a = stats.get('assists', 0)
            kills_total += k
            deaths_total += d

            teams = m.get('teams') or {}
            team_key = me.get('team', '').lower()
            my_team = teams.get(team_key, {})
            other_team_key = 'blue' if team_key == 'red' else 'red'
            other_team = teams.get(other_team_key, {})

            won = my_team.get('has_won')
            if won is not None:
                decided_count += 1
                if won:
                    wins_count += 1

            # deathmatch has no teams: no score line
            scoreLine = f"{my_team.get('rounds_won', 0)}-{other_team.get('rounds_won', 0)}" if my_team else None
            rounds = metadata.get('rounds_played', 0) or 1
            # deathmatch modes count as a single round, so per-round stats (ACS, ADR) make no sense there
            perRound = metadata.get('mode') not in ("Deathmatch", "Team Deathmatch")
            acs = round(stats.get('score', 0) / rounds) if perRound else None
            # damage_made sits on the player, not in stats
            adr = round((me.get('damage_made') or 0) / rounds) if perRound else None
            headshots = stats.get('headshots', 0)
            bodyshots = stats.get('bodyshots', 0)
            legshots = stats.get('legshots', 0)
            total_shots = headshots + bodyshots + legshots
            hs_pct = round(100 * headshots / total_shots) if total_shots else None

            if perRound:
                acs_list.append(acs)
                adr_list.append(adr)
            if hs_pct is not None:
                hs_list.append(hs_pct)

            matches.append({
                'raw': None,
                'start': metadata.get('game_start', 0) * 1000,
                'queue': metadata.get('mode') or 'Custom',
                'map': metadata.get('map', 'Unknown'),
                'agent': me.get('character', 'Unknown'),
                'agentIcon': me.get('assets', {}).get('agent', {}).get('small'),
                # HenrikDev writes "Unrated" when there is no rank; only show real ranks from ranked games
                'tier': me.get('currenttier_patched') if metadata.get('mode') == "Competitive"
                        and me.get('currenttier_patched') not in (None, "Unrated", "Unranked") else None,
                'won': won,
                'scoreLine': scoreLine,
                'kills': k,
                'deaths': d,
                'assists': a,
                'acs': acs,
                'adr': adr,
                'hs': hs_pct
            })

        summary = {
            'kd': round(kills_total / max(deaths_total, 1), 2) if matches else None,
            'acs': round(sum(acs_list) / len(acs_list)) if acs_list else None,
            'adr': round(sum(adr_list) / len(adr_list)) if adr_list else None,
            'hs': round(sum(hs_list) / len(hs_list)) if hs_list else None,
            'winRate': round(100 * wins_count / decided_count) if decided_count else None,
        }
        return {'total': len(matches), 'matches': matches, 'summary': summary, 'xp': None}
    except Exception as e:
        return {'error': str(e)}