"""Shared fixed-orientation inverse kinematics; no task skills."""
import mujoco
import numpy as np

HOME = np.array([0,-.247,0,.909,0,1.15644,0])


class Simulation:
    def solve_ik(self, target, initial=None):
        d=self.ikdata
        d.qpos[:]=self.data.qpos
        d.qpos[self.qids]=self.data.qpos[self.qids] if initial is None else initial
        desired=np.diag([-1.,1.,-1.])
        jp=np.zeros((3,self.model.nv)); jr=jp.copy()
        for _ in range(180):
            mujoco.mj_forward(self.model,d)
            rot=d.site_xmat[self.tcp].reshape(3,3)
            ep=np.asarray(target)-d.site_xpos[self.tcp]
            er=.5*sum((np.cross(rot[:,i],desired[:,i]) for i in range(3)),np.zeros(3))
            if np.linalg.norm(ep)<.00015 and np.linalg.norm(er)<.002:
                return d.qpos[self.qids].copy()
            mujoco.mj_jacSite(self.model,d,jp,jr,self.tcp)
            jac=np.vstack([jp[:,self.dofs],jr[:,self.dofs]*.35])
            err=np.r_[ep,er*.35]
            delta=jac.T@np.linalg.solve(jac@jac.T+np.eye(6)*.00004,err)
            delta*=min(1.,.12/(np.max(np.abs(delta))+1e-12))
            d.qpos[self.qids]=np.clip(d.qpos[self.qids]+delta,self.ranges[:,0]+.01,self.ranges[:,1]-.01)
        raise RuntimeError(f'IK did not converge for {np.round(target,3)}; position residual={np.linalg.norm(ep):.4f}m')
