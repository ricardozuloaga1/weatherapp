import unittest
from unittest.mock import patch
import requests
from fashn_transport import EncryptedDNSAdapter, HOST

class TransportTests(unittest.TestCase):
    def test_resolution_keeps_original_tls_identity(self):
        adapter=EncryptedDNSAdapter()
        req=requests.Request('GET','https://api.fashn.ai/v1/credits').prepare()
        with patch.object(adapter,'resolve',return_value='104.26.8.124'):
            pool=adapter.get_connection_with_tls_context(req,True)
        self.assertEqual(pool.host,'104.26.8.124')
        self.assertEqual(pool.assert_hostname,HOST)
        self.assertEqual(pool.conn_kw['server_hostname'],HOST)
        self.assertEqual(req.headers['Host'],HOST)
        self.assertEqual(adapter.max_retries.total,0)
    def test_rejects_disabled_tls_or_other_host(self):
        adapter=EncryptedDNSAdapter()
        for url,verify in [('https://api.fashn.ai/v1/credits',False),('https://example.com/',True)]:
            with self.assertRaises(requests.ConnectionError):
                adapter.get_connection_with_tls_context(requests.Request('GET',url).prepare(),verify)
