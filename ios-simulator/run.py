"""Run the local preview with the one existing approved library; never print its cookie."""
import os
import secrets
import sqlite3
from flask import Flask
import subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEVICE = 'CC80F470-D665-41B5-ADA4-C53FD23BC0D0'
# Read-only: launching a simulator must never reset in-flight generation jobs.
database = Path(__file__).resolve().parents[1] / 'instance/avatar-pilot/pilot.sqlite3'
with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as db:
    owners = db.execute('SELECT owner FROM fashn_avatars').fetchall()
    secret = db.execute("SELECT value FROM settings WHERE key='secret'").fetchone()[0]
app = Flask('simulator-session')
app.secret_key = secret
if len(owners) != 1:
    raise SystemExit('Expected one approved local library; choose a profile before launching.')
value = app.session_interface.get_signing_serializer(app).dumps({'owner': owners[0][0], 'csrf': secrets.token_hex(24), '_permanent': True})
env = dict(os.environ, SIMCTL_CHILD_WEATHERAVATAR_SESSION=value)
bundle = str(Path(os.environ.get('TMPDIR', '/tmp')) / 'weatheravatar-simulator/WeatherAvatar.app')
subprocess.run(['xcrun','simctl','install',DEVICE,bundle],check=True)
subprocess.run(['xcrun','simctl','launch','--terminate-running-process',DEVICE,'local.weatheravatar.preview'],env=env,check=True)
