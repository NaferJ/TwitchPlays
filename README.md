# TwitchPlays
These are the three Python files I use that allows Twitch Chat or Youtube Chat to control your keyboard or mouse to play a game. You are welcome to use or adapt this code for your own content.

To run the code you will need to install Python 3.9.  
Additionally, you will need to install the following python modules using Pip:  
python -m pip install keyboard  
python -m pip install pydirectinput  
python -m pip install pyautogui  
python -m pip install pynput  
python -m pip install requests  

Kick chat (optional):  
python -m pip install pusherclient  

Once Python is set up, simply change the Twitch username (or Youtube channel ID) in TwitchPlays_TEMPLATE.py, and you'll be ready to go.

Kick setup (optional):
- Set STREAM_SOURCE = "kick" in TwitchPlays_TEMPLATE.py.  
- Set KICK_CHANNEL to your Kick username.  
- Provide KICK_PUSHER_KEY and KICK_PUSHER_CLUSTER. Inspect Kick network calls if unsure, as these may change.  
- If your channel requires auth to read chat, paste your browser Cookie header into KICK_COOKIES and the CSRF token into KICK_CSRF, or leave them blank if not needed.  

This code is originally based off Wituz's Twitch Plays template, then expanded by DougDoug and DDarknut with help from Ottomated for the Youtube side. For now I am not reviewing any pull requests or code changes, this code is meant to be a simple prototype that is uploaded for educational purposes. But feel free to fork the project and create your own version!
