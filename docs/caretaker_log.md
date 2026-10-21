# Caretaker log

## 2026-10-21 18:25
- Found no supervisor or bot running: bot.log stopped at 16:46 ("first visit to Logs: scanning placement") and supervisor.log logged no exit, so the whole process tree was killed from outside (no crash event, no traceback). BTD6 was still running.
- Restarted the supervisor at 18:13. At the same moment another session installed the `BTD6Bot` scheduled task (`tools/install_task.ps1`), which started a second supervisor. Killed mine within a minute (it had only reached the main menu); the scheduled-task instance (24 h) is now the only bot running.
- Since 15:57: 3 RESULT lines, 3 wins and 0 losses, 0 lives lost. Player level L19. Logs/Easy was in progress at round 30 with 200 lives; the placement scan finished (704 points, 48% placeable).
- Seen: cash OCR misread for rounds 2-17 on Logs (e.g. 3117, 8297, 7337, apparently an extra leading digit). Reads were sane from round 18. Watch this; it can make the bot try purchases it can't afford.
- No development this run: another session had uncommitted edits in runner.py, run_forever.ps1 and README.md, so I left the code alone. Suggestion: run_forever.ps1 should refuse a second instance (named mutex), because the caretaker and the scheduled task can race.
