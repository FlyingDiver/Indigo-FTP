#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import sys
import time
import logging
from ftplib import FTP

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

	def uploadFileAction(self, pluginAction, ftpDevice):
		props = ftpDevice.pluginProps
		localFile =  indigo.activePlugin.substitute(pluginAction.props["localFile"])
		remoteFile =  indigo.activePlugin.substitute(pluginAction.props["remoteFile"])
		port = props["port"]
		self.logger.debug(u"uploadFileAction sending file: " + localFile)
		ftp = FTP()
		self.logger.debug(u"downloadFileAction setting passive mode %s" % props['passive'])
		ftp.set_pasv(props['passive'])
		self.logger.debug(u"uploadFileAction connecting to server: %s (%s)" % (props['address'], port))

		try:
			ftp.connect(props['address'], int(port), 5)
		except ftplib.all_errors as e:
			self.logger.exception("Connect error: %s" % e)
			
		try:
			ftp.login(user=props['serverLogin'], passwd=props['serverPassword'])
		except ftplib.all_errors as e:
			self.logger.exception("Connect error: %s" % e)
			
		try:
			ftp.cwd('/'+props['directory']+'/')
		except ftplib.all_errors as e:
			self.logger.exception("Connect error: %s" % e)

		try:
			ftp.storbinary('STOR ' + remoteFile, open(localFile, 'rb'))
		except ftplib.all_errors as e:
			self.logger.exception("Connect error: %s" % e)

		try:
			ftp.quit()
		except ftplib.all_errors as e:
			self.logger.exception("Connect error: %s" % e)
		self.logger.debug(u"uploadFileAction complete")


	def downloadFileAction(self, pluginAction, ftpDevice):
		props = ftpDevice.pluginProps
		remoteFile =  indigo.activePlugin.substitute(pluginAction.props["remoteFile"])
		localFile =  indigo.activePlugin.substitute(pluginAction.props["localFile"])
		self.logger.debug(u"downloadFileAction getting file: " + remoteFile)

		ftp = FTP()
		self.logger.debug(u"downloadFileAction setting passive mode %s" % props['passive'])
		ftp.set_pasv(props['passive'])
		self.logger.debug(u"downloadFileAction connecting to server: %s (%s)" % (props['address'], props["port"]))
		ftp.connect(props['address'], int(props["port"]), 5)
		ftp.login(user=props['serverLogin'], passwd=props['serverPassword'])
		ftp.cwd('/'+props['directory']+'/')
  		lfile = open(localFile, 'wb')
		ftp.retrbinary('RETR ' + remoteFile, lfile.write, 1024)
		ftp.quit()
		lfile.close()
		self.logger.debug(u"downloadFileAction complete")


	########################################
	# Menu Methods
	########################################
		
	def checkForUpdates(self):
		self.updater.checkForUpdate()

	def updatePlugin(self):
		self.updater.update()

	def forceUpdate(self):
		self.updater.update(currentVersion='0.0.0')

