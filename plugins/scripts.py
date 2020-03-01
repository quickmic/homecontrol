#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import os
import subprocess
import signal
import time

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01

SCRIPTS_TERMINATE_PROCESS = 0x00

def Init(ComQueue, Threads, Settings):
	for i in range(0, 25):
		if "scriptid" + str(i) in Settings:
			IDInternal = Settings["scriptid" + str(i)].lower()
			ComQueue[IDInternal] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue, Settings, IDInternal, str(i)))
			Threads[-1].start()

	return ComQueue, Threads

class Processes(multiprocessing.Process):
	def __init__(self, Command, Index, CommandsQueue, ComQueue, IDInternal):
		multiprocessing.Process.__init__(self)
		self.Command = Command
		self.CommandsQueue = CommandsQueue
		self.Index = Index
		self.ComQueue = ComQueue
		self.IDInternal = IDInternal

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle("homecontrol-scripts-" + self.Command)

		Process = subprocess.Popen(self.Command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, preexec_fn=os.setpgrp)
		Poll = None

		while Poll == None:
			if not self.CommandsQueue[self.Index].empty():
				Signal = self.CommandsQueue[self.Index].get()

				if Signal == SCRIPTS_TERMINATE_PROCESS:
					os.killpg(os.getpgid(Process.pid), signal.SIGTERM)

			time.sleep(0.5)
			Poll = Process.poll()

		self.ComQueue[self.IDInternal].put([SCRIPTS_TERMINATE_PROCESS, self.Index])

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.IDInternal = IDInternal
		self.Index = Index

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-scripts-' + self.Index)

		levelprevious = -1
		IDExternal = self.Settings["scriptid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH_NORETAIN, IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, IDExternal + "#"])
		InitCommands = []
		SliderLevelLast = "0"
		ProcessRunning = {}
		ProcessThread = {}
		CommandsQueue = {} #Queue to control shell scripts or processes

		for i in range (0, 25):
			try:
				self.Settings["scriptstart" + self.Index + "," + str(i)]
			except:
				levels = i
				interval = 1 / i
				break

		time.sleep(int(self.Index)) #staggered Initialization
		Process = [0 for i in range(levels + 1)] # preload array with 0
		l = i

		#Collect incomming commands on startup, and modify some of them (e.g. sliderlastlevel)
		time.sleep(int(self.Settings["waitforstatusupdate"]))

		while not self.ComQueue[self.IDInternal].empty():
			temp = self.ComQueue[self.IDInternal].get()
			InitCommands.append(temp)

		for i in range (0, len(InitCommands)):
			temp = InitCommands[i]

			if temp[0] == "levellast":
				SliderLevelLast = temp[1]
			elif temp[0] == "levellasttoggle":
				continue
			else:
				self.ComQueue[self.IDInternal].put(temp)

		if self.Settings["firstrun"] == "1":
			self.ComQueue[self.IDInternal].put(["init"])

		while True:
			data = self.ComQueue[self.IDInternal].get()

			if data[0] == SCRIPTS_TERMINATE_PROCESS:
				ProcessThread[data[1]].join()
				ProcessRunning[data[1]] = False

			elif data[0] == "state": #Toggle
				if data[1] == "1":
					#Kill previous started process in case still running
					if 1 in ProcessRunning:
						if ProcessRunning[1]:
							CommandsQueue[1].put(SCRIPTS_TERMINATE_PROCESS)
							ProcessThread[1].join()
							ProcessRunning[1] = False

					#Start process
					File = self.Settings["scriptstart" + self.Index + ",0"]

					if os.path.isfile(File):
						CommandsQueue[0] = multiprocessing.Queue()
						ProcessThread[0] = Processes(self.Settings["scriptstart" + self.Index + ",0"], 0, CommandsQueue, self.ComQueue, self.IDInternal)
						ProcessThread[0].start()
						ProcessRunning[0] = True

					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "STATE", "1"])
				elif data[1] == "0":
					#Kill previous started process in case still running
					if 0 in ProcessRunning:
						if ProcessRunning[0]:
							CommandsQueue[0].put(SCRIPTS_TERMINATE_PROCESS)
							ProcessThread[0].join()
							ProcessRunning[0] = False

					#Start process
					File = self.Settings["scriptstop" + self.Index + ",0"]

					if os.path.isfile(File):
						CommandsQueue[1] = multiprocessing.Queue()
						ProcessThread[1] = Processes(self.Settings["scriptstop" + self.Index + ",0"], 0, CommandsQueue, self.ComQueue, self.IDInternal)
						ProcessThread[1].start()
						ProcessRunning[1] = True

					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "STATE", "0"])
				elif data[1] == "undefined":
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "STATE", "undefined"])
			elif data[0] == "level":
				if data[1] == "undefined":
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "LEVEL", "undefined"])
				else:
					temp = float(data[1])

					for i in range (0, levels):
						if temp >= interval * i and temp <= interval * (i + 1):
							if temp > 0:
								SliderLevelLast = data[1]
								self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "LEVELLAST", data[1]])
								self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "LEVELLASTTOGGLE", "1"])
							else:
								self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "LEVELLASTTOGGLE", "0"])

							if levelprevious in ProcessRunning:
								if ProcessRunning[levelprevious]:
									CommandsQueue[levelprevious].put(SCRIPTS_TERMINATE_PROCESS)
									ProcessThread[levelprevious].join()
									ProcessRunning[levelprevious] = False

							File = self.Settings["scriptstart" + self.Index + "," + str(i)]

							if os.path.isfile(File):
								CommandsQueue[i] = multiprocessing.Queue()
								ProcessThread[i] = Processes(self.Settings["scriptstart" + self.Index + "," + str(i)], i, CommandsQueue, self.ComQueue, self.IDInternal)
								ProcessThread[i].start()
								ProcessRunning[i] = True
								levelprevious = i

					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "LEVEL", data[1]])
			elif data[0] == "init":
				if Process[0] != 0:
					os.killpg(os.getpgid(Process[0].pid), signal.SIGTERM)
					Process[0] = 0

				if Process[1] != 0:
					os.killpg(os.getpgid(Process[1].pid), signal.SIGTERM)
					Process[1] = 0

				if l == 1: # only one level, must be a "state" script
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "STATE", "0"])
				else: #more then one level, must be a multilevel script
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "LEVEL", "0"])
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "LEVELLAST", "0"])
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "LEVELLASTTOGGLE", "0"])

				continue
			elif data[0] == "levellasttoggle":
				if data[1] == "0":
					self.ComQueue[self.IDInternal].put(["level", "0"])
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "LEVELLASTTOGGLE", "0"])
				else:
					self.ComQueue[self.IDInternal].put(["level", SliderLevelLast])
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "LEVELLASTTOGGLE", "1"])
