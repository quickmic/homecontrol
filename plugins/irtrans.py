#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import time
import socket

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01

IRTRANS_CONNECT = 0x00
IRTRANS_SLIDERUPDATE = 0x01
IRTRANS_INCOMMINGDATA = 0x02
IRTRANS_SLIDER_TERMINATE = 0x03

def Init(ComQueue, Threads, Settings):
	for i in range(0, 1000):
		if "irtransid" + str(i) in Settings:
			IDInternal = Settings["irtransid" + str(i)].lower()
			ComQueue[IDInternal] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue, Settings, IDInternal, str(i)))
			Threads[-1].start()

	return ComQueue, Threads

#Timer used for Sliders (Repeat IR-Command X-Times)
class Slider(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, IndexID, Socket, CurrentValue, SetValue, SliderCommandQueue):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.IndexID = IndexID
		self.Socket = Socket
		self.CurrentValue = CurrentValue
		self.SetValue = SetValue
		self.IDInternal = IDInternal
		self.SliderCommandQueue = SliderCommandQueue

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-irtans-commandtimer-' + self.IndexID)

		CommandID = "irtranscommandid" + self.IndexID
		CommandUpID = "irtranscommandup" + self.IndexID
		CommandDownID = "irtranscommanddown" + self.IndexID
		CommandRangeID = "irtranscommandrange" + self.IndexID

		if self.SetValue >= self.CurrentValue:
			Command = self.Settings[CommandUpID]
			Repeat = self.SetValue - self.CurrentValue
			Increment = 1 / float(self.Settings[CommandRangeID])
		else:
			Command = self.Settings[CommandDownID]
			Repeat = self.CurrentValue - self.SetValue
			Increment = (1 / float(self.Settings[CommandRangeID])) * -1

		Repeat = int(Repeat * int(self.Settings[CommandRangeID]))

		for i in range (0, Repeat):
			self.CurrentValue = self.CurrentValue + Increment
			temp = "Asndhex H" + Command
			self.Socket.send(temp.encode())
			self.Socket.recv(32)
			tempValue = float("{0:.2f}".format(self.CurrentValue))
			self.ComQueue[self.IDInternal].put([IRTRANS_SLIDERUPDATE, self.Settings[CommandID], str(tempValue)])

			if not self.SliderCommandQueue.empty():
				IncommingData = self.SliderCommandQueue.get()

				if IncommingData == IRTRANS_SLIDER_TERMINATE:
					break

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.IDInternal = IDInternal
		self.Index = Index

	def connect( self ):
		Connected = False

		try:
			self.socketIRTransCommand.close
		except:
			None

		self.socketIRTransCommand = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		while Connected == False:
			print("IRTrans Commandsocket connecting...")

			try:
				self.socketIRTransCommand.connect((self.Settings["irtransip" + self.Index], int(self.Settings["irtransport" + self.Index])))
			except:
				time.sleep(5)
				continue

			time.sleep(5)
			Connected = True
			self.socketIRTransCommand.send(("ASCI").encode())
			print("IRTrans Commandsocket connected")
			time.sleep(2)

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-irtrans-commands-' + self.Index)

		self.IDExternal = self.Settings["irtransid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH_NORETAIN, self.IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, self.IDExternal + "#"])
		ThreadEvents = Events(self.ComQueue, self.Settings, self.IDInternal, self.Index)
		ThreadEvents.start()
		Values = {}
		InitCommands = []
		SliderThread = None
		SliderThreadActiveID = ""
		SliderCommandQueue = multiprocessing.Queue()

		#Init Values
		for i in range (0, 50):
			IndexID = self.Index + "," + str(i)
			CommandID = "irtranscommandid" + IndexID

			if CommandID in self.Settings:
				Values[self.Settings[CommandID]] = 0
				Values[self.Settings[CommandID] + "last"] = 0
			else:
				break

		#Init states as in Mosqitto DB
		time.sleep(int(self.Settings["waitforstatusupdate"]))

		while not self.ComQueue[self.IDInternal].empty():
			temp = self.ComQueue[self.IDInternal].get()

			if len(temp) > 1:

				Values[temp[0]] = temp[1] #Init previous values

		if self.Settings["firstrun"] == "1":
			self.ComQueue[self.IDInternal].put(["init"])

		self.connect()

		while True:
			Data = self.ComQueue[self.IDInternal].get()

			if Data[0] == IRTRANS_CONNECT:
				self.connect()
			elif Data[0] == "init":
				for i in range (0, 50):
					if "irtranscommandid" + self.Index + "," + str(i) in self.Settings:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings["irtranscommandid" + self.Index + "," + str(i)], "0"])
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings["irtranscommandid" + self.Index + "," + str(i)] + "last", "0"])
						Values[self.Settings["irtranscommandid" + self.Index + "," + str(i)]] = "0"
						Values[self.Settings["irtranscommandid" + self.Index + "," + str(i)] + "last"] = "0"
			elif Data[1] == "undefined":
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + Data[0], Data[1]])
			elif Data[0] == IRTRANS_SLIDERUPDATE: #Incomming Silder Value Update from Timer
				Values[Data[1]] = Data[2]
				Values[Data[1] + "last"] = Data[2]
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + Data[1], Data[2]])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + Data[1] + "last", Data[2]])
			elif Data[0] == IRTRANS_INCOMMINGDATA: #Data Received via IR
				for i in range (0, 50):
					IndexID = self.Index + "," + str(i)
					CommandID = "irtranscommandid" + IndexID
					CommandStateID = "irtranscommandstate" + IndexID
					CommandToggleID = "irtranscommandtoggle" + IndexID
					CommandUpID = "irtranscommandup" + IndexID
					CommandDownID = "irtranscommanddown" + IndexID
					CommandCommand = "irtranscommand" + IndexID
					CommandRangeID = "irtranscommandrange" + IndexID

					if CommandToggleID in self.Settings:
						if self.Settings[CommandToggleID].find(Data[1]) != -1:
							if Values[self.Settings[CommandID]] == 0:
								Values[self.Settings[CommandID]] = 1
							else:
								Values[self.Settings[CommandID]] = 0

							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID], str(Values[self.Settings[CommandID]])])
							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID] + "last", str(Values[self.Settings[CommandID]])])
							time.sleep(0.25) #Delay after Toggle (skip repeated commands)

							#Drop IR-Data for 0.25 Second after Toggle
							CacheIncomming = []

							while not self.ComQueue[self.IDInternal].empty():
								Temp10 = self.ComQueue[self.IDInternal].get()

								if len(Temp10[1]) < 10: #Not an IR command
									CacheIncomming.append(Temp10)

							#Pass other commands except toggle
							for i in range (0, len(CacheIncomming)):
								self.ComQueue[self.IDInternal].put(CacheIncomming[i])

							break

					if CommandUpID in self.Settings:
						if self.Settings[CommandUpID].find(Data[1]) != -1:
							Values[self.Settings[CommandID]] = float(Values[self.Settings[CommandID]]) + float(1 / float(self.Settings[CommandRangeID]))

							if Values[self.Settings[CommandID]] > 100:
								Values[self.Settings[CommandID]] = 100

							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID], str(Values[self.Settings[CommandID]])])
							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID] + "last", str(Values[self.Settings[CommandID]])])
							break
						elif self.Settings[CommandDownID].find(Data[1]) != -1:
							Values[self.Settings[CommandID]] = float(Values[self.Settings[CommandID]]) - float(1 / float(self.Settings[CommandRangeID]))

							if Values[self.Settings[CommandID]] < 0:
								Values[self.Settings[CommandID]] = 0

							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID], str(Values[self.Settings[CommandID]])])
							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID] + "last", str(Values[self.Settings[CommandID]])])
							break

					if CommandStateID in self.Settings:
						if self.Settings[CommandCommand].find(Data[1]) != -1:
							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID], str(self.Settings[CommandStateID])])
							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID] + "last", str(self.Settings[CommandStateID])])
							break
			elif Data[0].find("lasttoggle") != -1:
				if Data[1] == "1":
					temp3 = Data[0].replace("lasttoggle", "")
					Values[temp3] = Values[temp3 + "last"]
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + temp3, Values[temp3]])
			else: #Commands
				 #Terminate previous Thread, if still in progress (no simultanious commands possible)
				if SliderThread != None:
					if SliderThread.is_alive():
						SliderCommandQueue.put(IRTRANS_SLIDER_TERMINATE)
						SliderThread.join()

				for i in range (0, 50):
					IndexID = self.Index + "," + str(i)
					CommandID = "irtranscommandid" + IndexID
					CommandStateID = "irtranscommandstate" + IndexID
					CommandToggleID = "irtranscommandtoggle" + IndexID
					CommandUpID = "irtranscommandup" + IndexID
					CommandDownID = "irtranscommanddown" + IndexID
					CommandCommand = "irtranscommand" + IndexID
					CommandCommandRepeat = "irtranscommandrepeat" + IndexID

					if CommandID in self.Settings:
						if self.Settings[CommandID] == Data[0]:
							if CommandStateID in self.Settings: #check if state-command
								if self.Settings[CommandStateID] == Data[1]:
									temp = "Asndhex H" + self.Settings[CommandCommand]
									self.socketIRTransCommand.send(temp.encode())
									self.socketIRTransCommand.recv(32)
									self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID], self.Settings[CommandStateID]])
									self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID] + "last", self.Settings[CommandStateID]])
									Values[self.Settings[CommandID]] = self.Settings[CommandStateID]
									Values[self.Settings[CommandID] + "last"] = self.Settings[CommandStateID]
							elif CommandToggleID in self.Settings: #check if toggle-command
								if float(Values[self.Settings[CommandID]]) <= 0:
									Values[self.Settings[CommandID]] = "1"
									Values[self.Settings[CommandID] + "last"] = "1"
									self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID], "1"])
									self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID] + "last", "1"])
								else:
									Values[self.Settings[CommandID]] = "0"
									Values[self.Settings[CommandID] + "last"] = "0"
									self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID], "0"])
									self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Settings[CommandID] + "last", "0"])

								temp = "Asndhex H" + self.Settings[CommandToggleID]

								if CommandCommandRepeat in self.Settings:
									for i in range (0, int( self.Settings[CommandCommandRepeat]   ) + 1):
										self.socketIRTransCommand.send(temp.encode())
										self.socketIRTransCommand.recv(32)
								else:
									self.socketIRTransCommand.send(temp.encode())
									self.socketIRTransCommand.recv(32)
							elif CommandUpID in self.Settings: #check if slider-command
								SetValue = float(Data[1])

								if SetValue <= 0:
									SetValue = 0

								if SetValue >= 100:
									SetValue = 100

								CurrentValue = float(Values[self.Settings[CommandID]])
								SliderThread = Slider(self.ComQueue, self.Settings, self.IDInternal, IndexID, self.socketIRTransCommand, CurrentValue, SetValue, SliderCommandQueue)
								SliderThread.start()

class Events(multiprocessing.Process):
	def __init__( self, ComQueue, Settings, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.Index = Index
		self.IDInternal = IDInternal

	def connect(self):
		self.ComQueue[MQTT].put([MQTT_PUBLISH, self.Settings["irtransip" + self.Index].replace(".", "-") + "/online", "0"])
		Connected = False

		try:
			self.socketEvents.close
		except:
			None

		self.socketEvents = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socketEvents.setblocking(0)
		self.socketEvents.settimeout(15)

		while Connected == False:
			print("IRTrans Eventsocket connecting...")

			try:
				self.socketEvents.connect((self.Settings["irtransip" + self.Index], int(self.Settings["irtransport" + self.Index])))
			except:
				time.sleep(5)
				continue

			time.sleep(5)
			Connected = True
			self.socketEvents.send(("ASCR").encode())
			print("IRTrans Eventsocket connected")
			time.sleep(2)
			self.ComQueue[MQTT].put([MQTT_PUBLISH, self.Settings["irtransip" + self.Index].replace(".", "-") + "/online", "1"])

		self.ComQueue[self.IDInternal].put([IRTRANS_CONNECT])

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-irtrans-events-' + self.Index)

		Data = ""
		self.connect()

		while True:
			try:
				Data = self.socketEvents.recv(512)

				if not Data:
					Data = ""
					self.connect()
					continue

				Ret = str(Data).replace("\\n'", "")
				Pos = Ret.find("RCV_HEX")
				Ret = Ret[Pos + 8:]
				Ret = Ret[:len(Ret) - 1]
				self.ComQueue[self.IDInternal].put([IRTRANS_INCOMMINGDATA, Ret])
			except socket.timeout:
				if Data == "detecttimeout":
					Data = ""
					self.connect()
					continue

				Data = "detecttimeout"
				self.socketEvents.send(("Aver").encode()) #query Version as keep alive
				continue
