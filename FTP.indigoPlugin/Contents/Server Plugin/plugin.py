#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import sys
import time
import logging
import json
import os

from queue import Queue, Empty
from threading import Thread, Event
from ftplib import FTP, FTP_TLS, all_errors

kCurDevVersCount = 0  # current version of plugin devices


################################################################################
class Plugin(indigo.PluginBase):

    ########################################
    # Main Plugin methods
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pfmt)
        self.logLevel = int(self.pluginPrefs.get(f"logLevel", logging.INFO))
        self.indigo_log_handler.setLevel(self.logLevel)
        self.logger.debug(f"logLevel = {self.logLevel}")

        self.ftpQ = Queue()
        self.queueStop = Event()
        self.queueStop.clear()
        self.queueThread = Thread(target=self.queueHandler)
        self.queueThread.start()
        self.clearQueue = False

    def startup(self):
        self.logger.info("Starting up FTP")

    def shutdown(self):
        self.logger.info("Shutting down FTP")
        self.queueStop.set()  # stop the queue thread

    def deviceStartComm(self, device):
        instanceVers = int(device.pluginProps.get('devVersCount', 0))
        if instanceVers >= kCurDevVersCount:
            self.logger.debug(f"{device.name} : Device Version is up to date")
        elif instanceVers < kCurDevVersCount:
            newProps = device.pluginProps

            newProps["devVersCount"] = kCurDevVersCount
            device.replacePluginPropsOnServer(newProps)
            device.stateListOrDisplayStateIdChanged()
            self.logger.debug(f"deviceStartComm: Updated {device.name} to version {kCurDevVersCount}")

        else:
            self.logger.error(f"Unknown device version: {instanceVers} for device {device.name}")

        device.updateStateOnServer(key="serverStatus", value="Success")
        device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

    ########################################
    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            self.logLevel = int(valuesDict.get("logLevel", logging.INFO))
            self.indigo_log_handler.setLevel(self.logLevel)
            self.logger.debug(f"logLevel = {self.logLevel}")

    ########################################
    # Plugin Actions object callbacks (pluginAction is an Indigo plugin action instance)
    ######################

    def connect(self, ftpDevice):

        props = ftpDevice.pluginProps
        port = props["port"]

        self.logger.debug(f"ftp_tls mode {props['passive']}")
        if props['tls']:
            ftp = FTP_TLS()
        else:
            ftp = FTP()

        self.logger.debug(f"connect setting passive mode {props['passive']}")
        ftp.set_pasv(props['passive'])
        self.logger.debug(f"connect connecting to server: {props['address']} ({port})")

        try:
            ftp.connect(props['address'], int(port), 5)
        except all_errors as e:
            ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
            ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
            self.logger.error(f"ftp.connect error: {e}")
            return None

        try:
            ftp.login(user=props['serverLogin'], passwd=props['serverPassword'])
        except all_errors as e:
            ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
            ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
            self.logger.error(f"ftp.login error: {e}")
            return None

        if props['tls']:
            try:
                ftp.prot_p()
            except all_errors as e:
                ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
                ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                self.logger.error(f"ftp.prot_p error: {e}")
                return None

        try:
            ftp.cwd('/' + props['directory'] + '/')
        except all_errors as e:
            ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
            ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
            self.logger.error(f"ftp.cwd error: {e}")
            return None

        ftpDevice.updateStateOnServer(key="serverStatus", value="Success")
        ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
        return ftp

    def executeAction(self, pluginAction, ftpDevice, callerWaitingForResult):
        self.logger.debug(f"executeAction, queueing Action = {pluginAction.pluginTypeId}")

        completeHandler = None
        if callerWaitingForResult:
            completeHandler = indigo.acquireCallbackCompleteHandler()

        self.ftpQ.put((pluginAction, ftpDevice, completeHandler))

    def queueHandler(self):

        while True:
            if self.queueStop.isSet():
                self.logger.debug("queueHandler queueStop isSet")
                return

            time.sleep(1.0)

            if self.clearQueue:
                self.logger.debug("Clearing FTP Queue")
                self.ftpQ = Queue()
                self.clearQueue = False

            try:
                (pluginAction, ftpDevice, completeHandler) = self.ftpQ.get(False)
                self.logger.debug(f"queueHandler action = {pluginAction.pluginTypeId}, {self.ftpQ.qsize():d} in queue")

                result = None

                ftp = self.connect(ftpDevice)
                if not ftp:
                    self.logger.debug("executeAction, connection failure, re-queueing operation")
                    self.ftpQ.put((pluginAction, ftpDevice, completeHandler))
                    continue

                if pluginAction.pluginTypeId == "uploadFile":

                    localFile = indigo.activePlugin.substitute(pluginAction.props["localFile"])
                    remoteFile = indigo.activePlugin.substitute(pluginAction.props["remoteFile"])
                    self.logger.debug(f"uploadFileAction sending file: {localFile}")
                    try:
                        ftp.storbinary('STOR ' + remoteFile, open(localFile, 'rb'))
                        self.logger.debug("ftp.storbinary complete")
                    except all_errors as err:
                        ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
                        ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                        self.logger.error(f"ftp.storbinary error: {err}")

                elif pluginAction.pluginTypeId == "downloadFile":

                    remoteFile = indigo.activePlugin.substitute(pluginAction.props["remoteFile"])
                    localFile = indigo.activePlugin.substitute(pluginAction.props["localFile"])
                    self.logger.debug(f"downloadFileAction downloading file: {remoteFile} to {localFile}")
                    if localFile[0] != "/":      # if not absolute path, put it in Downloads
                        localFile = os.path.expanduser(f"~/Downloads/{localFile}")
                    try:
                        lfile = open(localFile, 'wb')
                    except Exception as err:
                        self.logger.error(f"Error opening local file: {err}")
                        return

                    try:
                        ftp.retrbinary('RETR ' + remoteFile, lfile.write, 1024)
                        self.logger.debug(u"ftp.retrbinary complete")
                    except all_errors as err:
                        ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
                        ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                        self.logger.error(f"ftp.retrbinary error: {err}")

                    lfile.close()

                elif pluginAction.pluginTypeId == "renameFile":
                    fromFile = indigo.activePlugin.substitute(pluginAction.props["fromFile"])
                    toFile = indigo.activePlugin.substitute(pluginAction.props["toFile"])
                    self.logger.debug(f"renameFileAction from: {fromFile} to: {toFile}")
                    try:
                        ftp.rename(fromFile, toFile)
                        self.logger.debug(u"ftp.rename complete")
                    except all_errors as err:
                        self.logger.error(f"ftp.rename error: {err}")

                elif pluginAction.pluginTypeId == u"deleteFile":

                    remoteFile = indigo.activePlugin.substitute(pluginAction.props["remoteFile"])
                    self.logger.debug(u"deleteFileAction deleting file: " + remoteFile)
                    try:
                        ftp.delete(remoteFile)
                        self.logger.debug(u"ftp.delete complete")
                    except all_errors as err:
                        self.logger.error(f"ftp.delete error: {err}")

                elif pluginAction.pluginTypeId == u"nameList":

                    try:
                        result = ftp.nlst()
                        self.logger.debug(f"ftp.nlst complete, names = {result}")
                        ftpDevice.updateStateOnServer(key="nameList", value=json.dumps(result))
                    except all_errors as err:
                        self.logger.error(f"ftp.nlst error: {err}")

                else:
                    self.logger.error(f"Unknown Plugin Action ID: {pluginTypeId}")

                try:
                    ftp.quit()
                except all_errors as e:
                    ftpDevice.updateStateOnServer(key="serverStatus", value="Failure")
                    ftpDevice.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                    self.logger.error(f"ftp.quit error: {e}")

                if completeHandler is not None:
                    completeHandler.returnResult(result)

            except Empty:
                pass

    ########################################
    # Menu Methods
    ########################################

    def clearAllQueues(self):
        self.clearQueue = True
        self.logger.debug("Setting clearQueue Flag")
