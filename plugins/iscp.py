#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import time
import socket
import logging

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01
SETTINGS_LOGGER = 0x02

ISCP_DISCONNECTED = 0x00
ISCP_TIMEOUT = 0x01

def Init(ComQueue, Threads, Settings):
	for i in range(0, 10):
		if "iscpid" + str(i) in Settings:
			IDInternal = Settings["iscpid" + str(i)].lower()
			ComQueue[IDInternal] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue, Settings, IDInternal, str(i)))
			Threads[-1].start()

	return ComQueue, Threads

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.Index = Index
		self.socketISCP = 0
		self.IDInternal = IDInternal

	def SendData(self, data):
		try:
			self.socketISCP.send(data.encode())
		except:
			None

	def Connect(self):
		self.ComQueue[MQTT].put([MQTT_PUBLISH, self.Settings["iscpip" + self.Index].replace(".", "-") + "/online", "0"])

		try:
			self.EventsThread.terminate()
			self.EventsThread.join()
			self.EventsThread.close()
			self.Settings[SETTINGS_LOGGER].debug("ISCP Close")
		except:
			None

		Connected = False

		try:
			self.socketISCP.close
		except:
			None

		self.socketISCP = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socketISCP.setblocking(0)
		self.socketISCP.settimeout(5)

		while Connected == False:
			self.Settings[SETTINGS_LOGGER].debug("ISCP connecting...")

			try:
				self.socketISCP.connect((self.Settings["iscpip" + self.Index], int(self.Settings["iscpport" + self.Index])))
			except:
				time.sleep(5)
				continue

			time.sleep(5)
			Connected = True

		self.Settings[SETTINGS_LOGGER].debug("ISCP connected")
		time.sleep(2)
		self.EventsThread = Events(self.ComQueue, self.Settings, self.Channels, self.IDInternal, self.IDExternal, self.Index, self.socketISCP)
		self.EventsThread.start()
		self.ComQueue[MQTT].put([MQTT_PUBLISH, self.Settings["iscpip" + self.Index].replace(".", "-") + "/online", "1"])
		self.ComQueue[self.IDInternal].put(["init"])

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-iscp-commands-' + self.Index)

		self.IDExternal = self.Settings["iscpid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, self.IDExternal + "#"])
		time.sleep(int(self.Settings["waitforstatusupdate"]))
		PWRToggleState = "-1"
		self.Channels = []

		#Drop all Updates on Start
		while not self.ComQueue[self.IDInternal].empty():
			self.ComQueue[self.IDInternal].get()

		self.Connect()

                #Load Channels
		for i in range (0, 200):
			if "iscpcommand" + self.Index + "," + str(i) in self.Settings:
				self.Channels.append(self.Settings["iscpcommand" + self.Index + "," + str(i)])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Channels[i], "undefined"])
			else:
				break

		while True:
			IncommingData = self.ComQueue[self.IDInternal].get()
			self.Settings[SETTINGS_LOGGER].debug("ISCP incomming command: " + str(IncommingData))

			if IncommingData[0] == "init":
				self.Settings[SETTINGS_LOGGER].debug("ISCP init")
				self.SendData("ISCP\x00\x00\x00\x10\x00\x00\x00" + chr(10) + "\x01\x00\x00\x00!1DIFQSTN\x0D") #Use Display query as init indicator

				for i in range(0, len(self.Channels)):
					time.sleep(0.01)
					self.SendData("ISCP\x00\x00\x00\x10\x00\x00\x00" + chr(len(self.Channels[i]) + 7) + "\x01\x00\x00\x00!1" + self.Channels[i] + "QSTN\x0D")
			elif IncommingData[0] == ISCP_DISCONNECTED:
				PWRToggleState = "-1"
				self.Connect()
			elif IncommingData[0] == "*":
				if IncommingData[1] == "undefined": #only accapt undefined state for all channels
					for i in range(0, len(self.Channels)):
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Channels[i], "undefined"])
						time.sleep(0.01)
			elif IncommingData[0] == "powertoggle":
				if PWRToggleState != IncommingData[1]:
					PWRToggleState = IncommingData[1]
					self.Settings[SETTINGS_LOGGER].debug("ISCP Powertoggle update: " + str(IncommingData))
				else:
					self.Settings[SETTINGS_LOGGER].debug("ISCP Powertoggle continue")
					continue

				if IncommingData[1] == "1":
					for i in range(0, len(self.Channels)):
						if self.Channels[i] != "PWR":
							time.sleep(0.01)
							self.SendData("ISCP\x00\x00\x00\x10\x00\x00\x00" + chr(len(self.Channels[i]) + 7) + "\x01\x00\x00\x00!1" + self.Channels[i] + "QSTN\x0D")
							self.Settings[SETTINGS_LOGGER].debug("ISCP State request")
				else:
					for i in range(0, len(self.Channels)):
						if self.Channels[i] != "PWR":
							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Channels[i], "undefined"])
			else:
				if IncommingData[1] != "undefined":
					Value = IncommingData[1]
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + IncommingData[0].upper(), Value]) #Don't wait for incomming state update, refresh directly

					if IncommingData[0] == "mvl":
						Value = str(hex(int(float(Value) / 0.0125)))[2:].upper()
						iscp_message = "MVL"
					else:
                	                        iscp_message = IncommingData[0].upper()

					if len(Value) == 1:
						Value = "0" + Value

					iscp_message = iscp_message + Value
					self.SendData("ISCP\x00\x00\x00\x10\x00\x00\x00" + chr(len(iscp_message) + 3) + "\x01\x00\x00\x00!1" + iscp_message + "\x0D")

					#Design Power function as toggle for all other Functions
					if IncommingData[0] == "pwr":
						self.ComQueue[self.IDInternal].put(["powertoggle", IncommingData[1]])

class Events(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, Channels, IDInternal, IDExternal, Index, socketISCP):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.Index = Index
		self.Channels = Channels
		self.IDInternal = IDInternal
		self.IDExternal = IDExternal
		self.socketISCP = socketISCP
		self.Status = {}

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-iscp-event-' + self.Index)

		MaxVolumeFactor = 1 / float(self.Settings["iscpmaxvolume" + self.Index])
		Data = ""
		Init = True

		while True:
			try:
				Data = self.socketISCP.recv(128)
				self.Settings[SETTINGS_LOGGER].debug("ISCP incomming message: " + str(Data))

				if not Data:
					self.ComQueue[self.IDInternal].put([ISCP_DISCONNECTED])
					continue
			except socket.timeout:
				if Data == ISCP_TIMEOUT:
					self.Settings[SETTINGS_LOGGER].debug("ISCP timeout")

					#Disable all channels
					for i in range(0, len(self.Channels)):
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.Channels[i], "undefined"])
						time.sleep(0.01)

					self.ComQueue[self.IDInternal].put([ISCP_DISCONNECTED])
					return

				Data = ISCP_TIMEOUT
				self.socketISCP.send(("ISCP\x00\x00\x00\x10\x00\x00\x00" + chr(10) + "\x01\x00\x00\x00!1PWRQSTN\x0D").encode()) #Use PWR query as keepalive
				continue
			except socket.error:
				self.Settings[SETTINGS_LOGGER].debug("ISCP disconnected")
				self.ComQueue[self.IDInternal].put([ISCP_DISCONNECTED])
				continue

			Data = Data.decode(encoding='ascii')
			DataArray = Data.split("\r\n")

			for i in range(0, len(DataArray) - 1):
				ID = DataArray[i][18:21]
				Value = DataArray[i][21:(len(DataArray[i]) - 1)]

				if ID == "MVL": #Master Volume
					Value = int(Value, 16)
					Value = "{:.2f}".format(float(Value * MaxVolumeFactor))
				else:
					if Value == "ON":
						Value = "1"
					elif Value == "OFF":
						Value = "0"

					#Refesh Power Toggle
					if ID == "PWR":
						if Value == "01":
							Value = "1"
						else:
							Value = "0"

							self.Status = {} #Force refresh all states after PWR is back on


							if not Init:
								self.Status["PWR"] = "0" #but keep PWR state

							Init = False

				if ID in self.Status:
					if self.Status[ID] != Value:
						Refresh = True
					else:
						Refresh = False
				else:
					Refresh = True

				if Refresh:
					self.Settings[SETTINGS_LOGGER].debug("ISCP send State: " + str([MQTT_PUBLISH, self.IDExternal + ID, Value]))

					#Refesh Power Toggle
					if ID == "PWR":
						self.ComQueue[self.IDInternal].put(["powertoggle", Value])
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + ID, Value])

					elif ID == "DIF":
						#DIF request used s init indication
						self.Settings[SETTINGS_LOGGER].debug("ISCP init triggered")
						self.Status = {}
						continue
					else:
						if "PWR" in self.Status:
							if self.Status["PWR"] != "0":
								self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + ID, Value])
							else:
								self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + ID, "undefined"])
						else:
							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + ID, "undefined"])

					self.Status[ID] = Value
