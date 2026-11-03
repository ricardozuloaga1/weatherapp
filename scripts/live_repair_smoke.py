"""Resume the benchmark's failed rain candidate through the production review/repair worker."""
import sys,json,sqlite3,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fashn import FashnJobs
p=Path('instance/avatar-pilot/benchmark-six')
db=sqlite3.connect('instance/avatar-pilot/pilot.sqlite3',check_same_thread=False)
jobs=FashnJobs(db,threading.RLock(),autostart=False,user_limit=100,global_limit=100)
base=json.loads((p/'manifest.json').read_text())['avatar']
owner=db.execute('SELECT owner FROM fashn_jobs WHERE id=?',(base,)).fetchone()[0]
jid,reused=jobs.enqueue(owner,jobs.image(owner,base),'outfit','warmrain',base,'Transfer the complete reference outfit.',product=(p/'warmrain-reference.png').read_bytes(),full_outfit=True)
if not reused:
    m=json.loads(db.execute('SELECT metadata FROM fashn_jobs WHERE id=?',(jid,)).fetchone()[0])
    m.update(quality_state='checking',provenance='live-benchmark-repair',billing_note='First pass reused from benchmark; only new repairs charged here.')
    with db:db.execute("UPDATE fashn_jobs SET status='reviewing',charge=0,image=?,metadata=? WHERE id=?",((p/'warmrain-max.png').read_bytes(),json.dumps(m),jid))
last=None
for _ in range(150):
    jobs.tick()
    j=next(j for j in jobs.public_jobs(owner) if j['id']==jid)
    snapshot={k:j.get(k) for k in ('id','status','quality_state','repair_count','credits_reserved_or_used','accepted','quality_note')}
    if snapshot!=last:print(json.dumps(snapshot),flush=True);last=snapshot
    if j['status'] in ('done','failed','unknown','unavailable'):
        (p/'live-pipeline-result.json').write_text(json.dumps(j,indent=2))
        if jobs.image(owner,jid):(p/'live-pipeline-result.png').write_bytes(jobs.image(owner,jid))
        break
    time.sleep(5)
else:raise SystemExit('Still pending; prediction persisted for server polling')
r=jobs.client.http.get('https://api.fashn.ai/v1/credits',headers=jobs.client.headers(),timeout=30)
r.raise_for_status();print('Provider credits',json.dumps(r.json()),flush=True)
