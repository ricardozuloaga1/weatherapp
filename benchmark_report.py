"""Serve private benchmark artifacts only to the owner of their source avatar."""
import json
from pathlib import Path
from flask import abort,session,send_file

def register_benchmark_report(app,jobs):
    app.config.setdefault('BENCHMARK_DIR',str(Path(__file__).parent/'instance/avatar-pilot/benchmark-six'))
    @app.get('/benchmark/')
    @app.get('/benchmark/<filename>')
    def benchmark_report(filename='report.html'):
        root=Path(app.config['BENCHMARK_DIR']).resolve()
        try:avatar=json.loads((root/'manifest.json').read_text())['avatar']
        except (OSError,KeyError,ValueError):abort(404)
        if not any(j['id']==avatar and j['kind']=='base' for j in jobs.public_jobs(session['owner'])):abort(404)
        path=(root/filename).resolve()
        if path.parent!=root or path.suffix not in {'.html','.css','.jpg','.png'} or not path.is_file():abort(404)
        return send_file(path)
