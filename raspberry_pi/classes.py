import numpy as np
import modern_robotics as mr
from typing import List

class Link():
    def __init__(self, inertiaMat: np.ndarray, mass: float, prevLink: 'Link',
                 Tsi: np.ndarray):
        """Constructer for Link class.
        :param inertiaMat: The 3x3 inertia matrix of the link with 
                           respect to the link frame. If the axes of 
                           the link frame coincide with the cqqciple 
                           axes of inertia, this matrix simplifies to 
                           a diagonal matrix.
        :param mass: The mass of the link in kg.
        :param prevLink: Previous link in the chain.
        :param Tsi: The 4x4 SE(3) transformation matrix of the link
                    frame {i} in the space frame {s}.
        """
        self.Gi: np.ndarray = np.zeros((6,6)) #6x6 spatial inertia matrix
        self.Gi[0:3,0:3] = inertiaMat
        self.Gi[3:6, 3:6] = np.diag([mass]*3, k=0)
        self.Tsi: np.ndarray = Tsi
        """Tii is the transformation matrix T_(i-1,i) in the home position:"""
        if prevLink == None:
            self.Tii = self.Tsi
        else:
            self.Tii: np.ndarray = np.dot(mr.TransInv(prevLink.Tsi), Tsi)

    def __repr__(self):
        return f"Link(Gi: {self.Gi}\nTii:{self.Tii}\nTsi: {self.Tsi})"

class Joint():
    """A storage class combining all the information relevant to joint
    calculations."""
    def __init__(self, screwAx: np.ndarray, links: List[Link], gearRatio: 
                 float, km: float, cpr: int, lims: List[float] = 
                 [-2*np.pi, 2*np.pi], tauStat: float=0, tauKin: 
                 float=0, bVisc: float=0, eff: float=1, 
                 inSpace: bool = True):
        """Constructor for Joint class.
        :param screwAx: A 6x1 screw axis in the home configuration, per 
        Definition 3.24 of the Modern Robotics book.
        :param links: Connecting links, in the order [prev, next].
        :param gearRatio: The reduction ratio 1:gearRatio between the
                          motor shaft and joint axes.
        :param km: Motor constant in Nm/A
        :param cpr: Counts per revolution of the encoder shaft.
        :param lims: The joint limits, in the order [lower, upper].
        :param tauStat: Static friction torque
        :param tauKin: Kinetic friction torque
        :param bVisc: Viscous damping coefficient in [(N/m)/(rad/s)]
        :param eff: Torque efficiency
        :param inSpace: Notes if the screw axis is in the space frame
                        (True) or in the body frame (False).
        """        
        self.screwAx: np.ndarray = screwAx
        self.lims: List[float] = lims
        self.gearRatio = gearRatio
        self.km = km
        self.cpr = cpr
        self.enc2Theta = 1/(cpr*gearRatio) * 2*np.pi
        self.links: List[Link] = links
        self.fricPar = dict(stat=tauStat, kin=tauKin, visc=bVisc,
                            eff=eff)
        self.inSpace: bool = inSpace
    
    def __repr__(self):
        return f"Joint(screwAx: {self.screwAx}\nlims: {self.lims}\n" +\
               f"gearRatio: {self.gearRatio}\ncpr: {self.cpr}\nenc2Theta:" +\
               f"{self.enc2Theta}\nlinks: {self.links}\n" +\
               f"inSpace: {self.inSpace}"  

class Robot():
    """Overarching robot class, containing all joints & links 
    described using their respective class instances.
    """
    def __init__(self, joints: List[Joint], links: List[Link], 
                 TsbHome: np.ndarray):
        """ Constructor for Robot class.
        :param joints: A list of Joint objects, with the joints 
                       being in ascending order from the joint 
                       closest to the robot's connection with the 
                       fixed world.
        :param links: A list of Link objects, with the links being 
                      in ascending order from the link closest to 
                      the robot's connection to the fixed world.
        :param TsbHome: Transformation matrix describing the end-
                        effector {b} in the space frame {s} in the home
                        configuration, i.e. all theta = 0.
        """
        self.joints: List[Joint] = joints
        self.screwAxes: List[np.ndarray] = [joint.screwAx for joint in 
                                            joints]
        self.limList: List[List[float]] = [joint.lims for joint in joints]
        self.links: List[Link] = links
        self.GiList: List[np.ndarray] = [link.Gi for link in links]
        
        self.TllList: List[np.ndarray] = [link.Tii for link in links]
        TiEF = np.dot(mr.TransInv(links[-1].Tsi), TsbHome)
        self.TllList.append(TiEF)
        self.TsbHome: np.ndarray = self.TllList[-1]
    
    def __repr__(self):
        return f"Robot:(joints: {self.joints}\nscrewAxes: " +\
               f"{self.screwAxes}\nlimList: {self.limList}\nlinks: " +\
               f"{self.links}\n GiList: {self.GiList}\n TllList: " +\
               f"{self.TllList}\n TsbHome: {self.TsbHome}"

class SerialData():
    """Container class containing all relevant information and functions
    for parsing and acting on data received over serial communication."""
    def __init__(self, lenData: int, joints: List[Joint], desAngles: 
                 List[float]=[0 for i in range(6)], maxDeltaAngle: List[float]=[0.3*np.pi for i in range(6)], 
                 angleTol: List[float]=[0 for i in range(6)]) -> "SerialData":
        """Constructor for SerialData class.
        :param lenData: The expected number of data packets (equal to
                        number of motor units).
        :param desAngles: List of desired angles for each motor, in 
                          radians (for position control).
        :param maxDeltaAngle: Maximum change in each joint angle 
                              between two received data packets (anti-
                              corruption check).
        :param joints: List of all Joint instances of the robot.
        :param angleTol: Tolerance of each desired joint angle in 
                         radians.
        NOTE 02-12-2021: desAngles and angleTol are outdated, 
        should be removed and code refactored.
        """
        self.lenData = lenData
        self.desAngle = desAngles #Depricated
        self.joints = joints
        self.totCount = [0 for i in range(lenData)]
        self.rotDirCurr = [None for i in range(lenData)]
        self.current = [None for i in range(lenData)]
        self.homing = [None for i in range(lenData)]
        #Often used in the form SerialData.currAngle[:-1]
        self.currAngle = [0. for i in range(lenData)]
        self.prevAngle = [0. for i in range(lenData)]
        self.mSpeed = [0. for i in range(lenData)]
        self.rotDirDes = [0 for i in range(lenData)]
        self.dataOut = ['0|0' for i in range(lenData)]
        self.maxDeltaAngle = maxDeltaAngle #Depricated
        self.angleTol = angleTol #Depricated
        self.limBool = [False for i in range(lenData)]

    def ExtractVars(self, dataPacket: List[str]):
        """Extracts & translates information in each datapacket.
        :param dataPacket: A string of the form 'totCount|rotDirCurr',
                           where totCount is an integer and rotDirCurr
                           a boolean (0 or 1). Potentially, it has an
                           additional argument 'curr', being an int.
        Example input:
        dataPacket = '1234|0'
        """
        for i in range(self.lenData):
            args = dataPacket[i].split('|')
            if len(args) >= 3:
                self.homing[i] = args[2]
                self.homing[i] = int(self.homing[i])
            if len(args) == 4:
                self.current[i] = args[3]
                self.current[i] = float(self.current[i])
            self.totCount[i], self.rotDirCurr[i] = args[0:2]
            self.totCount[i] = int(self.totCount[i])
            self.rotDirCurr[i] = int(self.rotDirCurr[i])
            self.prevAngle[i] = self.currAngle[i]
            if i == self.lenData-1:
                    #Gripper doesn't have an 'angle'
                    self.currAngle[i] = self.totCount[i]
            elif i == 3: #Diff drive 'difference' part, up & down:
                """Although the gears at the diff drive move in the
                same direction when going up / down, the motors are 
                placed in a mirrored fashion such that their 
                rotational shafts turn oppositely."""
                angleM4 = self.totCount[3]*self.joints[3].enc2Theta
                angleM5 = self.totCount[4]*self.joints[4].enc2Theta
                average = (angleM5 + angleM4)/2
                self.currAngle[i] = angleM5 - average
            elif i == 4: #Diff drive 'synchronous' part;
                """A similar argument as for the fourth axis is made."""
                angleM4 = self.totCount[3]*self.joints[3].enc2Theta
                angleM5 = self.totCount[4]*self.joints[4].enc2Theta
                self.currAngle[i] = (angleM4 + angleM5)/2
            else:
                self.currAngle[i] = self.totCount[i] *\
                                    self.joints[i].enc2Theta
            if i == 2 or i == 3:
                """Due to the unique mechanics of the robot, the 
                encoder only measures the absolute angle of these joints,
                not relative to the previous joint.
                """
                self.currAngle[i] -= self.totCount[i-1]*\
                                     self.joints[i-1].enc2Theta

    def Dtheta2Mspeed(self, dtheta: "np.ndarray[float]", 
                      dthetaMax: List[float], PWMMin: int, PWMMax: int):
        #DEPRICATED!
        """Translates desired motor velocities in rad/s to PWM.
        :param dtheta: Numpy array of motor velocities in [rad/s].
        :param dthetaMax: Angular velocity of each motor at a PWM of 255.
        :param PWMMin: Minimum PWM value necessary to move the motor.
        :param PWMMax: Maximum PWM value that the motors can be given.
        """
        if dtheta.size != self.lenData-1: #-1 for gripper
            raise InputError("size of dtheta != lenData-1: " +
                             f"{dtheta.size} != {self.lenData-1}")
        else:
            self.mSpeed = [PWMMin + round((dtheta[i]/dthetaMax[i])*(PWMMax-PWMMin)) 
            for i in range(self.lenData-1)] #Rudimentary solution, PID will help!

    def CheckCommFault(self) -> bool:
        #DEPRICATED
        """Checks if data got corrupted using a maximum achievable 
        change in angle between two timesteps.
        :return commFault: Boolean indicating if new angle is 
                           reasonable (False) or not (True).
        
        Known issue: If commFault occurs because maxDeltaAngle is 
        too low, i.e. the encoder actually moved more than maxDelta-
        Angle in one step, then the motor ceases to run because 
        the condition will now always be True.
        """
        commFault = [False for i in range(self.lenData)]
        for i in range(self.lenData):
            if abs(self.prevAngle[i] - self.currAngle[i]) >= self.maxDeltaAngle[i]:
                commFault[i] = True
                self.currAngle[i] = self.prevAngle[i]
                self.mSpeed[i] = 0
                self.homing[i] = 0
                self.dataOut[i] = f"{self.mSpeed[i]}|{self.rotDirDes[i]}|{self.homing[i]}"
        return commFault
    
    def CheckTolAng(self) -> bool:
        #DEPRICATED
        """Determines if the desired angle has been reached within the 
        given tolerance, and if the desired angle is reachable.
        If the desired angle is unreachable, the closest angle is chosen.
        :return success: Indicates if the angle is within the 
        tolerance of the goal angle (True) or not (False).
        """
        success = [False for i in range(self.lenData)]
        for i in range(self.lenData):
            if self.desAngle[i] < self.joints[i].lims[0]:
                self.desAngle[i] = self.joints[i].lims[0]
            elif self.desAngle[i] > self.joints[i].lims[1]:
                self.desAngle[i] = self.joints[i].lims[1] 
            if abs(self.currAngle[i] - self.desAngle[i]) <= self.angleTol[i]:
                success[i] = True
                self.mSpeed[i] = 0
                self.dataOut[i] = f"{self.mSpeed[i]}|{self.rotDirDes[i]}|{self.homing[i]}"
        return success

    def CheckJointLim(self):
        """Stops motors from running if the current angle goes past 
        the indicated joint limit.
        """
        #TODO: MAKE SEPERATE GRIPPER FUNCTIONS
        for i in range(self.lenData-1): #-1 for gripper
            self.limBool[i] = False
            if self.currAngle[i] < self.joints[i].lims[0] and \
               self.rotDirDes[i] == 1 and self.mSpeed[i] != 0:
                print(f"Lower lim reached: {self.rotDirDes[i]}")
                self.mSpeed[i] = 0
                self.limBool[i] = True
            elif self.currAngle[i] > self.joints[i].lims[1] and \
                self.rotDirDes[i] == 0 and self.mSpeed[i] != 0:
                print(f"Upper lim reached: {self.rotDirDes[i]}")
                self.mSpeed[i] = 0
                self.limBool[i] = True

    
    def GetDir(self):
        #DEPRICATED
        """Gives the desired direction of rotation.
        """
        for i in range(self.lenData):
            if self.currAngle[i] <= self.desAngle[i] and \
            self.rotDirCurr[i] != 0:
                self.rotDirDes[i] = 0
            elif self.currAngle[i] > self.desAngle[i] and self.rotDirCurr[i] != 1:
                self.rotDirDes[i] = 1
            else:
                self.rotDirDes[i] = self.rotDirCurr[i]
    
    def PControl1(self, i: int, mSpeedMax: int, mSpeedMin: int):
        #DEPRICATED
        """Gives motor speed commands propor tional to the angle error.
        :param i: Current iteration number.
        :param mSpeedMax: Maximum rotational speed, 
                          portrayed in PWM [0, 255].
        :param mSpeedMin: Minimum rotational speed, 
                          portrayed in PWM [0, 255]."""
        angleErr = abs(self.desAngle[i] - self.currAngle[i])
        self.mSpeed[i] = int(mSpeedMin + (angleErr/(10*np.pi))* \
                            (mSpeedMax - mSpeedMin))
        if self.mSpeed[i] > mSpeedMax:
            self.mSpeed[i] = mSpeedMax
        elif self.mSpeed[i] < mSpeedMin:
            self.mSpeed[i] = mSpeedMin

class PID():
    """Data storage class for PID information & execution of PID loops.
    """
    def __init__(self, kP: np.ndarray, kI: np.ndarray, kD: np.ndarray, ILim: np.ndarray):
        """Constructor for PID object.
        :param kP: Proportional gain term matrix.
        :param kI: Integral gain term matrix.
        :param kD: Differential gain term matrix.
        NOTE: To omit P-, I-, or D action, input kX = 0
        :param ILim: Limit to integral gain for anti-integral windup.
        """
        n = ILim.size
        self.kP = kP
        self.kI = kI
        self.kD = kD
        self.termI = np.zeros(n)
        self.ILim = ILim
        self.errPrev = np.zeros(n)

    def Execute(self, ref: np.ndarray, Fb: np.ndarray, dt: float):
        """Computes discrete PID error control given a reference 
        signal, a feedback signal, and PID constants.
        :param ref: Reference / Feed-forward signal.
        :param Fdb: Feedback signal.
        :param dt: Time between each error calculation in seconds.
        :return PID: PID output.
        
        Example input:
        ref = [0, 1, 2, 3, 4]
        Fdb = [0, 1.1, 1.9, 3.5, 4]
        kP = 1*np.eye(5)
        kI = 0.1*np.eye(5)
        kD = 0.01*np.eye(5)
        termI = [0,0,0,0,0]
        ILim = [5,5,5,5,5]
        dt = 0.01
        errPrev = [0,0,0,0,0]
        Output:
        [0.  0.7 2.3 1.5 4. ]
        """
        err = ref - Fb
        termP = np.dot(self.kP, err)
        for i in range(err.size):
            if abs(self.termI[i]) >= self.ILim[i]:
                self.termI[i] = np.sign(self.termI[i])*\
                                  self.ILim[i]
            else: #Trapezoidal integration
                trpz = dt*(self.errPrev[i] + err[i])/2
                self.termI[i] += self.kI[i,i]*trpz
        termD = np.dot(self.kD, (np.subtract(err, self.errPrev)/dt))
        PID = np.add(np.add(termP, self.termI), termD)
        self.errPrev = err
        return PID

    def Reset(self):
        """Reset previous error and integral term."""
        n = self.ILim.size
        self.errPrev = np.zeros(n)
        self.termI = np.zeros(n)
### ERROR CLASSES
class IKAlgorithmError(BaseException):
    """Custom error class for when the inverse kinematics algorithm is 
    unsuccesful.
    """
    def __init__(self, message: str = "The Inverse Kinematics algorithm " + 
                 "could not find a solution within its given iterations." + 
                 "This implies that either the configuration is outside" + 
                 "of the workspace of the robot, or the initial angle guess" +  
                 "was too far off."):
        self.message = message
    def __str__(self):
        return self.message

class DimensionError(BaseException):
    """Custom error class if dimensions of two inputs do not add up 
    while they should.
    """
    def __init__(self, message: str = ""):
        self.message = message
    def __str__(self):
        return self.message

class InputError(BaseException):
    """Custom error class if the data received over serial 
    communication is invalid.
    """
    def __init__(self, message: str = ""):
        self.message = message
    def __str__(self):
        return self.message
