#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import time
import multiprocessing
import os

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01

def Init(ComQueue, Threads, Settings):
	if "sensorsid" in Settings:
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
			setproctitle.setproctitle('homecontrol-sensors')

		Delay = int(self.Settings["sensorsrefreshrate"])
		IDExternal = self.Settings["sensorsid"] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH_NORETAIN, IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		Label = []
		InputFile = []
		PrevData = []
		Raspi = False

		if os.path.isdir("/sys/class/hwmon/"):
			arr = os.listdir("/sys/class/hwmon/")

			for i in range(0, len(arr)):
				for file in os.listdir("/sys/class/hwmon/" + arr[i]):
					if file.find("label") != -1:
						Temp = "/sys/class/hwmon/" + arr[i] + "/" + file
						Temp2 = open(Temp, "r")
						data = Temp2.read()
						data = data.replace("\n", "").strip()
						data = data.replace("+", "")
						Label.append(data)
						InputFile.append( Temp.replace("label", "input"))
						PrevData.append("-1")

		if os.path.isdir("/sys/class/thermal/"):
			arr = os.listdir("/sys/class/thermal/")

			for i in range(0, len(arr)):
				if arr[i].find("zone") != -1:
					InputFile.append("/sys/class/thermal/" + arr[i] +  "/temp")
					Label.append(arr[i])
					PrevData.append("-1")

		if os.path.isfile("/opt/vc/bin/vcgencmd"):
			Raspi = True

		while True:
			time.sleep(Delay)

			if Raspi:
				Temp = os.popen("/opt/vc/bin/vcgencmd measure_temp").readline()
				Temp = Temp.replace("temp=", "")
				Temp = Temp.replace("'C\n", "")
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "GPU", Temp])

			for i in range(0, len(Label)):
				try:
					file = open(InputFile[i], "r")
					data = file.read()
					data = data.replace("\n", "").strip()

					if Label[i].lower().find("fan") == -1:
						data = data[:-3] + "." + data[-3:]

					data4 = Label[i] + data

					if data4 != PrevData[i]:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + Label[i], data])
						PrevData[i] = data4
				except:
					None
