#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import time
import multiprocessing
import os
import bluetooth
from bluetooth.ble import DiscoveryService
import logging

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01
SETTINGS_LOGGER = 0x02

def Init(ComQueue, Threads, Settings):
	if "bluetoothid" in Settings:
		Threads.append(Controller(ComQueue, Settings))
		Threads[-1].start()

	return ComQueue, Threads

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings):
		multiprocessing.Process.__init__(self)
		self.Settings = Settings
		self.ComQueue = ComQueue

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-bluetooth')

		IDExternal = self.Settings["bluetoothid"] + "/"
		service = DiscoveryService()
		InRange = "-1"
		DeviceIterations = {}
		Devices = {}
		DeviceOnline = {}
		DeviceIterationsMax = {}

		for i in range(0, 100):
			if "bluetoothdevicemac" + str(i) in self.Settings:
				DeviceIterations[self.Settings["bluetoothdevicemac" + str(i)]] = 0
				Devices[self.Settings["bluetoothdevicemac" + str(i)]] = self.Settings["bluetoothdeviceid" + str(i)]
				DeviceOnline[self.Settings["bluetoothdevicemac" + str(i)]] = "-1"
				DeviceIterationsMax[self.Settings["bluetoothdevicemac" + str(i)]] = self.Settings["bluetoothiterations" + str(i)]

		while True:
			time.sleep(2)
			BTdevices = service.discover(2)

			for key in Devices:
				if key in BTdevices:
					DeviceIterations[key] = 0

					if DeviceOnline[key] != "1":
						self.Settings[SETTINGS_LOGGER].debug("Bluetooth online: " + Devices[key])
						DeviceOnline[key] = "1"
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + Devices[key], "1"])
				else:
					DeviceIterations[key] = DeviceIterations[key] + 1

					if DeviceIterations[key] >= int(DeviceIterationsMax[key]):
						DeviceIterations[key] = int(DeviceIterationsMax[key])

						if DeviceOnline[key] != "0":
							self.Settings[SETTINGS_LOGGER].debug("Bluetooth offline: " + Devices[key])
							DeviceOnline[key] = "0"
							self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + Devices[key], "0"])
