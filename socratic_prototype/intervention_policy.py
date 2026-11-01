"""Map graph warrants to permitted communication, then schedule delivery.

No behavioural evidence triggers or fabricated opposing reasons live here.
Usefulness estimates rank communication opportunities; they never determine
argument acceptance or override a rejected argument.
"""
from .tasks import get_task
from .semantics import CORE
from .records import require


def proof_closure(report, identifiers):
    arguments={a['id']:a for a in report['arguments']}
    retained=set();pending=list(identifiers)
    while pending:
        identifier=pending.pop()
        require(identifier in arguments,'Missing graph argument')
        if identifier in retained:continue
        retained.add(identifier);pending.extend(arguments[identifier]['subarguments'])
    return [a for a in report['arguments'] if a['id'] in retained]


def candidates(session,event,snapshot):
    """Only complete, evaluated graph proofs may warrant live candidates."""
    report=snapshot['graph_argumentation']
    if report['status']!='complete':return []
    condition=session['condition'];socratic=condition in {'D','F'}
    require(condition in {'A','C','D','E','F'},'Unknown or retired assistance condition')
    from .participant_model import selection_cost
    cost=selection_cost(session['policy']['interruption_cost'],snapshot['participant'])
    from .recommendations import from_graph,message as recommendation_message
    recommendation=from_graph(session['task'],event,report) if not socratic and condition!='A' else None
    facts={a['id']:a for a in report['assertions']}
    nodes={a['id']:a for a in report['arguments']}
    hypotheses={CORE+h['claim_id']:h for h in snapshot['participant']['hypotheses'] if h.get('claim_id')}
    environment=next(c for c in snapshot['claims'] if c['id'].endswith('_environment'))
    result=[]
    for argument in report['arguments']:
        presentation=argument.get('intervention')
        if not presentation or argument['label']=='rejected':continue
        audience=presentation['audience']
        require(audience in {'task','personalised','socratic'},'Unsupported intervention audience')
        if condition not in {'C','D','E','F'}:continue
        if audience=='personalised' and condition not in {'E','F'}:continue
        if audience=='socratic' and not socratic:continue
        if presentation['schedule']=='periodic' and event['index']%session['policy']['fixed_prompt_interval']:continue
        incoming=[a for a in report['attacks'] if a['target']==argument['id'] or argument['id'] in a['affected']]
        opposition=sorted({a['attacker'] for a in incoming})
        clarification=argument['label']=='undecided'
        if clarification:
            # Only an explicitly authored question may communicate an unresolved
            # conflict. Never silently turn an undecided warrant into advice.
            if not socratic or not presentation.get('clarification_message') or not any(
                    a['succeeds'] and nodes[a['attacker']]['rule']==presentation['clarification_objection'] for a in incoming):continue
        elif argument['label']!='accepted':continue
        hypothesis=None;name=presentation['issue'];usefulness=presentation['usefulness']
        evidence=[environment['id']]
        if audience=='personalised':
            source=facts[argument['conclusion']]['proposition']['subject']
            hypothesis=hypotheses.get(source)
            require(hypothesis is not None,'Personalised warrant lacks a model source')
            name=hypothesis['name'];evidence=[hypothesis['claim_id'],environment['id']]
            usefulness=hypothesis['inference']['usefulness']
        action='ask' if clarification else presentation['socratic_action'] if socratic else 'explain'
        message=presentation['clarification_message'] if clarification else presentation['socratic_message'] if socratic else presentation['conventional_message']
        if hypothesis:
            action='challenge' if socratic else 'advise'
            message=get_task(session['task']).hypothesis_message(name,socratic)
        if not socratic and callable(getattr(get_task(session['task']),'recommendation_message',None)):
            if not recommendation:continue
            action='advise';message_text=recommendation_message(session['task'],recommendation)
        else:message_text=message
        supports=[argument['id']]+([recommendation['argument_id']] if not socratic and recommendation else [])
        result.append({'id':argument['id']+'/intervention','name':name,'action':action,'messages':[message_text],'claim_ids':evidence,
            'usefulness':usefulness,'score':round(usefulness-cost,6),
            'supporting_arguments':supports,'recommendation':recommendation if not socratic else None,'interruption_cost':cost,'opposing_arguments':opposition,
            'argument_evaluation':'unresolved-clarification' if clarification else 'accepted',
            'hypothesis':hypothesis['name'] if hypothesis else None,'schedule':presentation['schedule'],
            'graph_scope':report['scope']})
    # Support is a communication fallback, not an inference from missing evidence.
    if any(c['schedule']!='fallback' for c in result):result=[c for c in result if c['schedule']!='fallback']
    return sorted(result,key=lambda c:(-c['score'],c['name'],c['supporting_arguments']))


def decide(session,event,snapshot,event_id):
    opportunities=candidates(session,event,snapshot);p=session['policy']
    delivered=[e['input'] for e in session['events'] if e['input'].get('kind')=='delivery' and e['input']['delivered']]
    since=event['index']-delivered[-1]['index'] if delivered else None
    cooldown=p['cooldown'][session['preference']]
    selected=opportunities[0] if opportunities else None
    rationale='No permitted graph-grounded candidate exceeds the relevance and interruption threshold.'
    active=False
    if session['condition'] in {'C','E'} and not opportunities:
        rationale='No accepted intervention warrant with a unique option-comparison proof supports a specific recommendation under the configured criterion.'
    if session['phase']=='calibration' or session['condition']=='A':
        rationale='Unassisted condition: neutral preparation window; no assistance delivered.'
    elif snapshot['graph_argumentation']['status']!='complete':
        rationale='Graph reasoning is '+snapshot['graph_argumentation']['status']+'; no assistance can be grounded. Install research dependencies if unavailable and start a new session.'
    elif since is not None and since<cooldown:
        rationale=f'Cooldown: {since} trials since the last delivered prompt; {cooldown} required for {session["preference"]} frequency.'
    elif selected and selected['score']>=p['threshold']:
        active=True
        rationale=f'{selected["name"]}: graph warrant {selected["argument_evaluation"]}; provisional usefulness {selected["usefulness"]:.3f} minus interruption cost {selected['interruption_cost']:.3f}; score {selected["score"]:.3f} meets threshold {p["threshold"]:.3f}.'
    neutral=[next(c['id'] for c in snapshot['claims'] if c['id'].endswith('_'+name)) for name in ['context','unknown']]
    from .recommendations import structured
    return {'intervention':structured(session['task'],session['condition'],selected) if active else None,'id':event_id+'_decision','action':selected['action'] if active else 'silence','rationale':rationale,
        'claim_ids':selected['claim_ids'] if active else neutral,'message':None,'candidates':opportunities,
        'threshold':p['threshold'],'interruption_cost':selected['interruption_cost'] if selected else p['interruption_cost'],'cooldown':cooldown,
        'frequency_preference':session['preference'],'eligible_point':get_task(session['task']).ELIGIBLE_POINT,
        'hypothesis':selected['hypothesis'] if active else None,'language':None,
        'reasoning_source':'graph','selected_candidate':selected['id'] if active else None,
        'argument_ids':selected['supporting_arguments'] if active else [],
        'opposing_argument_ids':selected['opposing_arguments'] if active else []}


def validate_decision(snapshot):
    """Independently enforce proof links at the delivery boundary."""
    d=snapshot['decision'];report=snapshot['graph_argumentation']
    require(not snapshot['arguments'],'Live graph decisions cannot carry independent candidate reasons')
    arguments={a['id']:a for a in report['arguments']}
    for candidate in d['candidates']:
        require(report['status']=='complete' and candidate['graph_scope']==report['scope'],'Candidate uses an incomplete or stale graph')
        supports=candidate['supporting_arguments'];opponents=candidate['opposing_arguments']
        require(bool(supports) and set(supports+opponents)<=arguments.keys(),'Candidate lacks graph provenance')
        for identifier in supports:
            argument=arguments[identifier];metadata=argument.get('intervention')
            if not metadata:
                rec=candidate.get('recommendation')
                require(rec is not None and identifier==rec['argument_id'] and argument['label']=='accepted',
                        'Candidate is not warranted by an intervention scheme or recommendation proof')
                from .argumentation import ARG
                assertion=next(a for a in report['assertions'] if a['id']==argument['conclusion'])['proposition']
                require(assertion['predicate']==ARG+'recommendedByCriterion' and
                        assertion['subject'].rsplit('/',1)[-1]==rec['option_id'] and
                        assertion['object']['value']==rec['criterion'] and candidate['action']=='advise',
                        'Recommended option or criterion differs from its graph proof')
                continue
            if candidate['argument_evaluation']=='unresolved-clarification':
                require(argument['label']=='undecided' and candidate['action']=='ask' and
                        candidate['messages']==[metadata.get('clarification_message')] and bool(opponents),
                        'Unresolved warrant cannot support conventional advice')
                require(any(arguments[a]['rule']==metadata['clarification_objection'] for a in opponents),
                        'Clarification lacks its authored objection')
            else:require(argument['label']=='accepted' and candidate['argument_evaluation']=='accepted','Candidate uses a rejected or undecided warrant')
        require(any(arguments[a].get('intervention') for a in supports),'Recommendation lacks an intervention warrant')
        expected=sorted({a['attacker'] for a in report['attacks'] if a['target'] in supports or set(a['affected'])&set(supports)})
        require(opponents==expected,'Candidate opposition differs from graph attacks')
    if d['action']=='silence':
        require(not d['argument_ids'] and not d['opposing_argument_ids'],'Silence cannot claim delivery provenance')
    else:
        selected=next((c for c in d['candidates'] if c['id']==d['selected_candidate']),None)
        require(selected is not None,'Decision lacks a selected graph candidate')
        require(d['argument_ids']==selected['supporting_arguments'] and d['opposing_argument_ids']==selected['opposing_arguments'],
                'Decision proof differs from selected candidate')
        if d.get('intervention') is not None:
            require(d['intervention']['recommendation']==selected.get('recommendation') and
                    d['intervention']['supporting_arguments']==selected['supporting_arguments'],
                    'Structured intervention differs from its selected proof')
        require(d['action']==selected['action'] and d['claim_ids']==selected['claim_ids'] and
                d['hypothesis']==selected['hypothesis'],'Decision differs from selected graph candidate')
