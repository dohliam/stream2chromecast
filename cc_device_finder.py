"""
Locates Chromecast devices on the local network.

version 0.3.1

Parts of this are adapted from code found in PyChromecast - https://github.com/balloob/pychromecast

"""


# Copyright (C) 2014-2016 Pat Carter
#
# This file is part of Stream2chromecast.
#
# Stream2chromecast is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Stream2chromecast is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Stream2chromecast.  If not, see <http://www.gnu.org/licenses/>.



import os
import socket, select
import datetime
import urlparse

import httplib, urllib
from xml.etree import ElementTree

CACHE_FILE = "~/.cc_device_cache"


def search_network(device_limit=None, time_limit=5):
    """ SSDP discovery """
    
    addrs = []
    
    start_time  = datetime.datetime.now() 
 
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(0)
    
    req = "\r\n".join(['M-SEARCH * HTTP/1.1',
                       'HOST: 239.255.255.250:1900',
                       'MAN: "ssdp:discover"',
                       'MX: 1',
                       'ST: urn:dial-multiscreen-org:service:dial:1',
                       '',''])
                       
    sock.sendto(req, ("239.255.255.250", 1900))


    while True:
        time_remaining = time_limit - (datetime.datetime.now() - start_time).seconds
        if time_remaining <= 0:
            break
            
        readable = select.select([sock], [], [], time_remaining)[0]

        if sock in readable:
            st, addr = None, None
            
            data = sock.recv(1024)

            for line in data.split("\r\n"):
                line = line.replace(" ", "")
            
                if line.upper().startswith("LOCATION:"):
                    addr = urlparse.urlparse(line[9:].strip()).hostname
                
                elif line.upper().startswith("ST:"):
                    st = line[3:].strip()


            if addr is not None and st == "urn:dial-multiscreen-org:service:dial:1":
                addrs.append(addr)
                
                if device_limit and len(addrs) == device_limit:
                    break


    sock.close()

    return addrs
    

                                      
def get_device_name(ip_addr):
    """ get the device friendly name for an IP address """
    
    try:
        conn = httplib.HTTPConnection(ip_addr + ":8008")
        conn.request("GET", "/ssdp/device-desc.xml")
        resp = conn.getresponse()
       
        if resp.status == 200:
            status_doc = resp.read()
            try:
                xml = ElementTree.fromstring(status_doc)

                device_element = xml.find("{urn:schemas-upnp-org:device-1-0}" + "device")

                return device_element.find("{urn:schemas-upnp-org:device-1-0}" + "friendlyName").text

            except ElementTree.ParseError:
                return ""    
        else:
            return "" 
    except:
        # unable to get a name - this might be for many reasons 
        # e.g. a non chromecast device on the network that responded to the search
        return "" 
        
        

def check_cache(name):
    """ check the search results cache file """ 
    
    result = None
    
    filepath = os.path.expanduser(CACHE_FILE)
    try:
        with open(filepath, "r") as f:
            for line in f.readlines():
                if "\t" in line:
                    line_split = line.strip().split("\t", 1)
                    if len(line_split) > 1:
                        hostname, host = line_split
                        if name == hostname:
                            # name is found - check that the host responds with the same name
                            device_name = get_device_name(host)
                            print "Device name response:", device_name
                            if name == device_name and device_name != "":
                                result = host
                                break
    except IOError:
        pass
        
    return result
    
    

def save_cache(host_map):
    """ save the search results for quick access later """
    
    filepath = os.path.expanduser(CACHE_FILE)
    with open(filepath, "w") as f:
        for key in host_map.keys():
            if len(key) > 0 and len(host_map[key]) > 0:
                # file format: hostname[tab]ip_addr
                f.write(key + "\t" + host_map[key] + "\n")
    
            
            
def find_device(name=None, time_limit=6):    
    """ find the first device (quick) or search by name (slower)"""
    
    if name is None or name == "":
        # no name specified so find the first device that responds
        print "searching the network for a Chromecast device"
        hosts = search_network(device_limit=1)
        if len(hosts) > 0:
            return hosts[0], get_device_name(hosts[0])
        else:
            return None, None
    else:
        # name specified, check the cached network search results file
        ip_addr = check_cache(name)
        if ip_addr is not None:
            # address found in cache
            print "found device in cache:", name
            return ip_addr, name
        else:
            # no cached results found run a full network search
            print "searching the network for:", name
            result_map = {}
            
            hosts = search_network(time_limit=time_limit)
            for host in hosts:
                device_name = get_device_name(host)
                if device_name != "":
                    result_map[device_name] = host
                
            save_cache(result_map)
            
            if name in result_map.keys():
                print "found device:", name
                return result_map[name], name
            else:
                return None, None

            






