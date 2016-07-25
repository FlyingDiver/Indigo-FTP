#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import sys
import time
import logging
import json
from ftplib import FTP, all_errors

from ghpu import GitHubPluginUpdater

kCurDevVersCount = 0		# current version of plugin devices			
	
################################################################################
class Plugin(indigo.PluginBase):
					
	########################################
	# Main Plugin methods
	########################################
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
		
		pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
		self.plugin_file_handler.setFormatter(pfmt)

		try:
			self.logLevel = int(self.pluginPrefs[u"logLevel"])
		except:
			self.logLevel = logging.INFO
		self.indigo_log_handler.setLevel(self.logLevel)
		self.logger.debug(u"logLevel = " + str(self.logLevel))


	def __del__(self):
		indigo.PluginBase.__del__(self)

	def startup(self):
		indigo.server.log(u"Starting up FTP")
		
		self.updater = GitHubPluginUpdater(self)
		self.updateFrequency = float(self.pluginPrefs.get('updateFrequency', "24")) * 60.0 * 60.0
		self.logger.debug(u"updateFrequency = " + str(self.updateFrequency))
		self.next_update_check = time.time()
							
	def shutdown(self):
		indigo.server.log(u"Shutting down FTP")


	def runConcurrentThread(self):
		
		try:
			while True:
				
				if (self.updateFrequency > 0.0) and (time.time() > self.next_update_check):
					self.next_update_check = time.time() + self.updateFrequency
					self.updater.checkForUpdate()

				self.sleep(60.0) 
								
		except self.stopThread:
			pass
						
						
	def deviceStartComm(self, device):
		device.updateStateOnServer(key="serverStatus", value="Success")
		device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
		
	####################
	def validatePrefsConfigUi(self, valuesDict):
		errorDict = indigo.Dict()

		updateFrequency = int(valuesDict['updateFrequency'])
		if (updateFrequency < 0) or (updateFrequency > 24):
			errorDict['updateFrequency'] = u"Update frequency is invalid - enter a valid number (between 0 and 24)"
			self.logger.debug(u"updateFrequency out of range: " + valuesDict['updateFrequency'])

		if len(errorDict) > 0:
			return (False, valuesDict, errorDict)
		return (True, valuesDict)

	########################################
	def closedPrefsConfigUi(self, valuesDict, userCancelled):
		if not userCancelled:
			try:
				self.logLevel = int(valuesDict[u"logLevel"])
			except:
				self.logLevel = logging.INFO
			self.indigo_log_handler.setLevel(self.logLevel)
			self.logger.debug(u"logLevel = " + str(self.logLevel))

			self.updateFrequency = float(self.pluginPrefs.get('updateFrequency', "24")) * 60.0 * 60.0
			self.logger.debug(u"updateFrequency = " + str(self.updateFrequency))
			self.next_update_check = time.time()


	########################################
	# Plugin Actions object callbacks (pluginAction is an Indigo plugin action instance)
	######################

	def	connect(self, ftpDevice):
	
		props = ftpDevice.pluginProps
		port = props["port"]
		ftp = FTP()
		self.logger.debug(u"connect setting passive mode %s" % props['passive'])
		ftp.set_pasv(props['passive'])
		self.logger.debug(u"connect connecting to server: %s (%s)" % (props['address'], port))

		try:
			ftp.connect(props['address'], int(port), 5)
		except all_errors as e:
			ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
			ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
			self.logger.error("ftp.connect error: %s" % e)
			
		try:
			ftp.login(user=props['serverLogin'], passwd=props['serverPassword'])
		except all_errors as e:
			ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
			ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
			self.logger.error("ftp.login error: %s" % e)
			
		try:
			ftp.cwd('/'+props['directory']+'/')
		except all_errors as e:
			ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
			ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
			self.logger.error("ftp.cwd error: %s" % e)

		ftpDevice.updateStateOnServer(key="serverStatus", value="Success")
		ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
		return ftp
			
	def uploadFileAction(self, pluginAction, ftpDevice):
		localFile =  indigo.activePlugin.substitute(pluginAction.props["localFile"])
		remoteFile =  indigo.activePlugin.substitute(pluginAction.props["remoteFile"])
		self.logger.debug(u"uploadFileAction sending file: " + localFile)

		ftp = self.connect(ftpDevice)
		
		try:
			ftp.storbinary('STOR ' + remoteFile, open(localFile, 'rb'))
		except all_errors as e:
			ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
			ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
			self.logger.error("ftp.storbinary error: %s" % e)

		try:
			ftp.quit()
		except all_errors as e:
			ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
			ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
			self.logger.error("ftp.quit error: %s" % e)
		self.logger.debug(u"uploadFileAction complete")


	def downloadFileAction(self, pluginAction, ftpDevice):
		remoteFile =  indigo.activePlugin.substitute(pluginAction.props["remoteFile"])
		localFile =  indigo.activePlugin.substitute(pluginAction.props["localFile"])
		self.logger.debug(u"downloadFileAction getting file: " + remoteFile)

		ftp = self.connect(ftpDevice)

		try:
  			lfile = open(localFile, 'wb')
  		except:
			self.logger.error("Error opening local file: %s" % e)
  			
		try:
			ftp.retrbinary('RETR ' + remoteFile, lfile.write, 1024)
		except all_errors as e:
			ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
			ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
			self.logger.error("ftp.retrbinary error: %s" % e)

		lfile.close()
		try:
			ftp.quit()
		except all_errors as e:
			ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
			ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
			self.logger.error("ftp.quit error: %s" % e)
		self.logger.debug(u"downloadFileAction complete")

	def renameFileAction(self, pluginAction, ftpDevice):
		fromFile =  indigo.activePlugin.substitute(pluginAction.props["fromFile"])
		toFile =  indigo.activePlugin.substitute(pluginAction.props["toFile"])
		self.logger.debug(u"renameFileAction from: " + fromFile + " to: " + toFile)

		ftp = self.connect(ftpDevice)
		
		try:
			ftp.rename(fromFile, toFile)
		except all_errors as e:
			self.logger.error("ftp.rename error: %s" % e)

		try:
			ftp.quit()
		except all_errors as e:
			self.logger.error("ftp.quit error: %s" % e)
		self.logger.debug(u"renameFileAction complete")


	def deleteFileAction(self, pluginAction, ftpDevice):
		remoteFile =  indigo.activePlugin.substitute(pluginAction.props["remoteFile"])
		self.logger.debug(u"deleteFileAction deleting file: " + remoteFile)

		ftp = self.connect(ftpDevice)

		try:
			ftp.delete(remoteFile)
		except all_errors as e:
			self.logger.error("ftp.delete error: %s" % e)

		try:
			ftp.quit()
		except all_errors as e:
			self.logger.error("ftp.quit error: %s" % e)
		self.logger.debug(u"deleteFileAction complete")

	def nameListAction(self, pluginAction, ftpDevice):
		self.logger.debug(u"nameListAction")

		ftp = self.connect(ftpDevice)

		try:
			names = ftp.nlst()
			ftpDevice.updateStateOnServer(key="nameList", value=json.dumps(names))
			self.logger.debug(u"names = %s" % names)
		except all_errors as e:
			self.logger.error("ftp.nlst error: %s" % e)

		try:
			ftp.quit()
		except all_errors as e:
			self.logger.error("ftp.quit error: %s" % e)
		self.logger.debug(u"deleteFileAction complete")
		return names

	########################################
	# Menu Methods
	########################################
		
	def checkForUpdates(self):
		self.updater.checkForUpdate()

	def updatePlugin(self):
		self.updater.update()

	def forceUpdate(self):
		self.updater.update(currentVersion='0.0.0')

