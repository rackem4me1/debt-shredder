"""Start the local app and open its simple home screen; no financial data leaves it."""
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8765/'


def running():
    try:
        with urlopen(URL, timeout=1) as response:
            return response.status == 200 and b'Debt Shredder' in response.read(16384)
    except (URLError, TimeoutError, OSError):
        return False


def main():
    if not running():
        with (ROOT / 'app-start.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, '-m', 'dashboard.server', '--port', '8765',
                '--data-dir', str(ROOT / 'local_scenarios')], cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=log, stderr=log, start_new_session=True)
        for _ in range(40):
            if running():
                break
            if process.poll() is not None:
                raise SystemExit('Could not start Debt Shredder. Check app-start.log; another app may be using port 8765.')
            time.sleep(.25)
        else:
            raise SystemExit('The app is taking longer to start. Try opening '+URL)
    webbrowser.open(URL)
    print('Debt Shredder is running at '+URL)
    print('You can close this launcher window. The app continues running on this Mac.')


if __name__ == '__main__':
    main()
