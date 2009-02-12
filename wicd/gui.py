#!/usr/bin/python

""" Wicd GUI module.

Module containg all the code (other than the tray icon) related to the 
Wicd user interface.

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

import os
import sys
import time
import gobject
import pango
import gtk
import gtk.glade
from dbus import DBusException
from dbus import version as dbus_version

from wicd import misc
from wicd import wpath
from wicd import dbusmanager
from wicd import prefs
from wicd import netentry
from wicd.misc import noneToString
from wicd.netentry import WiredNetworkEntry, WirelessNetworkEntry
from wicd.prefs import PreferencesDialog
from wicd.guiutil import error, GreyLabel, LabelEntry, SmallLabel

if __name__ == '__main__':
    wpath.chdir(__file__)

proxy_obj = daemon = wireless = wired = bus = None
language = misc.get_language_list_gui()
DBUS_AVAIL = False

def setup_dbus(force=True):
    global bus, daemon, wireless, wired, DBUS_AVAIL
    try:
        dbusmanager.connect_to_dbus()
    except DBusException:
        if force:
            print "Can't connect to the daemon, trying to start it automatically..."
            misc.PromptToStartDaemon()
            try:
                dbusmanager.connect_to_dbus()
            except DBusException:
                error(None, "Could not connect to wicd's D-Bus interface.  " +
                      "Check the wicd log for error messages.")
                return False
        else:  
            return False
    prefs.setup_dbus()
    netentry.setup_dbus()
    bus = dbusmanager.get_bus()
    dbus_ifaces = dbusmanager.get_dbus_ifaces()
    daemon = dbus_ifaces['daemon']
    wireless = dbus_ifaces['wireless']
    wired = dbus_ifaces['wired']
    DBUS_AVAIL = True
    
    return True

def handle_no_dbus(from_tray=False):
    global DBUS_AVAIL
    DBUS_AVAIL = False
    if from_tray: return False
    print "Wicd daemon is shutting down!"
    error(None, language['lost_dbus'], block=False)
    return False

        
class WiredProfileChooser:
    """ Class for displaying the wired profile chooser. """
    def __init__(self):
        """ Initializes and runs the wired profile chooser. """
        # Import and init WiredNetworkEntry to steal some of the
        # functions and widgets it uses.
        wired_net_entry = WiredNetworkEntry()

        dialog = gtk.Dialog(title = language['wired_network_found'],
                            flags = gtk.DIALOG_MODAL,
                            buttons = (gtk.STOCK_CONNECT, 1,
                                       gtk.STOCK_CANCEL, 2))
        dialog.set_has_separator(False)
        dialog.set_size_request(400, 150)
        instruct_label = gtk.Label(language['choose_wired_profile'] + ':\n')
        stoppopcheckbox = gtk.CheckButton(language['stop_showing_chooser'])

        wired_net_entry.is_full_gui = False
        instruct_label.set_alignment(0, 0)
        stoppopcheckbox.set_active(False)

        # Remove widgets that were added to the normal WiredNetworkEntry
        # so that they can be added to the pop-up wizard.
        wired_net_entry.vbox_top.remove(wired_net_entry.hbox_temp)
        wired_net_entry.vbox_top.remove(wired_net_entry.profile_help)

        dialog.vbox.pack_start(instruct_label, fill=False, expand=False)
        dialog.vbox.pack_start(wired_net_entry.profile_help, False, False)
        dialog.vbox.pack_start(wired_net_entry.hbox_temp, False, False)
        dialog.vbox.pack_start(stoppopcheckbox, False, False)
        dialog.show_all()

        wired_profiles = wired_net_entry.combo_profile_names
        wired_net_entry.profile_help.hide()
        if wired_net_entry.profile_list != None:
            wired_profiles.set_active(0)
            print "wired profiles found"
        else:
            print "no wired profiles found"
            wired_net_entry.profile_help.show()

        response = dialog.run()
        if response == 1:
            print 'reading profile ', wired_profiles.get_active_text()
            wired.ReadWiredNetworkProfile(wired_profiles.get_active_text())
            wired.ConnectWired()
        else:
            if stoppopcheckbox.get_active():
                daemon.SetForcedDisconnect(True)
        dialog.destroy()


class appGui(object):
    """ The main wicd GUI class. """
    def __init__(self, standalone=False):
        """ Initializes everything needed for the GUI. """
        setup_dbus()

        gladefile = os.path.join(wpath.share, "wicd.glade")
        self.wTree = gtk.glade.XML(gladefile)
        self.window = self.wTree.get_widget("window1")
        size = daemon.ReadWindowSize("main")
        width = size[0]
        height = size[1]
        if width > -1 and height > -1:
            self.window.resize(int(width), int(height))
        else:
            width = int(gtk.gdk.screen_width() / 2)
            if width > 530:
                width = 530
            self.window.resize(width, int(gtk.gdk.screen_height() / 1.7))

        dic = { "refresh_clicked" : self.refresh_clicked, 
                "quit_clicked" : self.exit, 
                "disconnect_clicked" : self.disconnect_all,
                "main_exit" : self.exit, 
                "cancel_clicked" : self.cancel_connect,
                "hidden_clicked" : self.connect_hidden,
                "preferences_clicked" : self.settings_dialog,
                "about_clicked" : self.about_dialog,
                "create_adhoc_clicked" : self.create_adhoc_network,
                }
        self.wTree.signal_autoconnect(dic)

        # Set some strings in the GUI - they may be translated
        label_instruct = self.wTree.get_widget("label_instructions")
        label_instruct.set_label(language['select_a_network'])

        probar = self.wTree.get_widget("progressbar")
        probar.set_text(language['connecting'])
        
        self.network_list = self.wTree.get_widget("network_list_vbox")
        self.status_area = self.wTree.get_widget("connecting_hbox")
        self.status_bar = self.wTree.get_widget("statusbar")
        menu = self.wTree.get_widget("menu1")

        self.status_area.hide_all()

        if os.path.exists(os.path.join(wpath.images, "wicd.png")):
            self.window.set_icon_from_file(os.path.join(wpath.images, "wicd.png"))
        self.statusID = None
        self.first_dialog_load = True
        self.is_visible = True
        self.pulse_active = False
        self.pref = None
        self.standalone = standalone
        self.wpadrivercombo = None
        self.connecting = False
        self.refreshing = False
        self.prev_state = None
        self.network_list.set_sensitive(False)
        label = gtk.Label("%s..." % language['scanning'])
        self.network_list.pack_start(label)
        label.show()
        self.wait_for_events(0.2)
        self.window.connect('delete_event', self.exit)
        self.window.connect('key-release-event', self.key_event)
        daemon.SetGUIOpen(True)
        bus.add_signal_receiver(self.dbus_scan_finished, 'SendEndScanSignal',
                        'org.wicd.daemon.wireless')
        bus.add_signal_receiver(self.dbus_scan_started, 'SendStartScanSignal',
                        'org.wicd.daemon.wireless')
        bus.add_signal_receiver(self.update_connect_buttons, 'StatusChanged',
                        'org.wicd.daemon')
        bus.add_signal_receiver(self.handle_connection_results,
                                'ConnectResultsSent', 'org.wicd.daemon')
        bus.add_signal_receiver(lambda: setup_dbus(force=False), 
                                "DaemonStarting", "org.wicd.daemon")
        bus.add_signal_receiver(self._do_statusbar_update, 'StatusChanged',
                                'org.wicd.daemon')
        if standalone:
            bus.add_signal_receiver(handle_no_dbus, "DaemonClosing", 
                                    "org.wicd.daemon")
            
        self._do_statusbar_update(*daemon.GetConnectionStatus())
        self.wait_for_events(0.1)
        self.update_cb = misc.timeout_add(2, self.update_statusbar)
        self.refresh_clicked()
        
    def handle_connection_results(self, results):
        if results not in ['Success', 'aborted'] and self.is_visible:
            error(self.window, language[results], block=False)

    def create_adhoc_network(self, widget=None):
        """ Shows a dialog that creates a new adhoc network. """
        print "Starting the Ad-Hoc Network Creation Process..."
        dialog = gtk.Dialog(title = language['create_adhoc_network'],
                            flags = gtk.DIALOG_MODAL,
                            buttons=(gtk.STOCK_CANCEL, 2, gtk.STOCK_OK, 1))
        dialog.set_has_separator(False)
        dialog.set_size_request(400, -1)
        self.chkbox_use_encryption = gtk.CheckButton(language['use_wep_encryption'])
        self.chkbox_use_encryption.set_active(False)
        ip_entry = LabelEntry(language['ip'] + ':')
        essid_entry = LabelEntry(language['essid'] + ':')
        channel_entry = LabelEntry(language['channel'] + ':')
        self.key_entry = LabelEntry(language['key'] + ':')
        self.key_entry.set_auto_hidden(True)
        self.key_entry.set_sensitive(False)

        chkbox_use_ics = gtk.CheckButton(language['use_ics'])

        self.chkbox_use_encryption.connect("toggled",
                                           self.toggle_encrypt_check)
        channel_entry.entry.set_text('3')
        essid_entry.entry.set_text('My_Adhoc_Network')
        ip_entry.entry.set_text('169.254.12.10')  # Just a random IP

        vbox_ah = gtk.VBox(False, 0)
        vbox_ah.pack_start(self.chkbox_use_encryption, False, False)
        vbox_ah.pack_start(self.key_entry, False, False)
        vbox_ah.show()
        dialog.vbox.pack_start(essid_entry)
        dialog.vbox.pack_start(ip_entry)
        dialog.vbox.pack_start(channel_entry)
        dialog.vbox.pack_start(chkbox_use_ics)
        dialog.vbox.pack_start(vbox_ah)
        dialog.vbox.set_spacing(5)
        dialog.show_all()
        response = dialog.run()
        if response == 1:
            wireless.CreateAdHocNetwork(essid_entry.entry.get_text(),
                                        channel_entry.entry.get_text(),
                                        ip_entry.entry.get_text(), "WEP",
                                        self.key_entry.entry.get_text(),
                                        self.chkbox_use_encryption.get_active(),
                                        False) #chkbox_use_ics.get_active())
        dialog.destroy()

    def toggle_encrypt_check(self, widget=None):
        """ Toggles the encryption key entry box for the ad-hoc dialog. """
        self.key_entry.set_sensitive(self.chkbox_use_encryption.get_active())

    def disconnect_all(self, widget=None):
        """ Disconnects from any active network. """
        daemon.Disconnect()

    def about_dialog(self, widget, event=None):
        """ Displays an about dialog. """
        dialog = gtk.AboutDialog()
        dialog.set_name("Wicd")
        dialog.set_version(daemon.Hello())
        dialog.set_authors([ "Adam Blackburn", "Dan O'Reilly" ])
        dialog.set_website("http://wicd.sourceforge.net")
        dialog.run()
        dialog.destroy()
        
    def key_event (self, widget, event=None):
        """ Handle key-release-events. """
        if event.state & gtk.gdk.CONTROL_MASK and \
           gtk.gdk.keyval_name(event.keyval) in ["w", "q"]:
            self.exit()
    
    def settings_dialog(self, widget, event=None):
        """ Displays a general settings dialog. """
        if not self.pref:
            self.pref = PreferencesDialog(self.wTree)
        else:
            self.pref.load_preferences_diag()
        if self.pref.run() == 1:
            self.pref.save_results()
        self.pref.hide()

    def connect_hidden(self, widget):
        """ Prompts the user for a hidden network, then scans for it. """
        dialog = gtk.Dialog(title=language['hidden_network'],
                            flags=gtk.DIALOG_MODAL,
                            buttons=(gtk.STOCK_CONNECT, 1, gtk.STOCK_CANCEL, 2))
        dialog.set_has_separator(False)
        lbl = gtk.Label(language['hidden_network_essid'])
        textbox = gtk.Entry()
        dialog.vbox.pack_start(lbl)
        dialog.vbox.pack_start(textbox)
        dialog.show_all()
        button = dialog.run()
        if button == 1:
            answer = textbox.get_text()
            dialog.destroy()
            self.refresh_networks(None, True, answer)
        else:
            dialog.destroy()

    def cancel_connect(self, widget):
        """ Alerts the daemon to cancel the connection process. """
        #should cancel a connection if there
        #is one in progress
        cancel_button = self.wTree.get_widget("cancel_button")
        cancel_button.set_sensitive(False)
        daemon.CancelConnect()
        # Prevents automatic reconnecting if that option is enabled
        daemon.SetForcedDisconnect(True)

    def pulse_progress_bar(self):
        """ Pulses the progress bar while connecting to a network. """
        if not self.pulse_active:
            return False
        if not self.is_visible:
            return True
        try:
            gobject.idle_add(self.wTree.get_widget("progressbar").pulse)
        except:
            pass
        return True

    def update_statusbar(self):
        """ Triggers a status update in wicd-monitor. """
        if not self.is_visible:
            return True
        
        if self.connecting:
            self._do_statusbar_update(*daemon.GetConnectionStatus())
        else:
            daemon.UpdateState()
        return True
    
    def _do_statusbar_update(self, state, info):
        if not self.is_visible:
            return True
        
        if state == misc.WIRED:
            return self.set_wired_state(info)
        elif state == misc.WIRELESS:
            return self.set_wireless_state(info)
        elif state == misc.CONNECTING:
            return self.set_connecting_state(info)
        elif state in (misc.SUSPENDED, misc.NOT_CONNECTED):
            return self.set_not_connected_state(info)
        return True
        
    def set_wired_state(self, info):
        self._set_not_connecting_state()
        self.set_status(language['connected_to_wired'].replace('$A', info[0]))
        return True
    
    def set_wireless_state(self, info):
        self._set_not_connecting_state()
        self.set_status(language['connected_to_wireless'].replace
                        ('$A', info[1]).replace
                        ('$B', daemon.FormatSignalForPrinting(info[2])).replace
                        ('$C', info[0]))
        return True
        
    def set_not_connected_state(self, info):
        if self.connecting:
            self._set_not_connecting_state()
        self.set_status(language['not_connected'])
        return True
        
    def _set_not_connecting_state(self):
        if self.connecting:
            gobject.source_remove(self.update_cb)
            self.update_cb = misc.timeout_add(2, self.update_statusbar)
            self.connecting = False
        if self.pulse_active:
            self.pulse_active = False
            gobject.idle_add(self.network_list.set_sensitive, True)
            gobject.idle_add(self.status_area.hide_all)
        if self.statusID:
            gobject.idle_add(self.status_bar.remove, 1, self.statusID)
    
    def set_connecting_state(self, info):
        if not self.connecting:
            gobject.source_remove(self.update_cb)
            self.update_cb = misc.timeout_add(500, self.update_statusbar, 
                                              milli=True)
            self.connecting = True
        if not self.pulse_active:
            self.pulse_active = True
            misc.timeout_add(100, self.pulse_progress_bar, milli=True)
            gobject.idle_add(self.network_list.set_sensitive, False)
            gobject.idle_add(self.status_area.show_all)
        if self.statusID:
            gobject.idle_add(self.status_bar.remove, 1, self.statusID)
        if info[0] == "wireless":
            gobject.idle_add(self.set_status, str(info[1]) + ': ' +
                   language[str(wireless.CheckWirelessConnectingMessage())])
        elif info[0] == "wired":
            gobject.idle_add(self.set_status, language['wired_network'] + ': ' +
                         language[str(wired.CheckWiredConnectingMessage())])
        return True
        
    def update_connect_buttons(self, state=None, x=None, force_check=False):
        """ Updates the connect/disconnect buttons for each network entry.

        If force_check is given, update the buttons even if the
        current network state is the same as the previous.
        
        """
        if not DBUS_AVAIL: return
        if not state:
            state, x = daemon.GetConnectionStatus()
        
        if self.prev_state != state or force_check:
            apbssid = wireless.GetApBssid()
            for entry in self.network_list:
                if hasattr(entry, "update_connect_button"):
                    entry.update_connect_button(state, apbssid)
        self.prev_state = state
    
    def set_status(self, msg):
        """ Sets the status bar message for the GUI. """
        self.statusID = self.status_bar.push(1, msg)
        
    def dbus_scan_finished(self):
        """ Calls for a non-fresh update of the gui window.
        
        This method is called after a wireless scan is completed.
        
        """
        if not DBUS_AVAIL: return
        gobject.idle_add(self.refresh_networks, None, False, None)
            
    def dbus_scan_started(self):
        """ Called when a wireless scan starts. """
        if not DBUS_AVAIL: return
        self.network_list.set_sensitive(False)
    
    def refresh_clicked(self, widget=None):
        """ Kick off an asynchronous wireless scan. """
        if not DBUS_AVAIL or self.connecting: return
        self.refreshing = True
        wireless.Scan(False)

    def refresh_networks(self, widget=None, fresh=True, hidden=None):
        """ Refreshes the network list.
        
        If fresh=True, scans for wireless networks and displays the results.
        If a ethernet connection is available, or the user has chosen to,
        displays a Wired Network entry as well.
        If hidden isn't None, will scan for networks after running
        iwconfig <wireless interface> essid <hidden>.
        
        """
        if fresh:
            if hidden:
                wireless.SetHiddenNetworkESSID(noneToString(hidden))
            self.refresh_clicked()
            return
        print "refreshing..."
        self.network_list.set_sensitive(False)
        self.wait_for_events()
        printLine = False  # We don't print a separator by default.
        # Remove stuff already in there.
        for z in self.network_list:
            self.network_list.remove(z)
            z.destroy()
            del z

        if wired.CheckPluggedIn() or daemon.GetAlwaysShowWiredInterface():
            printLine = True  # In this case we print a separator.
            wirednet = WiredNetworkEntry()
            self.network_list.pack_start(wirednet, False, False)
            wirednet.connect_button.connect("button-press-event", self.connect,
                                           "wired", 0, wirednet)
            wirednet.disconnect_button.connect("button-press-event", self.disconnect,
                                               "wired", 0, wirednet)
            wirednet.advanced_button.connect("button-press-event",
                                             self.edit_advanced, "wired", 0, 
                                             wirednet)

        num_networks = wireless.GetNumberOfNetworks()
        instruct_label = self.wTree.get_widget("label_instructions")
        if num_networks > 0:
            instruct_label.show()
            for x in range(0, num_networks):
                if printLine:
                    sep = gtk.HSeparator()
                    self.network_list.pack_start(sep, padding=10, fill=False,
                                                 expand=False)
                    sep.show()
                else:
                    printLine = True
                tempnet = WirelessNetworkEntry(x)
                self.network_list.pack_start(tempnet, False, False)
                tempnet.connect_button.connect("button-press-event",
                                               self.connect, "wireless", x,
                                               tempnet)
                tempnet.disconnect_button.connect("button-press-event",
                                                  self.disconnect, "wireless",
                                                  x, tempnet)
                tempnet.advanced_button.connect("button-press-event",
                                                self.edit_advanced, "wireless",
                                                x, tempnet)
        else:
            instruct_label.hide()
            if wireless.GetKillSwitchEnabled():
                label = gtk.Label(language['killswitch_enabled'] + ".")
            else:
                label = gtk.Label(language['no_wireless_networks_found'])
            self.network_list.pack_start(label)
            label.show()
        self.update_connect_buttons(force_check=True)
        self.network_list.set_sensitive(True)
        self.refreshing = False

    def save_settings(self, nettype, networkid, networkentry):
        """ Verifies and saves the settings for the network entry. """
        entry = networkentry.advanced_dialog
        opt_entlist = []
        req_entlist = []
        
        # First make sure all the Addresses entered are valid.
        if entry.chkbox_static_ip.get_active():
            req_entlist = [entry.txt_ip, entry.txt_netmask]
            opt_entlist = [entry.txt_gateway]
                
        if entry.chkbox_static_dns.get_active() and \
           not entry.chkbox_global_dns.get_active():
            req_entlist.append(entry.txt_dns_1)
            # Only append additional dns entries if they're entered.
            for ent in [entry.txt_dns_2, entry.txt_dns_3]:
                if ent.get_text() != "":
                    opt_entlist.append(ent)
        
        # Required entries.
        for lblent in req_entlist:
            if not misc.IsValidIP(lblent.get_text()):
                error(self.window, language['invalid_address'].
                                    replace('$A', lblent.label.get_label()))
                return False
        
        # Optional entries, only check for validity if they're entered.
        for lblent in opt_entlist:
            if lblent.get_text() and not misc.IsValidIP(lblent.get_text()):
                error(self.window, language['invalid_address'].
                                    replace('$A', lblent.label.get_label()))
                return False

        # Now save the settings.
        if nettype == "wireless":
            if not networkentry.save_wireless_settings(networkid):
                return False

        elif nettype == "wired":
            if not networkentry.save_wired_settings():
                return False
            
        return True

    def edit_advanced(self, widget, event, ttype, networkid, networkentry):
        """ Display the advanced settings dialog.
        
        Displays the advanced settings dialog and saves any changes made.
        If errors occur in the settings, an error message will be displayed
        and the user won't be able to save the changes until the errors
        are fixed.
        
        """
        dialog = networkentry.advanced_dialog
        dialog.set_values()
        dialog.show_all()
        while True:
            if self.run_settings_dialog(dialog, ttype, networkid, networkentry):
                break
        dialog.hide()
        
    def run_settings_dialog(self, dialog, nettype, networkid, networkentry):
        """ Runs the settings dialog.
        
        Runs the settings dialog and returns True if settings are saved
        successfully, and false otherwise.
        
        """
        result = dialog.run()
        if result == gtk.RESPONSE_ACCEPT:
            if self.save_settings(nettype, networkid, networkentry):
                return True
            else:
                return False
        return True
    
    def check_encryption_valid(self, networkid, entry):
        """ Make sure that encryption settings are properly filled in. """
        # Make sure no entries are left blank
        if entry.chkbox_encryption.get_active():
            encryption_info = entry.encryption_info
            for x in encryption_info:
                if encryption_info[x].get_text() == "":
                    error(self.window, language['encrypt_info_missing'])
                    return False
        # Make sure the checkbox is checked when it should be
        elif not entry.chkbox_encryption.get_active() and \
             wireless.GetWirelessProperty(networkid, "encryption"):
            error(self.window, language['enable_encryption'])
            return False
        return True

    def connect(self, widget, event, nettype, networkid, networkentry):
        """ Initiates the connection process in the daemon. """
        cancel_button = self.wTree.get_widget("cancel_button")
        cancel_button.set_sensitive(True)
        if nettype == "wireless":
            if not self.check_encryption_valid(networkid,
                                               networkentry.advanced_dialog):
                self.edit_advanced(None, None, nettype, networkid, networkentry)
                return False
            wireless.ConnectWireless(networkid)
        elif nettype == "wired":
            wired.ConnectWired()
        self.update_statusbar()
        
    def disconnect(self, widget, event, nettype, networkid, networkentry):
        """ Disconnects from the given network.
        
        Keyword arguments:
        widget -- The disconnect button that was pressed.
        event -- unused
        nettype -- "wired" or "wireless", depending on the network entry type.
        networkid -- unused
        networkentry -- The NetworkEntry containing the disconnect button.
        
        """
        widget.hide()
        networkentry.connect_button.show()
        if nettype == "wired":
            wired.DisconnectWired()
        else:
            wireless.DisconnectWireless()
        
    def wait_for_events(self, amt=0):
        """ Wait for any pending gtk events to finish before moving on. 

        Keyword arguments:
        amt -- a number specifying the number of ms to wait before checking
               for pending events.
        
        """
        time.sleep(amt)
        while gtk.events_pending():
            gtk.main_iteration()

    def exit(self, widget=None, event=None):
        """ Hide the wicd GUI.

        This method hides the wicd GUI and writes the current window size
        to disc for later use.  This method normally does NOT actually 
        destroy the GUI, it just hides it.

        """
        self.window.hide()
        gobject.source_remove(self.update_cb)
        bus.remove_signal_receiver(self._do_statusbar_update, 'StatusChanged',
                                   'org.wicd.daemon')
        [width, height] = self.window.get_size()
        try:
            daemon.WriteWindowSize(width, height, "main")
            daemon.SetGUIOpen(False)
        except dbusmanager.DBusException:
            pass

        if self.standalone:
            sys.exit(0)

        self.is_visible = False
        return True

    def show_win(self):
        """ Brings the GUI out of the hidden state. 
        
        Method to show the wicd GUI, alert the daemon that it is open,
        and refresh the network list.
        
        """
        self.window.present()
        self.wait_for_events()
        self.is_visible = True
        daemon.SetGUIOpen(True)
        self.wait_for_events(0.1)
        gobject.idle_add(self.refresh_clicked)
        self._do_statusbar_update(*daemon.GetConnectionStatus())
        bus.add_signal_receiver(self._do_statusbar_update, 'StatusChanged',
                                'org.wicd.daemon')
        self.update_cb = misc.timeout_add(2, self.update_statusbar)


if __name__ == '__main__':
    setup_dbus()
    app = appGui(standalone=True)
    mainloop = gobject.MainLoop()
    mainloop.run()
