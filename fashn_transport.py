"""Optional FASHN-only encrypted DNS transport; preserves TLS hostname verification."""
import ipaddress
import json
import subprocess
import time
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter

HOST = 'api.fashn.ai'


class EncryptedDNSAdapter(HTTPAdapter):
    def __init__(self, host=HOST):
        if host not in {HOST, "api.open-meteo.com", "geocoding-api.open-meteo.com", "air-quality-api.open-meteo.com", "api.rainviewer.com", "tilecache.rainviewer.com", "tile.openstreetmap.org"}:
            raise ValueError("Unsupported transport host")
        self.host = host
        super().__init__(max_retries=0)
        self.address = None
        self.expires = 0

    def resolve(self):
        if self.address and time.monotonic() < self.expires:
            return self.address
        # Only the public hostname goes to the resolver, never photos or API credentials.
        result = subprocess.run([
            '/usr/bin/curl', '-fsS', '--connect-timeout', '5', '--max-time', '12',
            '--resolve', 'cloudflare-dns.com:443:1.1.1.1',
            '-H', 'accept: application/dns-json',
            'https://cloudflare-dns.com/dns-query?name='+self.host+'&type=A',
        ], capture_output=True, timeout=15)
        if result.returncode:
            raise requests.ConnectionError('Encrypted FASHN DNS lookup failed.')
        payload = json.loads(result.stdout)
        for record in payload.get('Answer', []):
            if record.get('type') == 1:
                address = ipaddress.ip_address(record['data'])
                if address.version == 4 and address.is_global:
                    self.address = str(address)
                    self.expires = time.monotonic() + max(1, min(300, int(record.get('TTL', 60))))
                    return self.address
        raise requests.ConnectionError('No valid FASHN DNS answer.')

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        if urlsplit(request.url).hostname != self.host or verify is False:
            raise requests.ConnectionError('FASHN transport requires verified HTTPS to the expected host.')
        if any((proxies or {}).values()):
            return super().get_connection_with_tls_context(request, verify, proxies, cert)
        host, settings = self.build_connection_pool_key_attributes(request, verify, cert)
        host['host'] = self.resolve()
        settings.update(server_hostname=self.host, assert_hostname=self.host)
        request.headers['Host'] = self.host
        return self.poolmanager.connection_from_host(**host, pool_kwargs=settings)


def encrypted_session():
    session = requests.Session()
    session.mount('https://api.fashn.ai/', EncryptedDNSAdapter())
    return session
