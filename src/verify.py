"""Verify published trajectories and decisions offline. No credential reads or HTTP clients."""
import argparse, gzip, hashlib, json, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from incremental_env import IncrementalEnv
from incremental_policy import IncrementalPolicy,validate_choice

def load(path): return json.loads(gzip.decompress(path.read_bytes()))

class Questions(IncrementalPolicy):
    def request(self,state,questions,stage):
        for q in questions.values():
            q['instructions']=q['instructions'].replace('Return the actual probability distribution for this motor channel.','')
        return dict(state=state,questions=questions,stage=stage)

def verify(tolerance=1e-7):
    for line in (ROOT/'CHECKSUMS.sha256').read_text().splitlines():
        expected,name=line.split('  ',1)
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected, name
    decisions={r['tag']:r for r in load(ROOT/'data/decisions.json.gz')}
    assert len(decisions)==1632
    for r in decisions.values():
        assert r['http_status']==200 and r['error'] is None
        q=r['semantic_query']['questions']
        if r['provider']=='jev':
            answer={k:validate_choice(r['response']['answers'][k],v['criteria'])['choice'] for k,v in q.items()}
        else:
            assert r['response']['choices'][0]['finish_reason']=='stop'
            answer=json.loads(r['response']['choices'][0]['message']['content'])
        assert answer==r['value']
    qb=Questions(); results=[]
    for path in sorted((ROOT/'data/trajectories').glob('*.json.gz')):
        r=load(path); env=IncrementalEnv(r['seed'],render=False); maximum=0.
        try:
            assert env.observe()==r['initial']
            np.testing.assert_allclose(env.data.qpos,r['initial_qpos'],atol=tolerance,rtol=0)
            for c in r['cycles']:
                if r['provider']!='rules':
                    a=decisions[f'{r["id"]}_{c["index"]:03}_intent']
                    b=decisions[f'{r["id"]}_{c["index"]:03}_motor']
                    assert a['semantic_query']==qb.intent(c['before'])
                    assert b['semantic_query']==qb.motor(c['before'],c['intent'])
                    assert a['value']['intent']==c['intent'] and b['value']==c['motor']
                result=env.increment(c['motor'],c['intent'])
                assert result['accepted']==c['execution']['accepted']
                assert result['requested_delta_mm']==c['execution']['requested_delta_mm']
                error=float(np.max(np.abs(env.data.qpos-c['qpos'])))
                maximum=max(maximum,error)
                assert error<=tolerance,(r['id'],c['index'],error)
            assert env.success()==r['success']
            assert len(r['calls'])==r['api_calls']
            assert abs(sum(decisions[t]['seconds'] for t in r['calls'])-r['api_seconds'])<1e-7
            results.append(dict(id=r['id'],success=env.success(),cycles=len(r['cycles']),max_qpos_error=maximum))
        finally: env.close()
    assert len(results)==9
    probes=[]
    for repeat in range(2):
        for index in [0,15,30,45,60,75,90,105]:
            j,d=[decisions[f'probe_{repeat}_{index}_{p}'] for p in ['jev','deepseek']]
            assert j['semantic_query']==d['semantic_query']
            probes.append(j['seconds']-d['seconds'])
    return dict(verified=True,network_calls=0,credential_reads=0,qpos_tolerance=tolerance,episodes=results,
                matched_probe_pairs=len(probes),median_probe_delta_jev_minus_deepseek=float(np.median(probes)))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path)
    args=parser.parse_args(); result=verify(); text=json.dumps(result,indent=2)
    if args.output: args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(text)
    print(text)
