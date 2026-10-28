"""Start the local app and open its simple home screen; no financial data leaves it."""
from pathlib import Path
import json
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError
import webbrowser
from dashboard.identity import application_identity

ROOT = Path(__file__).resolve().parent
DATA_DIRECTORY = ROOT / 'local_scenarios'
URL = 'http://127.0.0.1:8765/'


def running():
    try:
        identity_url = URL + 'app-identity'
        with urlopen(identity_url, timeout=1) as response:
            if response.status != 200 or response.geturl() != identity_url:
                return False
            if response.headers.get_content_type() != 'application/json':
                return False
            raw = response.read(1025)
            return len(raw) <= 1024 and json.loads(raw) == application_identity(ROOT, DATA_DIRECTORY)
    except (URLError, TimeoutError, OSError, ValueError):
        return False


def main():
    if not running():
        with (ROOT / 'app-start.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, '-m', 'dashboard.server', '--port', '8765',
                '--data-dir', str(DATA_DIRECTORY.resolve())], cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=log, stderr=log, start_new_session=True)
        for _ in range(40):
            if running():
                break
            if process.poll() is not None:
                raise SystemExit('Could not verify this Debt Shredder instance. Check app-start.log; port 8765 may belong to another application or a different data directory. No records were opened.')
            time.sleep(.25)
        else:
            raise SystemExit('The app is taking longer to start. Try opening '+URL)
    webbrowser.open(URL)
    print('Debt Shredder is running at '+URL)
    print('You can close this launcher window. The app continues running on this Mac.')


if __name__ == '__main__':
    main()
