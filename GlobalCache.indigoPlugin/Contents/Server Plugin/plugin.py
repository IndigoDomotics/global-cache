#! /usr/bin/env python
# -*- coding: utf-8 -*-
########################################
# Global Cache Plugin
# Developed by Chris Baltas
########################################

################################################################################
# Imports
################################################################################
import os
import sys
import re
import socket
import string

################################################################################
# Globals
################################################################################


################################################################################
class Plugin(indigo.PluginBase):
	
	########################################
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs): 
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
		self.debug = pluginPrefs.get("showDebugInfo", False) 
		self.deviceList = []
	
	########################################
	def __del__(self):
		indigo.PluginBase.__del__(self)

	########################################
	# Plugin Start and Stop methods	
	########################################
	
	def startup(self):
		self.debugLog("startup called")

	def shutdown(self):
		self.debugLog("shutdown called")

	########################################
	# Device Start and Stop methods	
	########################################

	def deviceStartComm(self, device):
		self.debugLog("Starting device: " + device.name)
		if device.id not in self.deviceList:
			self.update(device)
			self.deviceList.append(device.id)
		if device.deviceTypeId == u'gcDevice':
			self.openGCSocket(device)			
		if device.deviceTypeId == u'gcRelayModule':
			gcDevice = indigo.devices[int(device.pluginProps['relayGCDevice'])]
			gcConnectionState = gcDevice.states["connectionState"]
			if gcConnectionState == "Connected":
				self.syncRelayModule(device)
			
	########################################
	def deviceStopComm(self, device):
		self.debugLog("Stopping device: " + device.name)
		if device.id in self.deviceList:
			self.deviceList.remove(device.id)
		if device.deviceTypeId == u'gcDevice':
			ir.close()
			try:
				device.updateStateOnServer(key="connectionState", value="Disconnected")
				device.updateStateOnServer(key="moduleAddress1", value="")
				device.updateStateOnServer(key="moduleAddress2", value="")
				device.updateStateOnServer(key="moduleAddress3", value="")	
				device.updateStateOnServer(key="moduleAddress4", value="")
				device.updateStateOnServer(key="moduleAddress5", value="")
			except:
				# Device Deleted
				pass
				
		elif device.deviceTypeId == u'gcIRModule':
			try:
				device.updateStateOnServer(key="deviceState", value="Offline")
			except:
				# Device Deleted
				pass				
				
#		Relay state should not change unless power is turned off to GC-100
#		It does not look like I can retrieve the current state form the GC-100
#
#		elif device.deviceTypeId == u'gcRelayModule':
#			try:
#				device.updateStateOnServer(key="relayState", value="Offline")
#			except:
#				# Device Deleted
#				pass	

    ########################################
    # Routines for GC controller
    ########################################

	def openGCSocket(self, device):
		global ir
		 		 		
		host = device.address
		port = device.pluginProps['portNumber']
		indigo.server.log("Opening Socket for: " + device.name + " to " +host+":"+port)
		
	#	Close the current socket if it's already open	
		try:
			ir.close()		
		except:
			pass		

		ir = socket.socket(socket.AF_INET, socket.SOCK_STREAM)	

		try:
			ir.connect((host, int(port)))
			device.updateStateOnServer(key="connectionState", value="Connected")
			indigo.server.log("Socket opened succesfully")
			try:
				self.debugLog("Retrieving list of devices from "+device.name) 	
				ir.send('getdevices' + chr(13))
				response = ir.recv(256)
				self.updateGCDeviceStates(device, response)
				self.syncAllRelayModules(device)			
			except:
				indigo.server.log("Unable to retrieve settings.  Please check your settings and try again")
		except:
			indigo.server.log("Unable to open socket.  Please check your settings and try again")
			device.updateStateOnServer(key="connectionState", value="Socket Error")		
		
    ########################################
	def updateGCDeviceStates(self, device, response):
		self.debugLog("Updating "+device.name+" States")	
		responseArray = response.split(chr(13))
		responseSize = len(responseArray)-2
		module1 = responseArray[0]
		module2 = responseArray[1]
		module3 = responseArray[2]
		if responseSize > 3:
			module4 = responseArray[3]
		else:
			module4 = "       N/A"
		if responseSize > 4:
			module5 = responseArray[4]
		else:
			module5 = "       N/A"
		device.updateStateOnServer(key="moduleAddress1", value=module1[7:])
		device.updateStateOnServer(key="moduleAddress2", value=module2[7:])
		device.updateStateOnServer(key="moduleAddress3", value=module3[7:])
		device.updateStateOnServer(key="moduleAddress4", value=module4[7:])
		device.updateStateOnServer(key="moduleAddress5", value=module5[7:])

    ########################################
    # Routines for IR Modules
    ########################################

	def sendIRtoGC (self, action):
		irDevice = indigo.devices[action.deviceId]
		irDeviceState = irDevice.states["deviceState"]
		gcDevice = indigo.devices[int(irDevice.pluginProps['irGCDevice'])]
		gcConnectionState = gcDevice.states["connectionState"]
		if gcConnectionState == "Connected":
			irDevice.updateStateOnServer(key="deviceState", value="Transmit")
			address = irDevice.pluginProps['irModuleAddress']
			portNumber = irDevice.pluginProps['irPortNumber']
			irAddress = address+":"+portNumber			
			completeID = action.props["completeID"]
			frequency = action.props["frequency"]
			count = action.props["count"]
			offset = action.props["offset"]
			irCode = action.props["irString"]
			irString = "sendir,"+irAddress+","+completeID+","+frequency+","+count+","+offset+","+irCode
			self.debugLog(irString)	
			try:
				ir.send(irString + chr(13))
				response = ir.recv(256)
				irDevice.updateStateOnServer(key="deviceState", value="Receive")
				irDevice.updateStateOnServer(key="irLastAck", value=response)				
				self.debugLog(response)
				irDevice.updateStateOnServer(key="deviceState", value="Idle")
			except:
				indigo.server.log("Connection to "+gcDevice.name+" lost, please verify device is powered on and")
				indigo.server.log("connected to the network. Disable then enable comm on the device and try again.")
		else:
			indigo.server.log(gcDevice.name+" "+gcConnectionState+" - Unable to transmit commands.")

    ########################################
    # Routines for Relay Module
    ########################################

	def setGCRelayState (self, action):
		relayDevice = indigo.devices[action.deviceId]
		setRelayState = action.props["relayState"]
		gcDevice = indigo.devices[int(relayDevice.pluginProps['relayGCDevice'])]
		gcConnectionState = gcDevice.states["connectionState"]
		if gcConnectionState == "Connected":
			address = relayDevice.pluginProps['relayModuleAddress']
			relayNumber = relayDevice.pluginProps['relayNumber']
			relayAddress = address+":"+relayNumber
			relayString = "setstate,"+relayAddress+","+setRelayState						
			self.debugLog(relayString)	
			try:
				ir.send(relayString + chr(13))
				response = ir.recv(256)
				if response[10] == "0":
					relayDevice.updateStateOnServer(key="relayState", value="Off")
				elif response[10] == "1":
					relayDevice.updateStateOnServer(key="relayState", value="On")
				relayDevice.updateStateOnServer(key="relayLastAck", value=response)	
				self.debugLog(response)
			except:
				indigo.server.log("Connection to "+gcDevice.name+" lost, please verify device is powered on and")
				indigo.server.log("connected to the network. Disable then enable comm on the device and try again.")
		else:
			indigo.server.log(gcDevice.name+" "+gcConnectionState+" - Unable to set relay state")				

	########################################
	def syncAllRelayModules(self, device):
		self.debugLog("Syncing all relay modules for "+device.name)
		for deviceId in self.deviceList:
			if indigo.devices[deviceId].deviceTypeId == u'gcRelayModule':
				self.syncRelayModule(indigo.devices[deviceId])
 			
	########################################
	def syncRelayModule (self, device):
		relayState = device.states["relayState"]
		if relayState == "":
			relayState = "Off"
		gcDevice = indigo.devices[int(device.pluginProps['relayGCDevice'])]
		gcConnectionState = gcDevice.states["connectionState"]
		if gcConnectionState == "Connected":
			address = device.pluginProps['relayModuleAddress']
			relayNumber = device.pluginProps['relayNumber']
			relayAddress = address+":"+relayNumber	
			indigo.server.log("Syncing "+device.name+" with "+gcDevice.name+" State: "+relayState)
			if relayState == "On":
				setRelayState = "1"
			elif relayState == "Off":
				setRelayState = "0"
			relayString = "setstate,"+relayAddress+","+setRelayState						
			self.debugLog(relayString)	
			try:
				ir.send(relayString + chr(13))
				response = ir.recv(256)
				if response[10] == "0":
					device.updateStateOnServer(key="relayState", value="Off")
				elif response[10] == "1":
					device.updateStateOnServer(key="relayState", value="On")
				device.updateStateOnServer(key="relayLastAck", value=response)	
				self.debugLog(response)
			except:
				indigo.server.log("Connection to "+gcDevice.name+" lost, please verify device is powered on and")
				indigo.server.log("connected to the network. Disable then enable comm on the device and try again.")
		else:
			indigo.server.log(gcDevice.name+" "+gcConnectionState+" - Unable to sync relay state")				
		
		    
    ########################################
    # Routines for Concurrent Thread
    ########################################
    # Haven't found a use for it yet
    
#	def runConcurrentThread(self):
# 		self.debugLog("Starting concurrent tread")
# 		try:
# 			while True:
# 				for deviceId in self.deviceList:
# 					self.update(indigo.devices[deviceId])
# 		except self.StopThread:
# 			pass

	########################################
	# Updates the various Plugin devices                    
    ########################################
    
 	def update(self,device):
 		localPropsCopy = device.pluginProps
 		localPropsUpdated = False
 		self.debugLog("Updating device: " + device.name)
		if device.deviceTypeId == u'gcIRModule':
			device.updateStateOnServer(key="deviceState", value="Idle")
			
#		Relay state should not change unless power is turned off to GC-100
#		It does not look like I can retrieve the current state form the GC-100			
#		
#		if device.deviceTypeId == u'gcRelayModule':
#			device.updateStateOnServer(key="relayState", value="Off")					

	########################################
	# Preference close dialog methods
	########################################

	def closedPrefsConfigUi(self, valuesDict, userCancelled):
		if not userCancelled:
			self.debug = valuesDict.get("showDebugInfo", False)
			if self.debug:
				indigo.server.log("Debug logging enabled")
			else:
				indigo.server.log("Debug logging disabled")
				
	########################################
	# Preference Validation methods 
    ########################################
	# Validate the plugin config window after user hits OK
	# Returns False on failure, True on success

	def validatePrefsConfigUi(self, valuesDict):	
		self.debugLog(u"validating Prefs called")
		errorsDict = indigo.Dict()
		errorsFound = False    

		# nothing to validate in this window
		
		if errorsFound:
			return (False, valuesDict, errorsDict)
		else:
			return (True, valuesDict)

	########################################
	# Device Validation methods 
    ########################################
	# Validate the device config window after the user hits OK
	# Returns False on failure, True on success
	
	def validateDeviceConfigUi(self, valuesDict, typeId, devId):
		self.debugLog(u"Device Validation called")
		errorsDict = indigo.Dict()
		errorsFound = False			

		if typeId == u'gcDevice':
			if len(valuesDict[u'address']) == 0:
				errorsDict[u'address'] = 'An IP address is required'
				errorsFound = True
				
			if len(valuesDict[u'portNumber']) == 0:
				errorsDict[u'portNumber'] = 'Port number is a required field'
				errorsFound = True

			try:
				if (int(valuesDict[u'portNumber']) < 0 or int(valuesDict[u'portNumber']) > 65535): 
					errorsDict[u'portNumber'] = 'Port number must be between 0 and 65535 (default is 4998)'
					errorsFound = True
			except:
					errorsDict[u'portNumber'] = 'Port number must be an integer'
					errorsFound = True	

		if typeId == u'gcIRModule':
		
			if len(valuesDict[u'irGCDevice']) > 0:

				if len(valuesDict[u'irModuleAddress']) == 0:
					errorsDict[u'irModuleAddress'] = 'Module address is a required field'
					errorsFound = True

				if len(valuesDict[u'irPortNumber']) == 0:
					errorsDict[u'irPortNumber'] = 'Port number is a required field'
					errorsFound = True									

				# Determine if model number is GC-100-06 and then do validation
				gcDevice = indigo.devices[int(valuesDict[u'irGCDevice'])]
				if (len(gcDevice.states["moduleAddress4"]) == 0 and len(gcDevice.states["moduleAddress5"]) == 0):
					if int(valuesDict[u'irModuleAddress']) > 2:
						errorsDict[u'irModuleAddress'] = 'Model GC-100-06 only has one IR module and its address is 2'
						errorsFound = True
			else:
				errorsDict[u'irGCDevice'] = 'You must select a Global Cache device'
				errorsFound = True

		if typeId == u'gcRelayModule':
		
			if len(valuesDict[u'relayGCDevice']) > 0:

				if len(valuesDict[u'relayModuleAddress']) == 0:
					errorsDict[u'relayModuleAddress'] = 'Module address is a required field'
					errorsFound = True
					
				if len(valuesDict[u'relayNumber']) == 0:
					errorsDict[u'relayNumber'] = 'Relay number is a required field'
					errorsFound = True
						
				# Determine if model number is GC-100-06 and then do validation
				gcDevice = indigo.devices[int(valuesDict[u'relayGCDevice'])]
				if (len(gcDevice.states["moduleAddress4"]) == 0 and len(gcDevice.states["moduleAddress5"]) == 0):
					errorsDict[u'relayModuleAddress'] = 'Model GC-100-06 has no relay module'
					errorsDict[u'relayNumber'] = 'Model GC-100-06 has no relays'
					errorsFound = True
			else:
				errorsDict[u'relayGCDevice'] = 'You must select a Global Cache device'
				errorsFound = True
															
		if errorsFound:
			return (False, valuesDict, errorsDict)
		else:
			return (True, valuesDict)
		
	########################################
	# Action Validation methods 
    ########################################
	# Validate the actions config window after the user hits OK
	# Returns False on failure, True on success
	
	def validateActionConfigUi(self, valuesDict, typeId, actionId):
		self.debugLog(u"Action Validation called")
		errorsDict = indigo.Dict()
		errorsFound = False

		if typeId == u'sendIR':
			if len(valuesDict[u'completeID']) == 0:
				errorsDict[u'completeID'] = 'ID is a required field'
				errorsFound = True

			try:
				if int(valuesDict[u'completeID']) < 1 :
					errorsDict[u'completeID'] = 'ID must be 1 or greater'
					errorsFound = True
			except:
					errorsDict[u'completeID'] = 'ID must be an integer'
					errorsFound = True	
											
			if len(valuesDict[u'frequency']) == 0:
				errorsDict[u'frequency'] = 'Frequency is a required field'
				errorsFound = True

			try: 
				if (int(valuesDict[u'frequency']) < 20000 or int(valuesDict[u'frequency']) > 250000): 
					errorsDict[u'frequency'] = 'Frequency must be between 20000 and 250000'
					errorsFound = True									
			except:
					errorsDict[u'frequency'] = 'Frequency must be an integer'
					errorsFound = True
									
			if len(valuesDict[u'count']) == 0:
				errorsDict[u'count'] = 'Count is a required field'
				errorsFound = True				

			try:
				if (int(valuesDict[u'count']) < 0 or int(valuesDict[u'count']) > 31): 
					errorsDict[u'count'] = 'Count must be between 0 and 31'
					errorsFound = True				
			except:
					errorsDict[u'count'] = 'Count must be an integer'
					errorsFound = True
					
			if len(valuesDict[u'offset']) == 0:
				errorsDict[u'offset'] = 'Offset is a required field'
				errorsFound = True	

			try:							
				if (int(valuesDict[u'offset']) < 1 or int(valuesDict[u'offset']) > 511): 
					errorsDict[u'offset'] = 'Offset must be between 1 and 511'
					errorsFound = True
			except:
					errorsDict[u'offset'] = 'Offset must be an integer'
					errorsFound = True
												
			if len(valuesDict[u'irString']) == 0:
				errorsDict[u'irString'] = 'GC IR String is a required field'
				errorsFound = True				

		if errorsFound:
			return (False, valuesDict, errorsDict)
		else:
			return (True, valuesDict)

	########################################
	# Device Menu Lists
    ########################################
    
	def getIRModuleList(self, filter="", valuesDict=None, typeId="", targetId=0):
		myArray = ["2", "4", "5"]
		return myArray

    ########################################
	def getIRPortList(self, filter="", valuesDict=None, typeId="", targetId=0):
		myArray = ["1","2","3"]
		return myArray

    ########################################				
	def getRelayModuleList(self, filter="", valuesDict=None, typeId="", targetId=0):
		myArray = ["3"]
		return myArray

    ########################################
	def getRelayList(self, filter="", valuesDict=None, typeId="", targetId=0):
		myArray = ["1","2","3"]
		return myArray
		