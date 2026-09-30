from pathlib import Path
import json,os,subprocess,time,socket,hashlib
from urllib.request import Request,urlopen
root=Path('docs/evidence/desktop-fixes-2026-09-30').resolve()
exe=Path('dist/PBIBrain/PBIBrain-Agent.exe').resolve()
env={k:v for k,v in os.environ.items() if not k.upper().startswith(('PYTHON','LBUG')) and k.upper() not in ('VIRTUAL_ENV','NODE_PATH')}
env['PATH']=r'C:\Windows\System32;C:\Windows'
results={}
for folder in ['Audit á (test)','Invalid á']:
 project=root/folder
 config=project/'.pbibrain/brain.json'
 config.parent.mkdir(exist_ok=True)
 if not config.exists():
  config.write_text(json.dumps({'version':1,'name':folder,'sources':['../Finance.pbip'],'database':'brain.lbug','identity_map':'identity-map.json'}),encoding='utf-8')
 before={str(f.relative_to(project)):hashlib.sha256(f.read_bytes()).hexdigest() for f in project.rglob('*') if f.is_file() and '.pbibrain' not in f.parts}
 run=subprocess.run([str(exe),'--project',str(project),'project-scan'],env=env,capture_output=True,text=True,encoding='utf-8',timeout=90)
 assert run.returncode==0,run.stderr
 with socket.socket() as sock:
  sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 with (root/('api-'+('valid' if folder.startswith('Audit') else 'invalid')+'.log')).open('w',encoding='utf-8') as log:
  proc=subprocess.Popen([str(exe),'--project',str(project),'serve','--port',str(port),'--ui',str(Path('frontend/dist').resolve())],env=env,stdout=log,stderr=log)
  url=f'http://127.0.0.1:{port}/api/'
  def request(endpoint,data=None):
   req=Request(url+endpoint,data=b'{}' if data else None,headers={'Content-Type':'application/json'})
   with urlopen(req,timeout=60) as response:return json.load(response)
  try:
   for i in range(100):
    try: overview=request('overview');break
    except Exception:
     if proc.poll() is not None:raise RuntimeError('server exited')
     time.sleep(.2)
   for i in range(2):
    scanned=request('scan',True)
    overview=request('overview');brain=request('brain')
    nodes={n['id']:n for n in brain['nodes']}
    assert any(e['type']=='USES_MODEL' for e in brain['edges'])
    assert not any(e['type']=='CONTAINS' and nodes[e['from_id']]['type']=='MODEL' and nodes[e['to_id']]['type']=='REPORT' for e in brain['edges'])
    assert overview['validation_state']==('valid' if folder.startswith('Audit') else 'invalid'),overview
    assert overview['validation_issues']==brain['validation']['issues']
   results[folder]={'scan':json.loads(run.stdout),'overview':overview,'source_unchanged':before=={str(f.relative_to(project)):hashlib.sha256(f.read_bytes()).hexdigest() for f in project.rglob('*') if f.is_file() and '.pbibrain' not in f.parts},'rescans':2,'environment':'sanitized Windows PATH; Python/Ladybug overrides removed'}
   assert results[folder]['source_unchanged']
  finally:
   proc.terminate();proc.wait(timeout=15)
(root/'packaged-api-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('Packaged valid/invalid API rescans and source immutability passed')
