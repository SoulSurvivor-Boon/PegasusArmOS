import os
import sys
from modern_robotics.core import GravityForces

#Find directory path of current file
current = os.path.dirname(os.path.realpath(__file__))
#Find directory path of parent folder and add to sys path
parent = os.path.dirname(current)
sys.path.append(parent)

import numpy as np
import modern_robotics as mr
from classes import Robot, Link, Joint
from robot_init import robot
from dynamics.dynamics_funcs import FricTau, FeedForward, MassMatrix, CorrCentTorques, GravTorques, FTipTorques, ForwardDynamics, SimulateStep

np.set_printoptions(precision=3)

tauComm = 5
dtheta = 1
tauStat = 0.02
bVisc = 0.04
tauKin = 0.015
eff = 0.8

def test_tauFricNoLoss():
    """Checks functionality if loss model is nullified"""
    tauStat = 0
    bVisc = 0
    tauKin = 0
    eff = 1
    tau = FricTau(tauComm, dtheta, tauStat, bVisc, tauKin, eff)
    assert tau == 0

def test_FricTauEff():
    """Checks efficiency calculation"""
    tauStat = 0
    bVisc = 0
    tauKin = 0
    eff = 0.8
    tau = FricTau(tauComm, dtheta, tauStat, bVisc, tauKin, eff)
    assert tau == tauComm/eff - tauComm

def test_FricTauStat():
    """Observe if static & kinetic friction (w/o viscous) works."""
    tauStat = 1
    dtheta = 0
    eff = 1
    bVisc = 0.04
    tau = FricTau(tauComm, dtheta, tauStat, bVisc, tauKin, eff)
    assert tau == tauStat
    dtheta = 1
    bVisc = 0
    tau = FricTau(tauComm, dtheta, tauStat, bVisc, tauKin, eff)
    assert tau == tauKin

def test_FricTauDyn():
    """Checks if full functionality works"""
    tauComm = 0.5
    tauStat = 1
    tauKin = 0.4
    dtheta = 1
    eff = 0.8
    bVisc = 0.05
    tau = FricTau(tauComm, dtheta, tauStat, bVisc, tauKin, eff)
    assert tau == (tauKin*np.sign(dtheta) + bVisc*dtheta) + tauComm/eff - tauComm

def test_FricTauSign():
    """See if FricTau correctly handles velocity signes"""
    dtheta = -1
    eff = 1
    tau = FricTau(tauComm, dtheta, tauStat, bVisc, tauKin, eff)
    assert tau == -tauKin + bVisc*dtheta     

def InverseDynamicsDEBUG(thetalist, dthetalist, ddthetalist, g, Ftip, Mlist, \
                    Glist, Slist):
    """Computes inverse dynamics in the space frame for an open chain robot

    :param thetalist: n-vector of joint variables
    :param dthetalist: n-vector of joint rates
    :param ddthetalist: n-vector of joint accelerations
    :param g: Gravity vector g
    :param Ftip: Spatial force applied by the end-effector expressed in frame
                 {n+1}
    :param Mlist: List of link frames {i} relative to {i-1} at the home
                  position
    :param Glist: Spatial inertia matrices Gi of the links
    :param Slist: Screw axes Si of the joints in a space frame, in the format
                  of a matrix with axes as the columns
    :return: The n-vector of required joint forces/torques
    This function uses forward-backward Newton-Euler iterations to solve the
    equation:
    taulist = Mlist(thetalist)ddthetalist + c(thetalist,dthetalist) \
              + g(thetalist) + Jtr(thetalist)Ftip

    Example Input (3 Link Robot):
        thetalist = np.array([0.1, 0.1, 0.1])
        dthetalist = np.array([0.1, 0.2, 0.3])
        ddthetalist = np.array([2, 1.5, 1])
        g = np.array([0, 0, -9.8])
        Ftip = np.array([1, 1, 1, 1, 1, 1])
        M01 = np.array([[1, 0, 0,        0],
                        [0, 1, 0,        0],
                        [0, 0, 1, 0.089159],
                        [0, 0, 0,        1]])
        M12 = np.array([[ 0, 0, 1,    0.28],
                        [ 0, 1, 0, 0.13585],
                        [-1, 0, 0,       0],
                        [ 0, 0, 0,       1]])
        M23 = np.array([[1, 0, 0,       0],
                        [0, 1, 0, -0.1197],
                        [0, 0, 1,   0.395],
                        [0, 0, 0,       1]])
        M34 = np.array([[1, 0, 0,       0],
                        [0, 1, 0,       0],
                        [0, 0, 1, 0.14225],
                        [0, 0, 0,       1]])
        G1 = np.diag([0.010267, 0.010267, 0.00666, 3.7, 3.7, 3.7])
        G2 = np.diag([0.22689, 0.22689, 0.0151074, 8.393, 8.393, 8.393])
        G3 = np.diag([0.0494433, 0.0494433, 0.004095, 2.275, 2.275, 2.275])
        Glist = np.array([G1, G2, G3])
        Mlist = np.array([M01, M12, M23, M34])
        Slist = np.array([[1, 0, 1,      0, 1,     0],
                          [0, 1, 0, -0.089, 0,     0],
                          [0, 1, 0, -0.089, 0, 0.425]]).T
    Output:
        np.array([74.69616155, -33.06766016, -3.23057314])
    """
    n = len(thetalist)
    Mi = np.eye(4)
    Ai = np.zeros((6, n))
    AdTi = [[None]] * (n + 1)
    Vi = np.zeros((6, n + 1))
    Vdi = np.zeros((6, n + 1))
    Vdi[:, 0] = np.r_[[0, 0, 0], -np.array(g)]
    AdTi[n] = mr.Adjoint(mr.TransInv(Mlist[n]))
    Fi = np.array(Ftip).copy()
    taulist = np.zeros(n)
    for i in range(n):
        Mi = np.dot(Mi,Mlist[i])
        Ai[:, i] = np.dot(mr.Adjoint(mr.TransInv(Mi)), np.array(Slist)[:, i])
        AdTi[i] = mr.Adjoint(np.dot(mr.MatrixExp6(mr.VecTose3(Ai[:, i] * \
                                            -thetalist[i])), \
                                 mr.TransInv(Mlist[i])))
        Vi[:, i + 1] = np.dot(AdTi[i], Vi[:,i]) + Ai[:, i] * dthetalist[i]
        Vdi[:, i + 1] = np.dot(AdTi[i], Vdi[:, i]) \
                       + Ai[:, i] * ddthetalist[i] \
                       + np.dot(mr.ad(Vi[:, i + 1]), Ai[:, i]) * dthetalist[i]
    for i in range (n - 1, -1, -1):
        Fi = np.dot(np.array(AdTi[i + 1]).T, Fi) \
             + np.dot(np.array(Glist[i]), Vdi[:, i + 1]) \
             - np.dot(np.array(mr.ad(Vi[:, i + 1])).T, \
                      np.dot(np.array(Glist[i]), Vi[:, i + 1]))
        taulist[i] = np.dot(np.array(Fi).T, Ai[:, i])
    return taulist

def test_FFOptZero():
    """Check if FF gives no required torques if no forces are applied."""
    theta = np.array([0, 0, 0, 0, 0])
    dtheta = np.array([0, 0, 0, 0, 0])
    ddtheta = np.array([0, 0, 0, 0, 0])
    g = np.array([0, 0, 0])
    FTip = np.array([0,0,0,0,0,0])
    tau = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    assert all(tau) == False
    #Change configuration: Shouldn't change anything
    theta = np.array([0.05*np.pi, 0.5*np.pi, 0.25*np.pi, 0, np.pi])
    tau = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    assert all(tau) == False

def test_FFOptGrav():
    theta = np.array([0,0,0,0,0])
    dtheta = np.array([0,0,0,0,0])
    ddtheta = np.array([0,0,0,0,0])
    g = np.array([0,0,-9.81])
    FTip = np.array([0,0,0,0,0,0])
    tau = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    """Increasing the angle of the second joint (downward) should
    make the torque for this joint (and the third) significantly larger.
    Additionally: The torque on the fourth joint should decrease, as 
    the gripper is now pointing downward."""
    theta = np.array([0,0.5*np.pi,0,0,0])
    tau2 = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    assert abs(tau2[1]) > abs(tau[1])
    assert abs(tau2[2]) > abs(tau[2])
    assert abs(tau2[3]) < abs(tau[3])

def test_FFOptdtheta():
    theta = np.array([0,0,0,0,0])
    dtheta = np.array([0,0,0,0,0])
    ddtheta = np.array([0,0,0,0,0])
    g = np.array([0,0,-9.81])
    FTip = np.array([0,0,0,0,0,0])
    tau = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    theta = np.array([0,0,0,0,0])
    dtheta = np.array([np.pi,0,0,0,0])
    ddtheta = np.array([0,0,0,0,0])
    g = np.array([0,0,-9.81])
    FTip = np.array([0,0,0,0,0,0])
    tau2 = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    assert np.allclose(tau2, tau2, atol=1e-03)

    theta = np.array([0,0,0,0])
    dtheta = np.array([np.pi,0,0,0])
    ddtheta = np.array([0,0,0,0])
    Mlist = [robot.links[i].Tii for i in range(len(theta))]
    Mlist.append(robot.TsbHome)
    Glist = [robot.links[i].Gi for i in range(len(theta))]
    Slist = np.c_[robot.screwAxes[0], robot.screwAxes[1]]
    for i in range(2, len(theta)):
        Slist = np.c_[Slist, robot.screwAxes[i]]
    tauMRFirst = InverseDynamicsDEBUG(theta, dtheta, ddtheta, g, FTip, Mlist,Glist, Slist)
    assert np.allclose(tauMRFirst, tau2[0:-1])

    Slist[:, -1] = robot.screwAxes[-1]
    tauMRLast = InverseDynamicsDEBUG(theta, dtheta, ddtheta, g, FTip, Mlist,Glist, Slist)
    assert np.allclose(tauMRLast, np.r_[tau2[0:-2], tau[-1:]], atol=1e-03)

def test_FFOptddtheta():
    theta = np.array([0,0,0,0,0])
    dtheta = np.array([0,0,0,0,0])
    ddtheta = np.array([0,0,0,0,0])
    g = np.array([0,0,-9.81])
    FTip = np.array([0,0,0,0,0,0])
    tau = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    ddtheta = np.array([0,0.25*np.pi,0,0,0])
    tau2 = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    #Expectation: Torque is higher for at least joint 2
    assert tau2[1] > tau[1]

def test_FFOptFTip():
    theta = np.array([0,0,0,0,0])
    dtheta = np.array([0,0,0,0,0])
    ddtheta = np.array([0,0,0,0,0])
    g = np.array([0,0,-9.81])
    FTip = np.array([0,0,0,0,0,0]) 
    tau = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    FTip = np.array([1,0,0,0,0,0]) #Pure x rotation in body frame
    tau2 = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    print(tau)
    print(tau2)
    #Expectation: Mainly joint five will have to give additional torque
    assert tau2[-1] > tau[-1]
    theta = np.array([0,0,0,0])
    dtheta = np.array([0,0,0,0])
    ddtheta = np.array([0,0,0,0])
    Mlist = [robot.links[i].Tii for i in range(len(theta))]
    Mlist.append(robot.TsbHome)
    Glist = [robot.links[i].Gi for i in range(len(theta))]
    Slist = np.c_[robot.screwAxes[0], robot.screwAxes[1]]
    for i in range(2, len(theta)):
        Slist = np.c_[Slist, robot.screwAxes[i]]
    tauMR = InverseDynamicsDEBUG(theta, dtheta, ddtheta, g, FTip, Mlist,Glist, Slist)
    #Expectation: All torques should be the same (minus the one missing in tauMR)
    assert np.allclose(tauMR, tau2[:-1])
    Slist[:,-1] = robot.screwAxes[-1] #Switch final axis
    tauMR2 = InverseDynamicsDEBUG(theta, dtheta, ddtheta, g, FTip, Mlist,Glist, Slist)
    assert np.allclose(tauMR2, np.r_[tau2[:-2], tau2[-1]])

    theta = np.array([0,0,0,0,0]) #Reset (dd)theta dimensions
    dtheta = np.array([0,0,0,0,0])
    ddtheta = np.array([0,0,0,0,0])
    FTip = np.array([0,1,0,0,0,0]) #Pure y rotation in body frame
    tau3 = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    print(tau3)
    """Expectation: At least joint four, three, and two will have to 
                    give additional torque
    Expectation: Joint five should be barely affected
    """
    assert all(np.greater(tau3[1:-2], tau[1:-2]))
    assert np.isclose(tau3[-1], tau[-1], atol=1e-3)
    FTip = np.array([0,0,0,1,0,0])#Pure linear force in x
    tau4 = FeedForward(robot, theta, dtheta, ddtheta, g, FTip)
    print(tau4)
    """Expectation: Mainly joint two, three, and four will have to 
                    give additional torque in the home configuration
        Expectation: Joint five should be barely affected
    """
    assert all(np.greater(tau3[1:-2], tau[1:-2]))
    assert np.isclose(tau3[-1], tau[-1], atol=1e-3)

def test_MassMatrixOrth():
    """Test if rigidly connected orthogonal screw axes do not
    affect eachother in terms of torques caused by joint accelleration.
    """
    theta = np.random.rand(5)
    M = MassMatrix(robot, theta)
    assert M[4,3] == M[3,4] and M[4,3] == 0 and M[0,0] != 0

def test_CorrCent():
    """Assert if the torques required to overcome coriolis- and 
    centripetal forces is zero when no velocity is present, and non-
    zero in its presence."""
    theta = np.random.rand(5)
    dtheta = [0,0,0,0,0]
    tauC = CorrCentTorques(robot, theta, dtheta)
    assert not tauC.any() and tauC.size == len(theta)
    dtheta = np.random.rand(5)
    tauC = CorrCentTorques(robot, theta, dtheta)
    assert tauC.all()

def test_Grav():
    """Check if the torques required to overcome gravity is 
    zero in absence of gravity, and non-zero is its presence."""
    theta = np.random.rand(5)
    g = np.array([0,0,0])
    tauG = GravTorques(robot, theta, g)
    assert not tauG.any() and tauG.size == len(theta)
    g = np.array([0,0,-9.81])
    tauG = GravTorques(robot, theta, g)
    """Always some small factor, due to link CoM's never being 
    perfectly aligned with a screw axis"""
    assert tauG.all()

def test_FD():
    """Ascertain if Forward Dynamics obtains non-zero joint accele-
    ration for non-zero inputs, and zero joint acc. for all dynamic
    inputs being zero."""
    theta = [0,0,0,0,0]
    dtheta = [0,0,0,0,0]
    tau = np.zeros(5)
    g = np.zeros(3)
    FTip = np.zeros(6)
    ddtheta = ForwardDynamics(robot, theta, dtheta, tau, g, FTip)
    assert all(a == 0 for a in ddtheta)

    theta = np.random.rand(5)
    dtheta = np.random.rand(5)
    tau = np.random.rand(5)
    g = np.array([0,0,-9.81])
    FTip = np.random.rand(6)
    ddtheta = ForwardDynamics(robot, theta, dtheta, tau, g, FTip)
    assert all(a != 0 for a in ddtheta)

def test_SimStep():
    """Test if Simulate step does not change configuration and velocity
    if there is no net torque on each joint. Moreover, confirm the change
    in configuration and velocity for non-zero net torque."""
    thetaPrev = [0,0,0,0,0]
    dthetaPrev = [0,0,0,0,0]
    ddthetaPrev = [0,0,0,0,0]
    tau = np.zeros(5)
    g = np.zeros(3)
    FTip = np.zeros(6)
    dt = 0.1
    thetaTup = SimulateStep(robot, thetaPrev, dthetaPrev, ddthetaPrev, tau, g, 
                 FTip, dt)
    for i in range(len(thetaTup)):
        for j in range(len(thetaTup[i])):
            assert thetaTup[i][j] == 0
    thetaPrev = np.random.rand(5)
    dthetaPrev = np.random.rand(5)
    ddthetaPrev = np.random.rand(5)
    tau = np.random.rand(5)
    g = np.array([0,0,-9.81])
    FTip = np.random.rand(6)
    thetaTup = SimulateStep(robot, thetaPrev, dthetaPrev, ddthetaPrev, tau, g, 
                 FTip, dt)
    for i in range(len(thetaTup)):
        for j in range(len(thetaTup[i])):
            assert thetaTup[i][j] != 0