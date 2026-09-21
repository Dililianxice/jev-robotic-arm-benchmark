"""Approved paired small-motion comparison; immutable upstream physics, local simulation only."""
import os
os.environ.setdefault('MUJOCO_GL', 'osmesa')
os.environ.setdefault('PYOPENGL_PLATFORM', 'osmesa')
import argparse, hashlib, json, sys, time, fcntl
from pathlib import Path
import numpy as np
import requests
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / 'outputs/robot_physics_v3'
UP = HERE / 'upstream'
sys.path.insert(0, str(UP))
from incremental_env import IncrementalEnv
from incremental_policy import IncrementalPolicy, validate_choice

SEEDS = [0, 1, 2]
MAX_CYCLES = 160
MAX_REQUESTS = 992  # 3 * 160 * 2 plus 32 matched-state probes

def dump(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    tmp.replace(path)

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def credential(name):
    p = ROOT / '.env'
    if p.is_symlink() or p.stat().st_mode & 0o077:
        raise RuntimeError('Credential file must be private')
    for line in p.read_text().splitlines():
        if line.startswith(name + '='): return line.split('=', 1)[1].strip()
    raise RuntimeError('Missing local credential')

class Questions(IncrementalPolicy):
    def request(self, state, questions, stage):
        # Both providers receive identical criteria and state. Neither is asked to
        # generate a probability distribution; Jev supplies its native one anyway.
        for q in questions.values():
            q['instructions'] = q['instructions'].replace(
                'Return the actual probability distribution for this motor channel.', '')
        return dict(state=state, questions=questions, stage=stage)

def rules(s):
    a = s['alignment']; z = s['tcp_mm'][2]
    if s['fruit_in_plate'] and s['gripper_command'] == 'open':
        intent = 'finish' if s['stable_released_in_plate'] and z >= 160 else 'withdraw'
    elif not s['held']:
        intent = 'grasp' if a['grasp_pose_reached'] else 'approach'
    elif not s['grasp_secured']: intent = 'grasp'
    elif a['over_plate']: intent = 'release' if a['at_release_height'] else 'lower'
    elif not a['at_travel_height']: intent = 'lift'
    else: intent = 'carry'
    motor = dict(x='hold', y='hold', z='hold', gripper='close')
    def direction(error, tolerance):
        return 'hold' if abs(error) <= tolerance else ('positive' if error > 0 else 'negative')
    if intent == 'approach':
        err = s['fruit_grasp_minus_tcp_mm']; motor['gripper'] = 'open'
        for axis, e in zip(('x', 'y'), err[:2]): motor[axis] = direction(e, 1)
        if max(abs(e) for e in err[:2]) <= 5: motor['z'] = direction(err[2], 1)
        elif z < s['grasp_tcp_mm'][2]: motor['z'] = 'positive'
    elif intent in ('lift', 'withdraw'):
        motor['z'] = direction(s['travel_tcp_z_mm'] - z, 3)
        if intent == 'withdraw': motor['gripper'] = 'open'
    elif intent in ('carry', 'lower'):
        for axis, e in zip(('x', 'y'), s['plate_release_minus_tcp_mm'][:2]):
            motor[axis] = direction(e, 3)
        motor['z'] = direction((s['travel_tcp_z_mm'] if intent == 'carry' else s['release_tcp_mm'][2]) - z, 3)
    elif intent in ('release', 'finish'): motor['gripper'] = 'open'
    return intent, motor

class Client:
    def __init__(self, provider):
        self.provider = provider
        self.key = credential('TYPESAFE_API_KEY' if provider == 'jev' else 'DEEPSEEK_API_KEY')
        self.session = requests.Session()
        self.count = 0
        self.records = []

    def call(self, query, tag):
        provider = self.provider
        stop = HERE / 'collection.stopped'
        if stop.exists(): raise RuntimeError('Provider stopped after failure')
        state, questions = query['state'], query['questions']
        if provider == 'jev':
            url = 'https://api.typesafe.ai/v1/systemone'
            payload = dict(model='jev-1.13.0', state=state, questions=questions)
        else:
            url = 'https://api.deepseek.com/chat/completions'
            payload = dict(model='deepseek-flash', thinking={'type':'disabled'}, temperature=0,
                max_tokens=150, response_format={'type':'json_object'}, messages=[
                dict(role='system', content='Answer each choice question using the supplied state, instructions and criteria. '
                    'Return one JSON object mapping each question key directly to its selected option label. '
                    'No explanations, probabilities, extra keys, tools or actions.'),
                dict(role='user', content=json.dumps(dict(state=state, questions=questions)))])
        assert self.key and self.key not in json.dumps(payload)
        ledger = HERE / (provider + '_attempts.jsonl')
        old = [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
        if len(old) >= MAX_REQUESTS or any(r['tag'] == tag for r in old):
            raise RuntimeError('Request budget or duplicate guard')
        target = HERE / 'api' / (tag + '.json')
        if target.exists(): raise RuntimeError('Request already exists')
        with ledger.open('a') as f:
            f.write(json.dumps(dict(tag=tag, time=time.time(), payload_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())) + '\n')
            f.flush(); os.fsync(f.fileno())
        started = time.perf_counter(); status = None
        record = dict(provider=provider, tag=tag, stage=query['stage'], request=payload,
                      semantic_query=query, request_bytes=len(json.dumps(payload).encode()), utc_start=time.time())
        try:
            response = self.session.post(url, json=payload, headers={'Authorization':'Bearer ' + self.key},
                timeout=(10, 30), allow_redirects=False, stream=True)
            headers_seconds = time.perf_counter() - started
            status = response.status_code
            record.update(headers_seconds=headers_seconds, http_status=status)
            raw = response.content
            body_seconds = time.perf_counter() - started
            record.update(body_seconds=body_seconds, response_bytes=len(raw))
            if status != 200: raise ValueError('HTTP failure')
            body = json.loads(raw)
            if self.key in json.dumps(body): raise ValueError('Credential echo')
            if provider == 'jev':
                if set(body['answers']) != set(questions): raise ValueError('Wrong question keys')
                value = {k: validate_choice(body['answers'][k], q['criteria'])['choice'] for k, q in questions.items()}
            else:
                if body['choices'][0].get('finish_reason') != 'stop': raise ValueError('Incomplete answer')
                value = json.loads(body['choices'][0]['message']['content'])
                if set(value) != set(questions) or any(value[k] not in q['criteria'] for k, q in questions.items()):
                    raise ValueError('Invalid answer')
            record.update(value=value, response=body, http_status=status, error=None,
                          headers_seconds=headers_seconds, body_seconds=body_seconds, response_bytes=len(raw))
        except Exception:
            record.update(value=None, http_status=status, error='provider_or_schema_failure')
            stop.write_text('Stop after first failed request; no retries.\n')
        record['seconds'] = time.perf_counter() - started
        self.count += 1; self.records.append(record); dump(target, record)
        if record['error']: raise RuntimeError('Provider request failed; record saved without error body')
        return record

def replay_original():
    source = next(UP.glob('incremental-gpt6-comparisons/*/jev/*.json'))
    r = json.loads(source.read_text()); e = IncrementalEnv(r['seed'], render=False)
    errors = []
    try:
        for c in r['cycles']:
            e.increment({k:v['choice'] for k,v in c['motor']['answers'].items()}, c['intent']['answers']['intent']['choice'])
            errors.append(float(np.max(np.abs(e.data.qpos - c['qpos']))))
        result = dict(source=str(source.relative_to(HERE)), source_sha256=sha(source),
                      cycles=len(errors), max_qpos_error=max(errors), success=e.success(), expected_success=r['success'])
        result['verified'] = result['max_qpos_error'] <= 1e-7 and result['success'] == result['expected_success']
        dump(OUT / 'upstream_replay.json', result)
        print(json.dumps(result), flush=True)
        if not result['verified']: raise RuntimeError('Original physics replay mismatch')
    finally: e.close()

def episode(provider, seed):
    ident = f'{provider}_seed{seed}'; directory = OUT / 'episodes'; directory.mkdir(exist_ok=True, parents=True)
    path = directory / (ident + '.json')
    journal = directory / (ident + '.jsonl')
    if path.exists() or journal.exists(): raise RuntimeError('Episode already started; no silent rerun')
    with journal.open('x'): pass
    start = time.perf_counter(); e = IncrementalEnv(seed, render=False)
    init_seconds = time.perf_counter() - start
    client = None if provider == 'rules' else Client(provider)
    qb = Questions(); cycles = []; api_seconds = 0.; physics_seconds = 0.; calls = []
    result = dict(id=ident, provider=provider, seed=seed, status='running', success=False,
                  initial=e.observe(), initial_qpos=e.data.qpos.tolist(), initialization_seconds=init_seconds)
    try:
        for i in range(MAX_CYCLES):
            s = e.observe()
            if client:
                a = client.call(qb.intent(s), f'{ident}_{i:03}_intent'); calls.append(a['tag']); api_seconds += a['seconds']
                intent = a['value']['intent']
                b = client.call(qb.motor(s, intent), f'{ident}_{i:03}_motor'); calls.append(b['tag']); api_seconds += b['seconds']
                motor = b['value']
            else: intent, motor = rules(s)
            t = time.perf_counter(); execution = e.increment(motor, intent); physics_seconds += time.perf_counter() - t
            cycle = dict(index=i, before=s, intent=intent, motor=motor, execution=execution,
                         after=e.observe(), qpos=e.data.qpos.tolist(), qvel=e.data.qvel.tolist(), wall_seconds=time.perf_counter()-start)
            cycles.append(cycle)
            with journal.open('a') as f: f.write(json.dumps(cycle) + '\n')
            if i % 10 == 0:
                print(json.dumps(dict(id=ident, cycle=i+1, intent=intent, held=cycle['after']['held'],
                                      in_plate=cycle['after']['fruit_in_plate'], wall=round(time.perf_counter()-start, 2))), flush=True)
            if e.success(): result.update(status='success', success=True); break
        else: result['status'] = 'cycle_cap'
    except Exception:
        result['status'] = 'error'; result['error'] = 'See sanitized API record or local traceback audit'
        raise
    finally:
        if client:
            calls = [r['tag'] for r in client.records]
            api_seconds = sum(r['seconds'] for r in client.records)
        result.update(cycles=cycles, calls=calls, completed_cycles=len(cycles), api_calls=client.count if client else 0,
                      api_seconds=api_seconds, physics_compute_seconds=physics_seconds,
                      wall_seconds=time.perf_counter()-start, sim_seconds=e.observe()['sim_seconds'], final=e.observe())
        dump(path, result); e.close()
    print(json.dumps({k:v for k,v in result.items() if k not in ('cycles','calls','initial','final','initial_qpos')}), flush=True)
    return result

def probes():
    source = json.loads(next(UP.glob('incremental-gpt6-comparisons/*/jev/*.json')).read_text())
    clients = {p:Client(p) for p in ('jev','deepseek')}; qb = Questions()
    for repeat in range(2):
        for j, index in enumerate([0, 15, 30, 45, 60, 75, 90, 105]):
            c = source['cycles'][index]; s = c['before']
            query = qb.intent(s) if j % 2 == 0 else qb.motor(s, c['intent']['answers']['intent']['choice'])
            for p in (['jev','deepseek'] if (repeat+j)%2 == 0 else ['deepseek','jev']):
                clients[p].call(query, f'probe_{repeat}_{index}_{p}')
    # 16 requests/provider; remaining reserve is unused, never a tuning budget.

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('mode', choices=['replay','rules','live','probes'])
    args=parser.parse_args(); OUT.mkdir(parents=True, exist_ok=True)
    with (HERE/'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.mode == 'replay': replay_original()
        elif args.mode == 'rules':
            for seed in SEEDS: episode('rules', seed)
        else:
            manifest = json.loads((HERE/'manifest.json').read_text())
            if (HERE/'collection.stopped').exists(): raise RuntimeError('Collection stopped after failure')
            for name, expected in manifest['hashes'].items():
                if sha(HERE/name) != expected: raise RuntimeError('Frozen source changed: '+name)
            replay = json.loads((OUT/'upstream_replay.json').read_text())
            if not replay['verified'] or sha(HERE/replay['source']) != replay['source_sha256']:
                raise RuntimeError('Original replay prerequisite not satisfied')
            if args.mode == 'probes': probes()
            else:
                for seed in SEEDS:
                    for p in (['jev','deepseek'] if seed%2 == 0 else ['deepseek','jev']): episode(p, seed)

if __name__ == '__main__': main()
