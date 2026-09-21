"""Post-hoc descriptive failure localization, never a tuning loop or accuracy gold standard."""
import json
from pathlib import Path
from collections import Counter
from bench import OUT, dump

def main():
    result=[]
    for p in sorted((OUT/'episodes').glob('*.json')):
        r=json.loads(p.read_text()); cs=r['cycles']; stalls=[]
        for c in cs:
            s=c['before']; err=s['fruit_grasp_minus_tcp_mm']
            if (c['intent']=='approach' and not s['held'] and max(abs(e) for e in err[:2])<=5
                and abs(err[2])>5 and all(c['motor'][axis]=='hold' for axis in ('x','y','z'))):
                stalls.append(dict(cycle=c['index'],tcp_mm=s['tcp_mm'],grasp_error_mm=err,motor=c['motor']))
        result.append(dict(id=r['id'],status=r['status'],intent_counts=dict(Counter(c['intent'] for c in cs)),
            all_xyz_hold_count=sum(all(c['motor'][a]=='hold' for a in ('x','y','z')) for c in cs),
            approach_aligned_but_xyz_hold_count=len(stalls),first_example=stalls[0] if stalls else None,
            note='Post-hoc symptom count. Repeated dependent states are not independent accuracy trials.'))
    dump(OUT/'failure_localization.json',result)
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
