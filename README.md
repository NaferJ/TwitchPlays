# TwitchPlays
These are the three Python files I use that allows Twitch Chat, Youtube Chat, or Kick Chat to control your keyboard or mouse to play a game. You are welcome to use or adapt this code for your own content.

Quick start (Windows):
1) Install Python 3.9+ (recommended 3.9). Make sure "Add Python to PATH" is checked.
2) Double‑click RUN_ME_FIRST.py. It will:
   - Ask to run as Administrator (recommended so games accept inputs).
   - Auto‑install all required Python packages from requirements.txt.
   - Launch TwitchPlays_TEMPLATE.py.

Manual install (alternative):
- From this folder, run:
  - python -m pip install -r requirements.txt

If you prefer individual commands, these are the same deps:
- python -m pip install keyboard
- python -m pip install pydirectinput
- python -m pip install pyautogui
- python -m pip install pynput
- python -m pip install requests
- python -m pip install pusherclient  # needed for Kick chat

Configuration:
- Open TwitchPlays_TEMPLATE.py and set your platform.
- For Kick, you can set:
  - STREAM_SOURCE = "kick"
  - KICK_CHANNEL = your Kick username (lowercase)
  - KICK_PUSHER_KEY and KICK_PUSHER_CLUSTER (see network inspector on kick.com if unsure)
  - If your channel requires auth to read chat, paste your browser Cookie header into KICK_COOKIES and the CSRF token into KICK_CSRF; otherwise leave them blank.

Notes:
- Shift+Backspace exits the program.
- Run as Administrator if the game ignores inputs.

This code is originally based off Wituz's Twitch Plays template, then expanded by DougDoug and DDarknut with help from Ottomated for the Youtube side. For now I am not reviewing any pull requests or code changes, this code is meant to be a simple prototype that is uploaded for educational purposes. But feel free to fork the project and create your own version!
