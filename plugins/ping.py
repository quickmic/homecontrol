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
import logging

MQTT = 0x00
MQTT_PUBLISH = 0x06
SETTINGS_LOGGER = 0x02

def Init(ComQueue, Threads, Settings):
	for i in range(0, 500):
		if "pingip" + str(i) in Settings:
			Threads.append(Controller(ComQueue, Settings, str(i)))
			Threads[-1].start()

	return ComQueue, Threads

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, Index):
		multiprocessing.Process.__init__(self)
		self.Settings = Settings
		self.ComQueue = ComQueue
		self.Index = Index

	def run(self):
		IP = self.Settings["pingip" + self.Index]

		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-ping-' + IP)

		time.sleep(float(self.Index) / 5 ) #staggered Initialization 500ms gap
		OnlineOld = "-1"
		Online = "-1"
		Delay = int(self.Settings["pinginterval" + self.Index])
		PingID = self.Settings["pingip" + self.Index].replace(".", "-") + "/online"
		ICMPID = int(self.Index) + 10000
		padBytes = [(0x42 & 0xff)]
		data = bytes(padBytes)
		header = struct.pack("!BBHHH", 8, 0, 0, ICMPID, 0)
		SourceData = header + data
		countTo = (int(len(SourceData) / 2)) * 2
		sum = 0
		count = 0
		loByte = 0
		hiByte = 0

		while count < countTo:
			loByte = SourceData[count]
			hiByte = SourceData[count + 1]
			sum = sum + (hiByte * 256 + loByte)
			count += 2

		if countTo < len(SourceData):
			loByte = SourceData[len(SourceData) - 1]
			sum += loByte

		sum &= 0xffffffff
		sum = (sum >> 16) + (sum & 0xffff)
		sum += (sum >> 16)
		checksum = ~sum & 0xffff
		checksum = socket.htons(checksum)
		header = struct.pack("!BBHHH", 8, 0, checksum, ICMPID, 0)
		Packet = header + data

		while True:
			time.sleep(Delay)

			while True:
				ICMPsocket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.getprotobyname("icmp"))
				ICMPsocket.settimeout(0.1) #100ms
				ICMPsocket.sendto(Packet, (IP, 1))

				try:
					PacketData, Address = ICMPsocket.recvfrom(64)

					if Address[0] == IP:
						Online = "1"
						ICMPsocket.close()
						break
					else: #Wrong ICMP packet received
						time.sleep(0.1)
						ICMPsocket.close()
						continue
				except:
					Online = "0"
					ICMPsocket.close()
					break

			if Online != OnlineOld:
				self.ComQueue[MQTT].put([MQTT_PUBLISH, PingID, Online])
				self.Settings[SETTINGS_LOGGER].debug("Ping: " + str(PingID) + " " + str(Online))
				OnlineOld = Online
