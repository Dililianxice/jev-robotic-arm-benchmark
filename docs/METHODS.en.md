# Frozen experimental method

## Question

Given the same observation representation, initial conditions, allowed actions, explicit policy instructions, inverse kinematics and physics, does Jev repeatedly choose useful small motions more reliably or with lower service latency than fast DeepSeek? This tests execution of a supplied feedback policy, not discovering a grasping strategy, visual perception, neural decoding or general robot intelligence.

The xArm7 scene and executor are fixed at OpenRoboto commit `7a4ed8b72c3c17d7aa790678ed9660df67c10dd3`. MuJoCo 3.13.0 and NumPy 2.5.3 are pinned. Before new API trials, the original published Jev trajectory was replayed: 113 cycles, maximum qpos difference 5.5247671715275e-10, below 1e-7. Three deterministic baseline trials then completed without changes to the scene or policy conditions.

## Shared interface

Each cycle queries an intent from approach/grasp/lift/carry/lower/release/withdraw/finish, followed by one request with four choices: negative/hold/positive for X,Y,Z and open/hold/close for the gripper. The model selects directions; code determines bounded 2/4/18mm magnitudes using target distances, runs IK and executes joint trajectories. No complete grasp/placement macro or action-rollout selector is introduced. This particular upstream project has no candidate forward-physics preview for either provider.

Observations contain exact TCP/object positions, signed errors, finger/plate contacts, alignment flags and grasp stability. The scene uses physical finger contacts, not a suction weld. Physics advances 0.32 seconds per cycle and pauses during API waiting, preserving the original synchronous interface.

The original physical success predicate requires stable release in the plate for at least 0.4 seconds, an open gripper, and TCP height at least 145mm. The prompt's FINISH description uses 160mm; the unchanged physical predicate governs termination. The budget is 160 cycles.

## Providers and seeds

Jev uses `jev-1.13.0` at its official endpoint. DeepSeek uses `deepseek-flash`, thinking disabled, temperature 0, JSON output and 150 maximum output tokens at its official endpoint. Each episode reuses a requests Session. Response model names and usage are recorded. The interface differs from the original OpenRouter transport.

Both providers receive the same question generator, criteria and state representation. The motor instruction asking for a generated probability distribution is removed for both. Jev still returns its native distribution; DeepSeek outputs only label values. Neither confidence thresholds nor model-generated reasoning are used for control.

Seeds 0/1/2 are fixed. Seed 0 is the original position; seeds 1/2 jitter initial fruit XY within ±12mm. Provider order is J/D, D/J, J/D respectively. This small sequence does not eliminate service-load or temporal confounding. Different decisions cause different states later in each episode; identical-state probes separately address that source of latency variation.

## Matched-state latency probes

Before collecting new results, probes were defined from cycles 0/15/30/45/60/75/90/105 of the original Jev recording. Alternating list positions use intent or motor questions; motor queries use that recording's selected intent. Repeat the eight queries twice, reversing adjacent provider order: 16 requests per provider, 16 matched pairs.

These are repeated historical states, suitable for controlled input/latency comparison, not independent accuracy tests. Historical Jev choices are not treated as ground truth. Record time to response headers, time to full response body and total time including parsing. Header timing mixes connection, network, queuing, possible compute and buffering. Different services flush headers differently; body timing is not pure generation latency.

## Budget and stopping

Each model can make at most 960 task requests, plus 16 probes. The implemented hard guard is 992 per provider; the unused 16 are not retries or a tuning allowance. Connect/read timeouts are 10/30 seconds. There are no automatic retries, fallbacks or replacement trials. A service/schema failure writes a global stop marker; subsequent live/probe entrypoints stop. Task failure at the cycle cap remains part of the planned paired study. A file lock, pre-request attempt ledger and duplicate guards prevent silent reruns.

All 9 episodes and all requests are reported, including failures. Failed duration is never called time to successful completion. Wall time includes API waiting and accelerated local physics computation. API waiting plus simulation time is only an estimated serial real-time duration, not a hardware measurement.

The exploratory continuation gate is either: both providers complete all pairs and Jev reduces API+simulation estimated duration by ≥20% in at least 2/3 pairs; or Jev completes at least two more of the three episodes. Missing/error trials make the gate indeterminate. This is a small screening criterion, not a statistical significance test. The present result passes only the success-count branch.

After collection, recorded commands are re-executed and qpos/outcomes checked. Videos exclude API waiting and are labeled accordingly. There are no hardware connections, neural data, participant trials or claims of BCI improvement.
