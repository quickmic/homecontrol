#!/usr/bin/python3
try:
	import setproctitle
	SETPROCTITLE = True
except:
	SETPROCTITLE = False

import multiprocessing
import time
import urllib.request
import datetime

#https://wiki.tuxbox-neutrino.org/wiki/Neutrino

NEUTRINO_EPG_FINISHED = 0x00

MQTT_PUBLISH = 0x06
MQTT_SUBSCRIBE = 0x01
MQTT = 0x00
MQTT_PUBLISH_NORETAIN = 0x08
SETTINGS_IPTOPIC = 0x01

def Init(ComQueue, Threads, Settings):
	for i in range(0, 25):
		if "neutrinoid" + str(i) in Settings:
			IDInternal = Settings["neutrinoid" + str(i)].lower()
			ComQueue[IDInternal] = multiprocessing.Queue()
			Threads.append(Controller(ComQueue, Settings, IDInternal, str(i)))
			Threads[-1].start()

	return ComQueue, Threads

class EPGUpdate(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, Index, IP, Username, Password, IDExternal, IDInternal, M3U):
		multiprocessing.Process.__init__(self)
		self.Settings = Settings
		self.ComQueue = ComQueue
		self.Index = Index
		self.IP = IP
		self.Username = Username
		self.Password = Password
		self.IDInternal = IDInternal
		self.IDExternal = IDExternal
		self.M3U = M3U

	def run(self):


		print("EPG1")

		if SETPROCTITLE:
			setproctitle.setproctitle("homecontrol-neutrino-epgupdate " + self.Index)

		EPGUpdateTime = self.Settings["neutrinoepgupdatetime" + self.Index]
		EPGPath = self.Settings["neutrinoepgpath" + self.Index]
		password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
		top_level_url = "http://" + self.IP + "/"
		password_mgr.add_password(None, top_level_url, self.Username, self.Password)
		handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
		opener = urllib.request.build_opener(handler)
		urllib.request.install_opener(opener)

		#EPG
		output = ""
		header = '<?xml version="1.0" encoding="utf-8" ?>\n<tv>\n'
		ChannelData = self.M3U.split("tvg-id=")

		urllib.request.urlopen("http://" + self.IP + "/control/standby?off")


		print("EPG2")


		#Zap
		for j in range(1, len(ChannelData)):
#		for j in range(1, 5):

			if ChannelData[j].find("radio=") == -1:
				ChannelID = ChannelData[j][1:17]
				response = urllib.request.urlopen("http://" + self.IP + "/control/zapto?" + ChannelID).read().decode(encoding='utf-8')
				time.sleep(3)


		print("EPG3")

		urllib.request.urlopen("http://" + self.IP + "/control/standby?on")
		BouquetTemp = ""





		for j in range(1, len(ChannelData)):
			ChannelID = ChannelData[j][1:17]
			Pos = ChannelData[j].find("group-title=") + 13
			Bouquet = ChannelData[j][Pos:]
			Pos = Bouquet.find('",')
			Bouquet = Bouquet[:Pos]

			if BouquetTemp != Bouquet:
				BouquetTemp = Bouquet

			time.sleep(1)

			response = urllib.request.urlopen("http://" + self.IP + "/control/epg?xml=true&channelid=" + ChannelID + "&details=true").read().decode(encoding='utf-8')
			Data = response.split("<prog>")
			Pos = Data[0].find("<channel_name>") + 14
			Data[0] = Data[0][Pos:]
			TempT = response
			Pos = Data[0].find("</channel_name>")
			ChannelName = Data[0][:Pos]
			ChannelName = ChannelName.replace("<![CDATA[", "").replace("]]>", "")
			ChannelName = ChannelName.replace("&","&amp;")
			ChannelName = ChannelName.replace("<","&lt;")
			ChannelName = ChannelName.replace(">","&gt;")
			ChannelName = ChannelName.replace('"','&quot;')
			ChannelName = ChannelName.replace("'","&apos;")

			if ChannelName != "":
				header = header + '  <channel id="' + ChannelID + '">\n      <display-name lang="en">' + ChannelName + '</display-name>\n  </channel>\n'

				for i in range(1, len(Data)):
					Pos = Data[i].find("<start_sec>") + 11
					Data[i] = Data[i][Pos:]
					Pos = Data[i].find("</start_sec>")
					StartTime = Data[i][:Pos]



					print("StartTime: " + str(StartTime))

					StartTime = datetime.datetime.fromtimestamp(float(StartTime))

					print("StartTime2: " + str(StartTime))


					StartTime = str(StartTime).replace("-", "").replace(" ", "").replace(":", "")

					Pos = Data[i].find("<stop_sec>") + 10
					Data[i] = Data[i][Pos:]
					Pos = Data[i].find("</stop_sec>")
					StopTime = Data[i][:Pos]
					StopTime = datetime.datetime.fromtimestamp(float(StopTime))
					StopTime = str(StopTime).replace("-", "").replace(" ", "").replace(":", "")

					Pos = Data[i].find("<info1>") + 7
					Data[i] = Data[i][Pos:]
					Pos = Data[i].find("</info1")
					Info1 = Data[i][:Pos]
					Info1 = Info1.replace("<![CDATA[", "").replace("]]>", "")
					Info1 = Info1.replace("&","&amp;")
					Info1 = Info1.replace("<","&lt;")
					Info1 = Info1.replace(">","&gt;")
					Info1 = Info1.replace('"','&quot;')
					Info1 = Info1.replace("'","&apos;")
					Info1 = Info1.replace("\x1a","&apos;")

					Pos = Data[i].find("<info2>") + 7
					Data[i] = Data[i][Pos:]
					Pos = Data[i].find("</info2")
					Info2 = Data[i][:Pos]
					Info2 = Info2.replace("<![CDATA[", "").replace("]]>", "")
					Info2 = Info2.replace("&","&amp;")
					Info2 = Info2.replace("<","&lt;")
					Info2 = Info2.replace(">","&gt;")
					Info2 = Info2.replace('"','&quot;')
					Info2 = Info2.replace("'","&apos;")
					Info2 = Info2.replace("\x1a","&apos;")

					#Main Info
					Pos = Data[i].find("<description>") + 13
					Data[i] = Data[i][Pos:]
					Pos = Data[i].find("</description")
					Info3 = Data[i][:Pos]
					Info3 = Info3.replace("<![CDATA[", "").replace("]]>", "")
					Info3 = Info3.replace("&","&amp;")
					Info3 = Info3.replace("<","&lt;")
					Info3 = Info3.replace(">","&gt;")
					Info3 = Info3.replace('"','&quot;')
					Info3 = Info3.replace("'","&apos;")
					Info3 = Info3.replace("\x1a","&apos;")

					output = output + '  <programme start="' + StartTime + ' +0200" stop="' + StopTime + ' +0200" channel="' + ChannelID + '">\n      <title lang="en">' + Info3 + ' / ' + Info1 + '</title>\n      <sub-title lang="en">' + Info1 + '</sub-title>\n      <desc lang="en">' + Info2 + '</desc>\n  </programme>\n'
			else:
				print("fail!!!")

		output = header + output + '</tv>'

		f = open(EPGPath, "w")
		f.write(output)
		f.flush()
		f.close()


		self.ComQueue[self.IDInternal].put([NEUTRINO_EPG_FINISHED])

		print("DONE")







class Status(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, Index, IP, Username, Password, IDExternal):
		multiprocessing.Process.__init__(self)
		self.Settings = Settings
		self.ComQueue = ComQueue
		self.Index = Index
		self.IP = IP
		self.Username = Username
		self.Password = Password
		self.IDExternal = IDExternal

	def RequestData(self, URL):
		time.sleep(0.5) # Refreshinterval

		while True:
			try:
				Response = urllib.request.urlopen(URL, timeout=5).read().decode(encoding='utf-8')

				if self.Online != "1":
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IP.replace(".", "-") + "/online", "1"])
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "epgupdate", "0"])
					self.Online = "1"

				return Response
			except:
				if self.Online != "0":
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IP.replace(".", "-") + "/online", "0"])
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "standby", "undefined"])
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "volume", "undefined"])
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "mode", "undefined"])
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "mute", "undefined"])
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "epgupdate", "undefined"])
					self.Online = "0"
					self.Standby = "-1"
					self.Volume = "-1"
					self.Mode = "-1"
					self.Mute = "-1"

				print("Neutrino offline")
				time.sleep(5)
				continue

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle("homecontrol-neutrino-status " + self.Index)

		password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
		top_level_url = "http://" + self.IP + "/"
		password_mgr.add_password(None, top_level_url, self.Username, self.Password)
		handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
		opener = urllib.request.build_opener(handler)
		urllib.request.install_opener(opener)

		self.Standby = "-1"
		self.Online = "-1"
		self.Volume = "-1"
		self.Mode = "-1"
		self.Mute = "-1"

		while True:
			response = self.RequestData("http://" + self.IP + "/control/standby")

#			if len(response) > 1:
			if (response[:2] == "on"):

#				print("standby on")

				if self.Standby != "1":
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "standby", "1"])
					self.Standby = "1"

			else:
				if self.Standby != "0":
					self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "standby", "0"])
					self.Standby = "0"

			response = self.RequestData("http://" + self.IP + "/control/volume")


			Temp = str(float(response) / 100)
#			print(Temp)

			if self.Volume != Temp:
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "volume", Temp])
				self.Volume = Temp

			response = self.RequestData("http://" + self.IP + "/control/getmode")
			response = response.replace("\n", "")
#			print(response)

			if self.Mode != response:
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "mode", response])
				self.Mode = response



			response = self.RequestData("http://" + self.IP + "/control/volume?status")








#			print(response)

			if self.Mute != response:
				self.ComQueue[MQTT].put([MQTT_PUBLISH, self.IDExternal + "mute", response])
				self.Mute = response

#http://dbox/control/volume 
#http://dbox/control/volume?40
#http://dbox/control/volume?mute
#http://dbox/control/volume?status   #mute status
#http://dbox/control/standby?on
#http://dbox/control/standby?off
#http://dbox/control/shutdown
#http://dbox/control/setmode?status #recordmode status
#http://192.168.0.7/control/info?version
#http://dbox/control/getmode
#http://dbox/control/setmode?radio
#http://dbox/control/setmode?tv
#http://dbox/control/info?streaminfo
#http://192.168.0.7/control/info?httpdversion
#http://dbox/control/getonidsid 
#http://192.168.0.7/control/getservicesxml
#http://dbox/control/getbouquetsxml
#http://dbox/control/getbouquets 
#http://dbox/control/getbouquet?bouquet=2&mode=TV







class Controller(multiprocessing.Process):
	def __init__(self, ComQueue, Settings, IDInternal, Index):
		multiprocessing.Process.__init__(self)
		self.Settings = Settings
		self.IDInternal = IDInternal
		self.ComQueue = ComQueue
		self.Index = Index

	def run(self):
		if SETPROCTITLE:
			setproctitle.setproctitle("homecontrol-neutrino " + self.Index)

		IDExternal = self.Settings["neutrinoid" + self.Index] + "/"
		self.ComQueue[MQTT].put([MQTT_PUBLISH_NORETAIN, IDExternal + "interface", self.Settings[SETTINGS_IPTOPIC]])
		self.ComQueue[MQTT].put([MQTT_SUBSCRIBE, IDExternal + "#"])
		IP = self.Settings["neutrinoip" + self.Index]
		Username = self.Settings["neutrinousername" + self.Index]
		Password = self.Settings["neutrinopassword" + self.Index]
#		self.NeutrinoEPGUpdateTime = self.Settings["neutrinoepgupdatetime" + self.Index]
		M3UURL = self.Settings["neutrinom3uurl" + self.Index]
		M3UUsername = self.Settings["neutrinom3uusername" + self.Index]
		M3UPassword = self.Settings["neutrinom3upassword" + self.Index]
		M3UPath = self.Settings["neutrinom3upath" + self.Index]
#		NeutrinoEPGPath = self.Settings["neutrinoepgpath" + self.Index]
		Status(self.ComQueue, self.Settings, self.Index, IP, Username, Password, IDExternal).start()
		self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + "epgupdate", "0"])

		password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
		top_level_url = "http://" + IP + "/"
		password_mgr.add_password(None, top_level_url, Username, Password)
		handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
		opener = urllib.request.build_opener(handler)
		urllib.request.install_opener(opener)

		#create playlists


		print("http://" + IP + "/control/getbouquets")

		response = urllib.request.urlopen("http://" + IP + "/control/getbouquets").read().decode(encoding='utf-8')


		print(response)

		print("111111111111")

		#Prepare EPGUpdateProcess
#		EPGUpdateProcess = EPGUpdate(self.ComQueue, self.Settings, self.Index, IP, Username, Password, IDExternal, IDInternal, M3U)
#		EPGUpdateProcess = EPGUpdate(self.ComQueue, self.Settings, self.Index, IP, Username, Password, IDExternal, IDInternal)





		Counter = 0
		M3U = "#EXTM3U\n"
		Data = response.split("\n")


		print("2222222")

		for i in range(0, len(Data) - 2):
			if Data[i].find("[") != -1:
				continue
			elif Data[i].lower().find("unkno") != -1:
				continue
			elif Data[i].lower().find("filmon") != -1:
				continue
			elif Data[i].lower().find("youtube") != -1:
				continue
			elif Data[i].lower().find("radio") != -1:
				continue

			print("1: " + Data[i])

			ID = str(int(Data[i][:2]))
			Bouquet = Data[i][2:].strip()

			response = urllib.request.urlopen("http://" + IP + "/control/getbouquet?bouquet=" + ID + "&mode=TV").read().decode(encoding='utf-8')
			Data2 = response.split("\n")





			print(Data2)


			for j in range(0, len(Data2)):
				Pos = Data2[j].find(" ")
				ChannelNumber = Data2[j][:Pos].strip()
				Data2[j] = Data2[j][Pos:].strip()
				Pos = Data2[j].find(" ")
				ChannelID = Data2[j][:Pos].strip()
				ChannelName = Data2[j][Pos:].strip()


				print(ChannelName)

				if (len(ChannelName) >=2):
					if (ChannelName.lower()[:3] != "unk"):
#						M3U = M3U + '#EXTINF:-1 tvg-id="' + ChannelID + '" tvg-name="' + ChannelName + '" tvg-logo="' + ChannelName + '.png" gro$

						M3U = M3U + '#EXTINF:-1 tvg-id="' + ChannelID + '" tvg-name="' + ChannelName + '" tvg-logo="' + ChannelName + '.png" group-title="' + Bouquet + '",' + ChannelName + '\n' + 'https://' + M3UUsername + ':' + M3UPassword + '@' + M3UURL  + '/stream/id=' + ChannelID + '\n'


				print("ccccc")


				print(M3U)
				print("wwwwwwww")

				Counter += 1


			print("dddd")

			f = open(M3UPath, "w")
			f.write(M3U)
			f.flush()
			f.close()



			print("ssss")


		print("22222222222222")


		#Prepare EPGUpdateProcess
		EPGUpdateProcess = EPGUpdate(self.ComQueue, self.Settings, self.Index, IP, Username, Password, IDExternal, self.IDInternal, M3U)



		#Request Status
		while True:

			print(self.IDInternal)

			temp2 = self.ComQueue[self.IDInternal].get()
#			temp2 = temp
#			temp2 = temp.split("|")

			print("Incomming" + str(temp2))


			if temp2[0] == NEUTRINO_EPG_FINISHED:
				EPGUpdateProcess.join()



			elif temp2[0] == "standby":
				if temp2[1] == "1":
					urllib.request.urlopen("http://" + IP + "/control/standby?on").read().decode(encoding='utf-8')
				else:
					urllib.request.urlopen("http://" + IP + "/control/standby?off").read().decode(encoding='utf-8')
			elif temp2[0] == "mute":

#				print("mute: " + str()


				if temp2[1] == "1":
					urllib.request.urlopen("http://" + IP + "/control/volume?mute").read().decode(encoding='utf-8')
				else:
					urllib.request.urlopen("http://" + IP + "/control/volume?unmute").read().decode(encoding='utf-8')
			elif temp2[0] == "volume":
				Temp = str(float(temp2[1]) * 100)
				urllib.request.urlopen("http://" + IP + "/control/volume?" + Temp).read().decode(encoding='utf-8')
			elif temp2[0] == "mode":
				urllib.request.urlopen("http://" + IP + "/control/setmode?" + temp2[1]).read().decode(encoding='utf-8')
			elif temp2[0] == "epgupdate":
				print("epgupdate")

				if temp2[1] == "1":
					print("epgupdate start")
					EPGUpdateProcess.start()


					print("Done2")

				else:
					print("epgupdate stop")

			if len(temp2) > 1:
				self.ComQueue[MQTT].put([MQTT_PUBLISH, IDExternal + temp2[0], temp2[1]])

