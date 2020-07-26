#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import time
import multiprocessing
import os
import logging

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01
SETTINGS_LOGGER = 0x02

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

		self.Settings[SETTINGS_LOGGER].debug("Sensors started")
		Delay = int(self.Settings["sensorsrefreshrate"])
		IDExternal = self.Settings["sensorsid"] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		WifiDevice = []
		SmartDevice = []
		SmartLabels = []
		Label = []
		InputFile = []
		PrevData = []
		PrevRaspiGPU = ""
		PrevWifi = []
		PrevDMU = ""
		PrevAdaptec = []
		PrevAdaptecHDD = []
		PrevSmart = []
		Raspi = False
		DMU = False
		Adaptec = False
		Smart = False

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
						InputFile.append(Temp.replace("label", "input"))
						PrevData.append("-1")
						self.Settings[SETTINGS_LOGGER].debug("Sensors /sys/class/hwmon/ found: " + str(data))

		if os.path.isdir("/sys/class/thermal/"):
			arr = os.listdir("/sys/class/thermal/")

			for i in range(0, len(arr)):
				if arr[i].find("zone") != -1:
					InputFile.append("/sys/class/thermal/" + arr[i] +  "/temp")
					Label.append(arr[i])
					PrevData.append("-1")
					self.Settings[SETTINGS_LOGGER].debug("Sensors /sys/class/thermal/ found: " + str(arr[i]))

		if os.path.isfile("/opt/vc/bin/vcgencmd"):
			Raspi = True
			self.Settings[SETTINGS_LOGGER].debug("Sensors Raspberry Pi detected")

		if os.path.isfile("/sbin/blkid"):
			if os.path.isfile("/usr/sbin/smartctl"):
				arr = os.listdir("/dev/")

				for i in range(0, len(arr)):
					if arr[i][:2] == "sd" and len(arr[i]) == 3:
						Temp = os.popen("/sbin/blkid /dev/" + arr[i]).read()
						Pos = Temp.find("UUID=")
						Temp = Temp[Pos + 6:]
						Pos = Temp.find('"')
						Temp = Temp[:Pos].strip()
						SmartDevice.append(Temp)
						SmartLabels.append([])
						PrevSmart.append([])
						UUID = Temp
						Temp = os.popen("/usr/sbin/smartctl -A /dev/disk/by-uuid/" + UUID).read()
						Lines = Temp.split("\n")

						for j in range(0, len(Lines)):
							Pos = Lines[j].find("Temperature")

							if Pos != -1:
								Pos = Lines[j].find(" ")
								Lines[j] = Lines[j][Pos:].strip()
								Pos = Lines[j].find(" ")
								HDDLabel = Lines[j][:Pos].strip()
								SmartLabels[len(SmartLabels) - 1].append(HDDLabel)
								PrevSmart[len(SmartLabels) - 1].append("-1")
								Smart = True

		if os.path.isfile("/usr/StorMan/arcconf"):
			Temp = os.popen("/usr/StorMan/arcconf LIST").read()
			Pos = Temp.find("Controllers found")
			Temp = Temp[Pos + 18:]
			Pos = Temp.find("\n")
			Temp = Temp[:Pos].strip()

			for i in range(0, int(Temp)):
				PrevAdaptecHDD.append(["-1", "-1", "-1", "-1", "-1", "-1", "-1", "-1"])

				PrevAdaptec.append("-1")
				Adaptec = True
				self.Settings[SETTINGS_LOGGER].debug("Adaptec Raid Controller " + str(i) + "detected")

		if os.path.isfile("/proc/dmu/temperature"):
			DMU = True

		if os.path.isfile("/usr/sbin/wl"):
			for i in range(0, 10):
				Temp = os.popen("/usr/sbin/wl -i eth" + str(i) + " phy_tempsense").readline()

				if Temp != "":
					WifiDevice.append(str(i))
					PrevWifi.append("")

		while True:
			time.sleep(Delay)

			if Smart:
				for i in range(0, len(SmartDevice)):
					for j in range(0, len(SmartLabels[i])):
						Temp = os.popen("/usr/sbin/smartctl -A /dev/disk/by-uuid/" + SmartDevice[i]).read()
						Pos = Temp.find(SmartLabels[i][j])
						Temp = Temp[Pos:]
						Pos = Temp.find("\n")
						Temp = Temp[:Pos]
						Pos = Temp.rfind(" ")
						Temp = Temp[Pos:].strip()

						if PrevSmart[i][j] != Temp:
							PrevSmart[i][j] = Temp
							self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "temperature/hdd-uuid-" + SmartDevice[i] + "/" + SmartLabels[i][j], Temp])

			if DMU:
				File = open("/proc/dmu/temperature", "r", encoding="ISO-8859-1")
				data = File.read()
				data = data.replace("CPU temperature", "").strip()
				data = data.replace(" ", "")
				data = data.replace(":", "")
				data = data.replace("øC", "")

				if len(data) == 3:
					data = data[:2] + "." + data[2:3]

				if PrevDMU != data:
					PrevDMU = data
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "CPU", data])

			if Raspi:
				Temp = os.popen("/opt/vc/bin/vcgencmd measure_temp").readline()
				Temp = Temp.replace("temp=", "")
				Temp = Temp.replace("'C\n", "")

				if PrevRaspi != data:
					PrevRaspi = data
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "GPU", Temp])

			if Adaptec:
				for i in range(0, len(PrevAdaptec)):
					time.sleep(1)
					Temp = os.popen("/usr/StorMan/arcconf getconfig " + str(i + 1) + " AD").read()
					Pos = Temp.find("Temperature")
					Temp = Temp[Pos + 11:]
					Pos = Temp.find("\n")
					Temp = Temp[:Pos]
					Temp = Temp.replace(":", "").strip()
					Pos = Temp.find("C")
					Temp = Temp[:Pos].strip()

					if PrevAdaptec[i] != Temp:
						PrevAdaptec[i] = Temp
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "temperature/adaptec" + str(i), Temp])

					time.sleep(1)
					Temp = os.popen("/usr/StorMan/arcconf GETSMARTSTATS " + str(i + 1)).read()
					TempHDD = Temp.split("Temperature")

					for j in range(1, len(TempHDD)):
						Pos = TempHDD[j].find("rawValue")
						TempHDD[j] = TempHDD[j][Pos + 10:]
						Pos = TempHDD[j].find('"')
						TempHDD[j] = TempHDD[j][:Pos]

						if PrevAdaptecHDD[i][j - 1] != TempHDD[j]:
							PrevAdaptecHDD[i][j - 1] = TempHDD[j]
							self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "temperature/adaptec" + str(i) + "/hdd" + str(j - 1), TempHDD[j]])

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

			for i in range(0, len(WifiDevice)):
				try:
					Temp = os.popen("/usr/sbin/wl -i eth" + WifiDevice[i] + " phy_tempsense").readline()
					Temp = Temp[:Temp.find("(")].strip()

					if PrevWifi[i] != Temp:
						PrevWifi[i] = Temp
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "temperature/wifi" + str(i), Temp])
				except:
					None

