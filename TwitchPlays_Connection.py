# DougDoug Note: 
# This is the code that connects to Twitch / Youtube and checks for new messages.
# You should not need to modify anything in this file, just use as is.

# This code is based on Wituz's "Twitch Plays" tutorial, updated for Python 3.X
# http://www.wituz.com/make-your-own-twitch-plays-stream.html
# Updated for Youtube by DDarknut, with help by Ottomated

import requests
import sys
import socket
import re
import random
import time
import os
import json
import concurrent.futures
import traceback
import threading
import ssl
from requests.adapters import HTTPAdapter

class KickHTTPAdapter(HTTPAdapter):
    """Custom HTTPAdapter to use a clean SSLContext for Kick.com requests (mitigates some 403/Cloudflare issues)."""
    def init_poolmanager(self, *args, **kwargs):
        # Create default SSL context and pass it to urllib3 so it doesn't tweak options like OP_NO_TICKET
        ssl_context = ssl.create_default_context()
        kwargs["ssl_context"] = ssl_context
        return super().init_poolmanager(*args, **kwargs)

MAX_TIME_TO_WAIT_FOR_LOGIN = 3
YOUTUBE_FETCH_INTERVAL = 1

class Twitch:
    re_prog = None
    sock = None
    partial = b''
    login_ok = False
    channel = ''
    login_timestamp = 0

    def twitch_connect(self, channel):
        if self.sock: self.sock.close()
        self.sock = None
        self.partial = b''
        self.login_ok = False
        self.channel = channel

        # Compile regular expression
        self.re_prog = re.compile(b'^(?::(?:([^ !\r\n]+)![^ \r\n]*|[^ \r\n]*) )?([^ \r\n]+)(?: ([^:\r\n]*))?(?: :([^\r\n]*))?\r\n', re.MULTILINE)

        # Create socket
        print('Connecting to Twitch...')
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Attempt to connect socket
        self.sock.connect(('irc.chat.twitch.tv', 6667))

        # Log in anonymously
        user = 'justinfan%i' % random.randint(10000, 99999)
        print('Connected to Twitch. Logging in anonymously...')
        self.sock.send(('PASS asdf\r\nNICK %s\r\n' % user).encode())

        self.sock.settimeout(1.0/60.0)

        self.login_timestamp = time.time()

    # Attempt to reconnect after a delay
    def reconnect(self, delay):
        time.sleep(delay)
        self.twitch_connect(self.channel)

    # Returns a list of irc messages received
    def receive_and_parse_data(self):
        buffer = b''
        while True:
            received = b''
            try:
                received = self.sock.recv(4096)
            except socket.timeout:
                break
            # except OSError as e:
            #     if e.winerror == 10035:
            #         # This "error" is expected -- we receive it if timeout is set to zero, and there is no data to read on the socket.
            #         break
            except Exception as e:
                print('Unexpected connection error. Reconnecting in a second...', e)
                self.reconnect(1)
                return []
            if not received:
                print('Connection closed by Twitch. Reconnecting in 5 seconds...')
                self.reconnect(5)
                return []
            buffer += received

        if buffer:
            # Prepend unparsed data from previous iterations
            if self.partial:
                buffer = self.partial + buffer
                self.partial = []

            # Parse irc messages
            res = []
            matches = list(self.re_prog.finditer(buffer))
            for match in matches:
                res.append({
                    'name':     (match.group(1) or b'').decode(errors='replace'),
                    'command':  (match.group(2) or b'').decode(errors='replace'),
                    'params':   list(map(lambda p: p.decode(errors='replace'), (match.group(3) or b'').split(b' '))),
                    'trailing': (match.group(4) or b'').decode(errors='replace'),
                })

            # Save any data we couldn't parse for the next iteration
            if not matches:
                self.partial += buffer
            else:
                end = matches[-1].end()
                if end < len(buffer):
                    self.partial = buffer[end:]

                if matches[0].start() != 0:
                    # If we get here, we might have missed a message. pepeW
                    print('either ddarknut fucked up or twitch is bonkers, or both I mean who really knows anything at this point')

            return res

        return []

    def twitch_receive_messages(self):
        privmsgs = []
        for irc_message in self.receive_and_parse_data():
            cmd = irc_message['command']
            if cmd == 'PRIVMSG':
                privmsgs.append({
                    'username': irc_message['name'],
                    'message': irc_message['trailing'],
                })
            elif cmd == 'PING':
                self.sock.send(b'PONG :tmi.twitch.tv\r\n')
            elif cmd == '001':
                print('Successfully logged in. Joining channel %s.' % self.channel)
                self.sock.send(('JOIN #%s\r\n' % self.channel).encode())
                self.login_ok = True
            elif cmd == 'JOIN':
                print('Successfully joined channel %s' % irc_message['params'][0])
            elif cmd == 'NOTICE':
                print('Server notice:', irc_message['params'], irc_message['trailing'])
            elif cmd == '002': continue
            elif cmd == '003': continue
            elif cmd == '004': continue
            elif cmd == '375': continue
            elif cmd == '372': continue
            elif cmd == '376': continue
            elif cmd == '353': continue
            elif cmd == '366': continue
            else:
                print('Unhandled irc message:', irc_message)

        if not self.login_ok:
            # We are still waiting for the initial login message. If we've waited longer than we should, try to reconnect.
            if time.time() - self.login_timestamp > MAX_TIME_TO_WAIT_FOR_LOGIN:
                print('No response from Twitch. Reconnecting...')
                self.reconnect(0)
                return []

        return privmsgs

# Thanks to Ottomated for helping with the yt side of things!
class YouTube:
    session = None
    config = {}
    payload = {}

    thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fetch_job = None
    next_fetch_time = 0

    re_initial_data = re.compile('(?:window\\s*\\[\\s*[\\"\']ytInitialData[\\"\']\\s*\\]|ytInitialData)\\s*=\\s*({.+?})\\s*;')
    re_config = re.compile('(?:ytcfg\\s*.set)\\(({.+?})\\)\\s*;')

    def get_continuation_token(self, data):
        cont = data['continuationContents']['liveChatContinuation']['continuations'][0]
        if 'timedContinuationData' in cont:
            return cont['timedContinuationData']['continuation']
        else:
            return cont['invalidationContinuationData']['continuation']

    def reconnect(self, delay):
        if self.fetch_job and self.fetch_job.running():
            if not fetch_job.cancel():
                print("Waiting for fetch job to finish...")
                self.fetch_job.result()
        print(f"Retrying in {delay}...")
        if self.session: self.session.close()
        self.session = None
        self.config = {}
        self.payload = {}
        self.fetch_job = None
        self.next_fetch_time = 0
        time.sleep(delay)
        self.youtube_connect(self.channel_id, self.stream_url)

    def youtube_connect(self, channel_id, stream_url=None):
        print("Connecting to YouTube...")

        self.channel_id = channel_id
        self.stream_url = stream_url

        # Create http client session
        self.session = requests.Session()
        # Spoof user agent so yt thinks we're an upstanding browser
        self.session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36'
        # Add consent cookie to bypass google's consent page
        requests.utils.add_dict_to_cookiejar(self.session.cookies, {'CONSENT': 'YES+'})

        # Connect using stream_url if provided, otherwise use the channel_id
        if stream_url is not None:
            live_url = self.stream_url
        else:
            live_url = f"https://youtube.com/channel/{self.channel_id}/live"

        res = self.session.get(live_url)
        if res.status_code == 404:
            live_url = f"https://youtube.com/c/{self.channel_id}/live"
            res = self.session.get(live_url)
        if not res.ok:
            if stream_url is not None:
                print(f"Couldn't load the stream URL ({res.status_code} {res.reason}). Is the stream URL correct? {self.stream_url}")
            else:
                print(f"Couldn't load livestream page ({res.status_code} {res.reason}). Is the channel ID correct? {self.channel_id}")
            time.sleep(5)
            exit(1)
        livestream_page = res.text

        # Find initial data in livestream page
        matches = list(self.re_initial_data.finditer(livestream_page))
        if len(matches) == 0:
            print("Couldn't find initial data in livestream page")
            time.sleep(5)
            exit(1)
        initial_data = json.loads(matches[0].group(1))

        # Get continuation token for live chat iframe
        iframe_continuation = None
        try:
            iframe_continuation = initial_data['contents']['twoColumnWatchNextResults']['conversationBar']['liveChatRenderer']['header']['liveChatHeaderRenderer']['viewSelector']['sortFilterSubMenuRenderer']['subMenuItems'][1]['continuation']['reloadContinuationData']['continuation']
        except Exception as e:
            print(f"Couldn't find the livestream chat. Is the channel not live? url: {live_url}")
            time.sleep(5)
            exit(1)

        # Fetch live chat page
        res = self.session.get(f'https://youtube.com/live_chat?continuation={iframe_continuation}')
        if not res.ok:
            print(f"Couldn't load live chat page ({res.status_code} {res.reason})")
            time.sleep(5)
            exit(1)
        live_chat_page = res.text

        # Find initial data in live chat page
        matches = list(self.re_initial_data.finditer(live_chat_page))
        if len(matches) == 0:
            print("Couldn't find initial data in live chat page")
            time.sleep(5)
            exit(1)
        initial_data = json.loads(matches[0].group(1))

        # Find config data
        matches = list(self.re_config.finditer(live_chat_page))
        if len(matches) == 0:
            print("Couldn't find config data in live chat page")
            time.sleep(5)
            exit(1)
        self.config = json.loads(matches[0].group(1))

        # Create payload object for making live chat requests
        token = self.get_continuation_token(initial_data)
        self.payload = {
            "context": self.config['INNERTUBE_CONTEXT'],
            "continuation": token,
            "webClientInfo": {
                "isDocumentHidden": False
            },
        }
        print("Connected.")

    def fetch_messages(self):
        payload_bytes = bytes(json.dumps(self.payload), "utf8")
        res = self.session.post(f"https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?key={self.config['INNERTUBE_API_KEY']}&prettyPrint=false", payload_bytes)
        if not res.ok:
            print(f"Failed to fetch messages. {res.status_code} {res.reason}")
            print("Body:", res.text)
            print("Payload:", payload_bytes)
            self.session.close()
            self.session = None
            return []
        try:
            data = json.loads(res.text)
            self.payload['continuation'] = self.get_continuation_token(data)
            cont = data['continuationContents']['liveChatContinuation']
            messages = []
            if 'actions' in cont:
                for action in cont['actions']:
                    if 'addChatItemAction' in action:
                        if 'item' in action['addChatItemAction']:
                            if 'liveChatTextMessageRenderer' in action['addChatItemAction']['item']:
                                item = action['addChatItemAction']['item']['liveChatTextMessageRenderer']
                                messages.append({
                                    'author': item['authorName']['simpleText'],
                                    'content': item['message']['runs']
                                })
            return messages
        except Exception as e:
            print(f"Failed to parse messages.")
            print("Body:", res.text)
            traceback.print_exc()
        return []

    def twitch_receive_messages(self):
        if self.session == None:
            self.reconnect(0)
        messages = []
        if not self.fetch_job:
            time.sleep(1.0/60.0)
            if time.time() > self.next_fetch_time:
                self.fetch_job = self.thread_pool.submit(self.fetch_messages)
        else:
            res = []
            timed_out = False
            try:
                res = self.fetch_job.result(1.0/60.0)
            except concurrent.futures.TimeoutError:
                timed_out = True
            except Exception:
                traceback.print_exc()
                self.session.close()
                self.session = None
                return
            if not timed_out:
                self.fetch_job = None
                self.next_fetch_time = time.time() + YOUTUBE_FETCH_INTERVAL
            for item in res:
                msg = {
                    'username': item['author'],
                    'message': ''
                }
                for part in item['content']:
                    if 'text' in part:
                        msg['message'] += part['text']
                    elif 'emoji' in part:
                        msg['message'] += part['emoji']['emojiId']
                messages.append(msg)
        return messages




class Kick:
    """Kick chat client using the official Kick API (Oct 2025) via KickApi package.
    Keeps the same public surface used by the template: kick_connect(), twitch_receive_messages(), reconnect().
    """
    def __init__(self):
        self.channel_name = ''
        self.channel_id = None
        self.messages = []
        self._lock = threading.Lock()
        self._connected = False
        self._kick_api = None
        self._last_message_time = None
        self._running = False
        self._chat_thread = None
        # Track seen message IDs to prevent duplicates across polls
        try:
            from collections import deque
            self._seen_ids = set()
            self._seen_order = deque(maxlen=2000)
        except Exception:
            self._seen_ids = set()
            self._seen_order = []  # fallback without maxlen
        try:
            self.debug = str(os.environ.get('KICK_DEBUG', '')).strip().lower() in ('1', 'true', 'yes', 'on')
        except Exception:
            self.debug = False
        # Poll interval (seconds) for Kick chat; lower for faster response
        try:
            self._poll_interval = float(os.environ.get('KICK_POLL_INTERVAL_SECONDS', '0.25'))
            if self._poll_interval < 0.05:
                self._poll_interval = 0.05
        except Exception:
            self._poll_interval = 0.25

    def kick_connect(self, channel, pusher_key=None, pusher_cluster=None, auth_endpoint=None, cookies=None, csrf_token=None):
        """Connect using KickAPI (official) and start polling thread."""
        self.channel_name = channel
        try:
            try:
                from kickapi import KickAPI
                print("✓ Using KickAPI for Kick connection...")
            except Exception:
                print("❌ KickAPI not found. Install with: pip install KickApi")
                return

            # Initialize API client
            self._kick_api = KickAPI()
            print(f"Connecting to Kick channel: {self.channel_name}")

            # Fetch channel information
            channel_info = self._kick_api.channel(self.channel_name)
            if not channel_info:
                print(f"❌ Channel '{self.channel_name}' not found")
                return

            # Derive channel_id and name safely
            self.channel_id = getattr(channel_info, 'id', None)
            channel_username = None
            try:
                user_obj = getattr(channel_info, 'user', None)
                channel_username = getattr(user_obj, 'username', None)
            except Exception:
                channel_username = self.channel_name

            if not self.channel_id:
                print("❌ Could not resolve Kick channel ID")
                return

            print(f"✓ Connected to Kick channel: {channel_username or self.channel_name} (ID: {self.channel_id})")

            # Start from NOW to mimic Twitch behavior (only new messages)
            from datetime import datetime, timedelta
            self._last_message_time = datetime.utcnow()
            # Startup grace: ignore any messages for a short window to avoid initial backlog
            self._startup_grace_end = self._last_message_time + timedelta(seconds=int(os.environ.get("KICK_STARTUP_GRACE_SECONDS", "1")))

            # Start polling thread
            self._running = True
            self._connected = True
            self._chat_thread = threading.Thread(target=self._chat_polling_loop, daemon=True)
            self._chat_thread.start()
            print("✓ Kick chat monitoring started")
        except Exception as e:
            print(f"❌ Error connecting to Kick: {e}")
            if self.debug:
                traceback.print_exc()

    def _chat_polling_loop(self):
        from datetime import datetime, timedelta
        
        def _serialize(obj, depth=0, max_depth=4):
            try:
                if depth > max_depth:
                    return f"<max_depth_reached:{type(obj).__name__}>"
                if obj is None or isinstance(obj, (str, int, float, bool)):
                    return obj
                if isinstance(obj, (list, tuple, set)):
                    return [_serialize(x, depth+1, max_depth) for x in list(obj)]
                if isinstance(obj, dict):
                    return {str(k): _serialize(v, depth+1, max_depth) for k, v in obj.items()}
                # Try vars/__dict__ for KickApi models
                d = {}
                for k, v in vars(obj).items():
                    if k.startswith('_'):
                        continue
                    d[k] = _serialize(v, depth+1, max_depth)
                if d:
                    return d
                return repr(obj)
            except Exception:
                return repr(obj)
        
        while self._running:
            try:
                if not self._kick_api or not self.channel_id:
                    time.sleep(1)
                    continue

                current_time = datetime.utcnow()
                if self.debug:
                    print(f"[KICK DEBUG] Fetching chat since datetime object: {self._last_message_time}")

                chat_data = None
                try:
                    # Pass datetime object directly as required by KickAPI, but make it exclusive with a small epsilon
                    eps_ms = 0
                    try:
                        eps_ms = int(os.environ.get('KICK_SINCE_EPS_MS', '500'))
                    except Exception:
                        eps_ms = 500
                    since_dt = self._last_message_time
                    if since_dt is not None and eps_ms > 0:
                        try:
                            since_dt = since_dt + timedelta(milliseconds=eps_ms)
                        except Exception:
                            pass
                    # Use since_dt (possibly bumped) for fetching
                    chat_data = self._kick_api.chat(self.channel_id, since_dt or self._last_message_time)

                    if self.debug:
                        print(f"[KICK DEBUG] Chat API response type: {type(chat_data)}")
                        if hasattr(chat_data, '__dict__'):
                            try:
                                print(f"[KICK DEBUG] Chat API attributes: {list(vars(chat_data).keys())}")
                            except Exception:
                                pass
                        # Full JSON-like dump (truncated)
                        try:
                            dump = _serialize(chat_data)
                            s = json.dumps(dump, ensure_ascii=False)
                            if len(s) > 8000:
                                s = s[:8000] + '... [truncated]'
                            print("[KICK DEBUG] RAW chat_data JSON:", s)
                        except Exception as _e:
                            print(f"[KICK DEBUG] Could not JSON-dump chat_data: {_e}")
                except Exception as e:
                    if self.debug:
                        print(f"[KICK DEBUG] API chat fetch error: {e}")
                    time.sleep(3)
                    continue

                if chat_data is not None:
                    # Try multiple ways to get messages
                    iterable = None

                    # Method 1: chat_data.messages
                    if hasattr(chat_data, 'messages'):
                        iterable = chat_data.messages
                        if self.debug:
                            try:
                                print(f"[KICK DEBUG] Found .messages attribute with {len(iterable) if iterable is not None else 0} items")
                            except Exception:
                                print("[KICK DEBUG] Found .messages attribute")

                    # Method 2: chat_data.data or chat_data.data.messages
                    elif hasattr(chat_data, 'data'):
                        data_obj = chat_data.data
                        if hasattr(data_obj, 'messages'):
                            iterable = data_obj.messages
                            if self.debug:
                                try:
                                    print(f"[KICK DEBUG] Found .data.messages with {len(iterable) if iterable is not None else 0} items")
                                except Exception:
                                    print("[KICK DEBUG] Found .data.messages")
                        elif isinstance(data_obj, (list, tuple)):
                            iterable = data_obj
                            if self.debug:
                                print(f"[KICK DEBUG] Using .data as list with {len(iterable)} items")

                    # Method 3: Direct list/tuple
                    elif isinstance(chat_data, (list, tuple)):
                        iterable = chat_data
                        if self.debug:
                            print(f"[KICK DEBUG] Using chat_data as list with {len(iterable)} items")

                    # Method 4: Try common field names
                    else:
                        for field_name in ['items', 'results', 'chat_messages', 'entries']:
                            if hasattr(chat_data, field_name):
                                iterable = getattr(chat_data, field_name)
                                if self.debug:
                                    try:
                                        print(f"[KICK DEBUG] Found .{field_name} with {len(iterable) if iterable is not None else 0} items")
                                    except Exception:
                                        print(f"[KICK DEBUG] Found .{field_name}")
                                break

                    if iterable:
                        # Collect parsed messages plus IDs/timestamps for de-duplication
                        parsed_msgs = []  # list of tuples: (msg_dict, msg_id_or_sig, msg_ts_or_None)
                        # Print first 5 raw messages as JSON
                        if self.debug:
                            try:
                                preview = [_serialize(m) for m in list(iterable)[:5]]
                                print("[KICK DEBUG] RAW first messages:", json.dumps(preview, ensure_ascii=False))
                            except Exception as _e:
                                print(f"[KICK DEBUG] Could not dump first messages: {_e}")
                        for i, msg in enumerate(iterable):
                            try:
                                if self.debug and i == 0:
                                    print(f"[KICK DEBUG] First message object type: {type(msg)}")
                                    if hasattr(msg, '__dict__'):
                                        try:
                                            print(f"[KICK DEBUG] First message attributes: {list(vars(msg).keys())}")
                                        except Exception:
                                            pass

                                # Try to get username
                                username = None
                                for user_field in ['sender', 'user', 'author', 'from']:
                                    user_obj = getattr(msg, user_field, None)
                                    if user_obj:
                                        for name_field in ['username', 'name', 'display_name', 'login']:
                                            username = getattr(user_obj, name_field, None)
                                            if username:
                                                break
                                        if username:
                                            break

                                # Fallback: username might be directly on message
                                if not username:
                                    for name_field in ['username', 'user_name', 'author_name', 'sender_name']:
                                        username = getattr(msg, name_field, None)
                                        if username:
                                            break

                                # Try to get message text
                                text = None
                                for text_field in ['text', 'content', 'message', 'body', 'msg']:
                                    text = getattr(msg, text_field, None)
                                    if text is not None:
                                        break

                                # Extract message id (best-effort)
                                msg_id = None
                                for id_field in ['id', 'message_id', 'uuid', 'sid']:
                                    msg_id = getattr(msg, id_field, None)
                                    if msg_id:
                                        break

                                # Extract timestamp (best-effort)
                                msg_ts_raw = None
                                for ts_field in ['created_at', 'timestamp', 'sent_at', 'time', 'date']:
                                    msg_ts_raw = getattr(msg, ts_field, None)
                                    if msg_ts_raw is not None:
                                        break
                                msg_ts = None
                                # Normalize timestamp to datetime if possible
                                try:
                                    from datetime import datetime
                                    if isinstance(msg_ts_raw, (int, float)):
                                        msg_ts = datetime.utcfromtimestamp(msg_ts_raw)
                                    elif isinstance(msg_ts_raw, str):
                                        try:
                                            # Try ISO 8601
                                            msg_ts = datetime.fromisoformat(msg_ts_raw.replace('Z', '+00:00')).replace(tzinfo=None)
                                        except Exception:
                                            msg_ts = None
                                    else:
                                        msg_ts = None
                                except Exception:
                                    msg_ts = None

                                if username and (text is not None):
                                    # Use raw timestamp string in signature when available to distinguish repeated votes
                                    sig_hint = msg_ts_raw if isinstance(msg_ts_raw, str) else (str(msg_ts_raw) if msg_ts_raw is not None else None)
                                    parsed_msgs.append(({'username': username, 'message': text, '_sig_ts': sig_hint}, msg_id, msg_ts))
                                    if self.debug:
                                        print(f"[KICK DEBUG] ✓ Parsed message: {username}: {text} | id={msg_id} ts={msg_ts_raw}")
                                else:
                                    if self.debug:
                                        print(f"[KICK DEBUG] ✗ Incomplete message - username: {username}, text: {text}")

                            except Exception as e:
                                if self.debug:
                                    print(f"[KICK DEBUG] Error processing message {i}: {e}")
                                continue

                        # De-duplicate against seen IDs; remember IDs during grace
                        in_grace = hasattr(self, "_startup_grace_end") and (current_time < self._startup_grace_end)

                        # Helper to remember a signature with bounded memory
                        def _remember(sig):
                            try:
                                self._seen_ids.add(sig)
                                if hasattr(self, '_seen_order') and self._seen_order is not None:
                                    # If deque with maxlen, append auto-evicts; if list fallback, manual cap
                                    try:
                                        self._seen_order.append(sig)
                                    except Exception:
                                        # list fallback
                                        self._seen_order.append(sig)
                                        if len(self._seen_order) > 2000:
                                            old = self._seen_order.pop(0)
                                            try:
                                                self._seen_ids.discard(old)
                                            except Exception:
                                                pass
                            except Exception:
                                pass

                        filtered_msgs = []
                        latest_ts = self._last_message_time
                        for m_dict, m_id, m_ts in parsed_msgs:
                            ts_part = m_dict.get('_sig_ts') if isinstance(m_dict, dict) else None
                            sig = m_id if m_id else (f"{m_dict['username']}|{m_dict['message']}|{ts_part}" if ts_part else f"{m_dict['username']}|{m_dict['message']}")
                            if sig in getattr(self, '_seen_ids', set()):
                                continue
                            if in_grace:
                                _remember(sig)
                                # Do not enqueue during grace
                                continue
                            # Mark as seen and enqueue
                            _remember(sig)
                            filtered_msgs.append(m_dict)
                            if m_ts is not None:
                                try:
                                    if latest_ts is None or m_ts > latest_ts:
                                        latest_ts = m_ts
                                except Exception:
                                    pass

                        if filtered_msgs:
                            with self._lock:
                                self.messages.extend(filtered_msgs)
                            if self.debug:
                                print(f"[KICK DEBUG] Added {len(filtered_msgs)} new messages to queue (after de-dup)")
                        elif self.debug:
                            if in_grace:
                                print("[KICK DEBUG] Startup grace active; remembered IDs, enqueued 0")
                            else:
                                print("[KICK DEBUG] No new messages found in this poll (after de-dup)")

                        # Advance cursor to the latest seen timestamp to avoid overlaps
                        try:
                            if latest_ts is not None:
                                self._last_message_time = latest_ts
                        except Exception:
                            pass
                    else:
                        if self.debug:
                            print("[KICK DEBUG] No message iterable found in chat_data")
                        # Fallback: widen window to last 5 minutes using datetime object
                        try:
                            if self.debug:
                                print("[KICK DEBUG] Fallback: retrying chat fetch with 5-minute window...")
                            alt_since_dt = current_time - timedelta(minutes=5)
                            alt_data = self._kick_api.chat(self.channel_id, alt_since_dt)
                            alt_iter = getattr(alt_data, 'messages', None)
                            if self.debug:
                                try:
                                    dump_alt = _serialize(alt_data)
                                    s2 = json.dumps(dump_alt, ensure_ascii=False)
                                    if len(s2) > 8000:
                                        s2 = s2[:8000] + '... [truncated]'
                                    print("[KICK DEBUG] RAW alt chat_data JSON:", s2)
                                except Exception:
                                    pass
                            if alt_iter and len(alt_iter) > 0:
                                if self.debug:
                                    print(f"[KICK DEBUG] Fallback returned {len(alt_iter)} messages; attempting to parse first few...")
                                fallback_msgs = []
                                for j, m in enumerate(alt_iter[:5]):
                                    try:
                                        u = None
                                        for uf in ['sender', 'user', 'author', 'from']:
                                            uo = getattr(m, uf, None)
                                            if uo:
                                                for nf in ['username', 'name', 'display_name', 'login']:
                                                    u = getattr(uo, nf, None)
                                                    if u:
                                                        break
                                            if u:
                                                break
                                        txt = None
                                        for tf in ['text', 'content', 'message', 'body', 'msg']:
                                            txt = getattr(m, tf, None)
                                            if txt is not None:
                                                break
                                        if u and (txt is not None):
                                            fallback_msgs.append({'username': u, 'message': txt})
                                    except Exception:
                                        continue
                                if fallback_msgs:
                                    with self._lock:
                                        self.messages.extend(fallback_msgs)
                                    if self.debug:
                                        print(f"[KICK DEBUG] Fallback added {len(fallback_msgs)} messages to queue")
                        except Exception as _e:
                            if self.debug:
                                print(f"[KICK DEBUG] Fallback fetch error: {_e}")

                # Ensure cursor moves forward; keep the furthest point (apply epsilon to avoid inclusive repeats)
                try:
                    from datetime import timedelta as _td
                    eps_ms2 = 0
                    try:
                        eps_ms2 = int(os.environ.get('KICK_SINCE_EPS_MS', '500'))
                    except Exception:
                        eps_ms2 = 500
                    if 'latest_ts' in locals() and latest_ts:
                        if self._last_message_time is None or latest_ts > self._last_message_time:
                            self._last_message_time = latest_ts
                    else:
                        # No latest_ts parsed; nudge cursor forward a tiny bit to prevent stalling on inclusive boundaries
                        if self._last_message_time is None or current_time > self._last_message_time:
                            self._last_message_time = current_time
                        try:
                            if self._last_message_time is not None and eps_ms2 > 0:
                                self._last_message_time = self._last_message_time + _td(milliseconds=eps_ms2)
                        except Exception:
                            pass
                except Exception:
                    self._last_message_time = current_time
                time.sleep(self._poll_interval)
            except Exception as e:
                if self.debug:
                    print(f"[KICK DEBUG] Error in chat polling: {e}")
                    traceback.print_exc()
                time.sleep(5)

    def twitch_receive_messages(self):
        msgs = []
        with self._lock:
            if self.messages:
                msgs = self.messages[:]
                self.messages.clear()
        time.sleep(1.0/60.0)
        return msgs

    def reconnect(self, delay):
        time.sleep(delay)
        self.kick_connect(self.channel_name)

    def disconnect(self):
        self._running = False
        self._connected = False
        if self._chat_thread and self._chat_thread.is_alive():
            try:
                self._chat_thread.join(timeout=2)
            except Exception:
                pass
        print("✓ Kick connection closed")
