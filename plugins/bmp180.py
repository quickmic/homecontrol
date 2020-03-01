#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import smbus
import time
import multiprocessing

MQTT = 0x00
MQTT_PUBLISH = 0x06
BMP180 = 0x07
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01

def Init(ComQueue, Threads, Settings):
	if "bmp180id" in Settings:
		Threads.append(Events(ComQueue, Settings))
		Threads[-1].start()

	return ComQueue, Threads

class Events(multiprocessing.Process):
	def __init__(self, ComQueue, Settings):
		multiprocessing.Process.__init__(self)
		self.Settings = Settings
		self.ComQueue = ComQueue

	def getShort(self, data, index):
		Temp = (data[index] << 8) + data[index + 1]

		if Temp > 32767:
			Temp = -(65536 - Temp)

		return Temp

	def getUshort(self, data, index):
		return (data[index] << 8) + data[index + 1]

	def ReadData(self):
		REG_CALIB  = 0xAA
		REG_MEAS   = 0xF4
		REG_MSB    = 0xF6
		REG_LSB    = 0xF7
		CRV_TEMP   = 0x2E
		CRV_PRES   = 0x34
		OVERSAMPLE = 3    # 0 - 3
		cal = self.bus.read_i2c_block_data(self.addr, REG_CALIB, 22)

		AC1 = self.getShort(cal, 0)
		AC2 = self.getShort(cal, 2)
		AC3 = self.getShort(cal, 4)
		AC4 = self.getUshort(cal, 6)
		AC5 = self.getUshort(cal, 8)
		AC6 = self.getUshort(cal, 10)
		B1  = self.getShort(cal, 12)
		B2  = self.getShort(cal, 14)
		MB  = self.getShort(cal, 16)
		MC  = self.getShort(cal, 18)
		MD  = self.getShort(cal, 20)

		#Read Temperature
		self.bus.write_byte_data(self.addr, REG_MEAS, CRV_TEMP)
		time.sleep(0.005)
		(msb, lsb) = self.bus.read_i2c_block_data(self.addr, REG_MSB, 2)
		UT = (msb << 8) + lsb

		#Read Pressure
		self.bus.write_byte_data(self.addr, REG_MEAS, CRV_PRES + (OVERSAMPLE << 6))
		time.sleep(0.04)
		(msb, lsb, xsb) = self.bus.read_i2c_block_data(self.addr, REG_MSB, 3)
		UP = ((msb << 16) + (lsb << 8) + xsb) >> (8 - OVERSAMPLE)

		#Refine Temperature
		X1 = ((UT - AC6) * AC5) >> 15
		X2 = (MC << 11) / (X1 + MD)
		B5 = X1 + X2
		Temperature = int(B5 + 8) >> 4

		#Refine Pressure
		B6  = B5 - 4000
		B62 = int(B6 * B6) >> 12
		X1  = (B2 * B62) >> 11
		X2  = int(AC2 * B6) >> 11
		X3  = X1 + X2
		B3  = (((AC1 * 4 + X3) << OVERSAMPLE) + 2) >> 2

		X1 = int(AC3 * B6) >> 13
		X2 = (B1 * B62) >> 16
		X3 = ((X1 + X2) + 2) >> 2
		B4 = (AC4 * (X3 + 32768)) >> 15
		B7 = (UP - B3) * (50000 >> OVERSAMPLE)

		P = (B7 * 2) / B4
		X1 = (int(P) >> 8) * (int(P) >> 8)
		X1 = (X1 * 3038) >> 16
		X2 = int(-7357 * P) >> 16
		Pressure = int(P + ((X1 + X2 + 3791) >> 4))

		return (Temperature / 10.0, Pressure / 100000.0)

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle('homecontrol-bmp180')

		TemperatureOld = ""
		PressureOld = ""
		Delay = int(self.Settings["bmp180refreshrate"])
		IDExternal = self.Settings["bmp180id"] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH_NORETAIN, IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.addr = 0x77 #Device
		self.bus = smbus.SMBus(int(self.Settings["bmp180bus"])) # Rev 2 Pi uses 1

		while True:
			Temperature, Pressure = self.ReadData()
			Temperature = "{:.2f}".format(Temperature)
			Pressure = "{:.4f}".format(Pressure)
			time.sleep(Delay)

			if TemperatureOld != Temperature:
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "temperature", Temperature])
				TemperatureOld = Temperature

			if PressureOld != Pressure:
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "pressure", Pressure])
				PressureOld = Pressure

