#!/usr/bin/env python

""" The wicd DBus Manager.

A module for storing wicd's dbus interfaces.

"""

#
#   Copyright (C) 2007 Adam Blackburn
#   Copyright (C) 2007 Dan O'Reilly
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License Version 2 as
#   published by the Free Software Foundation.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import dbus

class DBusManager(object):
    def __init__(self):
        self._bus = dbus.SystemBus()
        self._dbus_ifaces = {}  
    
    def get_dbus_ifaces(self):
        """ Returns a dict of dbus interfaces. """
        return self._dbus_ifaces
    
    def get_bus(self):
        """ Returns the loaded SystemBus. """
        return self._bus
    
    def connect_to_dbus(self):
        """ Connects to wicd's dbus interfaces and loads them into a dict. """
        proxy_obj = self._bus.get_object("org.wicd.daemon", '/org/wicd/daemon')
        daemon = dbus.Interface(proxy_obj, 'org.wicd.daemon')
        wireless = dbus.Interface(proxy_obj, 'org.wicd.daemon.wireless')
        wired = dbus.Interface(proxy_obj, 'org.wicd.daemon.wired')
        config = dbus.Interface(proxy_obj, 'org.wicd.daemon.config')
        self._dbus_ifaces = {"daemon" : daemon, "wireless" : wireless,
                             "wired" : wired, "config" : config} 
