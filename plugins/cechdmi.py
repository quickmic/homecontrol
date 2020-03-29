#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import logging

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01
SETTINGS_LOGGER = 0x02

def Init(ComQueue, Threads, Settings):
	if "cecid" in Settings:
		IDInternal = Settings["cecid"].lower()
		ComQueue[IDInternal] = multiprocessing.Queue()
		Threads.append(Controller(ComQueue, Settings, IDInternal))
		Threads[-1].start()

	return ComQueue, Threads

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.IDInternal = IDInternal

	def events(self, test, *args):
		try:
			if len(args) >= 1:
				if len(args[2]) >= 8:
					temp = str(args[2][-8:])

					if temp == "00:10:00": #HDMI1
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "0"])
					elif temp == "00:20:00": #HDMI2
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "1"])
					elif temp == "00:30:00": #HDMI3
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "2"])
					elif temp == "00:40:00": #HDMI4
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "3"])
					elif temp == "00:50:00": #HDMI5
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "4"])
					elif temp == "00:60:00": #HDMI6
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "5"])
					elif temp == "01:90:00": #ON
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "power", "1"])
					elif temp == "04:00:01": #ON, Sony TV specific
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "power", "1"])
					elif temp == "01:90:01": #Standby
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "power", "0"])
					elif temp == "09:00:01": #Standby, Sony TV specific
						self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "power", "0"])

			self.Settings[SETTINGS_LOGGER].debug("CEC Incomming Message: " + str(args))

		except Exception as e:
			self.Settings[SETTINGS_LOGGER].debug("CEC Incomming Message Error")
			None

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-cec')

		import cec
		self.IDExternal = self.Settings["cecid"] + "/"
		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, self.IDExternal + "#"])
		cec.add_callback(self.events, cec.EVENT_LOG)
		cec.init()
		device = cec.Device(0)
		opcode = cec.CEC_OPCODE_ACTIVE_SOURCE
		destination = cec.CECDEVICE_BROADCAST
		self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])

		if self.Settings["firstrun"] == "1":
			self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "0"])
			cec.transmit(destination, opcode, bytes([0x10, 0x00]))
			self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "power", "0"])
			device.standby()

		while True:
			IncommingData = self.ComQueue[self.IDInternal].get()
			self.Settings[SETTINGS_LOGGER].debug("CEC Incomming Command: " + str(IncommingData))

			if IncommingData[0] == "power":
				if IncommingData[1] == "1":
					device.power_on()
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "power", "1"])
				else:
					device.standby()
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "power", "0"])
			elif IncommingData[0] == "source":
				if IncommingData[1] == "0":
					cec.transmit(destination, opcode, bytes([0x10, 0x00]))
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "0"])
				elif IncommingData[1] == "1":
					cec.transmit(destination, opcode, bytes([0x20, 0x00]))
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "1"])
				elif IncommingData[1] == "2":
					cec.transmit(destination, opcode, bytes([0x30, 0x00]))
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "2"])
				elif IncommingData[1] == "3":
					cec.transmit(destination, opcode, bytes([0x40, 0x00]))
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "3"])
				elif IncommingData[1] == "4":
					cec.transmit(destination, opcode, bytes([0x50, 0x00]))
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "4"])
				elif IncommingData[1] == "5":
					cec.transmit(destination, opcode, bytes([0x60, 0x00]))
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "5"])
			elif IncommingData[0] == "init":
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "source", "0"])
				cec.transmit(destination, opcode, bytes([0x10, 0x00]))
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "power", "0"])
				device.standby()
