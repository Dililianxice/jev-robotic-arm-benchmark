# 数据、隐私与复现 / Data, privacy and reproducibility

本发布包只包含本轮人工构造的机械臂仿真及其模型决策，不包含脑信号、聊天原文、个人数据或其他项目材料。

|路径 / Path|内容 / Contents|
|---|---|
|`data/trajectories/*.json.gz`|9局状态、动作、物理反馈、qpos/qvel与相对时间 / Nine complete episode trajectories|
|`data/decisions.json.gz`|1632条脱敏决策记录：提示、公开API参数、回答、token用量和耗时 / Sanitized decisions, prompts, answers, usage and timings|
|`results/`|逐局、逐步、逐请求、同状态探针及离线验证 / CSV and JSON analysis outputs|
|`vendor/`|固定版本的场景、运动学、问题构造与机器人模型 / Pinned upstream components and assets|
|`archive/`|原采集、分析、诊断及适配测试逻辑，供审阅 / Collection and analysis source archive, not a portable run entrypoint|
|`src/`|公开包的离线汇总、物理验证和视频重放入口 / Portable offline entrypoints|
|`media/`|本轮seed0两组视频与最终状态截图 / Locally generated videos and final frames|

## 删除与保留 / Removed and retained

未复制 `.env`、密钥、认证头、账号邮箱、个人绝对路径、Python运行时、模型权重或其他项目。删除了模型服务返回的请求ID、创建时间、system fingerprint、service tier及请求UTC起始时间。媒体是本次自己生成的仿真录像，不是下载的社交媒体视频。

No credentials, credential files, authorization headers, account email, personal absolute paths, runtimes, weights or unrelated projects are distributed. Service response IDs, creation timestamps, system fingerprints, service tiers and request UTC start timestamps were removed. Videos were generated from this experiment, not copied from social media.

模型名称、公开接口地址、参数名、提示、合成状态、输出选择及概率、token用量、相对耗时不是密钥，保留它们以支持复查。`request_bytes`/`response_bytes`描述原HTTP消息长度，脱敏后的文件字节数会不同。内部 `jev_seed0` 等标签只是试验编号，不是服务请求ID。

Model names, public endpoint URLs, parameter names, prompts, synthetic observations, choices/probabilities, token counts and elapsed timings remain for auditability. Recorded byte counts describe original HTTP messages, not sanitized file sizes. Episode tags are experiment labels, not provider request IDs.

## 可以与不可以复现什么 / Reproducibility boundary

`src/verify.py` 检查SHA256、记录问题与动作对应、完整物理重放及成败；`src/summarize.py` 重新计算成功数、延迟和公开单价费用。重放不调用模型，因此不能重新测量当时的服务延迟，也不能证明第三方服务记录的真实性；它验证的是这些公开记录之间的一致性和可执行性。

Offline verification checks file integrity, recorded prompt/action correspondence, physical trajectories and outcomes. Summarization recomputes success counts, latency summaries and estimated costs. Replay does not remeasure historical provider latency or independently authenticate provider responses; it establishes internal consistency and executable physical outcomes of the published records.

初始哈希用于证明发布后的文件完整性，不是数字签名。Linux离线验证已执行；跨平台差异若超过容差会报错。公开渲染脚本使用便携字体，画面标注样式可与原视频略有不同。

Checksums are integrity records, not digital signatures. Portable verification was run on Linux; cross-platform numeric differences beyond tolerance fail explicitly. The portable renderer uses a different available font, so overlays may differ visually from the original videos.
