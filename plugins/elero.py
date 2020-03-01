#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import time
import termios
import os

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
ELEROIO = 0x01
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01

#Elero
ELERO_NOINFO = 0x00
ELERO_TOP_POSITION_STOP = 0x01
ELERO_BOTTOM_POSITION_STOP = 0x02
ELERO_INTERMEDIATE_POSITION_STOP = 0x03
ELERO_TILT_VENTILATION_POSITION_STOP = 0x04
ELERO_BLOCKING = 0x05
ELERO_OVERHEATED = 0x06
ELERO_TIMEOUT = 0x07
ELERO_START_MOVE_UP = 0x08
ELERO_START_MOVE_DOWN = 0x09
ELERO_MOVING_UP = 0x0A
ELERO_MOVING_DOWN = 0x0B
ELERO_STOPPED_IN_UNDEFINED_POSITION = 0x0D
ELERO_TOP_POSITION_STOP_WHICH_IS_TILT_POSITION = 0x0E
ELERO_BOTTOM_POSITION_STOP_WHICH_IS_INTERMEDIATE_POSITION = 0x0F
ELERO_SWITCH_DEVICE_OFF = 0x10
ELERO_SWITCH_DEVICE_ON = 0x11
ELERO_STATUS = 0x20
ELERO_REFRESH = 0x21
ELERO_CHANNEL_INDEX = 0x22
ELERO_CHANNEL_ID = 0x23
ELERO_CHANNEL_STATUS_OLD = 0x24
ELERO_CHANNEL_COUNTER = 0x25
ELERO_COMMAND_EXECUTED = 0x26

def Init(ComQueue, Threads, Settings):
	EleroEnabled = False

	for i in range(0, 16):
		if "eleroid" + str(i) in Settings:
			if not EleroEnabled:
				EleroEnabled = True
				ComQueue[ELEROIO] = multiprocessing.Queue()

			IDInternal = Settings["eleroid" + str(i)].lower()
			ComQueue[IDInternal] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue, Settings, IDInternal, str(i)))
			Threads[-1].start()

	if EleroEnabled:
		Threads.append(EleroIO(ComQueue, Settings))
		Threads[-1].start()

	return ComQueue, Threads

class StateUpdate(multiprocessing.Process):
	def __init__(self, ComQueue, RefreshTime):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.RefreshTime = RefreshTime

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-elero-stateupdate')

		time.sleep(self.RefreshTime)
		self.ComQueue[ELEROIO].put([ELERO_REFRESH])

class EleroIO(multiprocessing.Process):
	def __init__(self, ComQueue, Settings):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-elero-state')

		#Serial Connect
		IFLAG = 0
		OFLAG = 1
		CFLAG = 2
		LFLAG = 3
		ISPEED = 4
		OSPEED = 5
		CC = 6

		#Serial Connect
		Baud = 38400
		SerialPort = self.Settings["eleroserialdevice"]
		FD = os.open(SerialPort, os.O_RDWR | os.O_NOCTTY | os.O_NDELAY)
		Attrs = termios.tcgetattr(FD)
		bps_sym = termios.B38400

		#Set I/O speed.
		Attrs[ISPEED] = bps_sym
		Attrs[OSPEED] = bps_sym

		#8N1
		Attrs[CFLAG] &= ~termios.PARENB
		Attrs[CFLAG] &= ~termios.CSTOPB
		Attrs[CFLAG] &= ~termios.CSIZE
		Attrs[CFLAG] |= termios.CS8

		#No flow control
		Attrs[CFLAG] &= ~termios.CRTSCTS

		#Turn on READ & ignore contrll lines.
		Attrs[CFLAG] |= termios.CREAD | termios.CLOCAL

		#Turn off software flow control.
		Attrs[IFLAG] &= ~(termios.IXON | termios.IXOFF | termios.IXANY)

		#Make raw
		Attrs[LFLAG] &= ~(termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG)
		Attrs[OFLAG] &= ~termios.OPOST

		#http://unixwiz.net/techtips/termios-vmin-vtime.html
		Attrs[CC][termios.VMIN] = 0
		Attrs[CC][termios.VTIME] = 20
		termios.tcsetattr(FD, termios.TCSANOW, Attrs)

		#Set blocking
		os.set_blocking(FD, True)

		#Preload Settings (for Performance reasons)
		RefreshTime = float(self.Settings["elerostateupdateinterval"])
		EleroChannels = {}
		Commands = {}
		Commands[ELERO_STATUS] = [bytes.fromhex("AA054C00010004"), bytes.fromhex("AA054C00020003"), bytes.fromhex("AA054C00040001"), bytes.fromhex("AA054C000800FD"), bytes.fromhex("AA054C001000F5"), bytes.fromhex("AA054C002000E5"), bytes.fromhex("AA054C004000C5"), bytes.fromhex("AA054C00800085"), bytes.fromhex("AA054C01000004"), bytes.fromhex("AA054C02000003"), bytes.fromhex("AA054C04000001")]
		Commands[ELERO_MOVING_UP] = [bytes.fromhex("AA054C000120E4"), bytes.fromhex("AA054C000220E3"), bytes.fromhex("AA054C000420E1"), bytes.fromhex("AA054C000820DD"), bytes.fromhex("AA054C001020D5"), bytes.fromhex("AA054C002020C5")]
		Commands[ELERO_MOVING_DOWN] = [bytes.fromhex("AA054C000140C4"), bytes.fromhex("AA054C000240C3"), bytes.fromhex("AA054C000440C1"), bytes.fromhex("AA054C000840BD"), bytes.fromhex("AA054C001040B5"), bytes.fromhex("AA054C002040A5")]
		Commands[ELERO_STOPPED_IN_UNDEFINED_POSITION] = [bytes.fromhex("AA054C000110F4"), bytes.fromhex("AA054C000210F3"), bytes.fromhex("AA054C000410F1"), bytes.fromhex("AA054C000810ED"), bytes.fromhex("AA054C001010E5"), bytes.fromhex("AA054C002010D5")]
		ChannelCounter = 0

		for i in range(0, 25):
			if "eleroid" + str(i) in self.Settings:
				EleroChannels[ELERO_CHANNEL_INDEX, ChannelCounter] = i
				EleroChannels[ELERO_CHANNEL_ID, ChannelCounter] = self.Settings["eleroid" + str(i)].lower()
				EleroChannels[ELERO_CHANNEL_STATUS_OLD, ChannelCounter] = 0xFF
				EleroChannels[ELERO_CHANNEL_COUNTER] = ChannelCounter
				ChannelCounter += 1

		#Init Status Update Timer
		StateUpdateThread = StateUpdate(self.ComQueue, RefreshTime)
		StateUpdateThread.start()
		StatusProgress = 0

		while True:
			IncommingData = self.ComQueue[ELEROIO].get()
			byteData = b""

			if IncommingData[0] == ELERO_REFRESH: #Status update
				StateUpdateThread.join() #Wait Status timer finished
				os.write(FD, Commands[ELERO_STATUS][EleroChannels[ELERO_CHANNEL_INDEX, StatusProgress]]) # Request Status

				while len(byteData) != 7:
					byteData = byteData + os.read(FD, 1)

				data = byteData[5]

				if EleroChannels[ELERO_CHANNEL_STATUS_OLD, StatusProgress] != data:
					self.ComQueue[EleroChannels[ELERO_CHANNEL_ID, StatusProgress]].put([ELERO_STATUS, data]) #Send Data (Put in Queue)
					EleroChannels[ELERO_CHANNEL_STATUS_OLD, StatusProgress] = data

				#Recusive Status query
				if StatusProgress == EleroChannels[ELERO_CHANNEL_COUNTER]:
					StatusProgress = 0
				else:
					StatusProgress += 1

				#Restart Status Timer
				StateUpdateThread = StateUpdate(self.ComQueue, RefreshTime)
				StateUpdateThread.start()
			else: #Commands
				if len(IncommingData) > 1: #skip e.g. 'init'
					os.write(FD, Commands[IncommingData[0]][int(IncommingData[1])])

					while len(byteData) != 7:
						byteData = byteData + os.read(FD, 1)

					if len(IncommingData) > 2:
						IDInternal = self.Settings["eleroid" + IncommingData[2]].lower()
						self.ComQueue[IDInternal].put([ELERO_STATUS, IncommingData[0]])
						self.ComQueue[IDInternal].put([ELERO_COMMAND_EXECUTED])

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.IDInternal = IDInternal
		self.Index = Index

	def LoadSubjectivePositions(self, Direction, Duration):
		#Precalculate subjective command and progress positions and save in table
		#Avoid divided by zero
		if Direction == ELERO_MOVING_UP:
			SlowDurationEnd = float(self.Settings["eleroslowdurationupend" + self.Index])
			SlowDurationStart = float(self.Settings["eleroslowdurationupstart" + self.Index])
		else:
			SlowDurationEnd = float(self.Settings["eleroslowdurationdownend" + self.Index])
			SlowDurationStart = float(self.Settings["eleroslowdurationdownstart" + self.Index])

		#Precause divided by zero
		if SlowDurationStart == 0.0:
			SlowDurationStart = 0.0001

		if SlowDurationEnd == 0.0:
			SlowDurationEnd = 0.0001

		ThresholdProgressEnd = SlowDurationEnd / Duration[Direction]
		ThresholdProgressStart = SlowDurationStart / Duration[Direction]
		ThresholdProgressMiddle = 1 - (ThresholdProgressStart + ThresholdProgressEnd)
		FactorMiddle = Duration[Direction] / (Duration[Direction] - SlowDurationEnd - SlowDurationStart + SlowDurationEnd * ThresholdProgressEnd + SlowDurationStart * ThresholdProgressStart)
		FactorEnd = ThresholdProgressEnd * FactorMiddle
		FactorStart = ThresholdProgressStart * FactorMiddle
		ThresholdCommandStart = ThresholdProgressEnd * FactorEnd
		ThresholdCommandMiddle = (ThresholdProgressMiddle) * FactorMiddle + ThresholdProgressEnd * FactorEnd

		for i in range(0, 10001):
			Position = i / 10000

			#Precalculate subjective progress position
			if  Position <= ThresholdProgressEnd:
				ProgressPosition = Position * FactorEnd
			elif  Position >= ThresholdProgressEnd and Position <= 1 - ThresholdProgressStart:
				ProgressPosition = (Position - ThresholdProgressEnd) * FactorMiddle + ThresholdProgressEnd * FactorEnd
			else:
				ProgressPosition = (Position - (1 - ThresholdProgressStart)) * FactorStart + (((1 - ThresholdProgressStart) - ThresholdProgressEnd) * FactorMiddle + (ThresholdProgressEnd * FactorEnd))

			#Precalculate subjective command position
			if Position <= ThresholdCommandStart:
				CommandPosition = Position / FactorEnd
			elif Position >= ThresholdCommandStart and Position <= ThresholdCommandMiddle:
				CommandPosition = (Position - ThresholdProgressEnd * FactorEnd) / FactorMiddle + ThresholdProgressEnd
			else:
				CommandPosition = ((Position - (((1 - ThresholdProgressStart) - ThresholdProgressEnd) * FactorMiddle + (ThresholdProgressEnd * FactorEnd))) / FactorStart) + (1 - ThresholdProgressStart)

			#Fix Rounting issues
			if ProgressPosition > 1:
				ProgressPosition = 1.0

			if ProgressPosition < 0:
				ProgressPosition = 0.0

			if CommandPosition > 1:
				CommandPosition = 1.0

			if CommandPosition < 0:
				CommandPosition = 0.0

			#Save Positions
			self.ProgressTable[Direction, round(Position, 4)] = ProgressPosition
			self.CommandTable[Direction, round(Position, 4)] = CommandPosition

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-elero-commands-' + self.Index)

		ChannelID = int(self.Settings["elerochannel" + self.Index])
		IDExternal = self.Settings["eleroid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH_NORETAIN, IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.Duration = {}
		self.MovingStartTime = {}
		self.Duration[ELERO_MOVING_UP] = float(self.Settings["elerodurationup" + self.Index])
		self.Duration[ELERO_MOVING_DOWN] = float(self.Settings["elerodurationdown" + self.Index])
		self.MovingStartTime[ELERO_MOVING_UP] = 0.0
		self.MovingStartTime[ELERO_MOVING_DOWN] = 0.0
		self.TimeMeasurement = 0.0
		PositionCommand = 0.0
		self.Position = 1.0
		self.PositionStop = 1.0
		Status = ELERO_STOPPED_IN_UNDEFINED_POSITION
		Direction = ELERO_MOVING_DOWN
		PositionSubjectiveOld = -1.0
		time.sleep(int(ChannelID)) #staggered Initialization
		self.ProgressTable = {}
		self.CommandTable = {}
		WaitforCommandExecution = False

		#Preload subjective Positions
		self.LoadSubjectivePositions(ELERO_MOVING_DOWN, self.Duration)
		self.LoadSubjectivePositions(ELERO_MOVING_UP, self.Duration)

		#Init on Top Position
		self.ComQueue[ELEROIO].put([ELERO_MOVING_UP, str(ChannelID)])
		time.sleep(self.Duration[ELERO_MOVING_UP])

		#Restore previous State
		RestorePosition = ""

		TerminateCommand = ""

		while not self.ComQueue[self.IDInternal].empty():
			temp = self.ComQueue[self.IDInternal].get()

			if temp[0] == "position":
				RestorePosition = temp

		if RestorePosition != "":
			self.ComQueue[self.IDInternal].put(RestorePosition)

		self.ComQueue[self.IDInternal].put([ELERO_STATUS, ELERO_REFRESH])

		while True:
			#Incomming Commands or Status
			IncommingData = self.ComQueue[self.IDInternal].get()

			if IncommingData[0] == "position":
				IncommingData[1] = round(float(IncommingData[1]), 4)

				if IncommingData[1] > 1.0:
					IncommingData[1] = 1

				if IncommingData[1] < 0.0:
					IncommingData[1] = 0

				PositionTemp = self.ProgressTable[Direction, round(self.Position, 4)]

				if IncommingData[1] < round(PositionTemp, 2): #down
					PositionCommand = self.CommandTable[ELERO_MOVING_DOWN, round(IncommingData[1], 4)]

					if Status != ELERO_MOVING_DOWN: #skip if already moving down(update Commandposition only)
						#Send command and wait for execution
						self.ComQueue[ELEROIO].put([ELERO_MOVING_DOWN, str(ChannelID), self.Index])

						while True:
							IncommingData = self.ComQueue[self.IDInternal].get()

							if IncommingData[0] == ELERO_COMMAND_EXECUTED:
								break

					Status = ELERO_MOVING_DOWN
					PositionSubjectiveOld = -1 # Force refresh
				elif IncommingData[1] > round(PositionTemp, 2): #up
					PositionCommand = self.CommandTable[ELERO_MOVING_UP, round(IncommingData[1], 4)]

					if Status != ELERO_MOVING_UP: #skip if already moving up (update Commandposition only)
						self.ComQueue[ELEROIO].put([ELERO_MOVING_UP, str(ChannelID), self.Index])

                	                        #Send command and wait for execution
						while True:
							IncommingData = self.ComQueue[self.IDInternal].get()

							if IncommingData[0] == ELERO_COMMAND_EXECUTED:
								break

					Status = ELERO_MOVING_UP
					PositionSubjectiveOld = -1 # Force refresh
			elif IncommingData[0] == ELERO_STATUS:
				if IncommingData[1] != ELERO_REFRESH:
					Status = IncommingData[1]

			elif IncommingData[0] == ELERO_COMMAND_EXECUTED:
				WaitforCommandExecution = False

			#Status Actions
			if Status == ELERO_MOVING_UP or Status == ELERO_START_MOVE_UP:
				time.sleep(0.1)
				self.ComQueue[self.IDInternal].put([ELERO_STATUS, ELERO_REFRESH])

				if Direction == ELERO_MOVING_DOWN:
					self.StopElero()
					temp = self.ProgressTable[ELERO_MOVING_DOWN, round(self.PositionStop, 4)]
					self.PositionStop = self.CommandTable[ELERO_MOVING_UP, round(temp, 4)]
					self.Position = self.PositionStop
					self.MovingStartTime[ELERO_MOVING_UP] = 0.0
					self.MovingStartTime[ELERO_MOVING_DOWN] = 0.0

				Direction = ELERO_MOVING_UP

				if self.MovingStartTime[ELERO_MOVING_UP] == 0.0:
					self.MovingStartTime[ELERO_MOVING_UP] = time.time()
					self.TimeMeasurement = 0.0
				else:
					self.TimeMeasurement = time.time() - self.MovingStartTime[ELERO_MOVING_UP]

				self.Position = self.TimeMeasurement / self.Duration[ELERO_MOVING_UP] + self.PositionStop

				if self.Position > 1.0:
					self.Position = 1.0
					Status = ELERO_STOPPED_IN_UNDEFINED_POSITION

				if PositionCommand != -1.0:
					if self.Position >= PositionCommand:
						if WaitforCommandExecution == False:
							WaitforCommandExecution = True
							self.ComQueue[ELEROIO].put([ELERO_STOPPED_IN_UNDEFINED_POSITION, str(ChannelID), self.Index])
			elif Status == ELERO_MOVING_DOWN or Status == ELERO_START_MOVE_DOWN:
				time.sleep(0.1)
				self.ComQueue[self.IDInternal].put([ELERO_STATUS, ELERO_REFRESH])

				if Direction == ELERO_MOVING_UP:
					self.StopElero()
					temp = self.ProgressTable[ELERO_MOVING_UP, round(self.PositionStop, 4)]
					self.PositionStop = self.CommandTable[ELERO_MOVING_DOWN, round(temp, 4)]
					self.Position = self.PositionStop
					self.MovingStartTime[ELERO_MOVING_UP] = 0.0
					self.MovingStartTime[ELERO_MOVING_DOWN] = 0.0

				Direction = ELERO_MOVING_DOWN

				if self.MovingStartTime[ELERO_MOVING_DOWN] == 0.0:
					self.MovingStartTime[ELERO_MOVING_DOWN] = time.time()
					self.TimeMeasurement = 0.0
				else:
					self.TimeMeasurement = time.time() - self.MovingStartTime[ELERO_MOVING_DOWN]

				self.Position = self.PositionStop - self.TimeMeasurement / self.Duration[ELERO_MOVING_DOWN]

				if self.Position < 0.0:
					self.Position = 0.0
					Status = ELERO_STOPPED_IN_UNDEFINED_POSITION

				if PositionCommand != -1.0:
					if self.Position <= PositionCommand:
						if WaitforCommandExecution == False:
							WaitforCommandExecution = True
							self.ComQueue[ELEROIO].put([ELERO_STOPPED_IN_UNDEFINED_POSITION, str(ChannelID), self.Index])
			elif Status == ELERO_TOP_POSITION_STOP or Status == ELERO_TOP_POSITION_STOP_WHICH_IS_TILT_POSITION:
				self.Position = 1.0
				self.MovingStartTime[ELERO_MOVING_UP] = 0.0
				self.MovingStartTime[ELERO_MOVING_DOWN] = 0.0
				self.PositionStop = 1.0
			elif Status == ELERO_BOTTOM_POSITION_STOP or Status == ELERO_BOTTOM_POSITION_STOP_WHICH_IS_INTERMEDIATE_POSITION:
				self.Position = 0.0
				self.MovingStartTime[ELERO_MOVING_UP] = 0.0
				self.MovingStartTime[ELERO_MOVING_DOWN] = 0.0
				self.PositionStop = 0.0
			elif Status == ELERO_STOPPED_IN_UNDEFINED_POSITION or Status == ELERO_INTERMEDIATE_POSITION_STOP or Status == ELERO_TILT_VENTILATION_POSITION_STOP:
				self.StopElero()

			#Update Slider
			PositionSubjective = round(self.ProgressTable[Direction, round(self.Position, 4)], 2)

			if PositionSubjectiveOld != PositionSubjective:
				PositionSubjectiveOld = PositionSubjective
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "position", str(PositionSubjective)])

	def StopElero(self):
		if self.MovingStartTime[ELERO_MOVING_UP] != 0.0: #Moving up stop
			self.TimeMeasurement = time.time() - self.MovingStartTime[ELERO_MOVING_UP]
			self.PositionStop = self.TimeMeasurement / self.Duration[ELERO_MOVING_UP] + self.PositionStop

		if self.MovingStartTime[ELERO_MOVING_DOWN] != 0.0: # Moving down stop
			self.TimeMeasurement = time.time() - self.MovingStartTime[ELERO_MOVING_DOWN]
			self.PositionStop = self.PositionStop - self.TimeMeasurement / self.Duration[ELERO_MOVING_DOWN]

		if self.PositionStop > 1.0:
			self.PositionStop = 1.0
		elif self.PositionStop < 0.0:
			self.PositionStop = 0.0

		self.Position = self.PositionStop
		self.MovingStartTime[ELERO_MOVING_UP] = 0.0
		self.MovingStartTime[ELERO_MOVING_DOWN] = 0.0
