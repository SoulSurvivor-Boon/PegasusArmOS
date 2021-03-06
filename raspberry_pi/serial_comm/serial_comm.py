import os
import sys
#Find directory path of current file
current = os.path.dirname(os.path.realpath(__file__))
#Find directory path of parent folder and add to sys path
parent = os.path.dirname(current)
sys.path.append(parent)

from classes import SerialData, InputError
from robot_init import robot as Pegasus
from typing import Tuple
import serial
import serial.tools.list_ports
import time
import numpy as np
np.set_printoptions(precision=4, floatmode='fixed', suppress=True)


#TODO: Docstrings, examples, & tests.
def FindSerial(askInput=False) -> str:
    """Finds the Serial port to which the Arduino / Teensy is connected
    :param askInput: If multiple connections are found, 
                     ask the user to choose.
    :return port: The string representation of the port.
    :return warning: Boolean indicating a warning has been printed."""
    warning = False
    comports = serial.tools.list_ports.comports()
    port = []
    for p in comports:
        if p.manufacturer:
            if 'Arduino' in p.manufacturer or 'Teensy' in p.manufacturer:
                port.append(p.device)
    if not port:
        raise IOError("No microcontroller found!")
    elif len(port) > 1:
        print("Multiple micrcontrollers connected: ")
        if askInput:
            portIndex = input("Please choose the index (starting from 0)" + 
                              f"from the following list: {port}")
            try:
                port = port[portIndex]
            except:
                print("Invalid index, taking first port.")
                port = port[0]
        else:
            print(f"Taking first port ({port[0]})")
            port = port[0]
        warning = True
    else:
        port = port[0]
    return port, warning

def StartComms(comPort: str, baudRate: int = 115200) -> serial.Serial:
    """Intantiates a serial connection with a microcontroller over USB.
    :param comPort: The address of the communication port to which the 
                    local microcontroller is connected.
    :param baudRate: Maximum number of bytes being sent over serial
                     per second. Has to equate the set baudrate of the
                     local microcontroller.
    :return localMu: A Serial-class instance.

    Example input:
    comPort = "/dev/ttyAMA0"
    baudRate = 115200
    Output:
    localMu: serial.Serial(comPort, baudRate)
    """
    localMu = serial.Serial(comPort, baudRate, timeout=1)
    time.sleep(0.05) #wait for serial to open
    if localMu.isOpen():
        print(f"{localMu.port} connected!")
    return localMu

def GetComms(localMu: serial.Serial, encAlg: str = "utf-8") -> str:
    """Reads and decodes incoming byte data over a serial connection.
    :param localMu: A serial.Serial() instance representing the serial
                    communication to the local microcontroller.
    :param encAlg: String containing the algorithm used to encode and 
                   decode the bytes sent over serial.
    :return dataIn: String of decoded bytes available in the serial buffer 
                    until the representation of the newline character.
    Example input:
    localMu = StartComms("COM9", baudRate=115200)
    encalg = "utf-8"
    Output:
    "This is an example of information sent over the serial port."
    """
    # dataIn = localMu.readline().decode(encAlg).rstrip() #remove decoding
    # if(not dataIn):
    #     raise InputError("No string read.")
    # elif(dataIn[0] != "["):
    #     raise InputError("Invalid start marker")
    # return dataIn
    #EXPERIMENTAL!
    dataIn = localMu.read(localMu.inWaiting()).decode(encAlg)
    if '\n' in dataIn:
        lines = dataIn.split('\r\n')
        dataIn = lines[-2]
    return dataIn

def SReadAndParse(SPData: SerialData,  localMu: serial.Serial, 
                  encAlg: str = "utf-8") -> Tuple[float, bool]:
    """Serial read function which parses data into SerialData object.
    :param SPData: SerialData instance, stores & parses serial data.
    :param dtComm: Desired minimal time between communication loops.
    :param localMu: serial.Serial() instance representing the serial
                    communication with the local microcontroller.
    :param encAlg: Algorithm used to encode data into bytes for serial.
    :return controlBool: Boolean indicating if control can be done on 
                         new data.
    
    Example input:
    baudRate = 115200
    lenData = 6 #Number of motors
    cprList = [4320 for i in range(lenData)]
    desAngles = [3*np.pi for i in range(lenData)]
    maxDeltaAngles = [np.pi for i in range(lenData)]
    tolAngle = [0.04*np.pi for i in range(lenData)]
    SPData = SerialData(lenData, cprList, desAngles, maxDeltaAngles, tolAngle)
    localMu = StartComms("COM9", baudRate)
    encAlg = "utf-8"

    Example output:
    True
    """
    controlBool = True
    if localMu.inWaiting() == 0:
        return controlBool
    elif localMu.inWaiting() > 0:
        try:
            dataIn = GetComms(localMu, encAlg)
        except InputError as e:
            controlBool = False
            print(str(e))
            localMu.reset_input_buffer()
            return controlBool
        except UnicodeDecodeError as e:
            controlBool = False
            localMu.reset_input_buffer()
            return controlBool
        dataPacket = dataIn[1:-1].split('][')
        if len(dataPacket) != SPData.lenData: #flush & retry
            print("error")
            controlBool = False
            localMu.reset_input_buffer()
            return controlBool
        localMu.reset_input_buffer()
        #Expected form dataPacket[i]: "totCount|rotDir"
        #Or "totCount|rotDir|currentVal|homingBool"
        #Extract both variables, put into SPData object.
        SPData.ExtractVars(dataPacket)
    return controlBool

#Proof-of-concept function: No tests available
def SetPointControl1(SPData: SerialData, localMu: serial.Serial, 
                    mSpeedMax: int = 255, mSpeedMin: int = 150, 
                    encAlg: str = "utf-8"):
    """Outputs the desired motor speeds and rotational direction based 
    on the inputs of a local microcontroller over serial.
    :param: SPData: A SerialData class instance.
    :param localMu: A serial.Serial() instance representing the serial
                    communication to the local microcontroller.
    :param mSpeedMax: Maximum integer value of the motor speed PWM.
    :param mSpeedMin: Minimum integer value of the motor speed PWM.
    :param encAlg: String containing the algorithm used to encode and 
                   decode the bytes sent over serial. 
    
    Example input:
    lenData = 5 #Number of motors
    cprList = [4320 for i in range(lenData)]
    desAngles = [3*np.pi for i in range(lenData)]
    maxDeltaAngles = [0.1*np.pi for i in range(lenData)]
    tolAngle = [0.02*np.pi for i in range(lenData)]
    SPData = SerialData(lenData, cprList, desAngles, maxDeltaAngles, 
                        tolAngle)
    localMu = StartComms("COM9", 115200)
    mSpeedMax = 200
    mSpeedMin = 150
    encAlg = "utf-8"
    SetPointControl1(SPData, localMu, mSpeedMax, mSpeedMin, encAlg)
    """
    commFault = SPData.checkCommFault()
    SPData.GetDir()
    success = SPData.CheckTolAng()
    for i in range(SPData.lenData):
        if commFault[i] or success[i]:
            continue
        else:
            SPData.PControl1(i, mSpeedMax, mSpeedMin)
            #Proportional control
        SPData.dataOut[i] = f"{SPData.mSpeed[i]}|" + \
                            f"{SPData.rotDirDes[i]}"
    localMu.write(f"{SPData.dataOut}\n".encode(encAlg))

if __name__ == "__main__":
    ### SETUP SERIAL COMMUNICATION ###
    baudRate = 115200
    lenData = 6 #Number of motors
    cprList = [512]*lenData
    desAngles = [4*np.pi, 4*np.pi, 4*np.pi, 4*np.pi, 4*np.pi]
    maxDeltaAngles = [5*np.pi for i in range(lenData)]
    tolAngle = [0.02*np.pi for i in range(lenData)]
    SPData = SerialData(lenData, Pegasus.joints)
    dtComm = 0.005
    port, warning = FindSerial()
    localMu = StartComms(port)
    mSpeedMax = 200
    mSpeedMin = 120
    encAlg = "utf-8"
    print("Starting serial communication. \nType Ctrl+C to stop")
    ## END OF SERIAL COMMUNICATION SETUP ###

    try:
        lastCheck = time.perf_counter()
        lastPrint = time.perf_counter()
        dtPrint = 0.33
        while True:
            #SReadAndParse has an internal dt clock
            lastCheck = SReadAndParse(SPData, lastCheck, 
                                      dtComm, localMu)[0]
            if time.perf_counter() - lastPrint >= dtPrint:
                angles = np.array([SPData.currAngle])/np.pi
                print(angles)
                print(SPData.totCount)
                print(SPData.homing)
                lastPrint = time.perf_counter()
    except KeyboardInterrupt:
        #Set motor speeds to zero & close serial.
        localMu.write(f"{['0|0|0'] * lenData}\n".encode(encAlg))
        time.sleep(dtComm)
        localMu.__del__()
        print("Ctrl+C pressed, quitting...")
