import concurrent.futures
import random
import keyboard
import pydirectinput
import pyautogui
import TwitchPlays_Connection
from TwitchPlays_KeyCodes import *

##################### GAME VARIABLES #####################

# Replace this with your Twitch username. Must be all lowercase.
TWITCH_CHANNEL = 'dougdougw' 

# If streaming on Youtube, set this to False
STREAMING_ON_TWITCH = True

# If you're streaming on Youtube, replace this with your Youtube's Channel ID
# Find this by clicking your Youtube profile pic -> Settings -> Advanced Settings
YOUTUBE_CHANNEL_ID = "YOUTUBE_CHANNEL_ID_HERE" 

# If you're using an Unlisted stream to test on Youtube, replace "None" below with your stream's URL in quotes.
# Otherwise you can leave this as "None"
YOUTUBE_STREAM_URL = None

# Select your chat source: "twitch", "youtube", or "kick". Defaults to Twitch.
STREAM_SOURCE = "kick"

# Kick settings (only used if STREAM_SOURCE == "kick")
# Set your Kick channel username (lowercase)
KICK_CHANNEL = "Luisardito"
# Kick uses Pusher for chat. Provide the app key and cluster.
# Note: Values may change over time; inspect the Kick site network calls if needed.
KICK_PUSHER_KEY = ""  # Not used with KickAPI
KICK_PUSHER_CLUSTER = ""  # Not used with KickAPI
# Auth endpoint used by Kick for private chat channels (usually this URL works if cookies are provided):
KICK_AUTH_URL = "https://kick.com/broadcasting/auth"
# To read chat from your own account, you may need to be authenticated. Paste your browser Cookie header string and CSRF token if required.
# Leave empty strings if unauthenticated access works for your channel.
KICK_COOKIES = ""  # e.g. "__cf_bm=...; XSRF-TOKEN=...; kick_session=..."
KICK_CSRF = ""

##################### MESSAGE QUEUE VARIABLES #####################

# MESSAGE_RATE controls how fast we process incoming Twitch Chat messages. It's the number of seconds it will take to handle all messages in the queue.
# This is used because Twitch delivers messages in "batches", rather than one at a time. So we process the messages over MESSAGE_RATE duration, rather than processing the entire batch at once.
# A smaller number means we go through the message queue faster, but we will run out of messages faster and activity might "stagnate" while waiting for a new batch. 
# A higher number means we go through the queue slower, and messages are more evenly spread out, but delay from the viewers' perspective is higher.
# You can set this to 0 to disable the queue and handle all messages immediately. However, then the wait before another "batch" of messages is more noticeable.
MESSAGE_RATE = 0.5
# MAX_QUEUE_LENGTH limits the number of commands that will be processed in a given "batch" of messages. 
# e.g. if you get a batch of 50 messages, you can choose to only process the first 10 of them and ignore the others.
# This is helpful for games where too many inputs at once can actually hinder the gameplay.
# Setting to ~50 is good for total chaos, ~5-10 is good for 2D platformers
MAX_QUEUE_LENGTH = 20
MAX_WORKERS = 100 # Maximum number of threads you can process at a time 

last_time = time.time()
message_queue = []
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
active_tasks = []
pyautogui.FAILSAFE = False

##########################################################

# Count down before starting, so you have time to load up the game
countdown = 5
while countdown > 0:
    print(countdown)
    countdown -= 1
    time.sleep(1)

# Backward compatibility: If STREAM_SOURCE is not set, fall back to STREAMING_ON_TWITCH flag
source = STREAM_SOURCE.lower() if 'STREAM_SOURCE' in globals() else ('twitch' if STREAMING_ON_TWITCH else 'youtube')

if source == 'twitch':
    t = TwitchPlays_Connection.Twitch()
    t.twitch_connect(TWITCH_CHANNEL)
elif source == 'youtube':
    t = TwitchPlays_Connection.YouTube()
    t.youtube_connect(YOUTUBE_CHANNEL_ID, YOUTUBE_STREAM_URL)
elif source == 'kick':
    t = TwitchPlays_Connection.Kick()
    t.kick_connect(KICK_CHANNEL, KICK_PUSHER_KEY, KICK_PUSHER_CLUSTER, KICK_AUTH_URL, KICK_COOKIES, KICK_CSRF)
else:
    print(f"Unknown STREAM_SOURCE: {source}. Defaulting to twitch.")
    t = TwitchPlays_Connection.Twitch()
    t.twitch_connect(TWITCH_CHANNEL)

def handle_message(message):
    try:
        msg = message['message'].lower()
        username = message['username'].lower()

        print("Got this message from " + username + ": " + msg)

        # Now that you have a chat message, this is where you add your game logic.
        # Use the "HoldKey(KEYCODE)" function to permanently press and hold down a key.
        # Use the "ReleaseKey(KEYCODE)" function to release a specific keyboard key.
        # Use the "HoldAndReleaseKey(KEYCODE, SECONDS)" function press down a key for X seconds, then release it.
        # Use the pydirectinput library to press or move the mouse

        # I've added some example videogame logic code below:

        ###################################
        # Undertale Chaos: numeric votes (1-8)
        ###################################
        if msg in ("1","2","3","4","5","6","7","8"):
            key_map = {
                "1": ONE, "2": TWO, "3": THREE, "4": FOUR,
                "5": FIVE, "6": SIX, "7": SEVEN, "8": EIGHT
            }
            # Short tap on the number key to register the vote
            HoldAndReleaseKey(key_map[msg], 0.1)

        ####################################
        ####################################

    except Exception as e:
        print("Encountered exception: " + str(e))


while True:

    active_tasks = [t for t in active_tasks if not t.done()]

    #Check for new messages
    new_messages = t.twitch_receive_messages();
    if new_messages:
        message_queue += new_messages; # New messages are added to the back of the queue
        message_queue = message_queue[-MAX_QUEUE_LENGTH:] # Shorten the queue to only the most recent X messages

    messages_to_handle = []
    if not message_queue:
        # No messages in the queue
        last_time = time.time()
    else:
        # Determine how many messages we should handle now
        r = 1 if MESSAGE_RATE == 0 else (time.time() - last_time) / MESSAGE_RATE
        n = int(r * len(message_queue))
        if n > 0:
            # Pop the messages we want off the front of the queue
            messages_to_handle = message_queue[0:n]
            del message_queue[0:n]
            last_time = time.time();

    # If user presses Shift+Backspace, automatically end the program
    if keyboard.is_pressed('shift+backspace'):
        exit()

    if not messages_to_handle:
        continue
    else:
        for message in messages_to_handle:
            if len(active_tasks) <= MAX_WORKERS:
                active_tasks.append(thread_pool.submit(handle_message, message))
            else:
                print(f'WARNING: active tasks ({len(active_tasks)}) exceeds number of workers ({MAX_WORKERS}). ({len(message_queue)} messages in the queue)')
 