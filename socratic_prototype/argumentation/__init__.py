"""Versioned, researcher-only graph argumentation. It never controls live policy."""
import hashlib
from pathlib import Path
from ..semantics import CORE,DATA

ARG=CORE+'argumentation/'
VERSION='argumentation-0.1'
ROOT=Path(__file__).parent
LIMITS={'max_rounds':6,'max_arguments':256,'max_assertions':512,'max_matches':1024}


def documents(module):
    hook=getattr(module,'argumentation_documents',None)
    return (ROOT/'schema.ttl',ROOT/'shapes.ttl',ROOT/'schemes/shared.ttl')+tuple(hook() if hook else ())


def configuration(module):
    try:
        import rdflib
        backend='rdflib-sparql';backend_version=rdflib.__version__
    except ImportError:
        backend='unavailable';backend_version=None
    return {'version':VERSION,'mode':'shadow','semantics':'grounded','backend':backend,
            'backend_version':backend_version,'limits':dict(LIMITS),
            'documents':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in documents(module)}}


def analyse(session,event):
    config=session['argumentation_configuration']
    base={'version':VERSION,'mode':'shadow','backend':config['backend'],'semantics':'grounded',
          'scope':DATA+event['id']+'/state','assertions':[],'arguments':[],'attacks':[],
          'defeats':[],'critical_questions':[],'facts_turtle':'',
          'notice':'Researcher-only shadow analysis; labels are justification under these rules, not truth or intervention usefulness.'}
    if 'task_module' not in session or event['input']['kind']!='evaluation':
        return {**base,'status':'not-evaluated','reason':'Argument discovery runs on task-module evaluation snapshots.'}
    if config['backend']=='unavailable':
        return {**base,'status':'unavailable','reason':'Install requirements-research.txt and start a new session to execute graph reasoning.'}
    from ..records import require
    positions=[i for i,record in enumerate(session['events']) if record['id']==event['id']]
    require(len(positions)==1,'Argumentation requires one recorded snapshot event')
    # Offline inspection of an earlier event must not see later feedback/reviews.
    scoped_session={**session,'events':session['events'][:positions[0]+1]}
    from .discovery import discover
    return discover(scoped_session,event,base)
