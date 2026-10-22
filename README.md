# btd6bot

A screen-reading bot that plays **Bloons TD 6** (Steam, Windows) on its own: single-player standard maps only (no bosses, co-op, races or odysseys). The goal is the most **Hard-mode map wins per hour** while it runs unattended overnight. Along the way it levels a fresh account, unlocks towers and upgrades, and then works toward the remaining modes, including CHIMPS.

It only looks at the screen and sends mouse and keyboard input. It never reads or modifies game files or memory.

## Running

```
python bot.py run --hours 8     # play until time is up
python bot.py plan              # what would it play next, and why
python bot.py status            # account summary (level, towers, medals)
```

For unattended runs, the supervisor (`run_forever.ps1`) is installed as the Windows scheduled task **BTD6Bot**. It starts at logon, survives terminal and Claude restarts, launches BTD6 through Steam if needed, and restarts the bot if it exits, kills it if it hangs (watchdog), and restarts BTD6 if games stop finishing. **Ctrl+Alt+F8**, or creating a file named `STOP` in the project folder, stops it for good.

```
powershell -ExecutionPolicy Bypass -File tools\install_task.ps1   # install and start
schtasks /run /tn BTD6Bot                                         # start
schtasks /end /tn BTD6Bot                                         # stop the supervisor
```

An hourly Claude caretaker task (`btd6-bot-caretaker` in the app's Scheduled list) also runs. It reads the logs, restarts the bot if it died, fixes crash bugs, and commits each fix. Its notes go to `docs/caretaker_log.md`.

- Python 3.12 is installed at `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`.
- The game must run fullscreen at 1920×1200. This is the calibrated layout; other 16:10 resolutions scale.
- **Ctrl+Alt+F8** (or a `STOP` file) stops the bot immediately; a `PAUSE` file parks it at the main menu between games.

## How it plays

| Piece | What it does |
|---|---|
| `screen.py` | Captures the game window with `PrintWindow`, so other windows on top don't matter. Focuses the game without sending any keystrokes. |
| `inputs.py` | Sends input only while BTD6 is the foreground window, and clicks only where the game owns the pixel. **Never sends Esc.** |
| `hud.py` | Reads cash, lives and round with recognition-only OCR (about 50 ms). |
| `scanner.py` | Visits a map for the first time: holds a tower over a grid and checks whether the range circle turns red. The result is a placement map, and the thin blocked corridors reveal the track **before round 1**. |
| `maplearn.py` | Watches bloons move during defended rounds to learn the exact track and how far along it each point is. Scores tower spots by how much track they cover. Results are cached in `data/maps/`. |
| `game.py` | Places towers and verifies each placement (tower held, spot legal, cash dropped). Upgrades by clicking the tower and its path button. Upgrades still locked behind tower XP are unlocked from the in-game upgrade tree. Also handles targeting, selling and hero abilities. |
| `strategy.py` | Plays YAML build plans (`strategies/`). Plans use roles such as *dps*, *support*, *exit* or *far* instead of coordinates, so one plan works on every map. If lives drop, it panic-buys defense. |
| `match.py` | One game. It sets up a defense first (no round starts undefended), then keeps 2× speed with auto-start, traces the track, and handles level-ups and popups. A game paused by a popup is detected because the screen stops changing. |
| `menus.py` | Recognizes screens by OCR keywords. Never clicks purchase buttons or a Monkey Money continue. |
| `planner.py` / `account.py` | Picks the next map, mode and strategy by expected value per minute: XP, Monkey Money, new medals, unlocks, and win probability learned from past results. |
| `runner.py` | The loop: main menu → plan → search map → difficulty → mode → play → record. |

## Rules it follows

- Never lose: overbuild rather than risk it, and never start a round with no towers.
- Never spend Monkey Money on continues. Never click real-money or store buttons.
- Single-player only.

## Development

`tools/` holds small helpers that act on the live game:

- `act.py` clicks and keys.
- `ocr.py` dumps the text on screen.
- `shot.py` captures the screen.
- `test_match.py` takes over the game in progress.

`docs/screens/` holds reference captures of every screen the bot knows.
