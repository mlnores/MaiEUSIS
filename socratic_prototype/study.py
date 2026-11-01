"""Current study choices, separate from task mechanics and the Socratic policy."""
# The present comparison deliberately uses a common two-task calibration.
# A newly registered task defaults to its own calibration; studies can override it.
CALIBRATION_TASKS={'MAB':('MAB','TBS'),'TBS':('MAB','TBS')}


def required_calibrations(task,study=None):
    return tuple(study['tasks'][task]['calibration_tasks']) if study else CALIBRATION_TASKS.get(task,(task,))

CONDITIONS={
    'A':{'style':'none','personalised':False,'label':'No assistance'},
    'C':{'style':'direct','personalised':False,'label':'Generic direct recommendations'},
    'E':{'style':'direct','personalised':True,'label':'Personalised direct recommendations'},
    'D':{'style':'socratic','personalised':False,'label':'Generic Socratic questions'},
    'F':{'style':'socratic','personalised':True,'label':'Personalised Socratic questions'},
}

VERSION='study-0.1'


def default_study(protocol='short'):
    return {'id':'mab-tbs','tasks':{task:{'protocol':protocol,'calibration_tasks':list(required_calibrations(task))}
                                  for task in CALIBRATION_TASKS},'conditions':list(CONDITIONS)}


def validate_study(data,simulation=False):
    import copy
    from .records import fields,require,identity
    from .tasks import get_task
    from .tasks.execution import simulation_adapter
    fields(data,['id','tasks','conditions'],['version','execution'])
    require(identity(data['id']),'Invalid study ID')
    require(isinstance(data['tasks'],dict) and bool(data['tasks']),'Study needs environment configurations')
    require(isinstance(data['conditions'],list) and bool(data['conditions']) and len(set(data['conditions']))==len(data['conditions'])
            and set(data['conditions'])<=CONDITIONS.keys(),'Invalid study conditions')
    result=copy.deepcopy(data);result['version']=VERSION;execution={}
    for task,config in data['tasks'].items():
        fields(config,['protocol','calibration_tasks']);module=get_task(task)
        require(config['protocol'] in module.PROTOCOLS,'Unknown protocol for '+task)
        deps=config['calibration_tasks']
        require(isinstance(deps,list) and bool(deps) and len(set(deps))==len(deps) and task in deps
                and set(deps)<=data['tasks'].keys(),'Invalid calibration dependencies for '+task)
        if simulation:
            adapter=simulation_adapter(module);execution[task]=adapter.describe()
            if any(c in {'C','E'} for c in data['conditions']):
                require(callable(getattr(module,'recommendation_message',None)),'Direct conditions need a recommendation adapter for '+task)
    if simulation:result['execution']=execution
    elif 'execution' in result:result.pop('execution')
    return result
