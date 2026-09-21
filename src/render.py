"""Render an offline trajectory. The video excludes recorded API waiting."""
import argparse,gzip,json,sys
from pathlib import Path
import numpy as np
import imageio.v2 as imageio
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from incremental_env import IncrementalEnv
def render(episode,output):
    r=json.loads(gzip.decompress((ROOT/'data/trajectories'/f'{episode}.json.gz').read_bytes()))
    e=IncrementalEnv(r['seed'],render=True); output.parent.mkdir(parents=True,exist_ok=True)
    writer=imageio.get_writer(str(output),fps=15.625,codec='libx264',quality=7,macro_block_size=2)
    font=ImageFont.load_default(size=19); current=None
    def frame(env):
        if env.steps%32:return
        pic=Image.fromarray(env.render());d=ImageDraw.Draw(pic)
        d.rectangle((0,0,1000,95),fill='#14212d')
        d.text((12,10),f'{episode} | cycle {current["index"]+1} | {current["intent"]}',font=font,fill='white')
        d.text((12,38),f'Simulation {env.elapsed:.2f}s | recorded step-end wall {current["wall_seconds"]:.1f}s',font=font,fill='white')
        d.text((12,66),'OFFLINE REPLAY: API waiting excluded from video time',font=font,fill='#ffda7a')
        writer.append_data(np.array(pic))
    e.on_frame=frame
    try:
        for c in r['cycles']:
            current=c;e.increment(c['motor'],c['intent'])
            assert np.max(np.abs(e.data.qpos-c['qpos']))<1e-7
    finally:writer.close();e.close()
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('episode');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();render(a.episode,a.output)
