"""Receive a key on stdin and store it using the existing Codex Secrets broker."""
import sys
from datetime import datetime, timezone
sys.path.insert(0, '/Users/ricardozuloaga/Documents/Codex/2026-08-22/i-have-my-apis-listed-in')
import codex_secrets as broker
import getpass
key = getpass.getpass('FASHN key (hidden): ').strip() if sys.stdin.isatty() else sys.stdin.read().strip()
if not key or any(c.isspace() for c in key):
    raise SystemExit('Invalid credential input')
try:
    broker.keychain_store('FASHN_API_KEY', key)
    manifest = broker.load_manifest()
    manifest['secrets']['FASHN_API_KEY'] = {'source': 'FASHN dashboard', 'imported_at': datetime.now(timezone.utc).isoformat()}
    broker.save_manifest(manifest)
except Exception as exc:
    raise SystemExit('Secure storage failed (' + type(exc).__name__ + '); credential not displayed')
print('FASHN_API_KEY saved in Keychain')
