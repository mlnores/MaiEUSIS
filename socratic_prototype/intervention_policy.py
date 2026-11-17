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


def assistance_gate(task,snapshot):
    hook=getattr(get_task(task),'assistance_gate',None)
    return hook(snapshot) if hook else {'enabled':False,'eligible':True,'argument_ids':[],
                                      'reason':'No additional environment-specific performance gate.'}


def candidates(session,event,snapshot):
    """Only complete, evaluated graph proofs may warrant live candidates."""
    report=snapshot['graph_argumentation']
    if report['status']!='complete':return []
    gate=assistance_gate(session['task'],snapshot)
    if not gate['eligible']:return []
    condition=session['condition'];socratic=condition in {'D','F'}
    require(condition in {'A','C','D','E','F'},'Unknown or retired assistance condition')
    from .participant_model import selection_cost
    cost=selection_cost(session['policy']['interruption_cost'],snapshot['participant'])
    from .recommendations import from_graph,message as recommendation_message
    from .comparisons import from_graph as comparison_set,context as comparison_context
    recommendation=from_graph(session['task'],event,report) if not socratic and condition!='A' else None
    comparisons=comparison_set(session['task'],event,snapshot) if socratic else []
    required=getattr(get_task(session['task']),'required_comparison_count',lambda env:0)(snapshot['environment'])
    if socratic and required and len(comparisons)!=required:return []
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
        supports=sorted(set([argument['id']]+gate['argument_ids']+
                            ([recommendation['argument_id']] if not socratic and recommendation else [])))
        comparison=[] if clarification and not required else comparisons
        supports+=sorted({a for c in comparison for a in c['argument_ids']})
        opposition=sorted({a['attacker'] for a in report['attacks'] if a['target'] in supports or set(a['affected'])&set(supports)})
        result.append({'id':argument['id']+'/intervention','name':name,'action':action,'messages':[message_text],'claim_ids':evidence,
            'usefulness':usefulness,'score':round(usefulness-cost,6),
            'supporting_arguments':supports,'recommendation':recommendation if not socratic else None,'interruption_cost':cost,'opposing_arguments':opposition,
            'argument_evaluation':'unresolved-clarification' if clarification else 'accepted',
            'comparisons':comparison,'comparison_context':comparison_context(session['task'],comparison,event),
            'hypothesis':hypothesis['name'] if hypothesis else None,'schedule':presentation['schedule'],
            'graph_scope':report['scope']})
    from .personalisation import assess
    for candidate in result:
        adaptation=assess(session['task'],condition,event,snapshot,candidate)
        candidate['personalisation']=adaptation
        candidate['effective_usefulness']=round(candidate['usefulness']*adaptation['relevance_factor']*adaptation['uptake_factor'],6)
        candidate['score']=round(candidate['effective_usefulness']-cost,6)
    # Support is a communication fallback, not an inference from missing evidence.
    if any(c['schedule']!='fallback' for c in result):result=[c for c in result if c['schedule']!='fallback']
    return sorted(result,key=lambda c:(-c['score'],c['name'],c['supporting_arguments']))


def decide(session,event,snapshot,event_id):
    opportunities=candidates(session,event,snapshot);p=session['policy']
    gate=assistance_gate(session['task'],snapshot)
    delivered=[e['input'] for e in session['events'] if e['input'].get('kind')=='delivery' and e['input']['delivered']]
    since=event['index']-delivered[-1]['index'] if delivered else None
    cooldown=p['cooldown'][session['preference']]
    selected=next((c for c in opportunities if not c['personalisation']['redundant']),opportunities[0] if opportunities else None)
    if selected:cooldown+=selected['personalisation']['extra_cooldown']
    rationale='No permitted graph-grounded candidate exceeds the relevance and interruption threshold.'
    active=False
    if session['condition'] in {'C','E'} and not opportunities:
        rationale='No accepted intervention warrant with an option-ranking proof supports a specific recommendation under the configured criterion.'
    if session['phase']=='calibration' or session['condition']=='A':
        rationale='Unassisted condition: neutral preparation window; no assistance delivered.'
    elif snapshot['graph_argumentation']['status']!='complete':
        rationale='Graph reasoning is '+snapshot['graph_argumentation']['status']+'; no assistance can be grounded. Install research dependencies if unavailable and start a new session.'
    elif not gate['eligible']:
        rationale='Performance gate: '+gate['reason']
    elif selected and selected['personalisation']['redundant']:
        rationale='Personalised delivery: '+selected['personalisation']['reason']+' The shared ranking and argument evaluation are unchanged.'
    elif since is not None and since<cooldown:
        rationale=f'Cooldown: {since} trials since the last delivered prompt; {cooldown} required for {session["preference"]} frequency.'
    elif selected and selected['score']>=p['threshold']:
        active=True
        rationale=f'{selected["name"]}: graph warrant {selected["argument_evaluation"]}; delivery usefulness {selected["effective_usefulness"]:.3f} minus interruption cost {selected["interruption_cost"]:.3f}; score {selected["score"]:.3f} meets threshold {p["threshold"]:.3f}.'
    elif selected and selected['personalisation']['enabled']:
        rationale='Personalised delivery: '+selected['personalisation']['reason']+f' Adjusted score {selected["score"]:.3f} is below threshold {p["threshold"]:.3f}.'
    neutral=[next(c['id'] for c in snapshot['claims'] if c['id'].endswith('_'+name)) for name in ['context','unknown']]
    from .recommendations import structured
    return {'task':session['task'],'intervention':structured(session['task'],session['condition'],selected) if active else None,'id':event_id+'_decision','action':selected['action'] if active else 'silence','rationale':rationale,
        'comparison_context':selected['comparison_context'] if active else '',
        'claim_ids':selected['claim_ids'] if active else neutral,'message':None,'candidates':opportunities,
        'threshold':p['threshold'],'interruption_cost':selected['interruption_cost'] if selected else p['interruption_cost'],'cooldown':cooldown,
        'frequency_preference':session['preference'],'eligible_point':get_task(session['task']).ELIGIBLE_POINT,
        'hypothesis':selected['hypothesis'] if active else None,'language':None,
        'reasoning_source':'graph','assistance_gate':gate,'selected_candidate':selected['id'] if active else None,
        'condition':session['condition'],'personalisation':selected['personalisation'] if selected else None,
        'argument_ids':selected['supporting_arguments'] if active else [],
        'opposing_argument_ids':selected['opposing_arguments'] if active else []}


def validate_decision(snapshot):
    """Independently enforce proof links at the delivery boundary."""
    d=snapshot['decision'];report=snapshot['graph_argumentation']
    require(not snapshot['arguments'],'Live graph decisions cannot carry independent candidate reasons')
    arguments={a['id']:a for a in report['arguments']}
    gate=assistance_gate(d['task'],snapshot)
    require(d.get('assistance_gate')==gate,'Assistance gate differs from its graph evidence')
    require(gate['eligible'] or (d['action']=='silence' and not d['candidates']),
            'Assistance bypassed the performance gate')
    for candidate in d['candidates']:
        require(report['status']=='complete' and candidate['graph_scope']==report['scope'],'Candidate uses an incomplete or stale graph')
        if 'personalisation' in candidate:
            from .personalisation import assess
            module=get_task(d['task'])
            evaluation=snapshot.get('evaluation')
            if evaluation is None and callable(getattr(module,'comparison_evaluation',None)):
                evaluation=module.comparison_evaluation(snapshot['environment'])
            if evaluation is not None:
                expected_adaptation=assess(d['task'],d['condition'],evaluation,snapshot,candidate)
                require(candidate['personalisation']==expected_adaptation,'Delivery adaptation differs from its public model and graph evidence')
            adaptation=candidate['personalisation']
            effective=round(candidate['usefulness']*adaptation['relevance_factor']*adaptation['uptake_factor'],6)
            require(candidate['effective_usefulness']==effective and candidate['score']==round(effective-candidate['interruption_cost'],6),
                    'Delivery score differs from its model-based estimate')
        supports=candidate['supporting_arguments'];opponents=candidate['opposing_arguments']
        require(set(gate['argument_ids'])<=set(supports),'Intervention lacks its performance-gate proof')
        require(bool(supports) and set(supports+opponents)<=arguments.keys(),'Candidate lacks graph provenance')
        comparison=candidate.get('comparisons',[])
        required=getattr(get_task(d['task']),'required_comparison_count',lambda env:0)(snapshot['environment'])
        require(not required or candidate.get('recommendation') is not None or len(comparison)==required,
                'Socratic intervention lacks the required ranked pair')
        comparison_ids={identifier for c in comparison for identifier in c['argument_ids']}
        require(not comparison or (len(comparison)>=2 and candidate['recommendation'] is None),
                'Socratic comparisons require multiple alternatives and no recommendation')
        require(comparison_ids<=set(supports),'Comparison lacks selected graph proofs')
        if comparison:
            from .comparisons import from_graph,context
            module=get_task(d['task'])
            evaluation=module.comparison_evaluation(snapshot['environment'])
            require(comparison==from_graph(d['task'],evaluation,snapshot),'Comparison differs from graph evidence')
            require(candidate['comparison_context']==context(d['task'],comparison,evaluation),'Comparison text differs from evidence')
        if candidate.get('recommendation') and callable(getattr(get_task(d['task']),'comparison_evaluation',None)):
            from .recommendations import from_graph as recommendation_from_graph
            module=get_task(d['task'])
            require(candidate['recommendation']==recommendation_from_graph(
                d['task'],module.comparison_evaluation(snapshot['environment']),report),
                'Recommendation differs from its graph ranking')
        for identifier in supports:
            argument=arguments[identifier];metadata=argument.get('intervention')
            if identifier in gate['argument_ids']:
                require(argument['label']=='accepted','Performance gate proof is not accepted')
                continue
            if not metadata:
                if identifier in comparison_ids:
                    from .argumentation import ARG
                    proposition=next(a for a in report['assertions'] if a['id']==argument['conclusion'])['proposition']
                    require(argument['label']=='accepted' and proposition['predicate']==ARG+'worthComparingFor',
                            'Comparison uses a rejected or unsupported warrant')
                    continue
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
        if 'personalisation' in selected:
            require(d['personalisation']==selected['personalisation'] and not selected['personalisation']['redundant'],
                    'Active decision bypasses personalised delivery assessment')
            require(selected['score']>=d['threshold'],'Active decision is below the delivery threshold')
        require(d['argument_ids']==selected['supporting_arguments'] and d['opposing_argument_ids']==selected['opposing_arguments'],
                'Decision proof differs from selected candidate')
        if d.get('intervention') is not None:
            require(d['intervention']['recommendation']==selected.get('recommendation') and
                    d['intervention']['supporting_arguments']==selected['supporting_arguments'],
                    'Structured intervention differs from its selected proof')
            require(d['intervention'].get('comparisons',[])==selected.get('comparisons',[]) and
                    d.get('comparison_context','')==selected.get('comparison_context',''),
                    'Delivered comparison differs from its selected proof')
        require(d['action']==selected['action'] and d['claim_ids']==selected['claim_ids'] and
                d['hypothesis']==selected['hypothesis'],'Decision differs from selected graph candidate')
