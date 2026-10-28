"""A launcher must never open another installation's private data directory."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest

import START_APP as launcher
from dashboard.server import make_server


@contextmanager
def serving(server):
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/'
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.fixture
def instances(tmp_path):
    first, second = tmp_path / 'first-private', tmp_path / 'second-private'
    with serving(make_server(first, 0)) as first_url:
        with serving(make_server(second, 0)) as second_url:
            yield first, second, first_url, second_url


def configure(monkeypatch, directory, url):
    monkeypatch.setattr(launcher, 'DATA_DIRECTORY', directory, raising=False)
    monkeypatch.setattr(launcher, 'URL', url)


def test_only_instance_with_expected_private_directory_is_reused(instances, monkeypatch):
    first, second, first_url, second_url = instances
    configure(monkeypatch, first, first_url)
    assert launcher.running()
    monkeypatch.setattr(launcher, 'URL', second_url)
    assert not launcher.running()
    configure(monkeypatch, second, second_url)
    assert launcher.running()
    monkeypatch.setattr(launcher, 'URL', first_url)
    assert not launcher.running()


def test_same_data_directory_from_different_application_is_not_reused(instances, tmp_path, monkeypatch):
    first, _, first_url, _ = instances
    configure(monkeypatch, first, first_url)
    monkeypatch.setattr(launcher, 'ROOT', tmp_path / 'another-installation')
    assert not launcher.running()


def test_data_identity_uses_resolved_paths(instances, tmp_path, monkeypatch):
    first, _, first_url, _ = instances
    alias = tmp_path / 'alias'
    alias.symlink_to(first, target_is_directory=True)
    configure(monkeypatch, alias, first_url)
    assert launcher.running()


def test_identity_does_not_disclose_private_directory_paths(instances):
    first, second, first_url, second_url = instances
    identities = []
    for url in (first_url, second_url):
        with urlopen(url + 'app-identity', timeout=2) as response:
            raw = response.read().decode()
            assert response.headers['Cache-Control'] == 'no-store'
        identity = json.loads(raw)
        assert set(identity) == {'application', 'identity'}
        assert identity['application'] == 'debt-shredder-local-v1'
        assert len(identity['identity']) == 64
        assert str(first) not in raw and str(second) not in raw
        assert str(Path(launcher.__file__).resolve().parent) not in raw
        identities.append(identity)
    assert identities[0] != identities[1]


def test_unverified_instance_never_opens_browser(instances, tmp_path, monkeypatch):
    first, _, _, second_url = instances
    configure(monkeypatch, first, second_url)
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **k: type('Exited', (), {'poll': lambda self: 1})())
    opened = []
    monkeypatch.setattr(launcher.webbrowser, 'open', opened.append)
    with pytest.raises(SystemExit, match='identity|different|another'):
        launcher.main()
    assert opened == []
    assert not list(first.glob('*.json'))


def test_matching_instance_is_reused_without_starting_process(instances, monkeypatch):
    first, _, first_url, _ = instances
    configure(monkeypatch, first, first_url)
    def unexpected_process(*args, **kwargs):
        pytest.fail('An identity-matched instance should be reused')
    monkeypatch.setattr(launcher.subprocess, 'Popen', unexpected_process)
    opened = []
    monkeypatch.setattr(launcher.webbrowser, 'open', opened.append)
    launcher.main()
    assert opened == [first_url]


def test_title_only_legacy_service_is_not_an_identity(monkeypatch, tmp_path):
    class Legacy(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'<h1>Debt Shredder</h1>')
        def log_message(self, *args):
            pass
    with serving(ThreadingHTTPServer(('127.0.0.1', 0), Legacy)) as url:
        configure(monkeypatch, tmp_path, url)
        assert not launcher.running()
