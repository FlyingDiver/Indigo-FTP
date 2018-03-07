#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import sys
import time
import logging
import json

from Queue import Queue, Empty
from threading import Thread, Event
from ftplib import FTP, FTP_TLS, all_errors

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

    def startup(self):
        indigo.server.log(u"Starting up FTP")

        self.ftpQ = Queue()
        self.queueStop = Event()
        self.queueStop.clear()
        self.queueThread = Thread(target=self.queueHandler)
        self.queueThread.start()
        self.clearQueue = False

    def shutdown(self):
        indigo.server.log(u"Shutting down FTP")


    def runConcurrentThread(self):

        try:
            while True:

                self.sleep(60.0)

        except self.stopThread:
            self.queueStop.set()    # stop the queue thread


    def deviceStartComm(self, device):
        instanceVers = int(device.pluginProps.get('devVersCount', 0))
        if instanceVers >= kCurDevVersCount:
            self.logger.debug(device.name + u": Device Version is up to date")
        elif instanceVers < kCurDevVersCount:
            newProps = device.pluginProps

            newProps["devVersCount"] = kCurDevVersCount
            device.replacePluginPropsOnServer(newProps)
            device.stateListOrDisplayStateIdChanged()
            self.logger.debug(u"deviceStartComm: Updated " + device.name + " to version " + str(kCurDevVersCount))

        else:
            self.logger.error(u"Unknown device version: " + str(instanceVers) + " for device " + device.name)

        device.updateStateOnServer(key="serverStatus", value="Success")
        device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

    ####################
    def validatePrefsConfigUi(self, valuesDict):
        errorDict = indigo.Dict()

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

    ########################################
    # Plugin Actions object callbacks (pluginAction is an Indigo plugin action instance)
    ######################

    def connect(self, ftpDevice):

        props = ftpDevice.pluginProps
        port = props["port"]

        self.logger.debug(u"ftp_tls mode %s" % props['passive'])
        if props['tls']:
            ftp = FTP_TLS()
        else:
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
            return None

        try:
            ftp.login(user=props['serverLogin'], passwd=props['serverPassword'])
        except all_errors as e:
            ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
            ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
            self.logger.error("ftp.login error: %s" % e)
            return None

        if props['tls']:
            try:
                ftp.prot_p()
            except all_errors as e:
                ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
                ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                self.logger.error("ftp.prot_p error: %s" % e)
                return None

        try:
            ftp.cwd('/'+props['directory']+'/')
        except all_errors as e:
            ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
            ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
            self.logger.error("ftp.cwd error: %s" % e)
            return None

        ftpDevice.updateStateOnServer(key="serverStatus", value="Success")
        ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
        return ftp

    def executeAction(self, pluginAction, ftpDevice, callerWaitingForResult):
        self.logger.debug(u"executeAction, queueing Action = " + pluginAction.pluginTypeId)

        completeHandler = None
        if callerWaitingForResult:
            completeHandler = indigo.acquireCallbackCompleteHandler()

        self.ftpQ.put((pluginAction, ftpDevice, completeHandler))


    def queueHandler(self):

        while True:
            if self.queueStop.isSet():
                self.logger.debug(u"queueHandler queueStop isSet")
                return

            time.sleep(1.0)

            if self.clearQueue:
                self.logger.debug(u"Clearing FTP Queue")
                self.ftpQ = Queue()
                self.clearQueue = False


            try:
                (pluginAction, ftpDevice, completeHandler) = self.ftpQ.get(False)
                self.logger.debug(u"queueHandler action = %s, %d in queue" % (pluginAction.pluginTypeId, self.ftpQ.qsize()))

                result = None

                ftp = self.connect(ftpDevice)
                if not ftp:
                    self.logger.debug(u"executeAction, connection failure, requeueing operation")
                    self.ftpQ.put((pluginAction, ftpDevice, completeHandler))
                    continue

                if pluginAction.pluginTypeId == u"uploadFile":

                    localFile =  indigo.activePlugin.substitute(pluginAction.props["localFile"])
                    remoteFile =  indigo.activePlugin.substitute(pluginAction.props["remoteFile"])
                    self.logger.debug(u"uploadFileAction sending file: " + localFile)
                    try:
                        ftp.storbinary('STOR ' + remoteFile, open(localFile, 'rb'))
                        self.logger.debug(u"ftp.storbinary complete")
                    except all_errors as e:
                        ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
                        ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                        self.logger.error("ftp.storbinary error: %s" % e)


                elif  pluginAction.pluginTypeId == u"downloadFile":

                    remoteFile =  indigo.activePlugin.substitute(pluginAction.props["remoteFile"])
                    localFile =  indigo.activePlugin.substitute(pluginAction.props["localFile"])
                    self.logger.debug(u"downloadFileAction getting file: " + remoteFile)
                    try:
                        lfile = open(localFile, 'wb')
                    except:
                        self.logger.error("Error opening local file: %s" % e)
                    try:
                        ftp.retrbinary('RETR ' + remoteFile, lfile.write, 1024)
                        self.logger.debug(u"ftp.retrbinary complete")
                    except all_errors as e:
                        ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
                        ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                        self.logger.error("ftp.retrbinary error: %s" % e)

                    lfile.close()

                elif  pluginAction.pluginTypeId == u"renameFile":
                    fromFile =  indigo.activePlugin.substitute(pluginAction.props["fromFile"])
                    toFile =  indigo.activePlugin.substitute(pluginAction.props["toFile"])
                    self.logger.debug(u"renameFileAction from: " + fromFile + " to: " + toFile)
                    try:
                        ftp.rename(fromFile, toFile)
                        self.logger.debug(u"ftp.rename complete")
                    except all_errors as e:
                        self.logger.error("ftp.rename error: %s" % e)

                elif  pluginAction.pluginTypeId == u"deleteFile":

                    remoteFile =  indigo.activePlugin.substitute(pluginAction.props["remoteFile"])
                    self.logger.debug(u"deleteFileAction deleting file: " + remoteFile)
                    try:
                        ftp.delete(remoteFile)
                        self.logger.debug(u"ftp.delete complete")
                    except all_errors as e:
                        self.logger.error("ftp.delete error: %s" % e)

                elif  pluginAction.pluginTypeId == u"nameList":

                    try:
                        result = ftp.nlst()
                        self.logger.debug(u"ftp.nlst complete, names = %s" % result)
                        ftpDevice.updateStateOnServer(key="nameList", value=json.dumps(result))
                    except all_errors as e:
                        self.logger.error("ftp.nlst error: %s" % e)

                else:
                    self.logger.error(u"Unknown Plugin Action ID: " + pluginTypeId)

                try:
                    ftp.quit()
                except all_errors as e:
                    ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
                    ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                    self.logger.error("ftp.quit error: %s" % e)

                if completeHandler is not None:
                    completeHandler.returnResult(result)

            except Empty:
                pass
            except Exception, exc:
                if completeHandler is not None:
                    completeHandler.returnException(exc)


    ########################################
    # Menu Methods
    ########################################

    def clearAllQueues(self):
        self.clearQueue = True
        self.logger.debug(u"Setting clearQueue Flag")
