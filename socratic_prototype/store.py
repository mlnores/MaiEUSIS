"""Local durable store. Public events only; evaluator truth stays in browser logs."""
import copy
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime,timezone
from pathlib import Path
from threading import RLock
from contextlib import contextmanager
from .engine import POLICY, NETWORK, ingest, history
from .models import calibration_profile, VERSION
from .validation import fields, require, identity, CONDITIONS, turtle, shacl_report

RULES={'targets':[595,930,1035,1105],'multipliers':[1.1,2.3,3.3,4.2],
       'options': [[(100,.9),(265,.35)],[(180,.6),(260,.35)],[(145,.75),(245,.35)],[(145,.55),(350,.2)],
                   [(115,.9),(240,.45)],[(150,.6),(190,.45)],[(170,.75),(245,.4)],[(120,.8),(210,.3)]]}
# JSON roundtrip makes pairs lists consistently across SQLite and initial state.
RULES=json.loads(json.dumps(RULES))
CONFIGURATION_FIELDS=['task','condition','phase','protocol','initial_preference','seed','total_trials','policy','task_rules',
                      'network','model_version','schema_version','calibration_sources','calibration_profile']


def now():return datetime.now(timezone.utc).isoformat()

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class Store:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=RLock()
        with self.connect() as c:c.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, body TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        connection=sqlite3.connect(self.path,timeout=10)
        try:
            with connection:yield connection
        finally:connection.close()

    def save(self,s):
        with self.connect() as c:c.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)',(s['id'],json.dumps(s)))

    def get(self,sid):
        require(identity(sid) and len(sid)<=55,'Invalid session ID (maximum 55 characters)')
        with self.connect() as c:r=c.execute('SELECT body FROM sessions WHERE id=?',(sid,)).fetchone()
        if r is None:raise KeyError('Session not found')
        return json.loads(r[0])

    def list(self,participant=None):
        with self.connect() as c:rows=c.execute('SELECT body FROM sessions ORDER BY rowid DESC').fetchall()
        result=[]
        for row in rows:
            s=json.loads(row[0])
            if participant and s['participant_id']!=participant:continue
            result.append({k:s[k] for k in ['id','participant_id','task','condition','phase','protocol','created_at','finished','completed','total_trials']}|{'trials':len(history(s))})
        return result

    def create(self,data):
        fields(data,['participant_id','task','condition','phase','protocol','preference'],['id','calibration_ids','seed'])
        require(identity(data['participant_id']),'Use a pseudonymous participant ID (letters, digits, dash, underscore)')
        require(data['task'] in {'MAB','TBS'},'Unknown task')
        require(data['condition'] in CONDITIONS,'Unknown condition')
        require(data['phase'] in {'calibration','assisted'},'Unknown phase')
        require(data['protocol'] in {'short','full'},'Unknown protocol')
        require(data['preference'] in POLICY['cooldown'],'Unknown prompt frequency')
        require(data['phase']!='calibration' or data['condition']=='A','Calibration must be unassisted')
        sid=data.get('id') or 'socratic_'+uuid.uuid4().hex
        require(identity(sid) and len(sid)<=55,'Invalid session ID (maximum 55 characters)')
        require(isinstance(data.get('seed',sid),str) and len(data.get('seed',sid))<=100,'Invalid random seed')
        calibration={}; profile=None
        if data['phase']=='assisted':
            ids=data.get('calibration_ids',{})
            require(isinstance(ids,dict) and set(ids)=={'MAB','TBS'},'Comparison sessions require completed unassisted MAB and TBS calibration sessions')
            for task,source_id in ids.items():
                source=self.get(source_id)
                require(source['task']==task and source['participant_id']==data['participant_id'] and source['phase']=='calibration' and source['completed'],'Invalid or incomplete calibration source')
                require(source['protocol']==data['protocol'],'Calibration and assisted protocol must match')
                calibration[task]={'session_id':source_id,'profile':source['profile'],'digest':digest(source['events'])}
            if data['condition'] in {'E','F'}:profile=calibration[data['task']]['profile']
        s={'id':sid,'participant_id':data['participant_id'],'task':data['task'],'condition':data['condition'],
           'phase':data['phase'],'protocol':data['protocol'],'preference':data['preference'],'initial_preference':data['preference'],
           'seed':data.get('seed',sid),'created_at':now(),'events':[],'finished':False,'completed':False,
           'total_trials':(40 if data['protocol']=='short' else 200) if data['task']=='MAB' else (24 if data['protocol']=='short' else 192),
           'policy':copy.deepcopy(POLICY),'task_rules':copy.deepcopy(RULES),'network':NETWORK.describe(),
           'model_version':VERSION,'schema_version':'ontology-0.1','calibration_sources':calibration,'calibration_profile':profile}
        s['configuration_digest']=digest({k:s[k] for k in CONFIGURATION_FIELDS})
        with self.lock:
            with self.connect() as c:
                try:c.execute('INSERT INTO sessions VALUES (?,?)',(sid,json.dumps(s)))
                except sqlite3.IntegrityError:raise ValueError('Session ID already exists')
        return s

    def event(self,sid,data):
        with self.lock:
            s=self.get(sid)
            # Exact retries are idempotent. Different repeated payloads still fail validation.
            for e in s['events']:
                if e['input']==data:return e
            candidate,event=ingest(s,data,now())
            self.save(candidate);return event

    def finish(self,sid,data):
        fields(data,['completed'])
        require(type(data['completed']) is bool,'Invalid completion state')
        with self.lock:
            s=self.get(sid)
            if s['finished']:
                require(s['completed']==data['completed'],'Session already closed with different status')
                return s
            require(not data['completed'] or len(history(s))==s['total_trials'],'Cannot complete an unfinished protocol')
            s['finished']=True;s['completed']=data['completed'];s['finished_at']=now()
            s['profile']=calibration_profile(s['task'],history(s)) if s['phase']=='calibration' and s['completed'] else None
            self.save(s);return s

    def replay(self,sid):
        original=self.get(sid)
        require(original['configuration_digest']==digest({k:original[k] for k in CONFIGURATION_FIELDS}),'Recorded configuration hash does not match; settings were altered')
        expected={'policy':POLICY,'model_version':VERSION,'schema_version':'ontology-0.1','network':NETWORK.describe()}
        # Reject model/policy drift rather than pretending a new model reproduces an old run.
        for key,value in expected.items():
            require(original[key]==value,'Replay requires recorded '+key+' version/backend; current runtime differs')
        restored=copy.deepcopy(original);restored['events']=[];restored['finished']=False;restored['completed']=False
        restored['preference']=original['initial_preference']
        for event in original['events']:
            language=event.get('snapshot',{}).get('decision',{}).get('language')
            restored,new=ingest(restored,event['input'],event['timestamp'],language)
            require(new==event,'Replay mismatch at '+event['id'])
        restored['finished']=original['finished'];restored['completed']=original['completed']
        return {'matches':True,'events_replayed':len(restored['events']),'digest':digest(restored['events']),
                'recorded_digest':digest(original['events']),'api_calls':0}

    def export(self,sid):
        s=self.get(sid)
        from .analysis import summarize
        s['summary']=summarize(s)
        s['export']={'event_digest':digest(s['events']),'information_boundary':'Participant-visible events only. Evaluator logs are a separate browser download.'}
        return s
