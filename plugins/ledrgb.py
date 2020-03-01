#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import pigpio

MQTT = 0x00
MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01

LEDRGB_RED = 0x00
LEDRGB_GREEN = 0x01
LEDRGB_BLUE = 0x02
LEDRGB_BRIGHTNESS = 0x03
LEDRGB_REDLEVELLAST = 0x04
LEDRGB_GREENLEVELLAST = 0x05
LEDRGB_BLUELEVELLAST = 0x06
LEDRGB_BRIGHTNESSLEVELLAST = 0x07
LEDRGB_UNDEFINED = 0x08

def Init(ComQueue, Threads, Settings):
	for i in range(0, 25):
		if "ledrgbid" + str(i) in Settings:
			IDInternal = Settings["ledrgbid" + str(i)].lower()
			ComQueue[IDInternal] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue, Settings, IDInternal, str(i)))
			Threads[-1].start()

	return ComQueue, Threads

#https://dordnung.de/raspberrypi-ledstrip/
class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.ComQueue = ComQueue
		self.Settings = Settings
		self.Index = Index
		self.IDInternal = IDInternal

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-LedRGB-' + self.Index)

		pi = pigpio.pi()
		Value = {}
		Value[LEDRGB_RED] = 1.0
		Value[LEDRGB_GREEN] = 1.0
		Value[LEDRGB_BLUE] = 1.0
		Value[LEDRGB_BRIGHTNESS] = 1.0
		Value[LEDRGB_REDLEVELLAST] = 1.0
		Value[LEDRGB_GREENLEVELLAST] = 1.0
		Value[LEDRGB_BLUELEVELLAST] = 1.0
		Value[LEDRGB_BRIGHTNESSLEVELLAST] = 1.0
		StateUndefined = 0xFF
		ID = {}
		ID[LEDRGB_RED] = float(self.Settings["ledrgbgpiored" + self.Index])
		ID[LEDRGB_GREEN] = float(self.Settings["ledrgbgpiogreen" + self.Index])
		ID[LEDRGB_BLUE] = float(self.Settings["ledrgbgpioblue" + self.Index])
		IDExternal = self.Settings["ledrgbid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH_NORETAIN, IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, IDExternal + "#"])

		if self.Settings["firstrun"] == "1":
			self.ComQueue[self.IDInternal].put(["init"])

		while True:
			Data = self.ComQueue[self.IDInternal].get()

			if len(Data) > 1: #skip e.g. 'init'
				if Data[1] == "undefined" or Data[1] == "nan":
					StateUndefined = LEDRGB_UNDEFINED
					Data[1] = "0"
				else:
					if float(Data[1]) < 0:
						Data[1] = "0"

					StateUndefined = 0xFF

			if Data[0] == "red" or Data[0] == "green" or Data[0] == "blue":
				ValueIncomming = float(Data[1]) * 254.0 + 1.0 #Range: 1-255

				if Data[0] == "red":
					RGBID = LEDRGB_RED
				elif Data[0] == "green":
					RGBID = LEDRGB_GREEN
				elif Data[0] == "blue":
					RGBID = LEDRGB_BLUE

				#Precaution
				if ValueIncomming > 255:
					ValueIncomming = 255

				if ValueIncomming < 1:
					ValueIncomming = 1

				Value[RGBID] = ValueIncomming

				if ValueIncomming != 1: #Save last values for Restore
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + Data[0] + "levellast", str(round((Value[RGBID] - 1.0) / 254.0, 2))])

					if StateUndefined == LEDRGB_UNDEFINED:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + Data[0] + "levellasttoggle", "undefined"])
					else:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + Data[0] + "levellasttoggle", "1"])
				else:
					if StateUndefined == LEDRGB_UNDEFINED:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + Data[0] + "levellasttoggle", "undefined"])
					else:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + Data[0] + "levellasttoggle", "0"])

				if StateUndefined == LEDRGB_UNDEFINED:
					pi.set_PWM_dutycycle(int(ID[RGBID]), 1)
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + Data[0], "undefined"])
				else:
					pi.set_PWM_dutycycle(int(ID[RGBID]), int(Value[RGBID]))
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + Data[0], str(round((Value[RGBID] - 1.0) / 254.0, 2))])

				#Update Brightness Value
				if Value[LEDRGB_RED] >= Value[LEDRGB_GREEN] and Value[LEDRGB_RED] >= Value[LEDRGB_BLUE]:
					Value[LEDRGB_BRIGHTNESS] = Value[LEDRGB_RED]
				elif Value[LEDRGB_GREEN] >= Value[LEDRGB_RED] and Value[LEDRGB_GREEN] >= Value[LEDRGB_BLUE]:
					Value[LEDRGB_BRIGHTNESS] = Value[LEDRGB_GREEN]
				elif Value[LEDRGB_BLUE] >= Value[LEDRGB_GREEN] and Value[LEDRGB_BLUE] >= Value[LEDRGB_RED]:
					Value[LEDRGB_BRIGHTNESS] = Value[LEDRGB_BLUE]

				if StateUndefined == LEDRGB_UNDEFINED:
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightness", "undefined"])
				else:
					self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightness", str(round((Value[LEDRGB_BRIGHTNESS] - 1.0) / 254.0, 2))])

				Value[LEDRGB_BRIGHTNESSLEVELLAST] = round((Value[LEDRGB_BRIGHTNESS] - 1.0) / 254.0, 2)
			elif Data[0] == "brightnesslevellast":
				Value[LEDRGB_BRIGHTNESSLEVELLAST] = Data[1]
			elif Data[0] == "redlevellast":
				Value[LEDRGB_REDLEVELLAST] = Data[1]
			elif Data[0] == "greenlevellast":
				Value[LEDRGB_GREENLEVELLAST] = Data[1]
			elif Data[0] == "bluelevellast":
				Value[LEDRGB_BLUELEVELLAST] = Data[1]
			elif Data[0] == "brightnesslevellasttoggle":
				if StateUndefined != LEDRGB_UNDEFINED:
					if Data[1] == "1":
						self.ComQueue[self.IDInternal].put(["brightness", str(Value[LEDRGB_BRIGHTNESSLEVELLAST])])
					else:
						self.ComQueue[self.IDInternal].put(["brightness", "0"])
			elif Data[0] == "redlevellasttoggle":
				if StateUndefined != LEDRGB_UNDEFINED:
					if Data[1] == "1":
						self.ComQueue[self.IDInternal].put(["red", str(Value[LEDRGB_REDLEVELLAST])])
					else:
						self.ComQueue[self.IDInternal].put(["red", "0"])
			elif Data[0] == "greenlevellasttoggle":
				if StateUndefined != LEDRGB_UNDEFINED:
					if Data[1] == "1":
						self.ComQueue[self.IDInternal].put(["green", str(Value[LEDRGB_GREENLEVELLAST])])
					else:
						self.ComQueue[self.IDInternal].put(["green", "0"])
			elif Data[0] == "bluelevellasttoggle":
				if StateUndefined != LEDRGB_UNDEFINED:
					if Data[1] == "1":
						self.ComQueue[self.IDInternal].put(["blue", str(Value[LEDRGB_BLUELEVELLAST])])
					else:
						self.ComQueue[self.IDInternal].put(["blue", "0"])
			elif Data[0] == "brightness":
				ValueIncomming = float(Data[1]) * 254.0 + 1.0
				Temp3 = ValueIncomming / Value[LEDRGB_BRIGHTNESS]

				if Temp3 != 1:
					Value[LEDRGB_BRIGHTNESS] = ValueIncomming
					Value[LEDRGB_RED] = Value[LEDRGB_RED] * Temp3
					Value[LEDRGB_GREEN] = Value[LEDRGB_GREEN] * Temp3
					Value[LEDRGB_BLUE] = Value[LEDRGB_BLUE] * Temp3

					ValueRed = str(round((Value[LEDRGB_RED] - 1.0) / 254.0, 2))
					ValueGreen = str(round((Value[LEDRGB_GREEN] - 1.0) / 254.0, 2))
					ValueBlue = str(round((Value[LEDRGB_BLUE] - 1.0) / 254.0, 2))
					ValueBrightness = str(round((Value[LEDRGB_BRIGHTNESS] - 1.0) / 254.0, 2))

					if ValueIncomming != 1:
						if StateUndefined == LEDRGB_UNDEFINED:
							self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightnesslevellasttoggle", "undefined"])
						else:
							self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightnesslevellasttoggle", "1"])

						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "redlevellast", ValueRed])
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "greenlevellast", ValueGreen])
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "bluelevellast", ValueBlue])
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightnesslevellast", ValueBrightness])
						Value[LEDRGB_BRIGHTNESSLEVELLAST] = Data[1]
						Value[LEDRGB_REDLEVELLAST] = ValueRed
						Value[LEDRGB_GREENLEVELLAST] = ValueGreen
						Value[LEDRGB_BLUELEVELLAST] = ValueBlue
					else:
						if StateUndefined == LEDRGB_UNDEFINED:
							self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightnesslevellasttoggle", "undefined"])
							self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "redlevellasttoggle", "undefined"])
							self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "greenlevellasttoggle", "undefined"])
							self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "bluelevellasttoggle", "undefined"])
						else:
							self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightnesslevellasttoggle", "0"])


					#Precaution
					if int(Value[LEDRGB_RED]) > 255:
						print("test: " + str(Value[LEDRGB_RED]))
						Value[LEDRGB_RED] = 255

					if int(Value[LEDRGB_GREEN]) > 255:
						print("test: " + str(Value[LEDRGB_GREEN]))
						Value[LEDRGB_GREEN] = 255

					if int(Value[LEDRGB_BLUE]) > 255:
						print("test: " + str(Value[LEDRGB_BLUE]))
						Value[LEDRGB_BLUE] = 255


					if StateUndefined == LEDRGB_UNDEFINED:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "red", "undefined"])
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "green", "undefined"])
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "blue", "undefined"])
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightness", "undefined"])
						pi.set_PWM_dutycycle(int(ID[LEDRGB_RED]), 0)
						pi.set_PWM_dutycycle(int(ID[LEDRGB_GREEN]), 0)
						pi.set_PWM_dutycycle(int(ID[LEDRGB_BLUE]), 0)
					else:
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "red", ValueRed])
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "green", ValueGreen])
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "blue", ValueBlue])
						self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightness", ValueBrightness])
						pi.set_PWM_dutycycle(int(ID[LEDRGB_RED]), int(Value[LEDRGB_RED]))
						pi.set_PWM_dutycycle(int(ID[LEDRGB_GREEN]), int(Value[LEDRGB_GREEN]))
						pi.set_PWM_dutycycle(int(ID[LEDRGB_BLUE]), int(Value[LEDRGB_BLUE]))

			elif Data[0] == "init":
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "red", "0"])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "green", "0"])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "blue", "0"])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightness", "0"])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "redlevellast", "0"])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "greenlevellast", "0"])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "bluelevellast", "0"])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightnesslevellast", "0"])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "redlevellasttoggle", "0"])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "greenlevellasttoggle", "0"])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "bluelevellasttoggle", "0"])
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "brightnesslevellasttoggle", "0"])
				pi.set_PWM_dutycycle(int(ID[LEDRGB_RED]), 1)
				pi.set_PWM_dutycycle(int(ID[LEDRGB_GREEN]), 1)
				pi.set_PWM_dutycycle(int(ID[LEDRGB_BLUE]), 1)

