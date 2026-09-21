"""One apple, one plate; bounded Cartesian increments and contact-only transport."""
from pathlib import Path
import math
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
from simulation import Simulation, HOME

ROOT = Path(__file__).resolve().parent
PLATE = np.array([.44, .17, .008])
RADIUS = .027
TRAVEL_Z = .170
RELEASE_Z = .043
STEP_SECONDS = .32


def scene_xml():
    root = ET.parse(ROOT / 'robot/xarm7.xml').getroot()
    root.set('model', 'Jev / incremental XYZ')
    root.find('compiler').set('meshdir', str(ROOT / 'robot/assets'))
    root.find('option').set('timestep', '.002')
    root.remove(root.find('keyframe'))
    root.find(".//site[@name='link_tcp']").set('pos', '0 0 .145')
    for cls in ('pad_box1', 'pad_box2'):
        root.find(f".//default[@class='{cls}']/geom").set('friction', '1.5 .01 .001')
    asset, world = root.find('asset'), root.find('worldbody')
    for mat in asset.findall('material'):
        name = mat.get('name')
        mat.set('specular', '.24' if name != 'black' else '.08')
        mat.set('shininess', '.35')
        if name == 'white': mat.set('rgba', '.83 .845 .85 1')
    for name, color, spec in [('worktop', '.97 .975 .97 1', '.07'),
                              ('floor', '.95 .955 .95 1', '.02'),
                              ('metal', '.45 .48 .50 1', '.4'),
                              ('apple_skin', '.68 .055 .042 1', '.14'),
                              ('ceramic', '.88 .89 .86 1', '.24')]:
        ET.SubElement(asset, 'material', name=name, rgba=color, specular=spec, shininess='.25')
    ET.SubElement(asset, 'texture', name='studio_sky', type='skybox', builtin='gradient',
                  rgb1='.95 .95 .93', rgb2='.95 .95 .93', width='512', height='3072')
    visual = ET.SubElement(root, 'visual')
    ET.SubElement(visual, 'global', offwidth='1280', offheight='900')
    ET.SubElement(visual, 'headlight', diffuse='.25 .25 .25', ambient='.37 .37 .37', specular='.07 .07 .07')
    ET.SubElement(visual, 'quality', shadowsize='4096')
    ET.SubElement(world, 'geom', name='table', type='box', size='.60 .49 .022',
                  pos='.29 .03 -.022', material='worktop', friction='1 .01 .001')
    ET.SubElement(world, 'geom', name='floor', type='plane', size='6 6 .05',
                  pos='0 0 -.77', material='floor')
    ET.SubElement(world, 'geom', name='pedestal', type='cylinder', size='.073 .06',
                  pos='0 0 .06', rgba='.13 .15 .16 1')
    for x in (-.24, .82):
        for y in (-.40, .45):
            ET.SubElement(world, 'geom', type='box', size='.025 .025 .36',
                          pos=f'{x} {y} -.405', material='metal', contype='0', conaffinity='0')
    ET.SubElement(world, 'light', pos='-.5 -.7 2.4', dir='.25 .15 -1',
                  diffuse='.48 .46 .43', specular='.30 .30 .30', directional='true')
    ET.SubElement(world, 'light', pos='1.4 .8 1.7', dir='-.5 -.4 -1',
                  diffuse='.25 .26 .28', castshadow='false')
    fruit = ET.SubElement(world, 'body', name='fruit', pos='.38 -.13 .027')
    ET.SubElement(fruit, 'freejoint', name='fruit_joint')
    ET.SubElement(fruit, 'inertial', pos='0 0 0', mass='.065', diaginertia='.000018 .000019 .000019')
    ET.SubElement(fruit, 'geom', name='fruit_geom', type='ellipsoid', size='.027 .026 .026',
                  material='apple_skin', mass='.065', friction='1.5 .01 .005', condim='6', solref='.006 1')
    ET.SubElement(fruit, 'geom', name='stem', type='capsule', fromto='0 0 .022 .003 0 .034',
                  size='.0018', rgba='.22 .12 .055 1', mass='.0001', contype='0', conaffinity='0')
    ET.SubElement(fruit, 'geom', name='leaf', type='ellipsoid', pos='.007 0 .029',
                  size='.009 .004 .0006', euler='0 .3 .3', rgba='.18 .30 .09 1', mass='.0001', contype='0', conaffinity='0')
    ET.SubElement(world, 'geom', name='plate_base', type='cylinder', pos=f'{PLATE[0]} {PLATE[1]} .004',
                  size='.086 .004', material='ceramic', friction='1 .01 .001')
    for i in range(48):
        a, b = 2 * math.pi * i / 48, 2 * math.pi * (i + 1) / 48
        x1, y1 = PLATE[:2] + .085 * np.array([math.cos(a), math.sin(a)])
        x2, y2 = PLATE[:2] + .085 * np.array([math.cos(b), math.sin(b)])
        ET.SubElement(world, 'geom', name=f'plate_rim_{i}', type='capsule',
                      fromto=f'{x1} {y1} .008 {x2} {y2} .008', size='.004', material='ceramic')
    return ET.tostring(root, encoding='unicode')


class IncrementalEnv:
    solve_ik = Simulation.solve_ik

    def __init__(self, seed=0, render=True):
        self.seed = seed
        self.model = mujoco.MjModel.from_xml_string(scene_xml())
        self.data, self.ikdata = mujoco.MjData(self.model), mujoco.MjData(self.model)
        self.tcp = self.model.site('link_tcp').id
        self.qids = np.array([self.model.jnt_qposadr[self.model.joint(f'joint{i}').id] for i in range(1, 8)])
        self.dofs = np.array([self.model.jnt_dofadr[self.model.joint(f'joint{i}').id] for i in range(1, 8)])
        self.ranges = np.array([self.model.jnt_range[self.model.joint(f'joint{i}').id] for i in range(1, 8)])
        self.fruit = self.model.body('fruit').id
        self.fruit_geom = self.model.geom('fruit_geom').id
        self.fruit_dof = self.model.jnt_dofadr[self.model.joint('fruit_joint').id]
        self.fruit_qpos = self.model.jnt_qposadr[self.model.joint('fruit_joint').id]
        self.data.qpos[self.qids] = HOME
        self.data.ctrl[:7] = HOME
        if seed:
            self.data.qpos[self.fruit_qpos:self.fruit_qpos + 2] += np.random.default_rng(seed).uniform(-.012, .012, 2)
        mujoco.mj_forward(self.model, self.data)
        # Initial robot configuration only. No scripted task motion follows reset.
        q = self.solve_ik([.32, -.10, .20])
        self.data.qpos[self.qids] = q
        self.data.ctrl[:7] = q
        self.command_grip = 0.
        self.steps = 0
        self.stable_seconds = 0.
        self.contact_seconds = 0.
        self.on_frame = None
        self.max_lift = 0.
        self.grasp_attempts = 0
        self.last_intent = None
        self.last_feedback = 'Scene initialized. No task actions executed.'
        self.renderer = mujoco.Renderer(self.model, 720, 1000) if render else None
        self.camera = mujoco.MjvCamera()
        self.camera.lookat[:] = [.26, .035, .22]
        self.camera.distance = 1.52
        self.camera.azimuth = 135
        self.camera.elevation = -31
        self._hold(.5)
        self.start_time = float(self.data.time)
        self.stable_seconds = 0.

    @property
    def position(self): return self.data.site_xpos[self.tcp].copy()

    @property
    def fruit_position(self): return self.data.xpos[self.fruit].copy()

    @property
    def elapsed(self): return float(self.data.time) - getattr(self, 'start_time', 0.)

    def contacts(self):
        fingers = set()
        plate = False
        for c in self.data.contact[:self.data.ncon]:
            if c.dist > .001 or self.fruit_geom not in (c.geom1, c.geom2): continue
            other = c.geom2 if c.geom1 == self.fruit_geom else c.geom1
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, int(other)) or ''
            if name.startswith('left_finger_pad'): fingers.add('left')
            if name.startswith('right_finger_pad'): fingers.add('right')
            if name == 'plate_base': plate = True
        return fingers, plate

    def _in_plate(self):
        p = self.fruit_position
        _, support = self.contacts()
        return bool(np.linalg.norm(p[:2] - PLATE[:2]) < .053 and .028 < p[2] < .043 and support)

    def _step(self):
        self.data.qfrc_applied[self.dofs] = self.data.qfrc_bias[self.dofs]
        mujoco.mj_step(self.model, self.data)
        self.steps += 1
        self.max_lift = max(self.max_lift, float(self.fruit_position[2]))
        speed = np.linalg.norm(self.data.qvel[self.fruit_dof:self.fruit_dof + 3])
        fingers, _ = self.contacts()
        self.contact_seconds = self.contact_seconds + self.model.opt.timestep if len(fingers) == 2 and self.command_grip > .5 else 0.
        if self._in_plate() and self.command_grip < .25 and speed < .015:
            self.stable_seconds += self.model.opt.timestep
        else:
            self.stable_seconds = 0.
        if not np.isfinite(self.data.qpos).all(): raise RuntimeError('Physics diverged')
        if self.on_frame and self.steps % 16 == 0: self.on_frame(self)

    def _hold(self, seconds):
        for _ in range(round(seconds / self.model.opt.timestep)): self._step()

    def observe(self):
        tcp, fruit = self.position, self.fruit_position
        fingers, plate_contact = self.contacts()
        held = len(fingers) == 2 and self.command_grip > .5
        grasp = fruit + np.array([0., 0., .002])
        release = np.r_[PLATE[:2], RELEASE_Z]
        return {
            'task': 'Put the red apple in the plate, release it, and withdraw the open gripper upward.',
            'source': 'MuJoCo geometry + contacts, not camera vision',
            'units': 'millimetres; robot base coordinates; +Z is up',
            'tcp_mm': (tcp * 1000).round(1).tolist(),
            'fruit_mm': (fruit * 1000).round(1).tolist(),
            'grasp_tcp_mm': (grasp * 1000).round(1).tolist(),
            'plate_center_mm': (PLATE * 1000).round(1).tolist(),
            'release_tcp_mm': (release * 1000).round(1).tolist(),
            'fruit_grasp_minus_tcp_mm': ((grasp - tcp) * 1000).round(1).tolist(),
            'plate_release_minus_tcp_mm': ((release - tcp) * 1000).round(1).tolist(),
            'alignment': {
                'grasp_x_error_mm': round(float(grasp[0] - tcp[0]) * 1000, 1),
                'grasp_y_error_mm': round(float(grasp[1] - tcp[1]) * 1000, 1),
                'grasp_z_error_mm': round(float(grasp[2] - tcp[2]) * 1000, 1),
                'grasp_pose_reached': bool(np.all(np.abs(grasp[:2] - tcp[:2]) <= .004) and abs(grasp[2] - tcp[2]) <= .002),
                'over_plate': bool(np.all(np.abs(tcp[:2] - PLATE[:2]) <= .006)),
                'at_travel_height': bool(tcp[2] >= .165),
                'at_release_height': bool(abs(tcp[2] - RELEASE_Z) <= .004),
            },
            'travel_tcp_z_mm': TRAVEL_Z * 1000,
            'gripper_command': 'closed' if self.command_grip > .5 else 'open',
            'finger_contacts': sorted(fingers), 'held': held,
            'bilateral_contact_seconds': round(self.contact_seconds, 3),
            'grasp_secured': bool(held and self.contact_seconds >= .45),
            'fruit_bottom_mm': round((fruit[2] - .026) * 1000, 1),
            'plate_contact': plate_contact, 'fruit_in_plate': self._in_plate(),
            'stable_released_in_plate': self.stable_seconds >= .4,
            'stable_seconds': round(self.stable_seconds, 2),
            'previous_intent': self.last_intent, 'feedback': self.last_feedback,
            'sim_seconds': round(self.elapsed, 3),
        }

    def success(self):
        return bool(self.stable_seconds >= .4 and self.position[2] >= .145 and self.command_grip < .25)

    def increment(self, motor, intent):
        """Only directions from the model. No pick/place skill or semantic fallback."""
        expected = {'x', 'y', 'z', 'gripper'}
        if set(motor) != expected: raise ValueError('Incomplete motor command')
        direction = {'negative': -1., 'hold': 0., 'positive': 1.}
        if any(motor[a] not in direction for a in ('x', 'y', 'z')): raise ValueError('Invalid XYZ option')
        if motor['gripper'] not in ('open', 'hold', 'close'): raise ValueError('Invalid gripper option')
        current = self.position
        # Magnitude-only scaling near geometric targets. Never changes the selected sign.
        reference = self.fruit_position + [0, 0, .002]
        if intent in ('carry', 'lower', 'release'): reference = np.r_[PLATE[:2], RELEASE_Z if intent != 'carry' else TRAVEL_Z]
        if intent in ('lift', 'withdraw'): reference = np.r_[current[:2], TRAVEL_Z]
        distances = np.abs(reference - current)
        sizes = np.where(distances < .012, .002, np.where(distances < .025, .004, .018))
        delta = np.array([direction[motor[a]] for a in ('x', 'y', 'z')]) * sizes
        target = current + delta
        grip = self.command_grip if motor['gripper'] == 'hold' else float(motor['gripper'] == 'close')
        rejection = None
        if np.any(target < [.20, -.30, .025]) or np.any(target > [.65, .38, .32]):
            rejection = 'Workspace bound: requested increment rejected.'
        q = None
        if rejection is None:
            try: q = self.solve_ik(target)
            except RuntimeError: rejection = 'IK did not converge: requested increment rejected.'
        if rejection:
            self.last_feedback = rejection
            self._hold(STEP_SECONDS)
        else:
            if grip > .5 and self.command_grip < .5: self.grasp_attempts += 1
            self.command_grip = grip
            self.data.ctrl[7] = grip * 230
            initial_q = self.data.qpos[self.qids].copy()
            n = round(STEP_SECONDS / self.model.opt.timestep)
            for i in range(1, n + 1):
                t = i / n
                blend = t * t * t * (10 + t * (-15 + 6 * t))
                self.data.ctrl[:7] = initial_q + (q - initial_q) * blend
                self._step()
            self.last_feedback = 'Increment executed. Inspect updated pose and contacts.'
        self.last_intent = intent
        return {'accepted': rejection is None, 'reason': rejection,
                'requested_delta_mm': (delta * 1000).round(3).tolist(),
                'actual_delta_mm': ((self.position - current) * 1000).round(3).tolist(),
                'target_tcp_mm': (target * 1000).round(3).tolist(),
                'gripper_command': self.command_grip, 'sim_seconds': round(self.elapsed, 3)}

    def render(self):
        self.renderer.update_scene(self.data, camera=self.camera)
        return self.renderer.render().copy()

    def close(self):
        if self.renderer: self.renderer.close()
