from prometheus_client import Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
import json
import random
import time
import threading
import hvac
import os
import sys
import yaml
import OpenSSL
import ssl, socket
from http.server import HTTPServer, BaseHTTPRequestHandler

from datetime import datetime
from hvac.exceptions import Unauthorized

version = open(os.path.join(os.path.dirname(__file__), 'VERSION')).read().strip()
status = {
    'last_scrape': None,
    'collectors': {}
}


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/metrics'):
            output = generate_latest()
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(output)
        elif self.path == '/version':
            payload = json.dumps({'version': version}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == '/status':
            payload = json.dumps(status).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def load(config_path):
    if not os.path.exists(config_path):
        print('Missing {} file. Please create it.'.format(config_path))
        sys.exit(1)
    else:
        with open(config_path, 'r') as stream:
            try:
                return yaml.load(stream, Loader=yaml.FullLoader)
            except yaml.YAMLError as exc:
                print(exc)
                sys.exit(1)


def collect_certificates_drift():
    config_path = os.environ.get('CONFIG', False)
    if not config_path:
        config_path = sys.argv[1]
    config = load(config_path)
    data = {}

    for name, tls_data in config.get('tls', {}).items():
        data[name] = {}
        data[name]['s'] = -1
        data[name]['d'] = -1
        try:
            expire = lookup_certificate(config, name)
            now = datetime.now()
            drift = expire - now
            data[name]['s'] = int(drift.total_seconds())
            data[name]['d'] = int(drift.days)
        except ConnectionRefusedError:
            pass
        except ssl.SSLCertVerificationError as e:
            print(e)
            pass
        except socket.gaierror:
            pass

    return data


def lookup_certificate(config, name):
    fqdn = config['tls'][name]['fqdn']
    port = config['tls'][name].get('port', 443)
    cert = ssl.get_server_certificate((fqdn, port))
    x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)

    return datetime.strptime(x509.get_notAfter().decode('ascii'), '%Y%m%d%H%M%SZ')


def collect_public_certificates_drift():
    config_path = os.environ.get('CONFIG', False)
    if not config_path:
        config_path = sys.argv[1]
    config = load(config_path)
    data = {}

    for name, tls_data in config.get('tls_le', {}).items():
        data[name] = {}
        data[name]['s'] = -1
        data[name]['d'] = -1
        try:
            expire = (config, name)
            now = datetime.now()
            drift = expire - now
            data[name]['s'] = int(drift.total_seconds())
            data[name]['d'] = int(drift.days)
        except ConnectionRefusedError:
            pass
        except ssl.SSLCertVerificationError as e:
            print(e)
            pass
        except socket.gaierror:
            pass

    return data


def lookup_certificate_sni(config, name):
    fqdn = config['tls'][name]['fqdn']
    port = config['tls'][name].get('port', 443)
    context = ssl.create_default_context()
    conn = socket.create_connection((fqdn, port))
    sock = context.wrap_socket(conn, server_hostname=fqdn)
    sock.settimeout(10)
    try:
        der_cert = sock.getpeercert(True)
    finally:
        sock.close()
    certificate = ssl.DER_cert_to_PEM_cert(der_cert)
    x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, certificate)

    return datetime.strptime(x509.get_notAfter().decode('ascii'), '%Y%m%d%H%M%SZ')


def collect_token_drift():
    config_path = os.environ.get('CONFIG', False)
    if not config_path:
        config_path = sys.argv[1]
    config = load(config_path)
    data = {}

    for name, token in config.get('tokens', {}).items():
        data[name] = {}
        data[name]['s'] = -1
        data[name]['d'] = -1
        try:
            expire_datetime = lookup_token(config, token)['data']['expire_time']
            expire = datetime.strptime(expire_datetime[0:19], '%Y-%m-%dT%H:%M:%S')
            now = datetime.now()
            drift = expire - now
            data[name]['s'] = int(drift.total_seconds())
            data[name]['d'] = int(drift.days)
        except hvac.exceptions.Unauthorized:
            pass

    return data


def lookup_token(config, token):
    client = hvac.Client(
        url=config['vault']['server'],
        token=token,
        verify=config['vault']['verify'],
    )
    if client.is_authenticated():
        return client.lookup_token()
    else:
        raise Unauthorized("May be expired token")


def collect_accessor_drift():
    config_path = os.environ.get('CONFIG', False)
    if not config_path:
        config_path = sys.argv[1]
    config = load(config_path)
    data = {}

    for name, accessor in config.get('accessors', {}).items():
        data[name] = {}
        data[name]['s'] = -1
        data[name]['d'] = -1
        try:
            expire_datetime = lookup_accessor(config, accessor)['data']['expire_time']
            expire = datetime.strptime(expire_datetime[0:19], '%Y-%m-%dT%H:%M:%S')
            now = datetime.now()
            drift = expire - now
            data[name]['s'] = int(drift.total_seconds())
            data[name]['d'] = int(drift.days)
        except (hvac.exceptions.Unauthorized, hvac.exceptions.Forbidden, hvac.exceptions.InvalidPath) as e:
            print(f'accessor {name}: {e}', file=sys.stderr)

    return data


def lookup_accessor(config, accessor):
    client = hvac.Client(
        url=config['vault']['server'],
        token=os.environ.get('VAULT_TOKEN'),
        verify=config['vault']['verify'],
    )
    return client.auth.token.lookup_accessor(accessor)


def init_metrics(metrics):
    metrics['gts'] = Gauge('token_drift_seconds',
                          'Seconds remind before token expiration',
                          ['token'])
    metrics['gtd'] = Gauge('token_drift_days',
                          'Days remind before token expiration',
                          ['token'])
    metrics['gcs'] = Gauge('certificate_drift_seconds',
                           'Seconds remind before certificate expiration',
                           ['certificate'])
    metrics['gcd'] = Gauge('certificate_drift_days',
                           'Days remind before certificate expiration',
                           ['certificate'])
    metrics['gps'] = Gauge('public_certificate_drift_seconds',
                           'Seconds remind before public certificate expiration',
                           ['public_certificate'])
    metrics['gpd'] = Gauge('public_certificate_drift_days',
                           'Days remind before public certificate expiration',
                           ['public_certificate'])


def update_metrics(metrics, tokens_data, accessors_data, certificates_data, public_certificates_data):
    for name, values in {**tokens_data, **accessors_data}.items():
        metrics['gts'].labels(name).set(values['s'])
        metrics['gtd'].labels(name).set(values['d'])

    for name, values in certificates_data.items():
        metrics['gcs'].labels(name).set(values['s'])
        metrics['gcd'].labels(name).set(values['d'])

    for name, values in public_certificates_data.items():
        metrics['gps'].labels(name).set(values['s'])
        metrics['gpd'].labels(name).set(values['d'])


def update_status(status, tokens_data, accessors_data, certificates_data, public_certificates_data):
    status['last_scrape'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    status['collectors'] = {
        'tokens': {name: 'error' if v['s'] == -1 else 'ok' for name, v in tokens_data.items()},
        'accessors': {name: 'error' if v['s'] == -1 else 'ok' for name, v in accessors_data.items()},
        'certificates': {name: 'error' if v['s'] == -1 else 'ok' for name, v in certificates_data.items()},
        'public_certificates': {name: 'error' if v['s'] == -1 else 'ok' for name, v in public_certificates_data.items()},
    }


def log_errors(status):
    errors = []
    for collector, items in status.get('collectors', {}).items():
        for name, state in items.items():
            if state == 'error':
                errors.append(f'{collector}/{name}')
    if errors:
        print(f'[{datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}] collectors in error: {", ".join(errors)}', file=sys.stderr)


if __name__ == '__main__':
    scrape_interval = int(os.environ.get('INTERVAL', 300))
    metrics = {}
    init_metrics(metrics)
    port = int(os.environ.get('PORT', 8000))

    info = Info('drift_prom_exporter', 'Drift Prometheus Exporter build info')
    info.info({'version': version})

    print(f'drift_prom_exporter v{version}')

    pid_filename = os.environ.get('PID_FILENAME')
    if pid_filename:
        with open(pid_filename, 'w') as f:
            f.write(str(os.getpid()))

    server = HTTPServer(('', port), MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    while True:
        tokens_data = collect_token_drift()
        accessors_data = collect_accessor_drift()
        certificates_data = collect_certificates_drift()
        public_certificates_data = collect_public_certificates_drift()
        update_metrics(metrics, tokens_data, accessors_data, certificates_data, public_certificates_data)
        update_status(status, tokens_data, accessors_data, certificates_data, public_certificates_data)
        log_errors(status)
        elapsed = 0
        while elapsed < scrape_interval:
            time.sleep(60)
            elapsed += 60
            if elapsed < scrape_interval:
                log_errors(status)
