"""Start the loopback UI and open a browser after it is listening."""
from pathlib import Path
import webbrowser
from dashboard.server import make_server


def main():
    # Pick a free local port: an unrelated or older server must never be trusted.
    directory=Path(__file__).resolve().parent.parent/'local_scenarios'
    server=make_server(directory,0)
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'Debt Shredder is running at {url}',flush=True)
    print('Keep this window open while using the app. Press Control-C to stop.',flush=True)
    webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
