#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import time
import os
import subprocess
import signal
import logging

MQTT = 0x00
MQTT_PUBLISH_NORETAIN = 0x08

EVENTEXECUTION = 0x02
SETTINGS_WORKINGFOLDER = 0x00
SETTINGS_LOGGER = 0x02
MQTT_SUBSCRIBE = 0x01
EVENTSEXECUTION_TERMINATE_PROCESS = 0x00

def Init(ComQueue, Threads, Settings):
	if "eventexecutionenabled" in Settings:
		if Settings["eventexecutionenabled"] == "1":
			ComQueue[EVENTEXECUTION] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue, Settings))
			Threads[-1].start()

	return ComQueue, Threads

class Processes(multiprocessing.Process):
	def __init__(self, Command, ID, CommandsQueue, ComQueue, Settings):
		multiprocessing.Process.__init__(self)
		self.Command = Command
		self.CommandsQueue = CommandsQueue
		self.ID = ID
		self.ComQueue = ComQueue
		self.Settings = Settings

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle("homecontrol-eventexecution-" + self.Command)

		self.Settings[SETTINGS_LOGGER].debug("Eventexecution Process start: " + str(self.Command))
		Process = subprocess.Popen(self.Command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, preexec_fn=os.setpgrp)
		Poll = None

		while Poll == None:
			if not self.CommandsQueue[self.ID].empty():
				Signal = self.CommandsQueue[self.ID].get()

				if Signal == EVENTSEXECUTION_TERMINATE_PROCESS:
					os.killpg(os.getpgid(Process.pid), signal.SIGTERM)

			time.sleep(0.5)
			Poll = Process.poll()

		self.Settings[SETTINGS_LOGGER].debug("Eventexecution Process stopped: " + str(self.Command))
		self.ComQueue[EVENTEXECUTION].put([EVENTSEXECUTION_TERMINATE_PROCESS, self.ID])

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings

	def StatusDataUpdate(self, Data, StatusData):
		Pos = StatusData.find(Data[0] + "|")

		if Pos == -1:
			StatusData = StatusData + Data[0] + "|" + Data[1] + ";"
		else:
			PosEnd = StatusData.find(";", Pos)
			Temp = StatusData[Pos:PosEnd]

			if Data[0] + "|" + Data[1] != Temp:
				StatusData = StatusData[:Pos] + Data[0] + "|" + Data[1] + StatusData[PosEnd:]

		return StatusData

	def StatusDataGet(self, Data, StatusData):
		Pos = StatusData.find(Data + "|")

		if Pos == -1:
			return ""
		else:
			PosEnd = StatusData.find(";", Pos)
			Temp = StatusData[Pos:PosEnd].split("|")
			return Temp[1]

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle("homecontrol-eventexecution")

		StatusData = ""
		EventData = {}
		ProcessRunning = {}
		ProcessThread = {}
		IncommingState = {}
		CommandsQueue = {} #Queue to control shell scripts or processes

		#Preload all event files and subscribe required channels. Prevent multiple subscription for same event are covered in mqtt.py
		for File in os.listdir(self.Settings[SETTINGS_WORKINGFOLDER] + "/events"):
			f = open(self.Settings[SETTINGS_WORKINGFOLDER] + "/events/" + File, 'r')
			Data = f.read()
			f.close()
			ID = File.lower()

			if ID[-3:] == ".sh": #Skip Shell scripts
				continue

			EventData[ID] = Data.split("\n")

			#Subscribe events
			Subscription = File.replace("@", "/")
			self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, Subscription])

			#Check content of files, search for conditions and subscribe event
			for i in range(0, len(EventData[ID])): #Loop filedata
				Pos = EventData[ID][i].lower().find("condition:")

				if Pos != -1:
					Channel = EventData[ID][i][Pos + 10:]
					Pos = Channel.rfind("=")
					Channel = Channel[:Pos]
					Channel = Channel.strip()
					self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, Channel])

                #Drop all Updates on Start
		time.sleep(int(self.Settings["waitforstatusupdate"]))

#		while not self.ComQueue[EVENTEXECUTION].empty():
#			self.ComQueue[EVENTEXECUTION].get()

		while True:
			DataIncomming = self.ComQueue[EVENTEXECUTION].get()
#			self.Settings[SETTINGS_LOGGER].debug("Eventexecution Incomming Command: " + str(DataIncomming))

			if DataIncomming[0] == EVENTSEXECUTION_TERMINATE_PROCESS:
				ProcessThread[DataIncomming[1]].join()
				ProcessRunning[DataIncomming[1]] = False
			else:
				if len(DataIncomming) == 1: #Skip e.g. init (single commands)
					continue


				#Modify Incomming array to lower case
				for i in range(0, len(DataIncomming)):
					DataIncomming[i] = DataIncomming[i].lower()

				StatusData = self.StatusDataUpdate(DataIncomming, StatusData)
				EventID = DataIncomming[0].replace("/", "@")

				if EventID in EventData:
					#Check is State changed on incomming Data
					if EventID in IncommingState:
						if IncommingState[EventID] != DataIncomming[1]:
							IncommingState[EventID] = DataIncomming[1]
						else:
							continue
					else:
						IncommingState[EventID] = DataIncomming[1]

					for i in range(0, len(EventData[EventID])): #Loop filedata
						if EventData[EventID][i].lower().find("condition:") != -1:
							Ret = self.StatusDataGet(DataIncomming[0], StatusData)
							Pos = EventData[EventID][i].rfind("|")
							Ret2 = EventData[EventID][i][Pos]

							if Ret == Ret2: # Verify matching conditions
								for j in range(i + 1, len(EventData[EventID])):
									if EventData[EventID][j].lower().find("condition:") == -1 and EventData[EventID][j] != "": #run commands, but skip on new condition found
										if EventData[EventID][j].lower()[-3:] == ".sh": #Script command found
											if os.path.isfile(EventData[EventID][j]):
												#Kill previous started process in case still running
												if EventID in ProcessRunning:
													if ProcessRunning[EventID]:
														CommandsQueue[EventID].put(EVENTSEXECUTION_TERMINATE_PROCESS)
														ProcessThread[EventID].join()
														ProcessRunning[EventID] = False

												#Start process
												CommandsQueue[EventID] = multiprocessing.Queue()
												ProcessThread[EventID] = Processes(EventData[EventID][j], EventID, CommandsQueue, self.ComQueue, self.Settings)
												ProcessThread[EventID].start()
												ProcessRunning[EventID] = True

										else: #MQTT command found
											#push commands in MQTT Queue
											Pos = EventData[EventID][j].find("/")
											PosEnd = EventData[EventID][j].rfind("=")
											Payload = EventData[EventID][j][PosEnd + 1:]
											SendCommand = EventData[EventID][j][:Pos] + "/command" + EventData[EventID][j][Pos:PosEnd]
											self.ComQueue[MQTT].put([MQTT_PUBLISH_NORETAIN, SendCommand, Payload])
									else:
										break
								break
