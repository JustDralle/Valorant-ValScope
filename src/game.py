class Game:
    def __init__(self, matchID, players, localPlayer):
        self.matchID = matchID
        self.players = players
        self.localPlayer = localPlayer

    def find_hidden_names(self, players):
        self.found = False
        for player in players:
            if (player.incognito):
                self.found = True
                print(f"{player.full_name} - {player.team} {player.agent} | {player.rank} (peak {player.peak}) | smurf {player.smurfScore if player.smurfScore is not None else '?'}%")
        if not self.found:
            print("No hidden names found")
