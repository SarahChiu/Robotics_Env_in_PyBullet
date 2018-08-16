import os,  inspect
#currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
#parentdir = os.path.dirname(os.path.dirname(currentdir))
#os.sys.path.insert(0,parentdir)

import pybullet as p
import numpy as np
import copy
import math
import pybullet_data
import time

class Kuka:

  def __init__(self, baseInitPos, jointInitPos, gripperInitOrn, \
          maxForce=200., fingerAForce=6, fingerBForce=5.5, fingerTipForce=6, \
          urdfRootPath=pybullet_data.getDataPath(), timeStep=0.01): 
    self.urdfRootPath = urdfRootPath
    self.timeStep = timeStep
    self.baseInitPos = baseInitPos
    self.jointInitPos = jointInitPos
    self.gripperInitOrn = gripperInitOrn
    
    self.maxForce = 200.
    self.fingerAForce = fingerAForce
    self.fingerBForce = fingerBForce
    self.fingerTipForce = fingerTipForce
    self.useInverseKinematics = 1
    self.useSimulation = 1
    self.useNullSpace = 1
    self.useOrientation = 1
    self.kukaEndEffectorIndex = 6
    #lower limits for null space
    self.ll=[-.967,-2 ,-2.96,0.19,-2.96,-2.09,-3.05]
    #upper limits for null space
    self.ul=[.967,2 ,2.96,2.29,2.96,2.09,3.05]
    #joint ranges for null space
    self.jr=[5.8,4,5.8,4,5.8,4,6]
    #restposes for null space
    self.rp=[0,0,0,0.5*math.pi,0,-math.pi*0.5*0.66,0]
    #joint damping coefficents
    self.jd=[0.00001,0.00001,0.00001,0.00001,0.00001,0.00001,0.00001,0.00001,0.00001,0.00001,0.00001,0.00001,0.00001,0.00001]
    self.reset()
    
  def reset(self):
    objects = p.loadSDF(os.path.join(self.urdfRootPath,"kuka_iiwa/kuka_with_gripper2.sdf"))
    self.kukaUid = objects[0]
    #for i in range (p.getNumJoints(self.kukaUid)):
    #  print(p.getJointInfo(self.kukaUid,i))
    p.resetBasePositionAndOrientation(self.kukaUid,self.baseInitPos,[0.000000,0.000000,0.000000,1.000000])
    self.jointPositions = self.jointInitPos

    self.numJoints = p.getNumJoints(self.kukaUid)
    for jointIndex in range (self.numJoints):
      p.resetJointState(self.kukaUid,jointIndex,self.jointPositions[jointIndex])
      p.setJointMotorControl2(self.kukaUid,jointIndex,p.POSITION_CONTROL,targetPosition=self.jointPositions[jointIndex],force=self.maxForce)
    
    linkState = p.getLinkState(self.kukaUid,self.kukaEndEffectorIndex)
    self.endEffectorPos = np.array(linkState[0])
    jointState = p.getJointState(self.kukaUid, 7)
    self.endEffectorAngle = jointState[0]

    self.motorNames = []
    self.motorIndices = []
    self.jointUpperLimit = []
    
    for i in range (self.numJoints):
      jointInfo = p.getJointInfo(self.kukaUid,i)
      qIndex = jointInfo[3]
      upperLimit = jointInfo[9]
      if qIndex > -1:
        #print("motorname")
        #print(jointInfo[1])
        self.motorNames.append(str(jointInfo[1]))
        self.motorIndices.append(i)
        self.jointUpperLimit.append(upperLimit)

    self.jointUpperLimit = np.array(self.jointUpperLimit)

  def initState(self, jointPos, renders):
    for i in range(len(jointPos)):
        self.jointPositions[i] = jointPos[i]

    curJointStates = list(p.getJointStates(self.kukaUid, range(self.kukaEndEffectorIndex+1)))
    curJointPos = []
    for state in curJointStates:
        curJointPos.append(list(state)[0])

    jointDiff = [self.jointPositions[i]-curJointPos[i] for i in range(len(curJointPos))]
    self.applyPosDiffAction(jointDiff, renders)

    linkState = p.getLinkState(self.kukaUid,self.kukaEndEffectorIndex)
    self.endEffectorPos = np.array(linkState[0])
    jointState = p.getJointState(self.kukaUid, 7)
    self.endEffectorAngle = jointState[0]

  def setGoodInitStateEE(self, jointPoses, renders):
    curJointStates = list(p.getJointStates(self.kukaUid, range(self.kukaEndEffectorIndex+1)))
    curJointPos = []
    for state in curJointStates:
        curJointPos.append(list(state)[0])

    jointDiff = [jointPoses[i]-curJointPos[i] for i in range(len(curJointPos))]
    self.applyPosDiffAction(jointDiff, renders)

    linkState = p.getLinkState(self.kukaUid,self.kukaEndEffectorIndex)
    self.endEffectorPos = np.array(linkState[0])
    jointState = p.getJointState(self.kukaUid, 7)
    self.endEffectorAngle = jointState[0]

  def getActionDimension(self):
    if (self.useInverseKinematics):
      return len(self.motorIndices)
    return 6 #position x,y,z and roll/pitch/yaw euler angles of end effector

  def getObservationDimension(self):
    return len(self.getObservation())

  def getObservation(self):
    observation = []

    #calculate current position
    jointStates = list(p.getJointStates(self.kukaUid, range(self.kukaEndEffectorIndex+1)))
    jointPos = []
    for state in jointStates:
      jointPos.append(list(state)[0])

    state = p.getLinkState(self.kukaUid,self.kukaEndEffectorIndex)
    pos = state[0]
    orn = state[1]
    euler = p.getEulerFromQuaternion(orn)

    observation.extend(jointPos)
    observation.extend(list(pos))
    observation.extend(list(euler))
    
    return observation

  def applyAction(self, motorCommands):
    
    #print ("self.numJoints")
    #print (self.numJoints)
    if (self.useInverseKinematics):
      
      dx = motorCommands[0]
      dy = motorCommands[1]
      dz = motorCommands[2]
      da = motorCommands[3]
      fingerAngle = motorCommands[4]
      
      state = p.getLinkState(self.kukaUid,self.kukaEndEffectorIndex)
      actualEndEffectorPos = state[0]
      #print("pos[2] (getLinkState(kukaEndEffectorIndex)")
      #print(actualEndEffectorPos[2])
      
      self.endEffectorPos[0] = self.endEffectorPos[0]+dx
      if (self.endEffectorPos[0]>0.75):
        self.endEffectorPos[0]=0.75
      if (self.endEffectorPos[0]<0.45):
        self.endEffectorPos[0]=0.45
      self.endEffectorPos[1] = self.endEffectorPos[1]+dy
      if (self.endEffectorPos[1]<-0.22):
        self.endEffectorPos[1]=-0.22
      if (self.endEffectorPos[1]>0.22):
        self.endEffectorPos[1]=0.22
      
      #print ("self.endEffectorPos[2]")
      #print (self.endEffectorPos[2])
      #print("actualEndEffectorPos[2]")
      #print(actualEndEffectorPos[2])
      if (dz>0 or actualEndEffectorPos[2]>0.10):
        self.endEffectorPos[2] = self.endEffectorPos[2]+dz
      if (actualEndEffectorPos[2]<0.10):
        self.endEffectorPos[2] = self.endEffectorPos[2]+0.0001
    
     
      self.endEffectorAngle = self.endEffectorAngle + da
      pos = self.endEffectorPos
      orn = p.getQuaternionFromEuler([0,-math.pi,0]) # -math.pi,yaw])
      if (self.useNullSpace==1):
        if (self.useOrientation==1):
          jointPoses = p.calculateInverseKinematics(self.kukaUid,self.kukaEndEffectorIndex,pos,orn,self.ll,self.ul,self.jr,self.rp)
        else:
          jointPoses = p.calculateInverseKinematics(self.kukaUid,self.kukaEndEffectorIndex,pos,lowerLimits=self.ll, upperLimits=self.ul, jointRanges=self.jr, restPoses=self.rp)
      else:
        if (self.useOrientation==1):
          jointPoses = p.calculateInverseKinematics(self.kukaUid,self.kukaEndEffectorIndex,pos,orn,jointDamping=self.jd)
        else:
          jointPoses = p.calculateInverseKinematics(self.kukaUid,self.kukaEndEffectorIndex,pos)
   
      #print("jointPoses")
      #print("self.kukaEndEffectorIndex")
      #print(self.kukaEndEffectorIndex)
      if (self.useSimulation):
        for i in range (self.kukaEndEffectorIndex+1):
          #print(i)
          p.setJointMotorControl2(bodyIndex=self.kukaUid,jointIndex=i,controlMode=p.POSITION_CONTROL,targetPosition=jointPoses[i],targetVelocity=0,force=self.maxForce,positionGain=0.03,velocityGain=1)
      else:
        #reset the joint state (ignoring all dynamics, not recommended to use during simulation)
        for i in range (self.numJoints):
          p.resetJointState(self.kukaUid,i,jointPoses[i])
      #fingers
      p.setJointMotorControl2(self.kukaUid,7,p.POSITION_CONTROL,targetPosition=self.endEffectorAngle,force=self.maxForce)
      p.setJointMotorControl2(self.kukaUid,8,p.POSITION_CONTROL,targetPosition=-fingerAngle,force=self.fingerAForce)
      p.setJointMotorControl2(self.kukaUid,11,p.POSITION_CONTROL,targetPosition=fingerAngle,force=self.fingerBForce)
      
      p.setJointMotorControl2(self.kukaUid,10,p.POSITION_CONTROL,targetPosition=0,force=self.fingerTipForce)
      p.setJointMotorControl2(self.kukaUid,13,p.POSITION_CONTROL,targetPosition=0,force=self.fingerTipForce)
    else:
      for action in range (len(motorCommands)):
        motor = self.motorIndices[action]
        p.setJointMotorControl2(self.kukaUid,motor,p.POSITION_CONTROL,targetPosition=motorCommands[action],force=self.maxForce)

  def applyAction2(self, motorCommands, renders):
    
    if (self.useInverseKinematics):
      
      dx = motorCommands[0]
      dy = motorCommands[1]
      dz = motorCommands[2]
      da = motorCommands[3]
      
      state = p.getLinkState(self.kukaUid,self.kukaEndEffectorIndex)
      actualEndEffectorPos = state[0]
      
      self.endEffectorPos[0] = self.endEffectorPos[0]+dx
      if (self.endEffectorPos[0]>0.75):
        self.endEffectorPos[0]=0.75
      if (self.endEffectorPos[0]<0.45):
        self.endEffectorPos[0]=0.45
      self.endEffectorPos[1] = self.endEffectorPos[1]+dy
      if (self.endEffectorPos[1]<-0.22):
        self.endEffectorPos[1]=-0.22
      if (self.endEffectorPos[1]>0.22):
        self.endEffectorPos[1]=0.22
      
      if (dz>0 or actualEndEffectorPos[2]>0.10):
        self.endEffectorPos[2] = self.endEffectorPos[2]+dz
      if (actualEndEffectorPos[2]<0.10):
        self.endEffectorPos[2] = self.endEffectorPos[2]+0.0001
    
     
      self.endEffectorAngle = self.endEffectorAngle + da
      pos = self.endEffectorPos
      orn = p.getQuaternionFromEuler([0,-math.pi,0]) # -math.pi,yaw])
      if (self.useNullSpace==1):
        if (self.useOrientation==1):
          jointPoses = p.calculateInverseKinematics(self.kukaUid,self.kukaEndEffectorIndex,pos,orn,self.ll,self.ul,self.jr,self.rp)
        else:
          jointPoses = p.calculateInverseKinematics(self.kukaUid,self.kukaEndEffectorIndex,pos,lowerLimits=self.ll, upperLimits=self.ul, jointRanges=self.jr, restPoses=self.rp)
      else:
        if (self.useOrientation==1):
          jointPoses = p.calculateInverseKinematics(self.kukaUid,self.kukaEndEffectorIndex,pos,orn,jointDamping=self.jd)
        else:
          jointPoses = p.calculateInverseKinematics(self.kukaUid,self.kukaEndEffectorIndex,pos)

      initJointState = p.getJointStates(self.kukaUid, range(self.kukaEndEffectorIndex+1))
      initJointPos = np.array([state[0] for state in initJointState])
   
      prevEndEffectorPos = np.array(actualEndEffectorPos)
      jointState = p.getJointState(self.kukaUid, 7)
      prevJointPos = jointState[0]
      stuckNum = 0
      while True:
        #Calculate the current position
        linkState = p.getLinkState(self.kukaUid,self.kukaEndEffectorIndex)
        actualEndEffectorPos = np.array(linkState[0])
        jointState = p.getJointState(self.kukaUid, 7)
        actualJointPos = jointState[0]
        if sum(abs(np.array(jointPoses[:self.kukaEndEffectorIndex+1])-initJointPos)) > 0.3:
          break
        #Calculate the difference between the target position
        prevJointDiff = abs(actualJointPos-prevJointPos)
        jointDiff = abs(actualJointPos-self.endEffectorAngle)
        if np.linalg.norm(prevEndEffectorPos-actualEndEffectorPos) <= 1e-3 and prevJointDiff <= 1e-3:
          stuckNum += 1
        if (np.linalg.norm(self.endEffectorPos-actualEndEffectorPos) <= 1e-3 and jointDiff <= 1e-3) or stuckNum >= 1/self.timeStep:
          break

        if (self.useSimulation):
          for i in range (self.kukaEndEffectorIndex+1):
            p.setJointMotorControl2(\
              bodyIndex=self.kukaUid,jointIndex=i,controlMode=p.POSITION_CONTROL,targetPosition=jointPoses[i],targetVelocity=0,force=self.maxForce,positionGain=0.03,velocityGain=1)
        else:
          for i in range(self.numJoints):
            p.resetJointState(self.kukaUid,i,jointPoses[i])
        #fingers
        p.setJointMotorControl2(self.kukaUid,7,p.POSITION_CONTROL,targetPosition=self.endEffectorAngle,force=self.maxForce)
      
        p.setJointMotorControl2(self.kukaUid,10,p.POSITION_CONTROL,targetPosition=0,force=self.fingerTipForce)
        p.setJointMotorControl2(self.kukaUid,13,p.POSITION_CONTROL,targetPosition=0,force=self.fingerTipForce)

        p.stepSimulation()
        if renders:
          time.sleep(self.timeStep)
        prevEndEffectorPos = actualEndEffectorPos
        prevJointPos = actualJointPos

      self.endEffectorPos = actualEndEffectorPos
      self.endEffectorAngle = actualJointPos
      
    else:
      for action in range (len(motorCommands)):
        motor = self.motorIndices[action]
        p.setJointMotorControl2(self.kukaUid,motor,p.POSITION_CONTROL,targetPosition=motorCommands[action],force=self.maxForce)
     
  #directly apply position difference commands
  #handle obstacle avoidance
  def applyPosDiffAction(self, motorCommands, renders):
    #calculate the target position
    jointStates = list(p.getJointStates(self.kukaUid, range(len(motorCommands))))
    targetPos = []
    for state in jointStates:
      targetPos.append(list(state)[0])
    prevPos = np.array(targetPos)
    stuckNum = 0
    targetPos = np.clip(np.array(targetPos)+np.array(motorCommands), -self.jointUpperLimit[:len(targetPos)], self.jointUpperLimit[:len(targetPos)])
    while True:
      #calculate current position
      jointStates = list(p.getJointStates(self.kukaUid, range(len(motorCommands))))
      jointPos = []
      for state in jointStates:
        jointPos.append(list(state)[0])
      if sum(abs(np.array(jointPos)-prevPos)) <= 1e-2:
        stuckNum += 1
      if sum(abs(targetPos-np.array(jointPos))) <= 1e-2 or stuckNum >= 1/self.timeStep:
        break
      for action in range (len(motorCommands)):
        motor = self.motorIndices[action]
        p.setJointMotorControl2(self.kukaUid,motor,p.POSITION_CONTROL,targetPosition=targetPos[action],force=self.maxForce)
      p.stepSimulation()
      if renders:
        time.sleep(self.timeStep)
      prevPos = np.array(jointPos)
