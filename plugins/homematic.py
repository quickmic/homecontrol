#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import time
import logging
from xmlrpc.server import SimpleXMLRPCServer
import xmlrpc.client

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01
SETTINGS_LOGGER = 0x02
HOMEMATIC_PING = 0x00
HOMEMATIC_UPDATELEVELLAST = 0x01

def Init(ComQueue, Threads, Settings):
	for i in range(0, 6):
		if "homematicid" + str(i) in Settings:
			IDInternal = (Settings["homematicid" + str(i)]).lower()
			ComQueue[IDInternal] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue, Settings, IDInternal, str(i)))
			Threads[-1].start()

	return ComQueue, Threads

class KeepAlivePing(multiprocessing.Process):
	def __init__(self, ComQueue, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Index = Index
		self.IDInternal = IDInternal

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle("homecontrol-homematic-keepalive-" + self.Index)

		while True:
			time.sleep(1)
			self.ComQueue[self.IDInternal].put([HOMEMATIC_PING])

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.Index = Index
		self.SliderLevel = {}
		self.IDInternal = IDInternal

	def ReadData(self):
		DeviceData = list()
		DeviceList = self.proxy.listDevices()

		for i in range(0, len(DeviceList)):
			temp = str(DeviceList[i])

			if temp.find("BidCoS") == -1 and temp.find(":") != -1:
				pos = temp.find("'ADDRESS': '")
				temp = temp[pos+12:]
				pos = temp.find("'")
				temp = temp[:pos]
				Address = temp

				try:
					temp = str(self.proxy.getParamset(temp, "VALUES"))

					if temp == "{}":
						continue

					DeviceData = temp.split(",")

					for j in range(0, len(DeviceData)):
						pos = DeviceData[j].find("'")

						if pos != -1:
							temp2 = DeviceData[j][pos+1:]
							pos = temp2.find("'")
							temp3 = temp2[:pos]
							Parameter = temp3
							temp4 = DeviceData[j][pos+5:]

							if temp4[len(temp4)-1:] == "}":
								temp4 = temp4[:len(temp4)-1]

							Value = temp4

							if Value.lower() == "true":
								Value = "1"
							elif Value.lower() == "false":
								Value = "0"

							self.Settings[SETTINGS_LOGGER].debug("Homematic read data: " + Address + "/" + Parameter + " - " + str(Value))
							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + Address + "/" + Parameter, Value])
				except:
					None

	def Connect(self):
		Connected = False

		while not Connected:
			try:
				try:
					self.KeepAlivePingThread.terminate()
					self.KeepAlivePingThread.join()
					self.KeepAlivePingThread.close()
				except:
					None

				self.Settings[SETTINGS_LOGGER].debug("Homematic Connecting... " + self.Index)
				self.proxy = xmlrpc.client.ServerProxy('http://' + self.IP + ':' + str(self.Port))
				time.sleep(2)
				self.proxy.init(self.IP + ":" + str(50100 + int(self.Index)), 'homecontrol-' + self.Index)
				Connected = True
				self.KeepAlivePingThread = KeepAlivePing(self.ComQueue, self.IDInternal, self.Index) #Init Status Update Timer
				self.KeepAlivePingThread.start()
				self.Settings[SETTINGS_LOGGER].debug("Homematic Connection established... " + self.Index)
			except:
				self.Settings[SETTINGS_LOGGER].debug("Homematic Connection failed: " + self.Index)
				time.sleep(5)

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-homematic-commands-' + self.Index)

		self.IDExternal = self.Settings["homematicid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, self.IDExternal + "#"])
		self.IP = self.Settings["homematicip" + self.Index]
		self.Port = int(self.Settings["homematicport" + self.Index])
		InitCommands = []
		self.IP = self.Settings["ip"]
		self.Connect()
		self.Channels = []
		EventsThread = Events(self.ComQueue, self.Settings, self.IDInternal, self.IDExternal, self.Index)
		EventsThread.start()

		#Drop all Updates on Start but check for Init command
		time.sleep(int(self.Settings["waitforstatusupdate"]))

		while not self.ComQueue[self.IDInternal].empty():
			temp = self.ComQueue[self.IDInternal].get()
			InitCommands.append(temp)

		if self.Settings["firstrun"] == "1":
			self.ComQueue[self.IDInternal].put(["init"])

		for i in range (0, len(InitCommands)):
			temp = InitCommands[i]

			if temp[0] == "init":
				self.Settings[SETTINGS_LOGGER].debug("Homematic INIT")
				self.ComQueue[self.IDInternal].put(temp)
			elif temp[0] == HOMEMATIC_PING:
				None
			elif temp[0].find("levellast") != -1:
				temp10 = temp[0].replace("/levellast", "")
				self.SliderLevel[temp10] = temp[1]
			else:
				#Save channels
				self.Channels.append(temp[0].upper())

		while True:
			IncommingData = self.ComQueue[self.IDInternal].get()
#			self.Settings[SETTINGS_LOGGER].debug("Homematic incomming command: " + str(IncommingData))

			if IncommingData[0] == HOMEMATIC_PING:
				try:
					self.proxy.ping("1")
				except:
					#error
					for i in range (0, len(self.Channels)): #disable devices
						if self.Channels[i].find("STATE") != -1  or self.Channels[i].find("LEVEL") != -1:
							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Channels[i], "undefined"])

					self.Connect()
					self.ReadData()
					continue
			elif IncommingData[0] == "init":
				self.Settings[SETTINGS_LOGGER].debug("Homematic incomming command: init")
				self.ReadData()
			elif IncommingData[0] == HOMEMATIC_UPDATELEVELLAST:
				self.Settings[SETTINGS_LOGGER].debug("Homematic incomming command: HOMEMATIC_UPDATELEVELLAST")
				self.SliderLevel[IncommingData[1]] = IncommingData[2]
			elif IncommingData[0].find("levellasttoggle") != -1:
				self.Settings[SETTINGS_LOGGER].debug("Homematic incomming command: LEVELLASTTOGGLE")
				temp3 = IncommingData[0].split("/")

				if IncommingData[1] == "0":
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + temp3[0].upper() + "/" + "LEVELLASTTOGGLE", "0"])
					Value = "0"
				else:
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + temp3[0].upper() + "/" + "LEVELLASTTOGGLE", "1"])
					temp4 = IncommingData[0].replace("/levellasttoggle", "")
					Value = self.SliderLevel[temp4]

				self.proxy.setValue(temp3[0].upper(), "LEVEL", Value)
			else:
				self.Settings[SETTINGS_LOGGER].debug("Homematic incomming command: " + str(IncommingData))
				temp3 = IncommingData[0].split("/")
				SendData = IncommingData[1]

				if temp3[1] == "state":
					if SendData == "1":
						SendData = True
					else:
						SendData = False

				try:
					self.proxy.setValue(temp3[0].upper(), temp3[1].upper(), SendData)
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + temp3[0].upper() + "/" + temp3[1].upper(), IncommingData[1]])
				except:
					self.Settings[SETTINGS_LOGGER].debug("Homematic device offline: " + str(IncommingData))

class Events(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, IDExternal, Index):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.Index = Index
		self.SliderLevel = {}
		self.PreviousState = {}
		self.IDExternal = IDExternal
		self.IDInternal = IDInternal

	def event(self, interface_id, address, value_key, value):
		if value_key.lower() != "pong":
			self.Settings[SETTINGS_LOGGER].debug("Homematic incomming message: " + str(interface_id) + " - " +  str(address) + " - " +  str(value_key) + " - " +  str(value))

			if str(value).lower() == "true":
				Value = "1"
			elif str(value).lower() == "false":
				Value = "0"
			else:
				Value = str(value)

			#Skip identical incomming values
			if address + "/" + value_key in self.PreviousState:
				if self.PreviousState[address + "/" + value_key] == Value:
						return

			self.PreviousState[address + "/" + value_key] = Value
			self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + address + "/" + value_key, Value])

			if value_key.lower() == "level": #Save slider position for toggle function
				self.SliderLevel[address.lower()] = Value

				if float(Value) != 0:
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + address + "/" + value_key + "LASTTOGGLE", "1"])
				else:
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + address + "/" + value_key + "LASTTOGGLE", "0"])

			elif value_key.lower() == "working": #Update Slider Level-Position for Toggle-function (working = False) -> This rejects/skips the progress updates
				if value == False:
					if address.lower() in self.SliderLevel:
						if float(self.SliderLevel[address.lower()]) != 0:
							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + address + "/LEVELLAST", self.SliderLevel[address.lower()]])
							self.ComQueue[self.IDInternal].put([HOMEMATIC_UPDATELEVELLAST, address.lower(), self.SliderLevel[address.lower()]])

		return True

	def listDevices(self, interface_id):
		return []

	def newDevices(self, interface_id, dev_descriptions):
		return {}

	def deleteDevices(self, interface_id, addresses):
		return True

	def updateDevices(self, interface_id, address, hint):
		return True

	def newDevices(self, interface_id, dev_descriptions):
		return True

	def deleteDevices(self, interface_id, addresses):
		return True

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-homematic-event-' + self.Index)

		#XML RPC Server
		srv = SimpleXMLRPCServer(('0.0.0.0', 50100 + int(self.Index)), allow_none=True, logRequests=False)
		srv.register_introspection_functions()
		srv.register_multicall_functions()
		srv.register_instance(Events(self.ComQueue, self.Settings, self.IDInternal, self.IDExternal, self.Index))
		srv.serve_forever() #BLOCKING
