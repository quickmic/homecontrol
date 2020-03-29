#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import time
import json
import urllib.request
import subprocess
import signal
import os
import logging

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01
SETTINGS_LOGGER = 0x02

def Init(ComQueue, Threads, Settings):
	for i in range(0, 25):
		if "queryid" + str(i) in Settings:
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
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-query-' + self.Index)

		DataTemp = {}
		Delay = int(self.Settings["queryinterval" + self.Index])
		Query = self.Settings["query" + self.Index]
		IDExternal = self.Settings["queryid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		Online = -1

		if Query.find("http") != -1:
			QueryTyp = True
			IP = Query.replace("http://", "")
			IP = IP.replace("https://", "")
			Pos = IP.find("/")
			IP = IP[:Pos]
		else:
			QueryTyp = False

		while True:
			time.sleep(Delay)

			if QueryTyp:
				try:
					r = urllib.request.urlopen(Query)
					data = r.read()

					if Online != 1:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "online", "1"])
						self.Settings[SETTINGS_LOGGER].debug("Query: " + Query + " online")
						Online = 1


					data = json.loads(data)

					while not data == {}:
						dataTemp = {}

						for item in data:
							if isinstance(data[item], dict):
								dataMod = {}
								dataLocal = {}
								dataLocal.update(data[item])

								for item2 in dataLocal:
									dataMod.update({item + "/" + item2 : dataLocal[item2]})

								dataTemp = {**dataTemp, **dataMod}

							else:
								if str(item) in DataTemp:
									if DataTemp[str(item)] == str(data[item]):
										continue

								DataTemp[str(item)] = str(data[item])
								self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + str(item), str(data[item])])
								self.Settings[SETTINGS_LOGGER].debug("Query: " + Query + " " + str(item) + " " + str(data[item]))

						data = dataTemp
				except:
					if Online != 0:
						self.Settings[SETTINGS_LOGGER].debug("Query: " + Query + " offline")
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "online", "0"])
						Online = 0
			else:
				Process = subprocess.Popen(Query, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, preexec_fn=os.setpgrp)
				data = Process.stdout.readline()
				data = data.decode(encoding='ascii')
				os.killpg(os.getpgid(Process.pid), signal.SIGTERM)

				self.Settings[SETTINGS_LOGGER].debug("Query command data: " + str(data))
