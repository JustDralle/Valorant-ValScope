# ValScope
Smurf check for every player in your VALORANT match, plus a tracker-style view of your own matches and of any player.

By Dralle

# Quick start

**Easiest: the .exe**
1. Open the Riot Client and sign in (VALORANT can be open or not).
2. Double-click `dist\ValScope.exe`.
3. On first launch it asks for your region and creates `settings.json` next to the .exe.
4. Go in `settings.json` and put your henrikDevApiKey (get one here: https://api.henrikdev.xyz/dashboard/)
**From the source code** (Python 3.10 or newer)
```
pip install -r requirements.txt
cd src
python gui_web.py
```

Options: `--demo` shows the window with fake players (no Riot Client needed), `--debug` opens the browser dev tools.

The window is drawn by Edge WebView2, which is already installed on Windows 10 and 11.

# Features

## Live match tab
- Detects your match automatically once it has loaded (after agent select). It checks every `stateInterval` seconds; **CHECK NOW** checks right away.
- One card per player, split into **Attacking** and **Defending**, sorted by smurf rating.
- On each card:
  - agent and account level ("Lvl hidden" when the player hides it);
  - current rank, peak rank, lifetime ranked games, win rate this act, average RR per win;
  - smurf rating with the reasons written below it.
- Badges: **YOU**, **YOUR PARTY** (players queued with you), **HIDDEN** (privacy mode).
- Likely smurfs (60 % and more) get a red outline; the status bar counts the hidden players and likely smurfs.
- **Only hidden** shows only players in privacy mode; **Copy** copies a Riot ID.
- This software even shows hidden names and tracker unlike tracker.gg.
- Click a card to open that player's page.

## Smurf rating
An estimate from 2 % to 95 %, built from these signs:

| Sign | Points |
|---|---|
| Account level 30 or below / 60 or below / 100 or below | +25 / +15 / +5 |
| Lifetime ranked games: none / under 30 / under 80 / under 150 | +10 / +20 / +12 / +5 |
| Average RR per win (last 10 ranked games): 27+ / 23+ / 20+ | +25 / +15 / +5 |
| Recent win rate: 70 %+ / 60 %+ | +15 / +8 |
| Peak Diamond or higher in fewer than 100 ranked games | +15 |

High RR per win is the strongest sign: it means the hidden MMR is well above the shown rank. Under 35 % is green, 35 to 59 % yellow, 60 % and more red. If Riot does not answer (rate limit), the rating shows **?**; press CHECK NOW to retry.

## Player page
Opened from a live card, a search, or a scoreboard row.
- Rank, peak, ranked games, RR per win, smurf rating and its reasons.
- Totals over the last 10 matches: K/D, ACS, ADR, headshot %, win rate, total matches on the account.
- One row per match: result and score, agent, map, mode, date, K/D/A, ACS, ADR, HS %.
- Your own page also shows your account level and XP.
- Click a match to open its scoreboard.

## Match page
- Map, mode, date, length and final score.
- Round timeline: who won each round and how (E elimination, D defuse, B spike detonated, T time out).
- Full scoreboard for both teams: rank at the time, ACS, K/D/A, ADR, HS %, first bloods, and **parties** (who queued with whom, colour-coded).
- Round by round for the selected player: result, kills, damage, weapon, loadout value, credits spent, first blood, survived.
- Click any player in the scoreboard to open their page.

## Career tab
- Your profile: Riot ID, level and XP, rank, peak, ranked games, act win rate, your own smurf rating.
- Filters: All, Competitive, Unrated, Swiftplay, Other.
- K/D, ACS, ADR, HS % and win rate for the selected filter, plus your four most played agents.
- Your last 20 matches; **Load 10 more** goes up to the 100 that Riot keeps.

## Search (tracker-style)
- Type a Riot ID (`Name#TAG`) in the search box.
- Opens that player's page with their smurf rating and their matches. HenrikDev is used only to find the account; the rest comes from Riot through your client.
- Needs a free HenrikDev API key in `settings.json` (`henrikApiKey`), from https://docs.henrikdev.xyz.
- Without the Riot Client open, the search still shows the HenrikDev profile and matches, but no smurf rating.

# settings.json
Next to the .exe, or in `src/` when running from source. Open it with any text editor (e.g. Notepad).

| Key | Meaning |
|---|---|
| `region` | Your server region: `na`, `eu`, `latam`, `br`, `ap`, `kr` or `pbe`. Which servers belong to which region: https://support-valorant.riotgames.com/hc/en-us/articles/360055678634-Server-Select |
| `stateInterval` | Seconds between two checks for a new match (lower = faster, more CPU). |
| `ran` | `false` makes the app ask for the region again. |
| `henrikApiKey` | Your HenrikDev API key, for the search. Keep it private; `settings.json` is in `.gitignore`. |

# Limits
- Riot answers the party endpoint only for your own account, so during a live match only **your** party is shown. After the match, the scoreboard shows every party.
- Players who hide their account level stay "Lvl hidden"; the rating then works without that sign. (Don't know how to fix that tbh, tried multiple things already, none worked)
- These are Riot's unofficial client APIs; Riot can change them at any time.

# Other ways to run it
- `python gui.py`: the older Tkinter window. It has the same features except search ratings and clickable scoreboard players, and it is slower.
- `python main.py`: console only, prints the hidden players of each match.

# Building the .exe
Rebuild it after changing the code. Users of the .exe don't need Python.

**1. Install Python (once)**
Download Python 3.10 or newer from https://www.python.org/downloads/. In the installer, tick **"Add python.exe to PATH"**. To check, open a new terminal and run `python --version`.

**2. Install the dependencies (once, and again after `requirements.txt` changes)**
Open a terminal in the project folder (the one that contains `build.bat`), then run:
```
pip install -r requirements.txt pyinstaller
```

**3. Build**
Double-click `build.bat`, or run it from the terminal:
```
build.bat
```
It takes about 30 seconds and creates `dist\ValScope.exe`, a single file of about 15 MB. The `src/web/` folder (the interface) is packed inside it. PyInstaller's temporary files go to `build/`, which you can delete.

**4. Settings**
Copy your `settings.json` from `src/` next to the .exe to keep your region and HenrikDev key. Otherwise the .exe creates a new one on first launch and asks for the region and reset your henrikapidevkey.

**If something goes wrong**
- `'python' is not recognized`: Python is not in the PATH. Reinstall it with "Add python.exe to PATH" ticked, then open a new terminal.
- `No module named PyInstaller`: step 2 was skipped, or it ran with another Python than the one `build.bat` uses.
- The antivirus blocks or deletes the .exe: single-file PyInstaller builds are sometimes falsely flagged. Add an exception for the `dist` folder.
- The window is blank: the WebView2 runtime is missing. This only happens on old Windows 10 installs; get it from https://developer.microsoft.com/microsoft-edge/webview2/.
- The first launch takes a few seconds: the .exe unpacks itself to a temporary folder each time it starts. That's normal.

What `build.bat` runs, if you want to do it by hand:
```
python -m PyInstaller --noconfirm --onefile --windowed --name ValScope --add-data "<project>\src\web;web" --distpath dist --workpath build --specpath build src\gui_web.py
```
`<project>` is the full path of the project folder (`--add-data` is resolved from the `build` folder, so it needs a full path).

# Project files
| File | Role |
|---|---|
| `src/player.py` | Riot and HenrikDev calls, smurf rating, match parsing |
| `src/gui_web.py` | Webview app: fetches data for the page, watches for matches |
| `src/web/` | The interface (HTML, CSS, JavaScript) |
| `src/gui.py`, `src/main.py`, `src/game.py` | Tkinter and console versions |
| `build.bat` | Builds the .exe |

# Is This Bannable
USE AT YOUR OWN RISK. With all programs like this, there is no guarantee that it's safe because using the VALORANT API in this manner is against Riot's Terms of Service. No suspensions have been reported so far from using this program. All things considered, I would use this only on an alt account if you don't want to risk the API abuse account suspension on your main, albeit unlikely.
(imo, there's a really really low risk to getting banned or anything)

# Buy me a coffee
This software took me times to make it works and bypass riot's nickname hidding system, I'm doing it all on my free time so any help is really appreciated.
You can donate anything you want here : https://buymeacoffee.com/drallewastaken
For those that donates, There'll be a place for you on my website to thanks you helping me : https://dralle.fr

# License
Copyright (c) 2026 Dralle

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
