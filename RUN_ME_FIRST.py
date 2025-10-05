import os
import sys
import subprocess
import ctypes
import time

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
REQ_FILE = os.path.join(REPO_DIR, 'requirements.txt')
TEMPLATE = os.path.join(REPO_DIR, 'TwitchPlays_TEMPLATE.py')


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def elevate_if_needed():
    if is_admin():
        return False
    try:
        # Relaunch with admin rights
        params = '"' + sys.executable + '" "' + os.path.abspath(__file__) + '" --skip-elevate'
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, '"' + os.path.abspath(__file__) + '" --skip-elevate', None, 1)
        return True
    except Exception:
        return False


def pip_install(args):
    cmd = [sys.executable, '-m', 'pip'] + args
    print('> ' + ' '.join(cmd))
    return subprocess.call(cmd)


def ensure_dependencies():
    print('Installing/Updating dependencies...')
    if os.path.exists(REQ_FILE):
        rc = pip_install(['install', '--upgrade', '-r', REQ_FILE])
        if rc != 0:
            print('Failed installing from requirements.txt, falling back to individual installs...')
    # Fallback explicit list (in case requirements.txt not found)
    packages = [
        'keyboard',
        'pydirectinput',
        'pyautogui',
        'pynput',
        'requests',
        'pusherclient',  # needed for Kick chat
    ]
    pip_install(['install', '--upgrade'] + packages)


def run_template():
    print('\nLaunching TwitchPlays_TEMPLATE.py...')
    print('Tip: Shift+Backspace to exit the program.')
    return subprocess.call([sys.executable, TEMPLATE])


if __name__ == '__main__':
    if '--skip-elevate' not in sys.argv:
        if elevate_if_needed():
            # Parent process exits, elevated child will continue
            sys.exit(0)
        else:
            print('Could not auto-elevate to administrator. Continuing without elevation...')
            print('If your game ignores inputs, try running this script as Administrator.')
    else:
        # slight delay to let console focus after elevation
        time.sleep(0.5)

    ensure_dependencies()
    code = run_template()
    if code != 0:
        print(f'Program exited with code {code}.')
