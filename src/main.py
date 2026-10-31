import json, time
from valclient.client import Client
from player import Player
from game import Game

running = True
seenMatches = []

print('ValScope by Dralle')

with open('settings.json', 'r') as f:
    data = json.load(f)
    ranBefore = data['ran']
    region = data['region']
    stateInterval = data['stateInterval']

if (ranBefore == False):
    region = input("Enter your region: ").lower()
    client = Client(region=region)
    client.activate()

    with open('settings.json', 'w') as f:
            data['ran'] = True
            data['region'] = region
            json.dump(data, f, indent=4)
else:
    client = Client(region=region)
    client.activate()

print("Waiting for a match to begin")
while (running):
    time.sleep(stateInterval)
    try:
        # raises "You are not in a core-game" until the match has loaded
        matchID = client.coregame_fetch_player()['MatchID']

        if (matchID not in seenMatches):
            print('-'*55)
            print("Match detected")
            seenMatches.append(matchID)
            matchInfo = client.coregame_fetch_match(matchID)
            players = []
            localPlayer = None

            for player in matchInfo['Players']:
                if (client.puuid == player['Subject']):
                    localPlayer = Player(
                        client=client,
                        puuid=player['Subject'].lower(),
                        agentID=player['CharacterID'].lower(),
                        incognito=player['PlayerIdentity']['Incognito'],
                        team=player['TeamID'],
                        accountLevel=player['PlayerIdentity'].get('AccountLevel')
                    )
                else:
                    players.append(Player(
                        client=client,
                        puuid=player['Subject'].lower(),
                        agentID=player['CharacterID'].lower(),
                        incognito=player['PlayerIdentity']['Incognito'],
                        team=player['TeamID'],
                        accountLevel=player['PlayerIdentity'].get('AccountLevel')
                    ))

            currentGame = Game(matchID=matchID, players=players, localPlayer=localPlayer)
            print("\nFinding hidden names\n")
            currentGame.find_hidden_names(players)

    except Exception as e:
        if ("core" not in str(e)) and ("NoneType" not in str(e)):
            print("An error occurred:", e)
