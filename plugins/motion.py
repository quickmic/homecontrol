#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import time
import urllib.request
import socket
import logging

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01
SETTINGS_LOGGER = 0x02

def Init(ComQueue, Threads, Settings):
	for i in range(0, 5):
		if "motionid" + str(i) in Settings:
			IDInternal = Settings["motionid" + str(i)].lower()
			ComQueue[IDInternal] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue, Settings, IDInternal, str(i)))
			Threads[-1].start()

	return ComQueue, Threads

class Events(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, Index, IDExternal):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.Index = Index
		self.IDExternal = IDExternal

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-motion-event-'+ self.Index)

		socketListening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		socketListening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		socketListening.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		socketListening.bind(("0.0.0.0", 50000 + int(self.Index)))
		socketListening.listen(0)
		Event = {}

		while True:
			sockClient, addr = socketListening.accept()
			serialBuffer = sockClient.recv(8).decode(encoding='ascii') #waiting here for input
			self.Settings[SETTINGS_LOGGER].debug("Motion incomming message: " + str(serialBuffer))
			temp = serialBuffer.split("_")
			SendMQTT = self.IDExternal + temp[0] #StandardID + Index

			if temp[1] == "e1":
				if "event" + temp[0] in Event:
					if not Event["event" + temp[0]]:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/EVENT", "1"])
				else:
					self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/EVENT", "1"])

				Event["event" + temp[0]] = True
			elif temp[1] == "e0":
				if "event" + temp[0] in Event:
					if Event["event" + temp[0]]:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/EVENT", "0"])
				else:
					self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/EVENT", "0"])

				Event["event" + temp[0]] = False
			elif temp[1] == "m1":
				if "movie" + temp[0] in Event:
					if not Event["movie" + temp[0]]:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/MOVIE", "1"])
				else:
					self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/MOVIE", "1"])

				Event["movie" + temp[0]] = True
			elif temp[1] == "m0":
				if "movie" + temp[0] in Event:
					if Event["movie" + temp[0]]:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/MOVIE", "0"])
				else:
					self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/MOVIE", "0"])

				Event["movie" + temp[0]] = False
			elif temp[1] == "c1":
				if "connection" + temp[0] in Event:
					if not Event["connection" + temp[0]]:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/CONNECTION", "1"])
				else:
					self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/CONNECTION", "1"])

				Event["connection" + temp[0]] = True
			elif temp[1] == "c0":
				if "connection" + temp[0] in Event:
					if Event["connection" + temp[0]]:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/CONNECTION", "0"])
				else:
					self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/CONNECTION", "0"])

				Event["connection" + temp[0]] = False

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.IDInternal = IDInternal
		self.Index = Index

	def ReadState(self):
		#Get number of cameras
		Data = ""

		while Data == "": #Check if motion is running
			try:
				Data = self.URLLib.urlopen(self.URL + '0/detection/status').read().decode(encoding='utf-8')
			except:
				self.Settings[SETTINGS_LOGGER].debug("Motion not running")
				time.sleep(5)

		Data = Data.lower()
		temp = Data.split("\n")

		#Loop all cameras
		for i in range(0, len(temp) - 1):
			temp[i] = temp[i].replace("camera", "").strip()
			pos = temp[i].find(" ")
			temp[i] = temp[i][:pos]
			self.CameraID.append(temp[i])

			#Read Detection status:
			time.sleep(0.1)
			Data = self.URLLib.urlopen(self.URL + str(i) + '/detection/status').read().decode(encoding='utf-8')

			if Data.lower().find("active") != -1:
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + str(i) + "/DETECTION", "1"])
			else:
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + str(i) + "/DETECTION", "0"])

			#Query Connection status:
			time.sleep(0.1)
			Data = self.URLLib.urlopen(self.URL + str(i) + '/detection/connection').read().decode(encoding='utf-8')

			if Data.lower().find("ok") != -1:
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + str(i) + "/CONNECTION", "1"])
			else:
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + str(i) + "/CONNECTION", "0"])

			#Configure Motion settings for callbacks
			time.sleep(0.1)
			self.URLLib.urlopen(self.URL + self.CameraID[i] + '/config/set?on_event_start=/bin/echo%20-n%20' + str(i) + '_e1|/bin/netcat%20' + self.myIP + '%2050000%20-q%200').read()
			time.sleep(0.1)
			self.URLLib.urlopen(self.URL + self.CameraID[i] + '/config/set?on_event_end=/bin/echo%20-n%20' + str(i) + '_e0|/bin/netcat%20' + self.myIP + '%2050000%20-q%200').read()
			time.sleep(0.1)
			self.URLLib.urlopen(self.URL + self.CameraID[i] + '/config/set?on_movie_start=/bin/echo%20-n%20' + str(i) + '_m1|/bin/netcat%20' + self.myIP + '%2050000%20-q%200').read()
			time.sleep(0.1)
			self.URLLib.urlopen(self.URL + self.CameraID[i] + '/config/set?on_movie_end=/bin/echo%20-n%20' + str(i) + '_m0|/bin/netcat%20' + self.myIP + '%2050000%20-q%200').read()
			time.sleep(0.1)
			self.URLLib.urlopen(self.URL + self.CameraID[i] + '/config/set?on_camera_lost=/bin/echo%20-n%20' + str(i) + '_c0|/bin/netcat%20' + self.myIP + '%2050000%20-q%200').read()
			time.sleep(0.1)
			self.URLLib.urlopen(self.URL + self.CameraID[i] + '/config/set?on_camera_found=/bin/echo%20-n%20' + str(i) + '_c1|/bin/netcat%20' + self.myIP + '%2050000%20-q%200').read()
			time.sleep(0.1)
#			self.URLLib.urlopen(self.URL + self.CameraID[i] + "/config/write").read()
	                #Reset Events and pictures
			self.ComQueue[self.IDInternal].put([str(i) + "/event", "0"])
			self.ComQueue[self.IDInternal].put([str(i) + "/picture", "0"])

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-motion-' + self.Index)

		time.sleep(int(self.Index)) #staggered Initialization
		self.URL = "http://" + self.Settings["motionip" + self.Index] + ":" + self.Settings["motionport" + self.Index] + "/"
		self.IDExternal = self.Settings["motionid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.myIP = self.Settings["ip"]
		IDExternal = self.Settings["motionid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, self.IDExternal + "#"])
		EventsThread = Events(self.ComQueue, self.Settings, self.Index, IDExternal)
		EventsThread.start()
		time.sleep(int(self.Settings["waitforstatusupdate"]))
		self.CameraID = list()

		#http Authentification
		password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
		top_level_url = "http://" + self.myIP + "/"
		password_mgr.add_password(None, top_level_url, "quickmic", "password")
		handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
		opener = urllib.request.build_opener(handler)
		urllib.request.install_opener(opener)
		self.URLLib = urllib.request

		self.ReadState()

		while True:
			DataIncomming = self.ComQueue[self.IDInternal].get()
			self.Settings[SETTINGS_LOGGER].debug("Motion incomming command: " + str(DataIncomming))
			Temp = DataIncomming[0].split("/")

			if len(Temp) >= 2:
				SendMQTT = self.IDExternal + Temp[0] #StandardID + Index

				if Temp[1] == "detection":
					if DataIncomming[1] == "1":
						self.URLLib.urlopen(self.URL + self.CameraID[int(Temp[0])] + "/detection/start")
					else:
						self.URLLib.urlopen(self.URL + self.CameraID[int(Temp[0])] + "/detection/pause")
						self.URLLib.urlopen(self.URL + self.CameraID[int(Temp[0])] + "/action/eventend")
						self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/EVENT", "0"])

					self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/DETECTION", DataIncomming[1]])
				elif Temp[1] == "event":
					if DataIncomming[1] == "1":
						self.URLLib.urlopen(self.URL + self.CameraID[int(Temp[0])] + "/action/eventstart")
					else:
						self.URLLib.urlopen(self.URL + self.CameraID[int(Temp[0])] + "/action/eventend")

					self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/EVENT", DataIncomming[1]])
				elif Temp[1] == "picture":
					if DataIncomming[1] == "1":
						self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/PICTURE", "1"])
						self.URLLib.urlopen(self.URL + self.CameraID[int(Temp[0])] + '/action/snapshot')
						time.sleep(0.25)

					self.ComQueue[MQTT].put([MQTT_PUBLISH, SendMQTT + "/PICTURE", "0"])

				time.sleep(0.1)
			else:
				if Temp[0] == "init":
					self.Settings[SETTINGS_LOGGER].debug("Motion init")
					self.ReadState()
