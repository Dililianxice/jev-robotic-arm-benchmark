# Jev Robotic Arm Benchmark

### Does Jev work better when a robot needs a decision at every small step?

[中文](README.md) · **English**

I wanted to test more than whether an AI could describe a grasping plan. Could it repeatedly choose the right motion direction and gripper command, then actually finish the task?

This experiment connects **Jev 1.13** and **DeepSeek Flash with thinking disabled** to the same xArm7 simulation, with the same observation representation, initial conditions, action choices and physical executor. Their closed-loop states can diverge after different decisions. A deterministic implementation of the supplied rules is included as a baseline. **This is a small, auditable comparison—not a general robotics leaderboard.**

## Results

| Controller | Success | Cycles across three seeds | Matched-input request median | Estimated cost, including probes |
|---|---:|---|---:|---:|
| **Jev 1.13** | **3/3** | 109 / 105 / 106 | **0.359 s** | **$0.05481** |
| DeepSeek Flash | 0/3 | 160 / 160 / 160, capped | 0.834 s | $0.23388–0.46775 |
| Deterministic rules | 3/3 | 106 / 104 / 102 | No model calls | $0 |

The latency numbers come from **16 interleaved pairs with identical inputs**; Jev was faster in 15 pairs. They measure complete client-to-service requests, including network and service waiting, **not internal model inference**. Costs use recorded token usage and published rates, not account invoices. Jev made 640 task requests and DeepSeek 960, plus 16 probes each.

The three seeds only perturb the initial object position in the same task. Hundreds of dependent requests are not hundreds of independent robotics trials. Because DeepSeek did not complete, we do **not** claim a multiplier for successful task-completion speed. The exploratory gate passed through its success-count branch.

![Results](figures/comparison.png)

## Watch both outcomes

![Jev incremental control preview](media/jev-preview.gif)

*This GIF shows simulated motion at approximately 3× playback speed and excludes API waiting. It is not an end-to-end speed measurement. Full success and failure videos follow.*

The task is to grasp an apple, place it in a plate, release it, and withdraw upward.

| Jev: completed | DeepSeek: stalled after horizontal alignment |
|---|---|
| [![Jev](media/jev_seed0_final.jpg)](media/jev_seed0.mp4) | [![DeepSeek](media/deepseek_seed0_final.jpg)](media/deepseek_seed0.mp4) |
| [Watch/download video](https://github.com/Dililianxice/jev-robotic-arm-benchmark/raw/refs/heads/main/media/jev_seed0.mp4) | [Watch/download video](https://github.com/Dililianxice/jev-robotic-arm-benchmark/raw/refs/heads/main/media/deepseek_seed0.mp4) |

**Videos replay recorded actions through physics and exclude API waiting.** The overlays show simulation time and the recorded wall time at the end of the current step. This Jev trial took about 123 seconds in wall time, while its video lasts about 35 seconds. DeepSeek took about 324 seconds before the cap, with a 51-second video. Playback speed is not end-to-end control speed.

DeepSeek's failures were not API errors. After horizontal alignment, it repeatedly selected hold on all XYZ axes despite needing to descend. All successful and unsuccessful trials are published.

## What Jev does

Each cycle makes two requests: select one of eight intents, then select negative/hold/positive on each XYZ axis and open/hold/close for the gripper. Shared code determines increment magnitude, inverse kinematics and joint control. MuJoCo supplies the next geometry and contact state.

Jev returns native typed choices and probabilities; this experiment uses the choices without an extra confidence filter. DeepSeek returns short JSON labels, without explanations or self-reported probabilities. Neither model outputs torques, and there is no complete pick-and-place macro behind one action. However, the grasping policy is already described in the prompts and the observations contain exact simulation state.

## What the result means

**Jev was more reliable than this fast DeepSeek configuration in the frozen small-step interface, with lower matched-input request latency.** That is a concrete result worth retaining.

The rule controller also succeeded 3/3 without model calls. This fixed task therefore does not demonstrate a need for AI over a dedicated controller.

The question layout was designed for Jev's separate-question interface; DeepSeek processes the complete question set in one generation request. This is **not an independently optimized DeepSeek system**. Prompt organization or reasoning settings could change the outcome. There is only one object/task and small position jitter, no visual uncertainty or novel objects. Physics pauses during API calls, so this does not test moving targets, disturbances, or real UR10 safety. There are no neural data or human closed-loop trials; future BCI assistance is motivation, not an established result.

## Reproduce offline, without credentials

Use Python 3.12:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python src/summarize.py
python src/verify.py --output local_outputs/verification.json
```

The verifier checks file hashes, prompt/action correspondence, all nine physical trajectories, outcomes and sixteen matched probe pairs. It reads no credentials, makes no network requests and connects to no hardware. Cross-platform qpos tolerance is `1e-7`; the original local replay error was zero. Mismatches fail visibly.

Optional rendering requires a working OpenGL backend:

```bash
python src/render.py jev_seed0 --output local_outputs/jev.mp4
```

For headless Linux, configure EGL or OSMesa, for example `MUJOCO_GL=osmesa`. Pre-rendered MP4 files are included. The `archive/` directory preserves collection logic for inspection; it is not the portable public execution entrypoint. This release does not start new paid experiments by default.

- [Detailed English report](docs/REPORT.en.md) / [中文报告](docs/REPORT.zh.md)
- [Methods](docs/METHODS.en.md) / [冻结方案](docs/PROTOCOL.zh.md)
- [Episode results](results/episodes.csv), [request metrics](results/requests.csv), [matched probes](results/matched_probes.csv)
- [Publication verification](results/publication_verification.json), [data and privacy notes](docs/DATA.md), [provenance](docs/PROVENANCE.json)

## Attribution

Published by **Dililianxice**. My contribution is the official-endpoint Jev/DeepSeek adaptation, matched comparison, deterministic baseline, latency probes, auditing and reporting. The xArm7 scene and incremental-control framework come from **[OpenRoboto's project](https://github.com/openroboto-ai/jev-robot-control)** at commit `7a4ed8b72c3c17d7aa790678ed9660df67c10dd3`; its published comparison used GPT-6 Astra and GPT-4.1 mini, not DeepSeek.

Robot assets originate from MuJoCo Menagerie/UFACTORY. Licenses and notices are retained; see [third-party notices](THIRD_PARTY_NOTICES.md). This is an independent experiment, not an official evaluation or partnership with the providers. Codex assisted code, analysis and documentation; records were programmatically verified and independently code-reviewed.

Project code: MIT. Robot assets: BSD-3-Clause. Citation metadata: [CITATION.cff](CITATION.cff).
