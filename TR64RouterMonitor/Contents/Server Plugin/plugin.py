import re
import indigo
import socket
import traceback
import time

from simpletr64 import Discover, DeviceTR64
from simpletr64.actions.wan import Wan
from simpletr64.actions.wifi import Wifi
from simpletr64.actions.lan import Lan
from simpletr64.actions.system import System
from simpletr64.actions.fritz import Fritz

try:
    # noinspection PyCompatibility, PyUnresolvedReferences
    import Queue as queue
except ImportError:
    # noinspection PyCompatibility, PyUnresolvedReferences
    import queue

try:
    # noinspection PyCompatibility, PyUnresolvedReferences
    from urlparse import urlparse
except ImportError:
    # noinspection PyCompatibility,PyUnresolvedReferences
    from urllib.parse import urlparse


class Plugin(indigo.PluginBase):
    """Plugin to monitor your router device which needs to support TR64 protocol which is enabled.
    """
    _CleanupTimeForSkipStateUpdates = 60 * 10  # 10 minutes

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.debug = pluginPrefs.get("debug", False)

        self.discoveredRouterList = {}
        self.deviceDefinition = {}
        self.deviceTR64 = {}
        self.skipStateUpdate = []
        self.nextCleanSkipStateUpdate = 0
        self.cleanSkipStateUpdate()

        self.commandQueue = queue.Queue()

    def runConcurrentThread(self):
        """Run the background task
        """
        try:
            # set the first time when we will set new states
            nextWakeupCall = time.time() + int(self.pluginPrefs.get("updateFrequency", 300))

            # Run forever
            while True:
                if time.time() >= self.nextCleanSkipStateUpdate:
                    # it is time to cleanup failed states and to retry
                    self.cleanSkipStateUpdate()

                # empty the queue always as soon as possible
                self.runActions()

                # check if it is time to request and set new states
                if time.time() >= nextWakeupCall:
                    # set new states
                    self.updateStates()
                    # when it is time next time
                    nextWakeupCall = time.time() + int(self.pluginPrefs.get("updateFrequency", 300))

                # wait just for a short time, it will be quite if no action arrives
                self.sleep(0.5)  # in seconds
        except self.StopThread:
            # do any cleanup here
            pass
        except:
            self.exceptionLog()

    def networkRouterGenerator(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Callback to generate the list of routers for a device in the config of a device

        :param str filter:
        :param dict valuesDict: The valuesDict parameter will contain the valuesDict for the object being edited -
            if it's a device config UI then it'll be the valuesDict from that device. Note: if it's a new object that
            hasn't been saved yet, valuesDict may be None or empty so test accordingly.
        :param str typeId: The typeId parameter will contain the type - for instance, if it's an event, it will be
            the event type id.
        :param int targetId: The targetId is the ID of the object being edited. It will be 0 if it's a new object
            that hasn't been saved yet.
        :return: the list of router devices (id, display)
        :rtype: list[list[str]]
        """

        self.debugLog("Start discovery of devices")

        # add some more services to search for, just making sure every device answers
        services = ["ssdp:all", "urn:schemas-any-com:service:Any:1", "urn:dslforum-org:device:InternetGatewayDevice:1",
                    "urn:dslforum-org:device:LANDevice:1", "urn:dslforum-org:service:Layer3Forwarding:1",
                    "urn:schemas-upnp-org:device:basic:1", "urn:schemas-upnp-org:device:InternetGatewayDevice:1"]

        # Start a network UPnP discovery run
        results = Discover.discover(retries=2, timeout=0.3, service=services)

        self.debugLog("Discovery finished")

        candidates = {}
        routerFound = []

        # clean the list
        self.discoveredRouterList = {}

        for result in results:
            # filter the results, make sure there is only one result per host, take the best one
            if result.locationHost not in candidates.keys():
                candidates[result.locationHost] = result
            else:
                if Discover.rateServiceTypeInResult(result) > candidates[result.locationHost]:
                    candidates[result.locationHost] = result

        # go through all candidates
        for host in candidates.keys():
            result = candidates[host]

            try:
                hostname = socket.gethostbyaddr(result.locationHost)[0]
            except:
                hostname = result.locationHost

            # create a new plain device
            deviceTR64 = DeviceTR64.createFromURL(result.location)
            self.setupProxies(deviceTR64)

            # check if the device supports anything we know, so start with loading the device definitions
            try:
                deviceTR64.loadDeviceDefinitions(result.location, timeout=self.pluginPrefs.get("timeout", 0.5))
            except Exception as e:
                self.errorLog("For discovered host " + hostname +
                              " the device definitions could not be loaded: " + str(e))
                continue  # skip this host

            if len(deviceTR64.deviceServiceDefinitions.keys()) == 0:
                self.debugLog("For discovered host " + hostname + " there is no action/control URL defined, skip it.")
                continue  # skip this host

            isTR64 = False
            for serviceType in deviceTR64.deviceServiceDefinitions.keys():
                if serviceType.startswith("urn:dslforum-org:"):
                    isTR64 = True

            if not isTR64:
                self.debugLog("For discovered host " + hostname + " there is no support for TR64, skip it.")
                continue

            # return found host
            routerFound.append((hostname, hostname))
            # save the result for later
            self.discoveredRouterList[hostname] = result

        return routerFound

    def validatePrefsConfigUi(self, valuesDict):
        """Callback to validate the preference values for the plugin config UI

        :param dict valuesDict: valuesDict - the dictionary of values currently specified in the dialog
        :return: if ok
        :rtype: bool
        """
        errorDict = indigo.Dict()

        self.debug = valuesDict.get("debug", False)

        try:
            # check if it is an int
            updateFrequency = int(valuesDict["updateFrequency"])
        except:
            errorDict["updateFrequency"] = "Update frequency has to be a positive number."
            indigo.server.log("Update frequency has to be a positive number.")
        else:
            if updateFrequency <= 0:
                errorDict["updateFrequency"] = "Update frequency has to be a positive number."
                self.errorLog("Update frequency has to be a positive number.")

        try:
            # check if it is a float
            timeout = float(valuesDict["timeout"])
        except:
            errorDict["timeout"] = "Timeout has to be a positive number (float)."
            indigo.server.log("Timeout has to be a positive number (float).")
        else:
            if timeout <= 0:
                errorDict["timeout"] = "Timeout has to be a positive number (float)."
                self.errorLog("Timeout has to be a positive number (float).")

        if len(errorDict):
            return False, valuesDict, errorDict

        for deviceID in self.deviceTR64.keys():
            # go through all existing objects and reconfigure them, just in case something changed
            self.setupProxies(self.deviceTR64[deviceID], [valuesDict["httpProxy"], valuesDict["httpsProxy"]])

        return True, valuesDict

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        """Callback to validate the preference values for the device config UI

        :param dict valuesDict: valuesDict - the dictionary of values currently specified in the dialog
        :param str typeId: typeId - device type specified in the type attribute
        :param int devId: deviceId - the unique device ID for the device being edited (or 0 of it's a new device)
        :return: if it was ok
        """
        errorDict = indigo.Dict()
        deviceTR64 = None

        addressLabel = ""

        if not valuesDict["manualRouterEntry"]:
            # check if a router have been selected in the pop up menu
            if valuesDict["networkRouter"] == "":
                errorDict['showAlertText'] = errorDict["networkRouter"] = "Select a router or enter one manually."
                self.errorLog("Select a router or enter one manually.")
            else:
                # a router have been selected, check if we can load the device definitions
                url = self.discoveredRouterList[valuesDict["networkRouter"]].location
                # create a device based on its type
                deviceTR64 = self.createDeviceTR64(typeId, url, valuesDict.get("interfaceType"))
                # setup the device with proxies and load the device definitions
                self.setupProxies(deviceTR64)
                try:
                    deviceTR64.loadDeviceDefinitions(url, timeout=self.pluginPrefs.get("timeout", 1))
                except Exception as e:
                    errorDict['showAlertText'] = errorDict["networkRouter"] = \
                        "Can not load URL '" + url + "' for router '" + valuesDict["networkRouter"] + "': " + str(e)
                    self.errorLog("Can not load URL '" + url + "' for router '" + valuesDict["networkRouter"] +
                                  "': " + str(e))
                else:
                    # everything worked, set the address field in the main UI
                    addressLabel = valuesDict["networkRouter"]
        else:
            # check if the manual entered URL is correct

            if valuesDict["routerURL"].strip == "":
                # nothing has been given
                errorDict["routerURL"] = "Router URL must not be empty."
                self.errorLog("Router URL must not be empty.")
            else:
                # create a device based on its type
                deviceTR64 = self.createDeviceTR64(typeId, valuesDict["routerURL"], valuesDict.get("interfaceType"))
                # setup the device with proxies and load the device definitions
                self.setupProxies(deviceTR64)
                try:
                    deviceTR64.loadDeviceDefinitions(valuesDict["routerURL"],
                                                     timeout=self.pluginPrefs.get("timeout", 1))
                except Exception as e:
                    errorDict['showAlertText'] = errorDict["routerURL"] = \
                        "Can not load URL '" + valuesDict["routerURL"] + "': " + str(e)
                    self.errorLog("Can not load URL '" + valuesDict["routerURL"] + "': " + str(e))
                else:
                    # everything worked, set the address field in the main UI
                    addressLabel = urlparse(errorDict["routerURL"]).hostname

        if len(errorDict) == 0:
            # no error occured until here

            # check if the device supports any action
            if len(deviceTR64.deviceServiceDefinitions.keys()) == 0:
                # device has no actions defined
                errorDict['showAlertText'] = "The selected router does not support any actions, sorry."
                indigo.server.log("The selected router does not support any actions, sorry.")
            else:
                isTR64 = False
                for serviceType in deviceTR64.deviceServiceDefinitions.keys():
                    if serviceType.startswith("urn:dslforum-org:"):
                        isTR64 = True

                if not isTR64:
                    errorDict['showAlertText'] = "The selected router does not support any TR64 actions, sorry."
                    self.errorLog("The selected router does not support any TR64 actions, sorry.")

            if typeId != "routerSystem" and typeId != "fritzSystem":
                # for this type of device an interface id is needed
                try:
                    interfaceID = int(valuesDict["interfaceID"])
                except:
                    errorDict["interfaceID"] = "ID has to be a positive number."
                    indigo.server.log("ID has to be a positive number for %s." % typeId)
                else:
                    if interfaceID < 0:
                        errorDict["interfaceID"] = "ID has to be a positive number."
                        self.errorLog("ID has to be a positive number for %s." % typeId)

                if typeId == "lanDeviceInformation" or typeId == "wifiDeviceInformation":
                    # for this device an additional mac address is needed, check the format
                    if re.match("^[a-zA-Z0-9]{2}:[a-zA-Z0-9]{2}:[a-zA-Z0-9]{2}:[a-zA-Z0-9]{2}:[a-zA-Z0-9]{2}:"
                                "[a-zA-Z0-9]{2}$", valuesDict["macAddress"]) is None:
                        errorDict["macAddress"] = "Mac Address needs to be in the format XX:XX:XX:XX:XX:XX"
                        self.errorLog("Mac Address needs to be in the format XX:XX:XX:XX:XX:XX")

        if deviceTR64 and len(errorDict) == 0:
            # no error occured
            # safe the device definition URL, we can not safe it here at the server
            self.deviceDefinition[devId] = deviceTR64.deviceInformations["rootURL"]
            self.deviceTR64[devId] = deviceTR64
        else:
            # an error occured, make sure there is no device definition saved
            self.deviceDefinition[devId] = None
            self.deviceTR64[devId] = None

        if len(errorDict):
            return False, valuesDict, errorDict

        # set the address in Indigo UI
        valuesDict['address'] = addressLabel

        return True, valuesDict

    def deviceStartComm(self, dev):
        """Start a device after a configuration

        :param dev: the device to start
        """
        if dev.id in self.deviceTR64.keys() and self.deviceTR64[dev.id]:
            # we are initalized already, we are just after a config change
            # make sure we have all properties saved to the server
            if dev.id in self.deviceDefinition.keys():
                newProps = dev.pluginProps
                newProps["deviceDefinition"] = self.deviceDefinition[dev.id]
                dev.replacePluginPropsOnServer(newProps)
            else:
                self.deviceTR64[dev.id] = None
                dev.setErrorStateOnServer("Something went wrong with the device init, please go to device"
                                          "config again.ConfigSave")
                self.errorLog("Something went wrong with the device init for '" + dev.name +
                              "', please go to device config again.")

        elif "deviceDefinition" in dev.pluginProps.keys():
            # create the device, Device has been restarted
            self.deviceDefinition[dev.id] = dev.pluginProps["deviceDefinition"]
            self.deviceTR64[dev.id] = self.createDeviceTR64(dev.deviceTypeId, self.deviceDefinition[dev.id],
                                                            dev.pluginProps.get("interfaceType"))
            self.setupProxies(self.deviceTR64[dev.id])
            try:
                self.deviceTR64[dev.id].loadDeviceDefinitions(self.deviceDefinition[dev.id],
                                                              timeout=self.pluginPrefs.get("timeout", 1))
            except Exception as e:
                dev.setErrorStateOnServer("Device not initialized, can not load router URL '" +
                                          self.deviceDefinition[dev.id] + "': " + str(e))
                self.errorLog("Device not initialized, can not load router URL '" +
                              self.deviceDefinition[dev.id] + "': " + str(e))
                self.deviceTR64[dev.id] = None
        else:
            dev.setErrorStateOnServer("Something went wrong with the device init, please go to device config again.")
            self.errorLog("Something went wrong with the device init for '" + dev.name +
                          "', please go to device config again.")

        if self.deviceTR64[dev.id]:
            # the device has been created, we are ready

            dev.setErrorStateOnServer(None)  # remove error state in Indigo if any

            # prepare device
            self.deviceTR64[dev.id].username = dev.pluginProps["username"]
            self.deviceTR64[dev.id].password = dev.pluginProps["password"]
            # load all actions
            self.deviceTR64[dev.id].loadSCPD(timeout=self.pluginPrefs.get("timeout", 1), ignoreFailures=True)

            # get the first round of state values
            try:
                self.updateStates()
            except Exception as e:
                tb = traceback.format_exc()
                self.errorLog("Internal update issue: " + str(e) + " -- " + tb)

        return indigo.PluginBase.deviceStartComm(self, dev)

    def cleanSkipStateUpdate(self):
        """For any failed state call we clean the state so that a retry can be made
        """
        self.skipStateUpdate = []
        # remember when the next clean round will happen
        self.nextCleanSkipStateUpdate = time.time() + self._CleanupTimeForSkipStateUpdates

    def setupProxies(self, deviceTR64, values=None):
        """Set proxy definitions for a given device

        :param DeviceTR64 deviceTR64: the device to set the proxies for
        :param list values: if set dont use the server preference, instead the two strings in this
        """
        if values:
            httpProxy = values[0]
            httpsProxy = values[1]
        else:
            httpProxy = self.pluginPrefs.get("httpProxy")
            httpsProxy = self.pluginPrefs.get("httpsProxy")

        if httpProxy:
            deviceTR64.httpProxy = httpProxy
        else:
            deviceTR64.httpProxy = None

        if httpsProxy:
            deviceTR64.httpsProxy = httpsProxy
        else:
            deviceTR64.httpsProxy = None

    @staticmethod
    def createDeviceTR64(deviceType, url, subType=None):
        """Creates the right device depending

        :param str deviceType: the deviceType to create
        :param str url: the URL to the device definitions
        :param str subType: if type is lanDeviceInformation then we need a sub type for LAN or WIFI
        :return: the new object
        """
        if deviceType == "routerSystem":
            return System.createFromURL(url)
        elif deviceType == "routerLan":
            return Lan.createFromURL(url)
        elif deviceType == "routerWan":
            return Wan.createFromURL(url)
        elif deviceType == "routerWifi":
            return Wifi.createFromURL(url)
        elif deviceType == "lanDeviceInformation":
            return Lan.createFromURL(url)
        elif deviceType == "wifiDeviceInformation":
            return Wifi.createFromURL(url)
        elif deviceType == "fritzSystem":
            return Fritz.createFromURL(url)
        else:
            raise ValueError("Unknown deviceType: " + str(deviceType))

    def updateStates(self):
        """This updates all states for all active devices
        """
        # go through all devices
        for device in indigo.devices.iter(self.pluginId):
            if device.configured and device.enabled:
                # check if device was already started, we also call this during startup, better check
                if device.id in self.deviceTR64 and self.deviceTR64[device.id]:
                    # device is initialized

                    # we use a skipLabel to remember for which device which state call failed, so that we do not
                    # try again soon, this is the prefix
                    skipLabel = self.deviceTR64[device.id].deviceInformations["rootURL"] + "-"

                    if device.deviceTypeId == "routerSystem":

                        fails = 0

                        skipLabel += str(device.id) + "::RS::getSystemInfo"
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                systemInfo = self.deviceTR64[device.id].getSystemInfo(
                                        timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getSystemInfo failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "softwareVersion", systemInfo.softwareVersion)
                                self.updateDeviceState(device, "uptime", systemInfo.uptime)
                        else:
                            fails += 1

                        skipLabel += str(device.id) + "::RS::softwareUpdateAvailable"
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                updateAvailable = self.deviceTR64[device.id].softwareUpdateAvailable(
                                        timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action softwareUpdateAvailable failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "softwareUpdateAvailable", updateAvailable)
                        else:
                            fails += 1

                        skipLabel += str(device.id) + "::RS::getTimeInfo"
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                timeInfo = self.deviceTR64[device.id].getTimeInfo(
                                        timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getTimeInfo failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "currentTime", timeInfo.currentLocalTime)
                                self.updateDeviceState(device, "currentTimeZone", timeInfo.localTimeZoneName)
                        else:
                            fails += 1

                        if fails == 0:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                        elif fails == 2:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                        else:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                    elif device.deviceTypeId == "routerLan":

                        fails = 0

                        interfaceID = device.pluginProps["interfaceID"]

                        skipLabel += str(device.id) + "::RL::getAmountOfHostsConnected" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                hostAmount = self.deviceTR64[device.id].getAmountOfHostsConnected(
                                        lanInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getAmountOfHostsConnected failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "hostsConnected", hostAmount)
                        else:
                            fails += 1

                        skipLabel += str(device.id) + "::RL::getEthernetStatistic" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                ethernetStatistic = self.deviceTR64[device.id].getEthernetStatistic(
                                        lanInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getEthernetStatistic failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "lanBytesSent", str(ethernetStatistic.bytesSent))
                                self.updateDeviceState(device, "lanBytesReceived", str(ethernetStatistic.bytesReceived))
                                self.updateDeviceState(device, "lanPacketsSent", str(ethernetStatistic.packetsSent))
                                self.updateDeviceState(device, "lanPacketsReceived",
                                                       ethernetStatistic.packetsReceived)
                        else:
                            fails += 1

                        skipLabel += str(device.id) + "::RL::getEthernetInfo" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                ethernetInfo = self.deviceTR64[device.id].getEthernetInfo(
                                        lanInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getEthernetInfo failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "lanEnabled", ethernetInfo.enabled)
                                self.updateDeviceState(device, "lanStatus", ethernetInfo.status)
                                self.updateDeviceState(device, "lanMaxBitrate", ethernetInfo.maxBitRate)
                                self.updateDeviceState(device, "lanDuplex", ethernetInfo.duplexMode)
                        else:
                            fails += 1

                        if fails == 0:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                        elif fails == 3:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                        else:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                    elif device.deviceTypeId == "routerWan":

                        fails = 0

                        interfaceID = device.pluginProps["interfaceID"]

                        skipLabel += str(device.id) + "::RWAN::getByteStatistic" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                statistic = self.deviceTR64[device.id].getByteStatistic(
                                        wanInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getByteStatistic failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "wanBytesSent", str(statistic[0]))
                                self.updateDeviceState(device, "wanBytesReceived", str(statistic[1]))
                        else:
                            fails += 1

                        skipLabel += str(device.id) + "::RWAN::getPacketStatistic" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                statistic = self.deviceTR64[device.id].getPacketStatistic(
                                        wanInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getPacketStatistic failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "wanPacketsSent", str(statistic[0]))
                                self.updateDeviceState(device, "wanPacketsReceived", str(statistic[1]))
                        else:
                            fails += 1

                        skipLabel += str(device.id) + "::RWAN::getAmountOfHostsConnected" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                linkInfo = self.deviceTR64[device.id].getLinkInfo(
                                        wanInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getLinkInfo failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "wanEnabled", linkInfo.enabled)
                                self.updateDeviceState(device, "wanStatus", linkInfo.status)
                                self.updateDeviceState(device, "wanUpstreamRate", linkInfo.upstreamCurrentRate)
                                self.updateDeviceState(device, "wanDownstreamRate", linkInfo.downStreamCurrentRate)
                                self.updateDeviceState(device, "wanUpstreamMaxRate", linkInfo.upstreamMaxRate)
                                self.updateDeviceState(device, "wanDownstreamMaxRate", linkInfo.downstreamMaxRate)
                        else:
                            fails += 1

                        skipLabel += str(device.id) + "::RWAN::getConnectionInfo" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                connectInfo = self.deviceTR64[device.id].getConnectionInfo(
                                        wanInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getConnectionInfo failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "wanUptime", connectInfo.uptime)
                                self.updateDeviceState(device, "wanLastError", connectInfo.lastConnectionError)
                                self.updateDeviceState(device, "wanExternalIP", connectInfo.externalIPaddress)
                                self.updateDeviceState(device, "wanExternalDNS", connectInfo.dnsServers)
                        else:
                            fails += 1

                        skipLabel += str(device.id) + "::RWAN::getLinkProperties" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                linkProperties = self.deviceTR64[device.id].getLinkProperties(
                                        wanInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getLinkProperties failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "wanLinkStatus", linkProperties.linkStatus)
                        else:
                            fails += 1

                        if fails == 0:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                        elif fails == 5:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                        else:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                    elif device.deviceTypeId == "routerWifi":

                        fails = 0

                        interfaceID = device.pluginProps["interfaceID"]

                        skipLabel += str(device.id) + "::RWIFI::getStatistic" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                statistic = self.deviceTR64[device.id].getStatistic(
                                        wifiInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getStatistic failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "wifiBytesSent", str(statistic[0]))
                                self.updateDeviceState(device, "wifiBytesReceived", str(statistic[1]))
                        else:
                            fails += 1

                        skipLabel += str(device.id) + "::RWIFI::getPacketStatistic" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                statistic = self.deviceTR64[device.id].getPacketStatistic(
                                        wifiInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getPacketStatistic failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "wifiPacketsSent", str(statistic[0]))
                                self.updateDeviceState(device, "wifiPacketsReceived", str(statistic[1]))
                        else:
                            fails += 1

                        skipLabel += str(device.id) + "::RWIFI::getWifiInfo" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                wifiInfo = self.deviceTR64[device.id].getWifiInfo(
                                        wifiInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getWifiInfo failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "wifiEnabled", wifiInfo.enabled)
                                self.updateDeviceState(device, "wifiStatus", wifiInfo.status)
                                self.updateDeviceState(device, "wifiChannel", wifiInfo.channel)
                                self.updateDeviceState(device, "wifiSSID", wifiInfo.ssid)
                        else:
                            fails += 1

                        skipLabel += str(device.id) + "::RWIFI::getTotalAssociations" + interfaceID
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                totalAssociations = self.deviceTR64[device.id].getTotalAssociations(
                                        wifiInterfaceId=interfaceID, timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getTotalAssociations failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "wifiAmountAssociatedDevices", totalAssociations)
                        else:
                            fails += 1

                        if fails == 0:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                        elif fails == 4:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                        else:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                    elif device.deviceTypeId == "lanDeviceInformation":

                        interfaceID = device.pluginProps["interfaceID"]
                        macAddress = device.pluginProps["macAddress"]

                        try:
                            hostDetails = self.deviceTR64[device.id].getHostDetailsByMACAddress(macAddress,
                                                                                                lanInterfaceId=interfaceID,
                                                                                                timeout=self.pluginPrefs.get(
                                                                                                    "timeout", 0.5))
                        except Exception as e:
                            if not device.pluginProps["ignoreErrors"]:
                                self.errorLog("Action getHostDetailsByMACAddress failed for '%s' on %s: %s" %
                                              (device.name, self.deviceTR64[device.id].host, str(e)))

                            self.updateDeviceState(device, "ipAddress", "")
                            self.updateDeviceState(device, "hostname", "")
                            self.updateDeviceState(device, "leasetime", 0)
                            self.updateDeviceState(device, "active", False)
                        else:
                            self.updateDeviceState(device, "ipAddress", hostDetails.ipaddress)
                            self.updateDeviceState(device, "hostname", hostDetails.hostname)
                            self.updateDeviceState(device, "leasetime", hostDetails.leasetime)
                            self.updateDeviceState(device, "active", hostDetails.active)
                    elif device.deviceTypeId == "wifiDeviceInformation":

                        interfaceID = device.pluginProps["interfaceID"]
                        macAddress = device.pluginProps["macAddress"]

                        try:
                            hostDetails = self.deviceTR64[device.id].getSpecificAssociatedDeviceInfo(macAddress,
                                                                                                     wifiInterfaceId=interfaceID,
                                                                                                     timeout=self.pluginPrefs.get(
                                                                                                         "timeout",
                                                                                                         0.5))
                        except Exception as e:
                            if not device.pluginProps["ignoreErrors"]:
                                self.errorLog("Action getSpecificAssociatedDeviceInfo failed for '%s' on %s: %s" %
                                              (device.name, self.deviceTR64[device.id].host, str(e)))

                            self.updateDeviceState(device, "ipAddress", "")
                            self.updateDeviceState(device, "authenticated", False)
                        else:
                            self.updateDeviceState(device, "ipAddress", hostDetails.ipAddress)
                            self.updateDeviceState(device, "authenticated", hostDetails.authenticated)

                    elif device.deviceTypeId == "fritzSystem":

                        fails = 0

                        skipLabel += str(device.id) + "::RS::getCallList"
                        if skipLabel not in self.skipStateUpdate:
                            try:
                                callList = self.deviceTR64[device.id].getCallList(
                                        timeout=self.pluginPrefs.get("timeout", 0.5))
                            except Exception as e:
                                if not device.pluginProps["ignoreErrors"]:
                                    self.errorLog("Action getCallList failed for '%s' on %s: %s" %
                                                  (device.name, self.deviceTR64[device.id].host, str(e)))
                                self.skipStateUpdate.append(skipLabel)
                                fails += 1
                            else:
                                self.updateDeviceState(device, "callListEntryAmount", len(callList))

                                if len(callList) > 0:
                                    self.updateDeviceState(device, "lastCallCalledNumber",
                                                           callList[0].get("CalledNumber", ""))
                                    self.updateDeviceState(device, "lastCallCaller", callList[0].get("Caller", ""))
                                    self.updateDeviceState(device, "lastCallDate", callList[0].get("Date", ""))
                                    self.updateDeviceState(device, "lastCallDevice", callList[0].get("Device", ""))
                                    self.updateDeviceState(device, "lastCallType", callList[0].get("Type", ""))
                                    self.updateDeviceState(device, "lastCallDuration", callList[0].get("Duration", ""))
                                    self.updateDeviceState(device, "lastCallNumberType",
                                                           callList[0].get("Numbertype", "0"))
                        else:
                            fails += 1

                        if fails == 0:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                        else:
                            device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)

                    else:
                        self.errorLog("Unknown device %s" % device.deviceTypeId)

                    # sleep to make sure we dont use too much cpu and give the chance to interrupt
                    self.sleep(0.1)
                else:
                    # device is not initialized, do we retry?
                    pass

    def updateDeviceState(self, device, state, newValue):
        """Update a device state based on its time

        :param device: Indigo device to update
        :param state: the state name
        :param newValue: the new value
        """
        # thanks to Hue Lights author...
        # Change the device state on the server
        #   if it's different than the current state.
        if newValue != device.states[state]:
            try:
                self.debugLog(
                        "updateDeviceState: Updating device " + device.name + " state: " + str(state) + " = " + str(
                                newValue))
            except Exception as e:
                self.debugLog(
                        "updateDeviceState: Updating device " + device.name + " state: (Unable to display state due to "
                                                                              "error: " + str(
                                e) + ")")
            # If this is a floating point number, specify the maximum
            #   number of digits to make visible in the state.  Everything
            #   in this plugin only needs 1 decimal place of precission.
            #   If this isn't a floating point value, don't specify a number
            #   of decimal places to display.
            if newValue.__class__ == float:
                device.updateStateOnServer(key=state, value=newValue, decimalPlaces=4)
            else:
                device.updateStateOnServer(key=state, value=newValue)

    def validateActionConfigUi(self, valuesDict, typeId, devId):
        """Callback to validate if an action has been configured correctly when Action config UI have been opened.

        Important is that a user might not call the action config UI, we need to check carfully later if parameters have
        been given at all.

        :param valuesDict: all values
        :param typeId: the type of the device
        :param devId: the device id
        :return: if ok
        """
        errorMsgDict = indigo.Dict()

        if typeId == "setSSID":
            # check if the network name is ok, make some assumptions on how a network name should look like
            if re.match("^[a-zA-Z0-9]+[\w\-\.,\$!\"%\(\)=\?]*$", valuesDict["value"]) is None:
                errorMsgDict["value"] = "Please enter a valid SSID/name."
        elif typeId == "setChannel" or typeId == "optimizeForIPTV" or typeId == "dontOptimizeForIPTV":
            # the actions needs a parameter which is an integer and positive
            try:
                channel = int(valuesDict["value"])
            except:
                errorMsgDict["value"] = "Needs to be a positive number."
            else:
                if channel <= 0:
                    errorMsgDict["value"] = "Needs to be a positive number."

        if len(errorMsgDict):
            return False, valuesDict, errorMsgDict

        return True, valuesDict

    def runActions(self):
        """Go through the action queue and execute any pending action.
        """
        while not self.commandQueue.empty():
            # there is a command to proceed

            # command has two or three values: command name, device ID and an optional parameter

            command = self.commandQueue.get()

            if len(command) == 2:
                self.debugLog("Action %s received for %s" % (command[0], indigo.devices[command[1]].name))
            elif len(command) == 3:
                self.debugLog("Action %s with value '%s' received for %s" %
                              (command[0], command[2], indigo.devices[command[1]].name))
            else:
                self.errorLog("Action received with invalid amount of arguments: " + str(len(command)))
                self.commandQueue.task_done()
                continue

            # extract device
            device = indigo.devices[command[1]]

            # execute the action

            if command[0] == "resetDevice":
                try:
                    self.deviceTR64[device.id].reboot(timeout=self.pluginPrefs.get("timeout", 0.5))
                except Exception as e:
                    self.errorLog("Action %s failed for '%s' on %s: %s" %
                                  (command[0], device.name, self.deviceTR64[device.id].host, str(e)))
            elif command[0] == "enableInterface":
                try:
                    self.deviceTR64[device.id].setEnable(True, device.pluginProps["interfaceID"],
                                                         timeout=self.pluginPrefs.get("timeout", 0.5))
                except Exception as e:
                    self.errorLog("Action %s failed for '%s:%s' on %s: %s" %
                                  (command[0], device.name, device.pluginProps["interfaceID"],
                                   self.deviceTR64[device.id].host, str(e)))
            elif command[0] == "disableInterface":
                try:
                    self.deviceTR64[device.id].setEnable(False, device.pluginProps["interfaceID"],
                                                         timeout=self.pluginPrefs.get("timeout", 0.5))
                except Exception as e:
                    self.errorLog("Action %s failed for '%s:%s' on %s: %s" %
                                  (command[0], device.name, device.pluginProps["interfaceID"],
                                   self.deviceTR64[device.id].host, str(e)))
            elif command[0] == "setSSID":
                if len(command) == 3:
                    try:
                        self.deviceTR64[device.id].setSSID(command[2],
                                                           wifiInterfaceId=device.pluginProps["interfaceID"],
                                                           timeout=self.pluginPrefs.get("timeout", 0.5))
                    except Exception as e:
                        self.errorLog("Action %s with value '%s' failed for '%s:%s' on %s: %s" %
                                      (command[0], command[2], device.name, device.pluginProps["interfaceID"],
                                       self.deviceTR64[device.id].host, str(e)))
                else:
                    self.errorLog("Action %s on %s has no valid argument" % (command[0], command[1]))

            elif command[0] == "setChannel":
                if len(command) == 3:
                    try:
                        self.deviceTR64[device.id].setChannel(command[2],
                                                              wifiInterfaceId=device.pluginProps["interfaceID"],
                                                              timeout=self.pluginPrefs.get("timeout", 0.5))
                    except Exception as e:
                        self.errorLog("Action %s with value '%s' failed for '%s:%s' on %s: %s" %
                                      (command[0], command[2], device.name, device.pluginProps["interfaceID"],
                                       self.deviceTR64[device.id].host, str(e)))
                else:
                    self.errorLog("Action %s on %s has no valid argument" % (command[0], device.name))

            elif command[0] == "terminateConnection":
                try:
                    self.deviceTR64[device.id].terminateConnection(wanInterfaceId=device.pluginProps["interfaceID"],
                                                                   timeout=self.pluginPrefs.get("timeout", 0.5))
                except Exception as e:
                    self.errorLog("Action %s failed for '%s:%s' on %s: %s" %
                                  (command[0], device.name, device.pluginProps["interfaceID"],
                                   self.deviceTR64[device.id].host, str(e)))
            elif command[0] == "requestConnection":
                try:
                    self.deviceTR64[device.id].requestConnection(wanInterfaceId=device.pluginProps["interfaceID"],
                                                                 timeout=self.pluginPrefs.get("timeout", 0.5))
                except Exception as e:
                    self.errorLog("Action %s failed for '%s:%s' on %s: %s" %
                                  (command[0], device.name, device.pluginProps["interfaceID"],
                                   self.deviceTR64[device.id].host, str(e)))
            elif command[0] == "optimizeForIPTV":
                if len(command) == 3:
                    try:
                        self.deviceTR64[device.id].setOptimizedForIPTV(True, wifiInterfaceId=command[2],
                                                                       timeout=self.pluginPrefs.get("timeout", 0.5))
                    except Exception as e:
                        self.errorLog("Action %s with value '%s' failed for '%s:%s' on %s: %s" %
                                      (command[0], command[2], device.name, device.pluginProps["interfaceID"],
                                       self.deviceTR64[device.id].host, str(e)))
                else:
                    self.errorLog("Action %s on %s has no valid argument" % (command[0], device.name))
            elif command[0] == "dontOptimizeForIPTV":
                if len(command) == 3:
                    try:
                        self.deviceTR64[device.id].setOptimizedForIPTV(False, wifiInterfaceId=command[2],
                                                                       timeout=self.pluginPrefs.get("timeout", 0.5))
                    except Exception as e:
                        self.errorLog("Action %s with value '%s' failed for '%s:%s' on %s: %s" %
                                      (command[0], command[2], device.name, device.pluginProps["interfaceID"],
                                       self.deviceTR64[device.id].host, str(e)))
                else:
                    self.errorLog("Action %s on %s has no valid argument" % (command[0], device.name))
            elif command[0] == "doUpdate":
                try:
                    result = self.deviceTR64[device.id].doUpdate(timeout=self.pluginPrefs.get("timeout", 0.5))
                except Exception as e:
                    self.errorLog("Action %s failed for '%s' on %s: %s" %
                                  (command[0], device.name, self.deviceTR64[device.id].host, str(e)))
                else:
                    self.debugLog("DoUpdate: %s - %s" % result)
            else:
                self.debugError("Unknown command %s received for %s." % command)

            self.commandQueue.task_done()

            # sleep to make sure we dont use too much cpu and give the chance to interrupt
            self.sleep(0.1)

    def queueAction(self, action):
        """Callback which just queue an action to be executed later in the background thread

        :param action: the action to queue9
        """
        value = action.props.get('value')

        if value:
            self.debugLog("Action '%s' with value '%s' for %s queued." % (action.pluginTypeId, value, action.deviceId))
            self.commandQueue.put((action.pluginTypeId, action.deviceId, value))
        else:
            self.debugLog("Action '%s' for %s queued." % (action.pluginTypeId, action.deviceId))
            self.commandQueue.put((action.pluginTypeId, action.deviceId))
