"""Identical two-stage Cartesian interface for Jev and an ordinary LLM."""
import json
import math
import os
import time
import urllib.request

INTENTS = {
    'approach': 'Fruit not held and not already released in the plate. Open the gripper and align with the fruit grasp pose. Descend only after XY alignment.',
    'grasp': 'Close and settle the grasp: either fruit not held AND alignment.grasp_pose_reached is TRUE, OR fruit has bilateral contacts but grasp_secured is FALSE. Hold all XYZ and keep closing until grasp_secured becomes TRUE. Do not close early above the fruit.',
    'lift': 'Fruit held AND grasp_secured is TRUE, away from the plate; TCP below 165 mm. Keep fingers closed and lift vertically to travel height before moving sideways.',
    'carry': 'Fruit held, TCP at travel height (at least 165 mm), and plate X or Y alignment error exceeds 6 mm. Carry horizontally above plate center with fingers closed.',
    'lower': 'Fruit held AND alignment.over_plate is TRUE AND at_release_height is FALSE. Lower vertically with fingers closed. Never lower when away from the plate.',
    'release': 'Fruit held AND alignment.over_plate is TRUE AND alignment.at_release_height is TRUE. Open the fingers; hold XYZ. Never release away from the plate.',
    'withdraw': 'Fruit already released inside the plate, gripper open, TCP below 160 mm. Raise the open gripper vertically without regrasping.',
    'finish': 'Fruit stably released in the plate, gripper open, and TCP at least 160 mm high. The task is physically complete.'}

INTENT_INSTRUCTIONS = '''Choose the next immediate INTENT for this robot from the actual current geometry and contacts.
There is one apple and one plate. A held apple has bilateral finger contacts and a closed command; closed fingers alone do not imply held.
Use the option conditions. They define a feedback policy, not an obligation to stay in the previous intent.
The alignment fields are measured geometric checks, not previous commands. If grasp_pose_reached is false and fruit is not held, APPROACH rather than GRASP. If held but grasp_secured is false, GRASP again to let the fingers settle. If over_plate is false, do not LOWER or RELEASE.
When the apple is already released in the plate, withdraw then finish; do not approach or regrasp it.
After a verified grasp, lift at the source, carry at travel height, then lower at the plate.
When held AND already aligned over the plate, lower/release takes priority over lifting back to travel height.
Relative errors are desired position MINUS current TCP, in millimetres. Conditions use absolute magnitudes.
No teleportation or complete pick/place skill exists. Each update only executes a small Cartesian increment.'''

MOTOR_INSTRUCTIONS = '''Choose the next small motor increment for the given intent and current geometry.
Axis labels refer to the robot base frame. positive increases that coordinate; negative decreases it; hold leaves it unchanged.
Read the signed target-minus-TCP errors. A positive error requires positive motion; a negative error requires negative motion. Within 1 mm of the approach grasp target, hold that axis. For travel and placement, tolerance is 3 mm.
APPROACH: open fingers; correct X and Y using fruit_grasp_minus_tcp_mm. If either XY error exceeds 5 mm, HOLD Z (or raise if TCP is dangerously low); once aligned, correct Z toward grasp_tcp.
GRASP: HOLD all XYZ and CLOSE fingers; keep closing until bilateral contacts.
LIFT: HOLD X/Y, keep fingers CLOSED, increase Z to travel_tcp_z_mm. Hold Z when within 3 mm.
CARRY: keep fingers CLOSED, correct X/Y toward plate_center_mm; maintain Z at travel_tcp_z_mm.
LOWER: keep fingers CLOSED, correct X/Y toward plate center if necessary; decrease Z toward release_tcp_mm[2], hold Z within 3 mm.
RELEASE: HOLD XYZ and OPEN fingers.
WITHDRAW: HOLD X/Y, keep fingers OPEN, raise Z to travel height.
FINISH: HOLD all XYZ and keep fingers OPEN.
The motion must follow the selected intent. Do not keep descending once the grasp or release height is reached.
Return the actual probability distribution for this motor channel.'''


def validate_choice(answer, options):
    probs = answer.get('probabilities', {})
    if set(probs) != set(options): raise ValueError('Unexpected model choice labels')
    if any(isinstance(p, bool) or not isinstance(p, (float, int)) or not math.isfinite(p) or not 0 <= p <= 1 for p in probs.values()):
        raise ValueError('Invalid model probabilities')
    if abs(sum(probs.values()) - 1) > .025: raise ValueError('Unnormalized model probabilities')
    choice = answer.get('choice')
    if choice not in options or probs[choice] + 1e-6 < max(probs.values()):
        raise ValueError('Choice does not match distribution')
    result = {'choice': choice, 'probabilities': probs}
    confidence = answer.get('confidence')
    if confidence is not None:
        if not isinstance(confidence, (float, int)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('Invalid confidence')
        result['confidence'] = confidence
    return result


class IncrementalPolicy:
    def __init__(self, group='jev', model=None, reasoning_effort='low'):
        if group not in ('jev', 'llm'): raise ValueError('Unknown policy group')
        self.group = group
        self.model = 'typesafe/jev-1.13' if group == 'jev' else model or 'openai/gpt-4.1-mini'
        if group == 'llm' and self.model not in ('openai/gpt-4.1-mini', 'openai/gpt-6-astra'):
            raise ValueError('Unsupported comparison model')
        if reasoning_effort not in ('low', 'medium', 'high', 'xhigh', 'max'):
            raise ValueError('Unsupported reasoning effort')
        self.reasoning_effort = reasoning_effort
        self.calls = 0
        self.cost = 0.
        self.wait_seconds = 0.
        self.records = []

    def request(self, state, questions, stage):
        key = os.environ.get('OPENROUTER_API_KEY')
        if not key: raise RuntimeError('OPENROUTER_API_KEY is not configured locally.')
        if self.group == 'jev':
            payload = {'model': self.model, 'state': state, 'questions': questions}
            url = 'https://openrouter.ai/api/alpha/decisions'
        else:
            answers_schema = {}
            for name, question in questions.items():
                labels = list(question['criteria'])
                answers_schema[name] = {'type': 'object', 'properties': {
                    'choice': {'type': 'string', 'enum': labels},
                    'probabilities': {'type': 'object', 'properties': {k: {'type': 'number'} for k in labels},
                                      'required': labels, 'additionalProperties': False}},
                    'required': ['choice', 'probabilities'], 'additionalProperties': False}
            schema = {'type': 'object', 'properties': {'answers': {'type': 'object', 'properties': answers_schema,
                       'required': list(questions), 'additionalProperties': False}}, 'required': ['answers'], 'additionalProperties': False}
            payload = {'model': self.model, 'temperature': 0, 'max_tokens': 850,
                       'response_format': {'type': 'json_schema', 'json_schema': {'name': 'robot_motor_decisions', 'strict': True, 'schema': schema}},
                       'messages': [{'role': 'system', 'content':
                           'Answer every typed choice question using its instructions and criteria and the same supplied robot state. '
                           'Return the specified JSON answers. For each question, probabilities must include every option, '
                           'be finite numbers between 0 and 1, and sum to 1. Choose an option with the highest probability. '
                           'These are your self-reported assessments, not calibrated physical success probabilities. '
                           'Do not invent additional actions or call any external tools.'},
                           {'role': 'user', 'content': json.dumps({'state': state, 'questions': questions})}]}
            if self.model == 'openai/gpt-6-astra':
                payload.pop('temperature')
                payload.pop('max_tokens')
                payload.update(reasoning_effort=self.reasoning_effort, max_completion_tokens=4096)
            url = 'https://openrouter.ai/api/v1/chat/completions'
        request = urllib.request.Request(url,
            json.dumps(payload).encode(), headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=90) as response: raw = json.load(response)
        latency = time.perf_counter() - started
        self.calls += 1
        self.wait_seconds += latency
        cost = raw.get('usage', {}).get('cost')
        if cost is not None and (not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0):
            raise ValueError('Invalid provider cost')
        self.cost += cost or 0.
        parsed = raw if self.group == 'jev' else json.loads(raw['choices'][0]['message']['content'])
        if set(parsed.get('answers', {})) != set(questions): raise ValueError('Incomplete model response')
        answers = {k: validate_choice(parsed['answers'][k], q['criteria']) for k, q in questions.items()}
        record = {'stage': stage, 'group': self.group, 'model': raw.get('model', self.model), 'response_id': raw.get('id'),
                  'probability_source': 'native model distribution' if self.group == 'jev' else 'LLM self-reported distribution',
                  'answers': answers, 'latency_seconds': round(latency, 4), 'cost_usd': cost,
                  'request_options': {k: payload[k] for k in ('temperature', 'max_tokens', 'max_completion_tokens', 'reasoning_effort') if k in payload},
                  'usage': raw.get('usage', {}),
                  'observation': state, 'questions': questions}
        self.records.append(record)
        return record

    def intent(self, state):
        return self.request(state, {'intent': {'type': 'choice', 'instructions': INTENT_INSTRUCTIONS,
                                               'criteria': INTENTS}}, 'intent')

    def motor(self, state, intent):
        state = {**state, 'selected_intent': intent}
        questions = {}
        for i, axis in enumerate(('x', 'y', 'z')):
            instruction = (MOTOR_INSTRUCTIONS + f'\nCURRENT INTENT: {intent.upper()}. This question controls ONLY {axis.upper()}. '
                           f'Current {axis.upper()}={state["tcp_mm"][i]} mm. '
                           f'Fruit grasp {axis.upper()}={state["grasp_tcp_mm"][i]} mm. '
                           f'Fruit grasp minus current on this axis={state["fruit_grasp_minus_tcp_mm"][i]} mm. '
                           f'Plate release {axis.upper()}={state["release_tcp_mm"][i]} mm. '
                           f'Plate release minus current on this axis={state["plate_release_minus_tcp_mm"][i]} mm. '
                           'Use ONLY this axis for this answer; do not answer for another axis.')
            questions[axis] = {'type': 'choice', 'instructions': instruction,
                               'criteria': {'negative': f'Move {axis.upper()} toward a SMALLER coordinate. Correct when the relevant target {axis.upper()} is below current {axis.upper()} beyond tolerance, and intent permits motion on this axis.',
                                            'hold': f'Do not move {axis.upper()}. Correct if intent requires holding this axis or relevant target error is within tolerance.',
                                            'positive': f'Move {axis.upper()} toward a LARGER coordinate. Correct when the relevant target {axis.upper()} is above current {axis.upper()} beyond tolerance, and intent permits motion on this axis.'}}
        questions['gripper'] = {'type': 'choice', 'instructions': MOTOR_INSTRUCTIONS + ' Decide only the gripper.',
                                'criteria': {'open': 'Open the fingers.', 'hold': 'Keep the current finger command.', 'close': 'Close the fingers.'}}
        return self.request(state, questions, 'motor')
