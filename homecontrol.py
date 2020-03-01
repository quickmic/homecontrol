#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import time
import socket
import struct
import os
import signal
import sys

#MQTT
CONNECT = 1
CONNACK = 2
PUBLISH = 3
PUBACK = 4
PUBREC = 5
PUBREL = 6
PUBCOMP = 7
SUBSCRIBE = 8
SUBACK = 9
UNSUBSCRIBE = 10
UNSUBACK = 11
PINGREQ = 12
PINGRESP = 13
DISCONNECT = 14
AUTH = 15

#Communication
MQTT_SUBSCRIBE = 0x01
MQTT_REQUEST_RESPONSE = 0x02
MQTT_CONNECTED = 0x03
MQTT_DISCONNECTED = 0x04
MQTT_PING = 0x05
MQTT_PUBLISH = 0x06
MQTT_REQUEST = 0x07
MQTT_PUBLISH_NORETAIN = 0x08

MQTT = 0x00
EVENTEXECUTION = 0x02
INTERCOM = 0x03
STATELOG = 0x04

SETTINGS_WORKINGFOLDER = 0x00
SETTINGS_IPTOPIC = 0x01

class Keepalive(multiprocessing.Process):
	def __init__(self, ComQueue):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-mqtt-keepalive')

		while True:
			time.sleep(5)
			self.ComQueue[MQTT].put([MQTT_PING])

class Events(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, Init, MQTTSocket):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.MQTTSocket = MQTTSocket
		self.Init = Init

	def BytesToInt(self, Bytes):
		result = 0

		for b in Bytes:
			result = result * 256 + int(b)

		return result

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-mqtt-events')

		Data = b""
		StartTime = time.time()
		InitStates = {}

		while True:
			try:
				Data = Data + self.MQTTSocket.recv(32768) #sequencial read
			except: #MQTT Server offline
				return

			if not self.Init:
				CurrentTime = time.time()

				if CurrentTime - StartTime > int(self.Settings["waitforstatusupdate"]):
					self.Init = True

			while True:
				if len(Data) < 4: #Check Remaining Data
					break

				High = Data[0] >> 4

				if High == PUBLISH: #Incomming Message
					if Data[1] > 127:
						if Data[2] > 127:
							TopicBegin = 6
							PayloadBegin = TopicBegin + Data[5]
							PayloadEnd = Data[1] - 128 + (Data[2] - 128) * 128 + Data[3] * 16384 + 4
						else:
							TopicBegin = 5
							PayloadBegin = TopicBegin + Data[4]
							PayloadEnd = Data[1] - 128 + Data[2] * 128 + 3
					else:
						TopicBegin = 4
						PayloadBegin = TopicBegin + Data[3]
						PayloadEnd = Data[1] + 2

					if len(Data) < PayloadEnd:
						break

					Topic = (Data[TopicBegin:PayloadBegin]).decode('utf-8')
					Payload = (Data[PayloadBegin:PayloadEnd]).decode('utf-8')
					Data = Data[PayloadEnd:] #Remaining Data
					TopicIncomming = Topic
					Topic = Topic.lower().replace("/command/", "/")
					temp = Topic.split("/")
					ID = temp[0]
					action = Topic.replace(ID + "/", "")

					if temp[0] == "global":
						if temp[1] == "init":
							if Payload == "1":
								for i in self.ComQueue:
									self.ComQueue[i].put([temp[1]])

								self.ComQueue[MQTT].put([MQTT_PUBLISH, "global/init", "0"])
					else:
						if ID in self.ComQueue:
							if not self.Init: #While Init also send states
								if Topic.lower() in InitStates:
									continue

								InitStates[Topic.lower()] = Payload.lower()
								self.ComQueue[ID].put([action, Payload])
							else: # After init, send only commands
								if TopicIncomming.find("/command/") != -1: #Command
									self.ComQueue[ID].put([action, Payload])

						if TopicIncomming.find("/command/") == -1: #Send only states
							if "statelogfile" in self.Settings:
								self.ComQueue[STATELOG].put([TopicIncomming, Payload])

							if self.Settings["eventexecutionenabled"] == "1":
								self.ComQueue[EVENTEXECUTION].put([TopicIncomming, Payload])

							self.ComQueue[MQTT].put([MQTT_REQUEST_RESPONSE, TopicIncomming, Payload])

				elif High == UNSUBACK: #Unsubscription ack
					RemainingLenght = self.BytesToInt(Data[1:2])
					Data = Data[RemainingLenght + 2:]
				elif High == SUBACK: #Subscription ack
					RemainingLenght = self.BytesToInt(Data[1:2])
					Data = Data[RemainingLenght + 2:]
				elif High == PUBACK: #Publish ack
					RemainingLenght = self.BytesToInt(Data[1:2])
					Data = Data[RemainingLenght + 2:]
				elif High == PINGRESP: #Ping recv
					RemainingLenght = self.BytesToInt(Data[1:2])
					Data = Data[RemainingLenght + 2:]
				elif High == DISCONNECT: #Disconnected
					Data = b""
					self.ComQueue[MQTT].put([MQTT_DISCONNECTED])
					return
				elif High == CONNACK: #Connected
					RemainingLenght = self.BytesToInt(Data[1:2])
					Data = Data[RemainingLenght + 2:]
					self.ComQueue[MQTT].put([MQTT_CONNECTED])

class MQTTController(multiprocessing.Process):
	def __init__(self, ComQueue, Settings):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings

	def MQTTConnect(self, Init):
		try:
			MQTTSocket.close()
		except:
			None

		MQTTSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		while True:
			try:
				MQTTSocket.connect((self.Settings["mqttip"], int(self.Settings["mqttport"])))
				break
			except:
				time.sleep(5)

		MQTTSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		ClientID = (self.Settings[SETTINGS_IPTOPIC]).encode('utf-8')
		WillTopic = (self.Settings[SETTINGS_IPTOPIC] + "/online").encode('utf-8')
		WillPayload = ("0").encode('utf-8')
		WillQos = 0
		WillRetain = True
		Username = (self.Settings["mqttuser"]).encode('utf-8')
		Password = (self.Settings["mqttpassword"]).encode('utf-8')
		Keepalive = 10
		protocol = b"MQTT"
		LenghtRemaining = 2 + len(protocol) + 6 + len(ClientID)
		ConnectFlags = 0
		ConnectFlags |= 0x02
		LenghtRemaining += 2 + len(WillTopic) + 2 + len(WillPayload)
		ConnectFlags |= 0x04 | ((WillQos & 0x03) << 3) | ((WillRetain & 0x01) << 5)
		LenghtRemaining += 2 + len(Username)
		ConnectFlags |= 0x80
		ConnectFlags |= 0x40
		LenghtRemaining += 2 + len(Password)
		Packet = bytearray()
		Packet.append(0x10)
		BytesRemaining = []

		while True:
			Byte = LenghtRemaining % 128
			LenghtRemaining = LenghtRemaining // 128

			if LenghtRemaining > 0:
				Byte |= 0x80

			BytesRemaining.append(Byte)
			Packet.append(Byte)

			if LenghtRemaining == 0:
				break

		Packet.extend(struct.pack("!H" + str(len(protocol)) + "sBBH", len(protocol), protocol, 4, ConnectFlags, Keepalive))
		Packet.extend(struct.pack("!H", len(ClientID)))
		Packet.extend(ClientID)
		Packet.extend(struct.pack("!H", len(WillTopic)))
		Packet.extend(WillTopic)
		Packet.extend(struct.pack("!H", len(WillPayload)))
		Packet.extend(WillPayload)
		Packet.extend(struct.pack("!H", len(Username)))
		Packet.extend(Username)
		Packet.extend(struct.pack("!H", len(Password)))
		Packet.extend(Password)
		MQTTSocket.send(Packet)
		self.EventsThread = Events(self.ComQueue, self.Settings, Init, MQTTSocket)
		self.EventsThread.start()
		return MQTTSocket

	def Unsubscribe(self, MQTTSocket, Topic):
		#Unsubscribe
		Dup = False
		Topic = Topic.encode('utf-8')
		LenghtRemaining = 4 + len(Topic)
		Command = 0xA0 | (Dup << 3) | 0x2
		Packet = bytearray()
		Packet.append(Command)
		BytesRemaining = []

		while True:
			Byte = LenghtRemaining % 128
			LenghtRemaining = LenghtRemaining // 128

			if LenghtRemaining > 0:
				Byte |= 0x80

			BytesRemaining.append(Byte)
			Packet.append(Byte)

			if LenghtRemaining == 0:
				break

		Packet.extend(struct.pack("!H", 1))
		Packet.extend(struct.pack("!H", len(Topic)))
		Packet.extend(Topic)
		MQTTSocket.send(Packet)

	def Publish(self, MQTTSocket, Topic, Payload, Retain):
		#Publish
		Dup = False
		Qos = 0
		Command = 0x30 | ((Dup & 0x1) << 3) | (Qos << 1) | Retain
		Packet = bytearray()
		Packet.append(Command)
		Topic = Topic.encode('utf-8')
		Payload = Payload.encode('utf-8')
		PayloadLen = len(Payload)
		LenghtRemaining = 2 + len(Topic) + PayloadLen
		BytesRemaining = []

		while True:
			Byte = LenghtRemaining % 128
			LenghtRemaining = LenghtRemaining // 128

			if LenghtRemaining > 0:
				Byte |= 0x80

			BytesRemaining.append(Byte)
			Packet.append(Byte)

			if LenghtRemaining == 0:
				break

		Packet.extend(struct.pack("!H", len(Topic)))
		Packet.extend(Topic)
		Packet.extend(Payload)
		MQTTSocket.send(Packet)

	def MQTTSubscribe(self, MQTTSocket, Topic):
		#Subscribe
		Qos = 0
		Dup = False
		Topic = Topic.encode('utf-8')
		LenghtRemaining = 4 + len(Topic) + 1
		Command = 0x80 | (Dup << 3) | 0x2
		self.MQTTPacketCounter += 1

		if self.MQTTPacketCounter == 65536:
			self.MQTTPacketCounter = 0

		Packet = bytearray()
		Packet.append(Command)
		BytesRemaining = []

		while True:
			byte = LenghtRemaining % 128
			LenghtRemaining = LenghtRemaining // 128

			if LenghtRemaining > 0:
				byte |= 0x80

			BytesRemaining.append(byte)
			Packet.append(byte)

			if LenghtRemaining == 0:
				break

		Packet.extend(struct.pack("!H", self.MQTTPacketCounter))
		Packet.extend(struct.pack("!H", len(Topic)))
		Packet.extend(Topic)
		Packet.append(Qos)#
		MQTTSocket.send(Packet)

	#Modify here
	def Ping(self, MQTTSocket):
		Packet = struct.pack('!BB', 0xC0, 0)
		MQTTSocket.send(Packet)

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-mqtt-control')

		Init =  False
		MQTTSocket = self.MQTTConnect(Init)
		KeepaliveThread = Keepalive(self.ComQueue)
		KeepaliveThread.start()
		self.MQTTPacketCounter = 0
		Subscriptions = []
		RequestState = ""
		StartTime = time.time()

		#Default Subscriptions
		Subscriptions.append("global/#")

		while True:
			if not Init:
				CurrentTime = time.time()

				if CurrentTime - StartTime > int(self.Settings["waitforstatusupdate"]):
					Init = True
					self.Publish(MQTTSocket, self.Settings[SETTINGS_IPTOPIC] + "/online", "1", True)

			IncommingData = self.ComQueue[MQTT].get()

			if IncommingData[0] == MQTT_PUBLISH:
				self.Publish(MQTTSocket, IncommingData[1], IncommingData[2], True)
			elif IncommingData[0] == MQTT_PUBLISH_NORETAIN:
				self.Publish(MQTTSocket, IncommingData[1], IncommingData[2], False)
			elif IncommingData[0] == MQTT_REQUEST: #Status request from intercom
				RequestState = IncommingData[1]
				self.MQTTSubscribe(MQTTSocket, IncommingData[1])
			elif IncommingData[0] == MQTT_REQUEST_RESPONSE:
				if RequestState == IncommingData[1]:
					self.Unsubscribe(MQTTSocket, RequestState)
					self.ComQueue[INTERCOM].put([IncommingData[2]]) #Send Payload to Intercom
					RequestState = ""
			elif IncommingData[0] == MQTT_SUBSCRIBE: #Subscribe request from extern, e.g. statelog or eventsexecution
				if IncommingData[1] == "#":
					if not "#" in Subscriptions:
						for Subscription in Subscriptions:
							self.Unsubscribe(MQTTSocket, Subscription)

						self.MQTTSubscribe(MQTTSocket, IncommingData[1])
						print("MQTT subscribe1: " + str(   IncommingData[1]   ))
						Subscriptions.append(IncommingData[1])
				else:

					if not IncommingData[1] in Subscriptions:
						if not "#" in Subscriptions:
							print("MQTT Subscribe2: " + str(     IncommingData[1]   ))
							self.MQTTSubscribe(MQTTSocket, IncommingData[1])
							Subscriptions.append(IncommingData[1])

			elif IncommingData[0] == MQTT_CONNECTED:
				self.Publish(MQTTSocket, "global/init", "0", True)

				if Init: #Skip startup-init, but trigger on mqtt-reconnection
					self.Publish(MQTTSocket, self.Settings[SETTINGS_IPTOPIC] + "/online", "1", True)
			elif IncommingData[0] == MQTT_DISCONNECTED:
				MQTTSocket = self.MQTTConnect(Init)
			elif IncommingData[0] == MQTT_PING:
				self.Ping(MQTTSocket)
			else:
				print("UNKNOWN: " + str(IncommingData))


#Terminate Processes
def receiveSignal(signalNumber, frame):
	signal.signal(signalNumber, signal.SIG_IGN) # ignore additional signals

	for Thread in Threads:
		try:
			Thread.terminate()
			Thread.join()
			Thread.close()
		except:
			None
	sys.exit()

####################### Programm Start here #############################
if SETPROCTITLE:
	setproctitle.setproctitle('Homecontrol')


#register signals
signal.signal(signal.SIGHUP, receiveSignal)
signal.signal(signal.SIGINT, receiveSignal)
signal.signal(signal.SIGQUIT, receiveSignal)
signal.signal(signal.SIGILL, receiveSignal)
signal.signal(signal.SIGTRAP, receiveSignal)
signal.signal(signal.SIGABRT, receiveSignal)
signal.signal(signal.SIGBUS, receiveSignal)
signal.signal(signal.SIGFPE, receiveSignal)
#signal.signal(signal.SIGKILL, receiveSignal)
signal.signal(signal.SIGUSR1, receiveSignal)
signal.signal(signal.SIGSEGV, receiveSignal)
signal.signal(signal.SIGUSR2, receiveSignal)
signal.signal(signal.SIGPIPE, receiveSignal)
signal.signal(signal.SIGALRM, receiveSignal)
#signal.signal(signal.SIGTERM, receiveSignal)

Settings = {}
Settings["eventexecutionenabled"] = "0"
Settings["intercomenabled"] = "0"
Settings["waitforstatusupdate"] = "10"
Settings[SETTINGS_WORKINGFOLDER] = os.path.dirname(os.path.realpath(__file__))

ComQueue = {}
ComQueue[MQTT] = multiprocessing.Queue()

Threads = []

#Load Modules
Modules = {}
Files = os.listdir(Settings[SETTINGS_WORKINGFOLDER] + "/plugins")

for i in range(0, len(Files)):
	if Files[i][-3:] == ".py" and Files[i] != "main.py":
		ModuleName = "plugins." + Files[i].replace(".py", "")

		try: #Skip Modules with unmet dependencies
			Modules[ModuleName] = __import__(ModuleName, fromlist=['*'])
		except:
#			print("Error load modules: " + ModuleName)
			None




#load config
if Settings[SETTINGS_WORKINGFOLDER] + '/config.txt':
	f = open(Settings[SETTINGS_WORKINGFOLDER] + '/config.txt', 'r')
	config = f.read()
	f.close()
	sectionlines=config.split("\n")

	for i in range (0, len(sectionlines)):
		sectiondata = sectionlines[i].split("=")

		if len(sectiondata) == 2 and sectiondata[0][:1] != "#":
			sectiondata[1] = str(sectiondata[1])
			sectiondata[0] = str(sectiondata[0]).lower()
			Settings[sectiondata[0]] = sectiondata[1]

	Settings[SETTINGS_IPTOPIC] = Settings["ip"].replace(".", "-") #Fix for MQTT-Topics (replace all dots)

	#Start Initscript
	if "initscript" in Settings:
		os.system(Settings["initscript"])

	#Delay start
	if "startdelay" in Settings:
		time.sleep(int(Settings["startdelay"]))

	#Init all Modules
	for Key in Modules:
		try: #For Debug Only
#			print("Module loaded: " + str( Modules[Key]  ))
			ComQueue, Threads = Modules[Key].Init(ComQueue, Threads, Settings)
		except:
#			print("Module failed to load " + str(Modules[Key]))
			None

	Threads.append(MQTTController(ComQueue, Settings))
	Threads[-1].start()

	#Set firstrun flag to 0 in config.txt
	if "firstrun" in Settings:
		if Settings["firstrun"] == "1":
			print("RESET INIT")
			Settings["firstrun"] = "0"
			config = config.replace("firstrun=1", "firstrun=0")
			f = open(Settings[SETTINGS_WORKINGFOLDER] + '/config.txt', 'w')
			f.write(config)
			f.flush()
			f.close()
else:
        print("No config file found")



