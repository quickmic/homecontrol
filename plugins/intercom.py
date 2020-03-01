#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import socket
import time

MQTT = 0x00
INTERCOM = 0x03

#Communication
MQTT_REQUEST = 0x07

def Init(ComQueue, Threads, Settings):
	if "intercomenabled" in Settings:
		if Settings["intercomenabled"] == "1":
			ComQueue[INTERCOM] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue))
			Threads[-1].start()

	return ComQueue, Threads

class Controller(multiprocessing.Process):
	def __init__(self, ComQueue):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-intercom-events')

		socketListening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		socketListening.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		socketListening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		socketListening.bind(("0.0.0.0", 60002))
		socketListening.listen(10)

		while True:
			socketClient, addr = socketListening.accept()
			serialBuffer = socketClient.recv(256).decode(encoding='ascii') #waiting here for input
			temp = serialBuffer.replace("\n", "")
			self.ComQueue[MQTT].put([MQTT_REQUEST, temp])

			#Waiting for answer loop
			for i in range(0, 5): #Timout after 5 loops (0.5s)
				if self.ComQueue[INTERCOM].empty():
					if i == 4:
						socketClient.close()
					else:
						time.sleep(0.1)
				else:
					Data = self.ComQueue[INTERCOM].get()
					socketClient.send(Data[0].encode())
					socketClient.close()
					break
