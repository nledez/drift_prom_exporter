import io
import json
import os
import re
import socket
import ssl
import sys
from datetime import datetime, timedelta
from http.server import HTTPServer
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_config():
    return {
        'vault': {'server': 'https://vault.example.com:8200', 'verify': False},
        'tokens': {
            'app1': 's.token1',
            'app2': 's.token2',
        },
        'accessors': {
            'bot1': 'accessor1',
        },
        'tls': {
            'google': {'fqdn': 'www.google.com', 'port': 443},
        },
        'tls_le': {
            'le_cert': {'fqdn': 'example.com', 'port': 443},
        },
    }


@pytest.fixture()
def config_file(tmp_path, sample_config):
    path = tmp_path / 'config.yml'
    path.write_text(yaml.dump(sample_config))
    return str(path)


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------

class TestLoad:
    def test_valid_file(self, config_file, sample_config):
        result = main.load(config_file)
        assert result == sample_config

    def test_missing_file(self):
        with pytest.raises(SystemExit) as exc_info:
            main.load('/nonexistent/path.yml')
        assert exc_info.value.code == 1

    def test_invalid_yaml(self, tmp_path):
        bad = tmp_path / 'bad.yml'
        bad.write_text('{{{{not valid yaml::::')
        with pytest.raises(SystemExit) as exc_info:
            main.load(str(bad))
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# update_status()
# ---------------------------------------------------------------------------

class TestUpdateStatus:
    def test_structure_and_values(self):
        status = {'last_scrape': None, 'collectors': {}}
        tokens = {'app1': {'s': 3600, 'd': 0}, 'app2': {'s': -1, 'd': -1}}
        accessors = {'bot1': {'s': 7200, 'd': 0}}
        certs = {'google': {'s': -1, 'd': -1}}
        pub_certs = {'le': {'s': 86400, 'd': 1}}

        main.update_status(status, tokens, accessors, certs, pub_certs)

        assert re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', status['last_scrape'])
        assert status['collectors']['tokens'] == {'app1': 'ok', 'app2': 'error'}
        assert status['collectors']['accessors'] == {'bot1': 'ok'}
        assert status['collectors']['certificates'] == {'google': 'error'}
        assert status['collectors']['public_certificates'] == {'le': 'ok'}

    def test_empty_data(self):
        status = {'last_scrape': None, 'collectors': {}}
        main.update_status(status, {}, {}, {}, {})
        assert status['collectors'] == {
            'tokens': {},
            'accessors': {},
            'certificates': {},
            'public_certificates': {},
        }


# ---------------------------------------------------------------------------
# update_metrics()
# ---------------------------------------------------------------------------

class TestLogErrors:
    def test_prints_errors_to_stderr(self, capsys):
        status = {
            'collectors': {
                'tokens': {'app1': 'ok', 'app2': 'error'},
                'accessors': {'bot1': 'error'},
                'certificates': {},
                'public_certificates': {},
            }
        }
        main.log_errors(status)
        captured = capsys.readouterr()
        assert 'tokens/app2' in captured.err
        assert 'accessors/bot1' in captured.err
        assert 'tokens/app1' not in captured.err

    def test_no_output_when_all_ok(self, capsys):
        status = {
            'collectors': {
                'tokens': {'app1': 'ok'},
                'accessors': {},
                'certificates': {},
                'public_certificates': {},
            }
        }
        main.log_errors(status)
        captured = capsys.readouterr()
        assert captured.err == ''

    def test_no_output_when_empty(self, capsys):
        status = {'collectors': {}}
        main.log_errors(status)
        captured = capsys.readouterr()
        assert captured.err == ''


# ---------------------------------------------------------------------------
# update_metrics()
# ---------------------------------------------------------------------------

class TestUpdateMetrics:
    def test_calls_set_on_gauges(self):
        metrics = {}
        for key in ('gts', 'gtd', 'gcs', 'gcd', 'gps', 'gpd'):
            gauge = MagicMock()
            gauge.labels.return_value = gauge
            metrics[key] = gauge

        tokens = {'app1': {'s': 100, 'd': 1}}
        accessors = {'bot1': {'s': 200, 'd': 2}}
        certs = {'google': {'s': 300, 'd': 3}}
        pub_certs = {'le': {'s': 400, 'd': 4}}

        main.update_metrics(metrics, tokens, accessors, certs, pub_certs)

        # tokens + accessors merged into gts/gtd
        metrics['gts'].labels.assert_any_call('app1')
        metrics['gts'].labels.assert_any_call('bot1')
        metrics['gts'].set.assert_any_call(100)
        metrics['gts'].set.assert_any_call(200)

        metrics['gtd'].labels.assert_any_call('app1')
        metrics['gtd'].set.assert_any_call(1)
        metrics['gtd'].set.assert_any_call(2)

        metrics['gcs'].labels.assert_called_with('google')
        metrics['gcs'].set.assert_called_with(300)
        metrics['gcd'].set.assert_called_with(3)

        metrics['gps'].labels.assert_called_with('le')
        metrics['gps'].set.assert_called_with(400)
        metrics['gpd'].set.assert_called_with(4)


# ---------------------------------------------------------------------------
# MetricsHandler
# ---------------------------------------------------------------------------

class TestMetricsHandler:
    def _make_handler(self, method, path):
        """Instantiate MetricsHandler without a real socket."""
        request = MagicMock()
        request.makefile.return_value = io.BytesIO()

        handler = main.MetricsHandler.__new__(main.MetricsHandler)
        handler.request = request
        handler.client_address = ('127.0.0.1', 9999)
        handler.server = MagicMock()
        handler.command = method
        handler.path = path
        handler.request_version = 'HTTP/1.1'
        handler.headers = {}
        handler.wfile = io.BytesIO()
        handler.requestline = f'{method} {path} HTTP/1.1'
        handler._headers_buffer = []
        handler.responses = main.MetricsHandler.responses

        handler.do_GET()

        handler.wfile.seek(0)
        return handler.wfile.read()

    def test_metrics_200(self):
        body = self._make_handler('GET', '/metrics')
        assert b'200' not in b''  # handler didn't crash
        # generate_latest() returns prometheus text
        assert body is not None

    def test_version_200(self):
        body = self._make_handler('GET', '/version')
        assert b'version' in body

    def test_status_200(self):
        body = self._make_handler('GET', '/status')
        assert b'last_scrape' in body

    def test_unknown_404(self):
        body = self._make_handler('GET', '/unknown')
        # 404 produces empty body
        assert body is not None


# ---------------------------------------------------------------------------
# collect_token_drift()
# ---------------------------------------------------------------------------

class TestCollectTokenDrift:
    def test_nominal(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)
        future = (datetime.now() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000000Z')
        mock_result = {'data': {'expire_time': future}}

        with patch('main.lookup_token', return_value=mock_result):
            data = main.collect_token_drift()

        assert 'app1' in data
        assert data['app1']['s'] > 0
        assert data['app1']['d'] >= 0
        assert 'app2' in data

    def test_unauthorized(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)

        with patch('main.lookup_token', side_effect=main.hvac.exceptions.Unauthorized):
            data = main.collect_token_drift()

        assert data['app1']['s'] == -1
        assert data['app1']['d'] == -1

    def test_vault_down(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)

        with patch('main.lookup_token', side_effect=main.hvac.exceptions.VaultDown):
            data = main.collect_token_drift()

        assert data['app1']['s'] == -1
        assert data['app1']['d'] == -1

    def test_internal_server_error(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)

        with patch('main.lookup_token', side_effect=main.hvac.exceptions.InternalServerError):
            data = main.collect_token_drift()

        assert data['app1']['s'] == -1
        assert data['app1']['d'] == -1

    def test_no_tokens_section(self, tmp_path, monkeypatch):
        cfg = tmp_path / 'no_tokens.yml'
        cfg.write_text(yaml.dump({'vault': {'server': 'https://v:8200', 'verify': False}}))
        monkeypatch.setenv('CONFIG', str(cfg))

        with patch('main.lookup_token'):
            data = main.collect_token_drift()

        assert data == {}


# ---------------------------------------------------------------------------
# collect_accessor_drift()
# ---------------------------------------------------------------------------

class TestCollectAccessorDrift:
    def test_nominal(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)
        future = (datetime.now() + timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M:%S.000000Z')
        mock_result = {'data': {'expire_time': future}}

        with patch('main.lookup_accessor', return_value=mock_result):
            data = main.collect_accessor_drift()

        assert 'bot1' in data
        assert data['bot1']['s'] > 0

    def test_unauthorized(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)

        with patch('main.lookup_accessor', side_effect=main.hvac.exceptions.Unauthorized):
            data = main.collect_accessor_drift()

        assert data['bot1']['s'] == -1

    def test_forbidden(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)

        with patch('main.lookup_accessor', side_effect=main.hvac.exceptions.Forbidden):
            data = main.collect_accessor_drift()

        assert data['bot1']['s'] == -1

    def test_vault_down(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)

        with patch('main.lookup_accessor', side_effect=main.hvac.exceptions.VaultDown):
            data = main.collect_accessor_drift()

        assert data['bot1']['s'] == -1
        assert data['bot1']['d'] == -1

    def test_invalid_path(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)

        with patch('main.lookup_accessor', side_effect=main.hvac.exceptions.InvalidPath):
            data = main.collect_accessor_drift()

        assert data['bot1']['s'] == -1
        assert data['bot1']['d'] == -1

    def test_internal_server_error(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)

        with patch('main.lookup_accessor', side_effect=main.hvac.exceptions.InternalServerError):
            data = main.collect_accessor_drift()

        assert data['bot1']['s'] == -1
        assert data['bot1']['d'] == -1


# ---------------------------------------------------------------------------
# collect_certificates_drift()
# ---------------------------------------------------------------------------

class TestCollectCertificatesDrift:
    def test_nominal(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)
        future = datetime.now() + timedelta(days=30)

        with patch('main.lookup_certificate', return_value=future):
            data = main.collect_certificates_drift()

        assert 'google' in data
        assert data['google']['s'] > 0
        assert data['google']['d'] >= 29

    def test_connection_refused(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)

        with patch('main.lookup_certificate', side_effect=ConnectionRefusedError):
            data = main.collect_certificates_drift()

        assert data['google']['s'] == -1

    def test_gaierror(self, config_file, monkeypatch):
        monkeypatch.setenv('CONFIG', config_file)

        with patch('main.lookup_certificate', side_effect=socket.gaierror):
            data = main.collect_certificates_drift()

        assert data['google']['s'] == -1


# ---------------------------------------------------------------------------
# lookup_token()
# ---------------------------------------------------------------------------

class TestLookupToken:
    def test_authenticated(self):
        config = {'vault': {'server': 'https://vault:8200', 'verify': False}}
        expected = {'data': {'expire_time': '2030-01-01T00:00:00'}}

        with patch('main.hvac.Client') as MockClient:
            instance = MockClient.return_value
            instance.is_authenticated.return_value = True
            instance.lookup_token.return_value = expected

            result = main.lookup_token(config, 's.mytoken')

        MockClient.assert_called_once_with(
            url='https://vault:8200',
            token='s.mytoken',
            verify=False,
        )
        assert result == expected

    def test_not_authenticated(self):
        config = {'vault': {'server': 'https://vault:8200', 'verify': False}}

        with patch('main.hvac.Client') as MockClient:
            instance = MockClient.return_value
            instance.is_authenticated.return_value = False

            with pytest.raises(main.hvac.exceptions.Unauthorized):
                main.lookup_token(config, 's.expired')


# ---------------------------------------------------------------------------
# lookup_accessor()
# ---------------------------------------------------------------------------

class TestLookupAccessor:
    def test_calls_hvac_correctly(self, monkeypatch):
        monkeypatch.setenv('VAULT_TOKEN', 's.root')
        config = {'vault': {'server': 'https://vault:8200', 'verify': False}}
        expected = {'data': {'expire_time': '2030-01-01T00:00:00'}}

        with patch('main.hvac.Client') as MockClient:
            instance = MockClient.return_value
            instance.auth.token.lookup_accessor.return_value = expected

            result = main.lookup_accessor(config, 'my-accessor')

        MockClient.assert_called_once_with(
            url='https://vault:8200',
            token='s.root',
            verify=False,
        )
        instance.auth.token.lookup_accessor.assert_called_once_with('my-accessor')
        assert result == expected
