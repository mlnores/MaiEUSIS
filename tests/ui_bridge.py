"""File-backed test bridge; no network or browser required."""
import json
import sys
from pathlib import Path
# Keep this per-request bridge lightweight. The exact CPT backend uses the same
# probabilities; SHACL has separate integration checks in the Python suite.
sys.modules['pgmpy']=None
sys.modules['pyshacl']=None
from socratic_prototype.store import Store
from socratic_prototype.demo import run_scripted

def main():
    store=Store(Path(sys.argv[1])/'sessions.sqlite3')
    request=json.load(sys.stdin);path=request['path'];body=request.get('body')
    if path=='/reference_page':
        from socratic_prototype.server import render_index
        return render_index(json.loads(Path('docs/simulation/reference-study.json').read_text()))
    if path=='/fixture_reference':
        from socratic_prototype.simulation import run
        study=json.loads(Path('docs/simulation/reference-study.json').read_text());study['conditions']=['A']
        run(store,[dict(id='synthetic_ui',source='Engineering fixture',task_models={'REFERENCE':{'right_bias':.5}})],study=study)
        return {'REFERENCE':next(s['id'] for s in store.list() if s['phase']=='calibration' and s['task']=='REFERENCE')}
    if path=='/fixture':
        return {task:run_scripted(store,task,participant='synthetic_ui') for task in ['MAB','TBS']}
    if path.startswith('/api/sessions?'):return store.list('synthetic_ui')
    if path=='/api/sessions' and body is None:return store.list()
    if path=='/api/sessions':
        study=json.loads(Path('docs/simulation/reference-study.json').read_text()) if body['task']=='REFERENCE' else None
        s=store.create(body,study=study);return {k:s[k] for k in ['id','condition','policy','total_trials','phase','configuration_digest']}
    bits=path.strip('/').split('/');sid=bits[2];action=bits[3]
    if action=='events':return {'record':store.event(sid,body),'processing_ms':1}
    if action=='finish':return store.finish(sid,body)
    if action=='export':return store.export(sid)
    if action=='replay':return store.replay(sid)
    raise ValueError(path)

if __name__=='__main__':
    try:print(json.dumps({'ok':True,'data':main()}))
    except Exception as error:print(json.dumps({'ok':False,'error':str(error)}))
