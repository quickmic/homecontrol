#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import math
import datetime
import calendar
import multiprocessing
import time
import logging

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01
SETTINGS_LOGGER = 0x02

def Init(ComQueue, Threads, Settings):
	if "astroid" in Settings:
		IDInternal = Settings["astroid"].lower()
		ComQueue[IDInternal] = multiprocessing.Queue()
		Threads.append(Controller(ComQueue, Settings, IDInternal))
		Threads[-1].start()

	return ComQueue, Threads

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal):
		multiprocessing.Process.__init__(self)
		self.Settings = Settings
		self.ComQueue = ComQueue
		self.IDInternal = IDInternal

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('Homecontrol-Astro-Events')

		self.IDExternal = self.Settings["astroid"] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, self.IDExternal + "#"])
		self.EventsThread = Events(self.ComQueue, self.Settings, self.IDExternal)
		self.EventsThread.start()
		time.sleep(int(self.Settings["waitforstatusupdate"]))

		#Drop all Updates on Start
		while not self.ComQueue[self.IDInternal].empty():
			self.ComQueue[self.IDInternal].get()

		while True:
			IncommingData = self.ComQueue[self.IDInternal].get()

			if len(IncommingData) > 1:
				if IncommingData[0] == "night": #Toggle Night mode
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "Night", IncommingData[1]])
					self.Settings[SETTINGS_LOGGER].debug("Astro: toggle night mode")

			else:
				if IncommingData[0] == "init":
					self.Settings[SETTINGS_LOGGER].debug("Astro: init")
					self.EventsThread.terminate()
					self.EventsThread.join()
					self.EventsThread.close()
					time.sleep(5)
					self.EventsThread = Events(self.ComQueue, self.Settings, self.IDExternal)
					self.EventsThread.start()

class Events(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDExternal):
		multiprocessing.Process.__init__(self)
		self.Settings = Settings
		self.ComQueue = ComQueue
		self.IDExternal = IDExternal

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('Homecontrol-Astro-Events')

		self.Pi = 3.1415926536
		RAD = self.Pi / 180.0
		h = -(50.0 / 60.0) * RAD
		self.Longitude = float(self.Settings["astrolongitude"])
		self.Latitude = float(self.Settings["astrolatitude"]) * RAD
		SunraiseTimeOld = ""
		SunsetTimeOld = ""
		NightOld = ""

		while True:
			Zone = self.setzone()
			heute = datetime.datetime.now()
			T = float(heute.strftime('%j'))
			Sunraise = self.SunRaise(T, h)
			Sunset  = self.SunSet(T, h)
			Sunraise = Sunraise - self.Longitude / 15.0 + Zone
			Sunset = Sunset - self.Longitude / 15.0 + Zone
			min,std = math.modf(Sunraise)
			min = min * 60
			SunraiseH = int(std)
			SunraiseM = int(min)
			SunraiseTime = datetime.time(SunraiseH, SunraiseM, 0)

			if SunraiseTime != SunraiseTimeOld:
				SunraiseTimeOld = SunraiseTime
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "Sunraise", str(SunraiseTime)])
				self.Settings[SETTINGS_LOGGER].debug("Astro set sunraise: " + str(SunraiseTime))

			min,std = math.modf(Sunset)
			min = min * 60
			SunsetH = int(std)
			SunsetM = int(min)
			SunsetTime = datetime.time(SunsetH, SunsetM, 0)

			if SunsetTime != SunsetTimeOld:
				SunsetTimeOld = SunsetTime
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "Sunset", str(SunsetTime)])
				self.Settings[SETTINGS_LOGGER].debug("Astro set sunset: " + str(SunsetTime))

			Night = self.CheckNight(datetime.datetime.now().time(), SunsetTime, SunraiseTime)

			if Night != NightOld:
				NightOld = Night
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "Night", Night])
				self.Settings[SETTINGS_LOGGER].debug("Astro set night: " + str(Night))

			time.sleep(60)


	def CheckNight(self, now, start, end):
		if start <= end:
			if start <= now < end:
				return "1"
			else:
				return "0"
		else: #over midnight e.g., 23:30-04:15
			if start <= now or now < end:
				return "1"
			else:
				return "0"

	def setzone(self):
		year  = datetime.date.today().year
		heute = datetime.date.today()
		day3  = max(week[-1] for week in calendar.monthcalendar(year, 3))
		dayszstart = datetime.date(year,3,day3)
		day10 = max(week[-1] for week in calendar.monthcalendar(year, 10))
		dayszende = datetime.date(year,10,day10)

		if heute < dayszstart:
			Zone = 1
		elif heute >= dayszstart and heute <= dayszende:
			Zone = 2
		else:
			Zone = 1

		return (Zone)

	def Declination(self, T):
		return (0.409526325277017 * math.sin(0.0169060504029192 * (T - 80.0856919827619)));

	def TimeShift(self, Deklination, h):
		return (12.0 * math.acos((math.sin(h) - math.sin(self.Latitude) * math.sin(Deklination)) / (math.cos(self.Latitude) * math.cos(Deklination))) / self.Pi);

	def TimeEquation(self, T):
		return (-0.170869921174742*math.sin(0.0336997028793971 * T + 0.465419984181394) - 0.129890681040717 * math.sin(0.0178674832556871 * T - 0.167936777524864));

	def SunRaise(self, T, h):
		DK = self.Declination(T)
		return (12 - self.TimeShift(DK, h) - self.TimeEquation(T));

	def SunSet(self, T, h):
		DK = self.Declination(T)
		return (12 + self.TimeShift(DK, h) - self.TimeEquation(T));
