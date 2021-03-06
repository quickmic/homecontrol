#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import time
import binascii
import socket
import struct
import ssl
import json
import datetime
from PIL import Image, ImageDraw
import base64
import io

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

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01

ROOMBA_PING = 0x00
ROOMBA_DISCONNECTED = 0x01
ROOMBA_CONNECTED = 0x02

def Init(ComQueue, Threads, Settings):
	for i in range(0, 25):
		if "roombaid" + str(i) in Settings:
			IDInternal = Settings["roombaid" + str(i)].lower()
			ComQueue[IDInternal] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue, Settings, IDInternal, str(i)))
			Threads[-1].start()

	return ComQueue, Threads

class RoombaKeepalive(multiprocessing.Process):
	def __init__(self, ComQueue, IDInternal):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.IDInternal = IDInternal

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-Roomba-keepalive')

		while True:
			time.sleep(5)
			self.ComQueue[self.IDInternal].put([ROOMBA_PING])

class RoombaEvents(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, Index, IDInternal, IDExternal, RoombaSocket):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.Index = Index
		self.RoombaSocket = RoombaSocket
		self.IDInternal = IDInternal
		self.IDExternal = IDExternal

	def BytesToInt(self, Bytes):
		result = 0

		for b in Bytes:
			result = result * 256 + int(b)

		return result

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-Roomba-events')

		Data = b''
		MapInit = False
		XData = 0
		YData = 0
		MapOffsetX = int(self.Settings["roombamapoffsetx" + self.Index])
		MapOffsetY = int(self.Settings["roombamapoffsety" + self.Index])
		PreviousState = {}
		Mission = False
		MapImage = Image.new('RGB', (int(self.Settings["roombamapresx" + self.Index]), int(self.Settings["roombamapresy" + self.Index])))
		MapDraw = ImageDraw.Draw(MapImage)

		while True:
			try:
				Data = Data + self.RoombaSocket.recv(32768) #sequencial read
			except: #Roomba Server offline
				self.ComQueue[self.IDInternal].put([ROOMBA_DISCONNECTED])
				return

			while True:
				if len(Data) < 4: #Check Remaining Data
					break

				High = Data[0] >> 4

				if High == PUBLISH: #Incommaing Message
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
					DrawMap = False
					JsonData = json.loads(Payload)

					while not JsonData == {}:
						dataTemp = {}

						for item in JsonData:
							if isinstance(JsonData[item], dict):
								dataMod = {}
								dataLocal = {}
								dataLocal.update(JsonData[item])

								for item2 in dataLocal:
									dataMod.update({item + "/" + item2 : dataLocal[item2]})

								dataTemp = {**dataTemp, **dataMod}
							else:
								if str(item) in PreviousState:
									if PreviousState[str(item)] == str(JsonData[item]):
#										print("Identical: " +   str(item) + " - "  + str(JsonData[item])   )
										continue

								PreviousState[str(item)] = str(JsonData[item])

								if str(JsonData[item]).lower() == "true":
									JsonData[item] = "1"

								if str(JsonData[item]).lower() == "false":
									JsonData[item] = "0"

								if str(JsonData[item]).lower() == "on":
									JsonData[item] = "1"

								if str(JsonData[item]).lower() == "off":
									JsonData[item] = "0"

								if item == "state/reported/cleanMissionStatus/cycle":
									if str(JsonData[item]) == "none":
										self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "start", "0"])
										Mission = False
									else:
										self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "start", "1"])
										Mission = True

								elif item == "state/reported/cleanMissionStatus/phase":
									if Mission:
										if str(JsonData[item]) == "run":
											self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "pause", "0"])
										else:
											self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "pause", "1"])
									else:
										self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "pause", "-1"])

								elif item.find("/sqft") != -1:
									temp1 = item.replace("/sqft", "/sqm")
									temp2 = "{:.2f}".format(float(JsonData[item]) * 0.0929)
									self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + temp1,  temp2])

								self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + str(item), str(JsonData[item])])

								#Map
								if item == "state/reported/pose/point/x":
									XData = int(JsonData[item])
									DrawMap = True

								if item == "state/reported/pose/point/y":
									YData = int(JsonData[item])
									DrawMap = True

						JsonData = dataTemp

					if DrawMap:
						X = XData + MapOffsetX
						Y = YData * -1 + MapOffsetY

						if MapInit:
							MapDraw.line((XOld, YOld, X, Y))
							MapData = io.BytesIO()
							MapImage.save(MapData, format='PNG')
							MapDataHex = MapData.getvalue()
							MapData = base64.b64encode(MapDataHex).decode()
							self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "map", MapData])
						else:
							MapInit = True

						XOld = X
						YOld = Y
				elif High == UNSUBACK: #Unsubscription ack
					print("Unsubscription ack: " + str(Data))
					RemainingLenght = self.BytesToInt(Data[1:2])
#                                       print("RemainingLenght: " + str(RemainingLenght))
					Data = Data[RemainingLenght + 2:]
#                                       print("RemainingData: " + str(Data))
#					continue
				elif High == SUBACK: #Subscription ack
					print("Subscription ack: " + str(Data))
					RemainingLenght = self.BytesToInt(Data[1:2])
#                                       print("RemainingLenght: " + str(RemainingLenght))
					Data = Data[RemainingLenght + 2:]
#                                       print("RemainingData: " + str(Data))
#					continue
				elif High == PUBACK: #Publish ack
					print("Publish ack: " + str(Data))
					RemainingLenght = self.BytesToInt(Data[1:2])
#                                       print("RemainingLenght: " + str(RemainingLenght))
					Data = Data[RemainingLenght + 2:]
#                                       print("RemainingData: " + str(Data))
#					continue
				elif High == PINGRESP: #Ping recv
#					print("Ping Received: " + str(Data))
#					print("Ping Received")
					RemainingLenght = self.BytesToInt(Data[1:2])
#                                       print("RemainingLenght: " + str(RemainingLenght))
					Data = Data[RemainingLenght + 2:]
#					print("RemainingData: " + str(Data))
#                                       continue

				elif High == DISCONNECT: #Disconnected
					print("Disconnected")
					Data = b''
#                                       print("RemainingData: " + str(Data))
					self.ComQueue[self.IDInternal].put([ROOMBA_DISCONNECTED])
					return

#					continue
				elif High == CONNACK: #Connected
					print("Connected")
					RemainingLenght = self.BytesToInt(Data[1:2])
#					print("RemainingLenght: " + str(RemainingLenght))
					Data = Data[RemainingLenght + 2:]
#					print("RemainingData: " + str(Data))
					self.ComQueue[self.IDInternal].put([ROOMBA_CONNECTED])
#					continue
				else:
					print("OTHER !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" + str(Data))
					time.sleep(1)
class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.Index = Index
		self.IDInternal = IDInternal

	def SubscribeTopics(self, SocketRoomba, Subscriptions):
		if "#" in Subscriptions:
			self.RoombaSubscribe(SocketRoomba, "#")
			print("SUBSCRIBE: ALL" )
		else:
			for i in range(0, len(Subscriptions)):
				print("SUBSCRIBE: " + Subscriptions[i])
				self.RoombaSubscribe(SocketRoomba, Subscriptions[i])

	def RoombaConnect(self):
		try:
			SocketRoomba2.close()
			print("Close Done")
		except:
			None

		SocketRoomba2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		SocketRoomba = ssl.wrap_socket(SocketRoomba2, ssl_version=ssl.PROTOCOL_TLS, ciphers="DEFAULT@SECLEVEL=1", cert_reqs=ssl.CERT_NONE)

		while True:
			try:
				SocketRoomba.connect((self.Settings["roombaip" + self.Index], int(self.Settings["roombaport" + self.Index])))
				break
			except:
				time.sleep(5)

		SocketRoomba.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		ClientID = (self.Settings["roombausername" + self.Index]).encode('utf-8')
		Username = (self.Settings["roombausername" + self.Index]).encode('utf-8')
		Password = (self.Settings["roombapassword" + self.Index]).encode('utf-8')
		Keepalive = 10
		protocol = b"MQTT"
		LenghtRemaining = 2 + len(protocol) + 6 + len(ClientID)
		ConnectFlags = 0
		ConnectFlags |= 0x02
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

		Keepalive = 60

		Packet.extend(struct.pack("!H" + str(len(protocol)) + "sBBH", len(protocol), protocol, 4, ConnectFlags, Keepalive))
		Packet.extend(struct.pack("!H", len(ClientID)))
		Packet.extend(ClientID)
		Packet.extend(struct.pack("!H", len(Username)))
		Packet.extend(Username)
		Packet.extend(struct.pack("!H", len(Password)))
		Packet.extend(Password)
		SocketRoomba.send(Packet)
		self.RoombaEventsThread = RoombaEvents(self.ComQueue, self.Settings, self.Index, self.IDInternal, self.IDExternal, SocketRoomba)
		self.RoombaEventsThread.start()
		return SocketRoomba

	def RoombaPublish(self, SocketRoomba, Topic, Payload, Retain):
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
		SocketRoomba.send(Packet)

	def RoombaPing(self, SocketRoomba):
		Packet = struct.pack('!BB', 0xC0, 0)
		SocketRoomba.send(Packet)

	def timestamp(self):
		td = datetime.datetime.now() - datetime.datetime(1970, 1, 1)
		return str(int(td.total_seconds()))

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-roomba-control')

		self.IDExternal = self.Settings["roombaid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH_NORETAIN, self.IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, self.IDExternal + "#"])
		SocketRoomba = self.RoombaConnect()
		RoombaKeepaliveThread = RoombaKeepalive(self.ComQueue, self.IDInternal)
		RoombaKeepaliveThread.start()
		self.Settings["roombapacketid" + self.Index] = 0
		RequestState = ""
		Init =  False
		InitStates = {}
		StartTime = time.time()

		while True:
			IncommingData = self.ComQueue[self.IDInternal].get()
			Update = False

			if IncommingData[0] == ROOMBA_PING:
				self.RoombaPing(SocketRoomba)

			if not Init:
				CurrentTime = time.time()

				if CurrentTime - StartTime > int(self.Settings["waitforstatusupdate"]):
					Init = True
				else:
					continue

			if IncommingData[0] == ROOMBA_CONNECTED:
				print("Connected")
			elif IncommingData[0] == ROOMBA_DISCONNECTED:
				print("Disconnected")
				SocketRoomba = self.RoombaConnect()
			elif IncommingData[0] == "start":
				if IncommingData[1] == "0":
					self.RoombaPublish(SocketRoomba, "cmd", '{"command": "dock", "time": ' + self.timestamp() + ', "initiator": "localApp"}', False)
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + IncommingData[0], "0"])
				else:
					self.RoombaPublish(SocketRoomba, "cmd", '{"command": "start", "time": ' + self.timestamp() + ', "initiator": "localApp"}', False)
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + IncommingData[0], "1"])
			elif IncommingData[0] == "pause":
				if IncommingData[1] == "1":
					self.RoombaPublish(SocketRoomba, "cmd", '{"command": "pause", "time": ' + self.timestamp() + ', "initiator": "localApp"}', False)
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + IncommingData[0], "1"])
				else:
					self.RoombaPublish(SocketRoomba, "cmd", '{"command": "resume", "time": ' + self.timestamp() + ', "initiator": "localApp"}', False)
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + IncommingData[0], "0"])
			elif IncommingData[0] == "state/reported/carpetboost":
				temp = "carpetBoost"
				Update = True
			elif IncommingData[0] == "state/reported/vachigh":
				temp = "vacHigh"
				Update = True
			elif IncommingData[0] == "state/reported/noautopasses":
				temp = "noAutoPasses"
				Update = True
			elif IncommingData[0] == "state/reported/twopass":
				temp = "twoPass"
				Update = True
			elif IncommingData[0] == "state/reported/binpause":
				temp = "binPause"
				Update = True
			elif IncommingData[0] == "state/reported/openonly":
				temp = "openOnly"
				Update = True

			if Update:
				if IncommingData[1] == "1":
					self.RoombaPublish(SocketRoomba, "delta", '{"state": {"' + temp + '": true}}', False)
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + IncommingData[0], "1"])
				else:
					self.RoombaPublish(SocketRoomba, "delta", '{"state": {"' + temp + '": false}}', False)
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + IncommingData[0], "0"])
