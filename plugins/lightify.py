#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import time
import codecs
import socket
import binascii
import random
import sys

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01

LIGHTIFY_REFRESH = 0x00

def Init(ComQueue, Threads, Settings):
	for i in range(0, 5):
		if "lightifyid" + str(i) in Settings:
			IDInternal = Settings["lightifyid" + str(i)].lower()
			ComQueue[IDInternal] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue, Settings, IDInternal, str(i)))
			Threads[-1].start()

	return ComQueue, Threads

class StateUpdate(multiprocessing.Process):
	def __init__(self, ComQueue, Index, IDInternal):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Index = Index
		self.IDInternal = IDInternal

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle("homecontrol-lightify-statustimer-" + self.Index)

		while True:
			time.sleep(1)
			self.ComQueue[self.IDInternal].put([LIGHTIFY_REFRESH])

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.Settings = Settings
		self.ComQueue = ComQueue
		self.IDInternal = IDInternal
		self.Index = Index

	def Connect(self):
		for i in range(0, len(self.lightifyDevicesState)):
			self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.lightifyDevicesName[i] + "/state", "undefined"])

		self.lightifyDevicesID = list()
		self.lightifyDevicesState = list()
		self.lightifyDevicesName = list()
		self.ComQueue[MQTT].put([MQTT_PUBLISH, self.Settings["lightifyip" + self.Index].replace(".", "-") + "/online", "0"])
		Connected = False
		self.socketLightify = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socketLightify.setblocking(0)
		self.socketLightify.settimeout(15)

		while Connected == False:
			try:
				self.socketLightify.connect((self.LightifyIP, self.LightifyPort))
				time.sleep(5)
				Connected = True
			except:
				time.sleep(5)

		self.ComQueue[MQTT].put([MQTT_PUBLISH, self.Settings["lightifyip" + self.Index].replace(".", "-") + "/online", "1"])
		self.socketLightify.send(bytes.fromhex("0B000013000000000100000000")) #get devices
		data = self.socketLightify.recv(1024)
		recvData = binascii.hexlify(data)
		recvData = recvData[6:]
		offset = 0
		i = 0

		#Detect devices and save ID and Name
		while offset + 100 < len(recvData):
			self.lightifyDevicesName.append(codecs.decode(recvData[offset + 68:offset + 100], 'hex').decode('ascii').strip("\0"))
			self.lightifyDevicesID.append(recvData[offset + 20:offset + 36].decode('ascii'))
			self.lightifyDevicesState.append("-1")
			offset = offset + 100
			i = i + 1

	def Status(self):
		self.SessionID = self.SessionID + 1
		sessionID = str(self.SessionID).zfill(8)
		self.socketLightify.send(bytes.fromhex("0B000013" + sessionID + "0100000000"))

		try:
			data = self.socketLightify.recv(1024)
		except:
			self.Connect()
			return

		recvData = binascii.hexlify(data)
		recvData = recvData[6:]
		offset = 0

		for i in range(0, len(self.lightifyDevicesState)):
			if str(recvData[offset + 17:offset + 19]) == "b'ff'":
				state = "undefined"
			else:
				state = str(int(recvData[offset + 52:offset + 54]))

			offset = offset + 100

			if state != self.lightifyDevicesState[i]:
				self.lightifyDevicesState[i] = state
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.lightifyDevicesName[i] + "/state", state])

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle("homecontrol-lightify " + self.Index)

#		RefreshTime = float(self.Settings["lightifyupdateinterval" + self.Index])
		self.IDExternal = self.Settings["lightifyid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH_NORETAIN, self.IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, self.IDExternal + "#"])


		self.LightifyIP = self.Settings["lightifyip" + self.Index]
		self.LightifyPort = int(self.Settings["lightifyport" + self.Index])
		self.SessionID = 0
		self.lightifyDevicesID = list()
		self.lightifyDevicesState = list()
		self.lightifyDevicesName = list()
		self.Connect()

		StateUpdateThread = StateUpdate(self.ComQueue, self.Index, self.IDInternal)
		StateUpdateThread.start()

		#Request Status
		while True:
			IncommingData = self.ComQueue[self.IDInternal].get()

			if IncommingData[0] == LIGHTIFY_REFRESH: #Restart Status Refresh Timer
				self.Status()
			else: #send command
				Temp = IncommingData[0].split("/")

				if len(IncommingData) > 1: #skip e.g. 'init'
					if IncommingData[1] != "undefined":
						for i in range(0, len(self.lightifyDevicesName)):
							if Temp[0] == self.lightifyDevicesName[i].lower():
								self.SessionID = self.SessionID + 1
								sessionID = str(self.SessionID).zfill(8)
								self.socketLightify.send(bytes.fromhex("0F000032" + sessionID + self.lightifyDevicesID[i].upper() + "0" + IncommingData[1]))

								try:
									ret = self.socketLightify.recv(1024)
									recvData = binascii.hexlify(ret)
									retbyte = recvData[len(recvData) - 2:]

									if retbyte == b'00': #Refresh State
										self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.lightifyDevicesName[i] + "/state", IncommingData[1]])
									else:
										self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + self.lightifyDevicesName[i] + "/state", "undefined"])
								except:
									self.Connect()

								break
