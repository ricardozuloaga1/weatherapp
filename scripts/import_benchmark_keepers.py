"""Import only manually passed benchmark outputs, once; preserve all existing jobs/profiles."""
import hashlib,json,sqlite3,threading,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fashn import FashnJobs,OUTFIT_VERSION
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'instance/avatar-pilot/benchmark-six'; report=json.loads((p/'report.json').read_text())
db=sqlite3.connect(ROOT/'instance/avatar-pilot/pilot.sqlite3',check_same_thread=False)
assert db.execute("SELECT COUNT(*) FROM fashn_jobs WHERE status IN ('queued','submitting','polling','checking','reviewing')").fetchone()[0]==0,'Wait for active jobs'
backup=sqlite3.connect(p/'before-pipeline.sqlite3');db.backup(backup);backup.close()
jobs=FashnJobs(db,threading.RLock(),autostart=False)
base=report['avatar'];owner=db.execute('SELECT owner FROM fashn_jobs WHERE id=? AND deleted=0',(base,)).fetchone()[0]
scenarios={'parka':'cold','linen':'sun','navy-wide':'mild','sport-dress':'sun','warmrain':'warmrain'}
imported=[]
with db:
    db.execute('INSERT OR IGNORE INTO fashn_external_spend VALUES(?,?,?)',('benchmark-six-2026-11-03',owner,report['new_credits']))
    for row in report['rows']:
        if not row['final_pass']:continue
        ref=(p/row['reference']).read_bytes();raw=(p/row['best']).read_bytes()
        cache='benchmark-keeper:'+hashlib.sha256((base+row['id']).encode()).hexdigest()
        old=db.execute('SELECT id FROM fashn_jobs WHERE owner=? AND cache=?',(owner,cache)).fetchone()
        if old:imported.append(old[0]);continue
        jid=hashlib.sha256(cache.encode()).hexdigest()[:24]
        meta=dict(provider='fashn',model='tryon-max',pipeline=OUTFIT_VERSION,kind='outfit',scenario=scenarios[row['id']],avatar_id=base,
            preview=False,accepted=True,full_outfit=True,quality_state='passed',quality_review='manual-benchmark',
            quality_note=row['notes'][2],reference_hash=hashlib.sha256(ref).hexdigest(),created_at=time.time(),
            actual_credits=0,expected_credits=0,historical_pipeline_credits=row['cost'],
            provenance='benchmark-keeper',billing_note='Existing benchmark output; import has no charge.',
            dimensions=[1792,2400],repair_count=(row['cost']//3)-1)
        db.execute('INSERT INTO fashn_jobs(id,owner,cache,status,charge,metadata,image) VALUES(?,?,?,?,?,?,?)',(jid,owner,cache,'done',0,json.dumps(meta),raw))
        imported.append(jid)
print(json.dumps({'saved_keepers':len(imported),'new_generation_credits':0,'total_accounted_credits':jobs.spent(owner)}))
