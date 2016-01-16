TR 64 - Router Monitor - Indigo Plugin
======================================

This plugin for Indigo let you interact with devices which supports UPnP/TR64. Usually these are devices which
do provide any kind of network connection like Cable/ADSL/WAN modems, WIFI-, LAN-router but as well some media devices.
For now this plugin supports mainly:

* Cable/ADSL or short WAN devices
* LAN devices
* WIFI devices

and in particular products from AVM called Fritz (Box, Repeater, etc).

The plugin provides dedicated data for certain type of devices like how much bytes have been transferred, how many
host are connected, what is the external IP address but also you can get very specific data about a device in your
network for example the IP address of it and if it is connected. This can be used to for presence monitoring. Further
details will follow down.

Installation
============

Find the latest version here for download::

    https://github.com/bpannier/TR64RouterMonitor/dist/TR64RouterMonitor-latest.zip

After unpacking, double click on it should bring Indigo up and ask if the plugin should be installed.

Configuration
=============

This plugin provides different logical devices which will be bind against a physical device where one physical device
can be bind against several logical devices. Most of the logical devices provides several values which gets gathered
through one or multiple calls to the physical device. The protocol which gets used is TR64 based on UPnP based on SOAP
based on HTTP. Even when your device supports TR64 or UPnP your device might not support all features, states or
actions which will be mentioned here, you also will see this in your logfile in case some functionality is missing.

Pre-Condition - Physical Device Configuration:
++++++++++++++++++++++++++++++++++++++++++++++

Any physical device needs to enable TR64 or UPnP, for a Fritz.box for example you can find this under:

Home-network / Network / Network Settings (Heimnetz / Netzwerk / Netzwerkeinstellungen)::

    * Permit access for applications TR64 (Zugriff für Anwendungen zulassen)
    * Status information's using UPnP (Statusinformationen ueber UPnP uebertragen)

Also it is highly recommended to enable authentication.


Plugin Configuration:
+++++++++++++++++++++

    * Update frequency - how often will the devices which belongs to this plugin be updated

    * Turn on Debug - you can get some more verbose information's in the logfile

    * HTTP/HTTPS Proxy - set a proxy of the form "http://hostname:port"

    * Network timeout - after how much seconds a connection should fail


Indigo Device Configuration:
++++++++++++++++++++++++++++

For LAN / WAN / WIFI devices you will have to specify an interface id. Many routers provide more than one interface and
you have to choose with which one you like to interact. The numbering starts with 1. Be aware that most WIFI routers
provide today different frequencies (2.4, 5 Ghz) which will be mapped at least to two different devices.

Also you have to choose to which physical device the logical device in Indigo should be bind. When the Indigo device
configuration opens, the plugin will try to discover any device in your local network which supports TR64, you then
can choose from the list of devices. In case your device will not be found you can assume your device will not be
supported, in very rare cases you might specify the router manually ... sorry, for them who knows, documentation might
be added later.

You can and should specify the username/password or password only to authenticate this plugin against your physical
device.

Also you can toggle the checkbox to "ignore errors", in case your device do not support the full functionality
errors in the logfile of this device will be omitted.


The logical devices which you can add and configure in Indigo after installing this plugin:


Router System
-------------

This provides states and actions which are not associated with any network type but with the system in itself.

States::

    * softwareVersion
    * softwareUpdateAvailable
    * uptime
    * currentTime
    * currentTimeZone

Actions::

    * resetDevice - Reboot the physical device


LAN Router
----------

This provides states and actions for the LAN part of a router.

States::

    * hostsConnected - the amount of hosts connected/known
    * lanBytesSent
    * lanBytesReceived
    * lanPacketsSent
    * lanPacketsReceived
    * lanEnabled
    * lanStatus
    * lanMaxBitrate
    * lanDuplex

Actions::

    * enableInterface
    * disableInterface


WAN Router
----------

This provides states and actions for the WAN/ADSL/Cable/etc part of a router.

States::

    * wanBytesSent
    * wanBytesReceived
    * wanPacketsSent
    * wanPacketsReceived
    * wanEnabled
    * wanStatus
    * wanUpstreamRate
    * wanDownstreamRate
    * wanUpstreamMaxRate
    * wanDownstreamMaxRate
    * wanUptime
    * wanLastError
    * wanExternalIP
    * wanExternalDNS
    * wanLinkStatus

Actions::

    * enableInterface
    * disableInterface
    * terminateConnection
    * requestConnection


WIFI Router
-----------

This provides states and actions for a WIFI router.

States::

    * wifiBytesSent
    * wifiBytesReceived
    * wifiPacketsSent
    * wifiPacketsReceived
    * wifiEnabled
    * wifiStatus
    * wifiAmountAssociatedDevices - how many WIFI devices are/have been connected to this router on the given interface.
    * wifiChannel - the channel of the WIFI network
    * wifiSSID - the name of the WIFI network

Actions::

    * enableInterface
    * disableInterface
    * setSSID - set a new WIFI network name
    * setChannel - set a new channel for the WIFI network of the given interface; please refer your router documentation


LAN Device Information
----------------------

This is a virtual device which provides information's about one specific device which is connected to the router via
LAN. The device will be specified with it's MAC address in the configuration of the Indigo device.

States::

    * ipAddress
    * hostname
    * leasetime
    * active


Wifi Device Information
-----------------------

This is a virtual device which provides information's about one specific device which is connected to the router via
WIFI. The device will be specified with it's MAC address in the configuration of the Indigo device.

States::

    * ipAddress
    * authenticated


Fritz Product
-------------

This is a virtual device which supports AVM Fritz Box/Repeater/etc, it will not work with any other physical device.
Also within this product family your device might not support all features, please check your documentation.

States::

    * callListEntryAmount - how many calls have been received/made
    * lastCallCalledNumber
    * lastCallCaller
    * lastCallDate
    * lastCallDevice
    * lastCallType - 1: answered, 2: missed, 3: outgoing
    * lastCallDuration
    * lastCallNumberType

Actions::

    * doUpdate - do an software update if available
    * optimizeForIPTV - the WIFI network could be optimized for IP TV applications
    * dontOptimizeForIPTV


Request
=======

I am always looking forward to extend the scope of this plugin, please give me feedback if you like to see additional
functionality or even when you like to contribute. Many TR64 devices supports much more functionality than supported
by this plugin, to check what your devices will support have a look on a tool to check:

http://bpannier.github.io/simpletr64/

This is a Python library which comes with a tool to discover any UPnP devices on the network::

    $ upnp_tools discover

To understand what kind of functionality a particular device supports you run::

    $ upnp_tools deviceinfo <devicename/ip>

If you find some functionality which is in your interest and might support more people please let me know and hopefully
I can extend the plugin. Please, send me in that case the output of the last command above.


Source Code
===========

This plugin is actively developed on GitHub, where the code is
`always available <https://github.com/bpannier/TR64RouterMonitor>`_.

You can either clone the public repository::

    $ git clone git://github.com/bpannier/TR64RouterMonitor.git

Download the `tarball <https://github.com/bpannier/TR64RouterMonitor/tarball/master>`_::

    $ curl -OL https://github.com/bpannier/TR64RouterMonitor/tarball/master

Or, download the `zipball <https://github.com/bpannier/TR64RouterMonitor/zipball/master>`_::

    $ curl -OL https://github.com/bpannier/simpletr64/TR64RouterMonitor/master


Once you have a copy of the source, you will have to create and install the plugin with

    $ make install


Author
======

This plugin is written and maintained by `Benjamin Pannier <http://bpannier.github.io/>`_ <sourcecode@ka.ro>

Please, feel free to contribute good karma and credits are guaranteed.


History
=======

1.0.0 (2016-01-16)
++++++++++++++++++

* Birth!