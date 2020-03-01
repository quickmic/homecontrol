#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing

STATELOG = 0x04
MQTT = 0x00
MQTT_SUBSCRIBE = 0x01

def Init(ComQueue, Threads, Settings):
	if "statelogfile" in Settings:
		ComQueue[STATELOG] = multiprocessing.Queue()
		Threads.append(Controller(ComQueue, Settings))
		Threads[-1].start()

	return ComQueue, Threads

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-log-events')

		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, "#"])
		Data = ""
		OldData = ""

		while True:
			IncommingData = self.ComQueue[STATELOG].get()

			if len(IncommingData) == 1:
				continue

			DataPos = Data.find(IncommingData[0] + "|")

			if DataPos == -1:
				Data = Data + IncommingData[0] + "|" + IncommingData[1] + "\n"
			else:
				temp2 = Data[DataPos:]
				temp2 = temp2[:temp2.find("\n")]
				Data = Data.replace(temp2, IncommingData[0] + "|" + IncommingData[1])

			if OldData != Data:
				OldData = Data
				f = open(self.Settings["statelogfile"], 'w')
				f.write(Data)
				f.flush()
				f.close()
