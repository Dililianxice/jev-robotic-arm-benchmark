# Third-party materials

## xArm7 model and meshes

The files under `robot/` are the UFACTORY xArm7 model from
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie/tree/8161bba264d7fa7c99ca301e91e7fb44737676ad/ufactory_xarm7).
The local source revision used to build the experiment is
`8161bba264d7fa7c99ca301e91e7fb44737676ad`.
Copyright (c) 2018, UFACTORY Inc. BSD-3-Clause; the complete notice is in
[`robot/LICENSE`](robot/LICENSE). The checked-in XML is unchanged from that revision.
Scene changes such as the table, apple, plate, lights, friction and TCP site offset
are applied in `incremental_env.py` when loading the model.

## Runtime dependencies

MuJoCo, NumPy, Pillow, imageio and imageio-ffmpeg are installed separately;
their respective upstream licenses apply. Their package versions are pinned in
`requirements.txt`. No Python runtime, model weights or FFmpeg executable is vendored.

## Branding and video

OpenRoboto branding and the recorded comparison media are provided by OpenRoboto.
The browser pages use system fonts. The pre-rendered video contains rasterized
text; no proprietary font files are redistributed.
