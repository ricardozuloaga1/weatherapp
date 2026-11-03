"""Run the local preview with the one existing approved library; never print its cookie."""
import os
import secrets
import subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pilot import create_app

DEVICE = 'CC80F470-D665-41B5-ADA4-C53FD23BC0D0'
app = create_app(fashn_autostart=False)
owners = app.extensions['pilot_store'].db.execute('SELECT owner FROM fashn_avatars').fetchall()
if len(owners) != 1:
    raise SystemExit('Expected one approved local library; choose a profile before launching.')
value = app.session_interface.get_signing_serializer(app).dumps({'owner': owners[0][0], 'csrf': secrets.token_hex(24), '_permanent': True})
env = dict(os.environ, SIMCTL_CHILD_WEATHERAVATAR_SESSION=value)
bundle = str(Path(os.environ.get('TMPDIR', '/tmp')) / 'weatheravatar-simulator/WeatherAvatar.app')
subprocess.run(['xcrun','simctl','install',DEVICE,bundle],check=True)
subprocess.run(['xcrun','simctl','launch','--terminate-running-process',DEVICE,'local.weatheravatar.preview'],env=env,check=True)
