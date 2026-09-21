# Results: repeated small-step robot decisions

## Finding

In this fixed configuration, Jev completed 3/3 episodes, DeepSeek Flash completed 0/3 and the deterministic controller completed 3/3. Jev also had lower matched-input client-to-service request latency. This establishes a narrow configuration-specific advantage over the tested LLM setup; it does not establish superiority over conventional control or general robotics intelligence.

The source scene, prompts and collection limits were frozen before observing new model outcomes. The benchmark preserves explicit rules, precise state, a physical finger gripper, shared IK and small Cartesian increments. The original framework is credited in the main README. The linked Zhihu article could not be retrieved; this work is not presented as an exact reproduction of that article or a separate social-media hardware demonstration.

## Every episode

| Controller | Seed | Outcome | Cycles | Requests | Simulation seconds | Wall seconds | Estimated USD |
|---|---:|---|---:|---:|---:|---:|---:|
| Jev |0|success|109|218|34.88|123.31|0.018214|
| Jev |1|success|105|210|33.60|110.89|0.017547|
| Jev |2|success|106|212|33.92|114.13|0.017712|
| DeepSeek |0|cycle cap|160|320|51.20|324.07|0.077052–0.154104|
| DeepSeek |1|cycle cap|160|320|51.20|309.36|0.077035–0.154071|
| DeepSeek |2|cycle cap|160|320|51.20|289.18|0.077387–0.154773|
| Rules |0|success|106|0|33.92|5.09|0|
| Rules |1|success|104|0|33.28|4.94|0|
| Rules |2|success|102|0|32.64|4.86|0|

The small rule-controller wall times reflect accelerated simulation; they are not five-second hardware executions. Physics pauses during model calls. DeepSeek never completed, so successful completion-time reductions are undefined for all three model pairs. Its termination time is reported for accountability, not used as a successful completion speed.

## Failure localization

All 1632 requests returned HTTP 200 and valid answers. DeepSeek repeatedly selected hold on all axes after XY alignment, although the approach target remained substantially lower. A post-hoc symptom counter found 145/146/140 such steps in its three episodes, versus zero for Jev and rules. These are dependent repeated states, not independent accuracy observations. The definition and first instances are retained in `results/failure_localization.json`.

This is a reproducible policy-execution failure in the current interface, not proof of an intrinsic inability to control arms. The question layout originated with Jev, and a single LLM generation sees the whole question collection. Prompt organization, decomposition and reasoning settings were not independently optimized for DeepSeek. Any follow-up optimization needs a separate development/test split; the present result was not repaired after inspection.

## Request timing

| Provider | Task requests | Full-request median | P95 |
|---|---:|---:|---:|
| Jev |640|0.456s|0.865s|
| DeepSeek |960|0.901s|1.273s|

Task trajectories differ, so these pooled distributions mix different phases. The fixed-state probes provide a cleaner input comparison: 16 matched pairs, Jev median 0.359415s, DeepSeek median 0.833792s. The median paired difference, Jev minus DeepSeek, is −0.440129s; Jev is faster in 15/16 pairs.

This is end-to-end service latency. Network routing, connection state, provider queuing, load, batching and hardware remain uncontrolled. Response-header and body completion timing are available in `results/requests.csv`, but neither isolates internal model inference. No claim about the cause of the timing difference is justified by this experiment alone.

An earlier high-level task-interface pilot observed Jev around 1.20s and DeepSeek around 0.92s per request. That earlier negative observation is retained in the research history; this new interface/service run does not invalidate it. Its raw records are outside this release, which covers only the current incremental-control experiment.

## Costs

Including probes, Jev made 656 requests, estimated at $0.054808656. DeepSeek made 976 requests, estimated at $0.233876232–0.467752464. Task-only estimates are in the table above.

Jev uses the published $0.042 per million input tokens, with output free. DeepSeek uses returned cache-hit/miss and completion counts; its off-peak/peak public rates give the displayed range. These are estimates rather than invoices. Request counts differ because DeepSeek reached the cap; the total cost ratio is not a pure per-decision efficiency ratio. No billing usage is missing in this collection.

Sources: [TypeSafe models/pricing](https://docs.typesafe.ai/models), [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/). The snapshot corresponds to the experimental collection date, 2026-09-21.

## Verification and interpretation

All nine trajectories were re-executed locally with maximum qpos error 0 and matching outcomes. The original upstream Jev recording was separately reproduced within 1e-7 tolerance. Interface/physics tests, adapter success/failure tests and cost edge checks passed; independent code review checked accounting and interpretation. Publication adds a portable offline verifier and sanitized records.

Only one task, one object and three small position perturbations were tested. Exact geometry, contact flags and a written policy remove much of real-world difficulty. The rule controller's 3/3 result shows that AI is unnecessary for this fixed workflow. No moving target, external disturbance, camera uncertainty, unknown object, real UR10 or human BCI loop was tested.

The practical result is that Jev deserves consideration as a repeated structured-decision component in this interface. It is not evidence that a general-purpose robot policy or thought decoder has been solved.

See [the method](METHODS.en.md), [all episode metrics](../results/episodes.csv), [the physics audit](../results/offline_audit.json), and [the data inventory](DATA.md).

![Comparison](../figures/comparison.png)
