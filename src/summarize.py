"""Recompute summary metrics from sanitized decisions and trajectories; standard library only."""
import gzip,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(p): return json.loads(gzip.decompress(p.read_bytes()))
data=load(ROOT/'data/decisions.json.gz')
episodes=[load(p) for p in sorted((ROOT/'data/trajectories').glob('*.json.gz'))]
groups={}
for provider in ['rules','jev','deepseek']:
    es=[r for r in episodes if r['provider']==provider]
    main=[r for r in data if r['provider']==provider and not r['tag'].startswith('probe_')]
    probes=[r for r in data if r['provider']==provider and r['tag'].startswith('probe_')]
    requests=main+probes; low=high=0.
    for r in requests:
        u=r['response']['usage']
        if provider=='jev':lo=hi=u['input_tokens']*.042/1e6
        else:
            lo=(u['prompt_cache_hit_tokens']*.003+u['prompt_cache_miss_tokens']*.15+u['completion_tokens']*.6)/1e6
            hi=2*lo
        low+=lo; high+=hi
    groups[provider]=dict(success=sum(e['success'] for e in es),n=len(es),cycles=[e['completed_cycles'] for e in es],
        main_requests=len(main),probe_requests=len(probes),
        main_request_p50_seconds=statistics.median(r['seconds'] for r in main) if main else None,
        identical_state_probe_p50_seconds=statistics.median(r['seconds'] for r in probes) if probes else None,
        estimated_total_cost_usd=[low,high])
print(json.dumps(groups,indent=2))
