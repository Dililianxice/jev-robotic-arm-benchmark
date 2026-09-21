"""Descriptive audit/report; never changes the frozen collection protocol."""
import csv, json, sys
from pathlib import Path
from collections import Counter
import numpy as np
import bench
from bench import HERE, OUT, UP, IncrementalEnv, Questions, dump, sha

def csv_write(path, rows):
    if not rows: return
    with path.open('w', newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def cost(r):
    u=r.get('response',{}).get('usage',{})
    if r['provider']=='jev':
        if not isinstance(u.get('input_tokens'),int): return None,None
        low=high=u['input_tokens']*.042/1e6
    else:
        if any(not isinstance(u.get(k),int) for k in ('prompt_cache_hit_tokens','prompt_cache_miss_tokens','completion_tokens')):
            return None,None
        hit=u['prompt_cache_hit_tokens']; miss=u['prompt_cache_miss_tokens']
        low=(hit*.003+miss*.15+u['completion_tokens']*.6)/1e6; high=2*low
    return low,high

def main():
    episodes=[json.loads(p.read_text()) for p in sorted((OUT/'episodes').glob('*.json'))]
    apis={p.stem:json.loads(p.read_text()) for p in sorted((HERE/'api').glob('*.json'))}
    rows=[]; audit=[]; steps=[]; qb=Questions()
    manifest=json.loads((HERE/'manifest.json').read_text())
    assert all(sha(HERE/n)==v for n,v in manifest['hashes'].items())
    for r in episodes:
        e=IncrementalEnv(r['seed'],render=False); max_error=0.; calls=[]
        assert e.observe()==r['initial']
        grasp_count=0
        try:
            for c in r['cycles']:
                assert e.observe()==c['before']
                if r['provider']!='rules':
                    a=apis[f'{r["id"]}_{c["index"]:03}_intent']; b=apis[f'{r["id"]}_{c["index"]:03}_motor']
                    assert a['semantic_query']==qb.intent(c['before'])
                    assert b['semantic_query']==qb.motor(c['before'],c['intent'])
                    assert a['value']['intent']==c['intent'] and b['value']==c['motor']
                    calls += [a,b]
                actual=e.increment(c['motor'],c['intent'])
                assert actual==c['execution']
                error=float(np.max(np.abs(e.data.qpos-c['qpos']))); max_error=max(max_error,error)
                assert error<=1e-7
                assert e.observe()==c['after']
                steps.append(dict(id=r['id'],provider=r['provider'],seed=r['seed'],cycle=c['index'],intent=c['intent'],
                    **c['motor'],accepted=c['execution']['accepted'],held=c['after']['held'],
                    in_plate=c['after']['fruit_in_plate'],sim_seconds=c['after']['sim_seconds']))
            if r['status']!='error': assert e.success()==r['success']
            grasp_count=e.grasp_attempts
        finally: e.close()
        allcalls=[apis[t] for t in r['calls']]
        assert r['api_calls']==len(allcalls)
        assert abs(sum(a['seconds'] for a in allcalls)-r['api_seconds'])<1e-7
        known=[cost(a) for a in allcalls if cost(a)[0] is not None]
        unknown=len(allcalls)-len(known)
        low=sum(c[0] for c in known); high=sum(c[1] for c in known)
        lat=[a['seconds'] for a in allcalls]
        rows.append(dict(id=r['id'],provider=r['provider'],seed=r['seed'],success=r['success'],status=r['status'],
            cycles=r['completed_cycles'],grasp_attempts=grasp_count,rejected_actions=sum(not c['execution']['accepted'] for c in r['cycles']),
            calls=r['api_calls'],api_seconds=r['api_seconds'],wall_seconds=r['wall_seconds'],sim_seconds=r['sim_seconds'],
            serial_realtime_estimate=r['api_seconds']+r['sim_seconds'],physics_compute_seconds=r['physics_compute_seconds'],
            api_p50=float(np.median(lat)) if lat else 0.,api_p95=float(np.percentile(lat,95)) if lat else 0.,
            cost_low_usd=low if not unknown else None,cost_high_usd=high if not unknown else None,
            known_cost_low_subtotal=low,known_cost_high_subtotal=high,unknown_cost_requests=unknown))
        audit.append(dict(id=r['id'],verified=r['status']!='error',recorded_prefix_verified=True,max_qpos_error=max_error,cycles=len(r['cycles'])))
    csv_write(OUT/'episodes.csv',rows); csv_write(OUT/'cycles.csv',steps)
    apirows=[]
    for a in apis.values():
        u=a.get('response',{}).get('usage',{}); lo,hi=cost(a)
        apirows.append(dict(tag=a['tag'],provider=a['provider'],probe=a['tag'].startswith('probe_'),stage=a['stage'],
            seconds=a['seconds'],headers_seconds=a.get('headers_seconds'),body_seconds=a.get('body_seconds'),
            body_after_headers_seconds=a['body_seconds']-a['headers_seconds'] if 'body_seconds' in a and 'headers_seconds' in a else None,
            request_bytes=a['request_bytes'],response_bytes=a.get('response_bytes'),
            input_tokens=u.get('input_tokens',u.get('prompt_tokens')),output_tokens=u.get('output_tokens',u.get('completion_tokens')),
            cache_hit_tokens=u.get('prompt_cache_hit_tokens'),http_status=a['http_status'],error=a['error'],
            response_model=a.get('response',{}).get('model'),cost_low_usd=lo,cost_high_usd=hi))
    csv_write(OUT/'requests.csv',apirows)
    groups={}
    final_tags={tag for r in episodes for tag in r['calls']}
    for p in ('rules','jev','deepseek'):
        rs=[r for r in rows if r['provider']==p]; aa=[a for a in apirows if a['provider']==p and a['tag'] in final_tags]
        groups[p]=dict(n=len(rs),success=sum(r['success'] for r in rs),
            mean_cycles=float(np.mean([r['cycles'] for r in rs])) if rs else None,
            median_wall=float(np.median([r['wall_seconds'] for r in rs])) if rs else None,
            median_serial_estimate=float(np.median([r['serial_realtime_estimate'] for r in rs])) if rs else None,
            calls=len(aa),api_p50=float(np.median([a['seconds'] for a in aa])) if aa else None,
            api_p95=float(np.percentile([a['seconds'] for a in aa],95)) if aa else None,
            cost_low=sum(r['known_cost_low_subtotal'] for r in rs),cost_high=sum(r['known_cost_high_subtotal'] for r in rs),
            unknown_cost_requests=sum(r['unknown_cost_requests'] for r in rs))
    paired=[]
    for seed in bench.SEEDS:
        j=next((r for r in rows if r['provider']=='jev' and r['seed']==seed),None)
        d=next((r for r in rows if r['provider']=='deepseek' and r['seed']==seed),None)
        if j and d: paired.append(dict(seed=seed,both_success=j['success'] and d['success'],
            jev_minus_deepseek_wall=j['wall_seconds']-d['wall_seconds'],
            jev_serial_time_reduction=(1-j['serial_realtime_estimate']/d['serial_realtime_estimate']) if j['success'] and d['success'] else None,
            cycle_difference=j['cycles']-d['cycles']))
    probe_pairs=[]
    for repeat in range(2):
        for index in (0,15,30,45,60,75,90,105):
            prefix=f'probe_{repeat}_{index}_'
            if prefix+'jev' in apis and prefix+'deepseek' in apis:
                j,d=apis[prefix+'jev'],apis[prefix+'deepseek']
                assert j['semantic_query']==d['semantic_query']
                valid=not j['error'] and not d['error']
                probe_pairs.append(dict(repeat=repeat,index=index,stage=j['stage'],valid=valid,jev_error=j['error'],deepseek_error=d['error'],jev_seconds=j['seconds'],
                    deepseek_seconds=d['seconds'],jev_minus_deepseek=j['seconds']-d['seconds'],
                    all_labels_agree=(j['value']==d['value']) if valid else None))
    csv_write(OUT/'matched_probes.csv',probe_pairs)
    complete=all(groups[p]['n']==3 for p in groups) and len(paired)==3 and not any(r['status']=='error' for r in rows)
    gate=(sum(x['both_success'] and x['jev_serial_time_reduction']>=.2 for x in paired)>=2
          and all(x['both_success'] for x in paired)) or (complete and groups['jev']['success']-groups['deepseek']['success']>=2)
    summary=dict(groups=groups,paired=paired,completed=complete,exploratory_advantage_gate=bool(gate) if complete else None,
                 probe_pairs=probe_pairs,all_episode_physics_verified=all(a['verified'] for a in audit))
    dump(OUT/'summary.json',summary); dump(OUT/'offline_audit.json',audit)
    make_plot(rows,apirows,probe_pairs)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

def make_plot(rows,apirows,probes):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors={'rules':'#777777','jev':'#0077BB','deepseek':'#EE7733'}
    fig,axes=plt.subplots(2,2,figsize=(11,8))
    names=list(colors)
    for x,p in enumerate(names):
        r=[a for a in rows if a['provider']==p]
        for k,a in enumerate(r):
            xx=x+(k-1)*.08
            axes[0,0].scatter(xx,a['cycles'],color=colors[p],marker='o' if a['success'] else 'x',s=50)
            axes[0,1].scatter(xx,a['serial_realtime_estimate'],color=colors[p],marker='o' if a['success'] else 'x',s=50)
    for ax,title,ylabel in [(axes[0,0],'Matched initial positions; o success, x failure','Control cycles'),
                            (axes[0,1],'Serial estimate = API wait + simulation time','Seconds (not measured hardware time)')]:
        ax.set(xticks=range(3),xticklabels=names,title=title,ylabel=ylabel,ylim=(0,None))
    for p in ('jev','deepseek'):
        v=sorted(a['seconds'] for a in apirows if a['provider']==p and not a['probe'])
        if v: axes[1,0].plot(v,np.arange(1,len(v)+1)/len(v),label=p,color=colors[p])
    axes[1,0].set(xlabel='Full request seconds',ylabel='Empirical cumulative fraction',title='All control requests (dependent observations)')
    axes[1,0].legend(frameon=False)
    for a in probes:
        axes[1,1].plot([0,1],[a['jev_seconds'],a['deepseek_seconds']],color='#aaaaaa',alpha=.55,lw=.8)
        axes[1,1].scatter([0,1],[a['jev_seconds'],a['deepseek_seconds']],c=[colors['jev'],colors['deepseek']],s=16)
    axes[1,1].set(xticks=[0,1],xticklabels=['jev','deepseek'],ylabel='Full request seconds',title='Identical-state latency probes',ylim=(0,None))
    for ax in axes.flat:
        ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Jev vs DeepSeek: shared incremental xArm7 control\nFailure duration is not time to successful completion',fontsize=14)
    fig.tight_layout(); fig.savefig(OUT/'comparison.png',dpi=180); fig.savefig(OUT/'comparison.pdf'); plt.close(fig)

if __name__=='__main__': main()
