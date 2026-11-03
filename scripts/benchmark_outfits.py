"""Resumable, bounded FASHN benchmark. Private inputs/results stay under instance/."""
import sys,os,json,time,base64,io,sqlite3,threading,concurrent.futures
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fashn import FashnClient,SETTINGS,decode_output
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'instance/avatar-pilot/benchmark-six';OUT.mkdir(parents=True,exist_ok=True)
lock=threading.Lock();ledger_path=OUT/'ledger.json';ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
LIMIT=42

def save():
 tmp=ledger_path.with_suffix('.tmp');tmp.write_text(json.dumps(ledger,indent=2)+'\n');tmp.replace(ledger_path)
def uri(path):
 from PIL import Image
 raw=Path(path).read_bytes()
 with Image.open(io.BytesIO(raw)) as im:mime=Image.MIME[im.format]
 return 'data:'+mime+';base64,'+base64.b64encode(raw).decode()
def balance():
 c=FashnClient();r=c.http.get('https://api.fashn.ai/v1/credits',headers=c.headers(),timeout=(20,40));r.raise_for_status();return r.json()
def run(spec):
 key=spec['id'];cost=spec['cost'];c=FashnClient()
 with lock:
  record=ledger.get(key)
  if record and record['status'] in ('done','failed','unknown','submitting'):return key,record['status']
  if not record:
   if sum(r['reserved'] for r in ledger.values())+cost>LIMIT:raise ValueError('Benchmark credit cap reached')
   record={'status':'submitting','reserved':cost,'started':time.time(),'model':spec['model'],'source':spec['source'],'reference':spec['reference'],'prompt':spec.get('prompt'),'settings':spec.get('settings',{})};ledger[key]=record;save()
 if not record.get('prediction'):
  common={'model_image':uri(ROOT/spec['source']),'return_base64':True,'output_format':'png','seed':42}
  if spec['model']=='tryon-max':inputs=dict(SETTINGS,**common,product_image=uri(ROOT/spec['reference']),prompt=spec['prompt'])
  else:inputs=dict(common,garment_image=uri(ROOT/spec['reference']),category='auto',garment_photo_type='model',mode='quality',segmentation_free=False,num_samples=1)
  inputs.update(spec.get('settings',{}))
  try:
   r=c.http.post('https://api.fashn.ai/v1/run',headers=c.headers(),json={'model_name':spec['model'],'inputs':inputs},timeout=(60,90),allow_redirects=False)
   if 400<=r.status_code<500:
    with lock:record.update(status='failed',error='Request rejected: HTTP '+str(r.status_code),reserved=0);save()
    return key,'failed'
   r.raise_for_status();prediction=r.json()['id']
   with lock:record.update(prediction=prediction,status='polling');save()
  except Exception as e:
   with lock:record.update(status='unknown',error=type(e).__name__);save()
   return key,'unknown'
 deadline=time.time()+600
 while time.time()<deadline:
  try:
   result,credits=c.poll(record['prediction'])
   if result.get('status')=='completed':
    raw,size=decode_output(result['output'][0]);(OUT/(key+'.png')).write_bytes(raw)
    with lock:record.update(status='done',actual_credits=credits,dimensions=list(size),elapsed_seconds=round(time.time()-record['started'],1));save()
    return key,'done'
   if result.get('status')=='failed':
    with lock:record.update(status='failed',error='Provider generation failed',actual_credits=credits);save()
    return key,'failed'
  except Exception:pass
  time.sleep(5)
 return key,'polling'
if __name__=='__main__':
 if sys.argv[1]=='balance':print(json.dumps(balance()));sys.exit()
 plan=json.loads(Path(sys.argv[1]).read_text())
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  for result in pool.map(run,plan):print(*result,flush=True)
 print('Reserved credits',sum(r['reserved'] for r in ledger.values()),flush=True)
