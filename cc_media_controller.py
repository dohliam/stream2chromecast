"""
Provides a control interface to the Chromecast Media Player app

version 0.2.1

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



import socket, ssl, select
import json
import sys
import time
import re

import cc_device_finder
import cc_message


MEDIAPLAYER_APPID = "CC1AD845"
 

class CCMediaController():
    def __init__(self, device_name=None):
        """ initialise """
        
        self.host = self.get_device(device_name)

        self.sock = None
        
        self.request_id = 1
        self.source_id = "sender-0"

        self.receiver_app_status = None
        self.media_status = None
        self.volume_status = None
        self.current_applications = None
        
    
    
    def get_device(self, device_name):
        """ get the device ip address """
        
        host = None
        
        is_ip_addr = device_name is not None and re.match( "[0-9]+.[0-9]+.[0-9]+.[0-9]+$", device_name) is not None
        
        if is_ip_addr:
            host = device_name
            try:
                print "ip_addr:", host, "device name:", cc_device_finder.get_device_name(host)
            except socket.error:
                sys.exit("No Chromecast found on ip:" + host)
        else:
            host, name = cc_device_finder.find_device(name=device_name)
            if host is None:
                sys.exit("No Chromecast found on the network")
                
            print "device name:", name    
            
        return host
        
        
        
    def open_socket(self):
        """ open a socket if there is not currently one open """
        
        if self.sock is None:
            self.sock = socket.socket()
            self.sock = ssl.wrap_socket(self.sock)

            self.sock.connect((self.host,8009))

                
    def close_socket(self):
        """ close the socket if there is one open """
        
        if self.sock is not None:
            self.sock.close()
            
        self.sock = None



    def send_data(self, namespace, data_dict):
        """ send data to the device in binary format"""
        
        data = json.dumps(data_dict)
        
        #print "Sending: ", namespace, data
        
        msg = cc_message.format_message(self.source_id, self.destination_id, namespace, data)
        
        self.sock.write(msg)

        
        
    def read_message(self):
        """ read a complete message from the device """

        data = ""
        while len(data) < 4:
            data += self.sock.recv(4)
        
        msg_length, data = cc_message.extract_length_header(data) 
        while len(data) < msg_length:
            data += self.sock.recv(2048)
            
       
        message_dict = cc_message.extract_message(data)
        
        message = {}
        
        try:
            message = json.loads(message_dict['data'])
        except:
            pass
        
        #print message_dict['namespace']
        #print json.dumps(message, indent=4, separators=(',', ': '))
        
        return message   
        
         
    
    def get_response(self, request_id):
        """ get the response matching the original request id """
        
        resp = {}
        
        count = 0
        while len(resp) == 0:
            msg = self.read_message()
            
            msg_type = msg.get("type", msg.get("responseType", ""))
            
            if msg_type == "PING":
                data = {"type":"PONG"}
                namespace = "urn:x-cast:com.google.cast.tp.heartbeat"
                self.send_data(namespace, data) 
                
                # if 30 ping/pong messages are received without a response to the request_id, 
                # assume no response is coming
                count += 1
                if count == 30:
                    return resp
                
            elif msg_type == "RECEIVER_STATUS":
                self.update_receiver_status_data(msg)
                
            elif msg_type == "MEDIA_STATUS":
                self.update_media_status_data(msg)
            
            if "requestId" in msg.keys() and msg['requestId'] == request_id:
                resp = msg
                
        return resp



    def send_msg_with_response(self, namespace, data):
        """ send a request to the device and wait for a response matching the request id """
        
        self.request_id += 1
        data['requestId'] = self.request_id
        
        self.send_data(namespace, data)
        
        return self.get_response(self.request_id)

            
        
    def update_receiver_status_data(self, msg):
        """ update the status for the Media Player app if it is running """
        
        self.receiver_app_status = None
        
        if msg.has_key('status'):
            status = msg['status']
            if status.has_key('applications'):
                self.current_applications = status['applications']
                for application in self.current_applications:
                    if application.get("appId") == MEDIAPLAYER_APPID:
                        self.receiver_app_status = application
                        
                        
            if status.has_key('volume'):
                self.volume_status = status['volume']
                        
                        
                        
    def update_media_status_data(self, msg): 
        """ update the media status if there is any media loaded """
        
        self.media_status = None
        
        status = msg.get("status", [])
        if len(status) > 0:  
            self.media_status = status[0] # status is an array - selecting the first result..?                 


         
        
    def connect(self, destination_id):  
        """ connect to to the receiver or the media transport """
        
        if self.sock is None:
            self.open_socket()
                     
        self.destination_id = destination_id
        
        data = {"type":"CONNECT","origin":{}}
        namespace = "urn:x-cast:com.google.cast.tp.connection"
        self.send_data(namespace, data)
        
        
    
    def get_receiver_status(self):
        """ send a status request to the receiver """
        
        data = {"type":"GET_STATUS"}
        namespace = "urn:x-cast:com.google.cast.receiver"
        self.send_msg_with_response(namespace, data)
                
    
    
    def get_media_status(self):
        """ send a status request to the media player """
        
        data = {"type":"GET_STATUS"}
        namespace = "urn:x-cast:com.google.cast.media"
        self.send_msg_with_response(namespace, data)   
            
            
                    
    def load(self, content_url, content_type, sub, sub_language):
        """ Launch the player app, load & play a URL """
        
        self.connect("receiver-0")

        self.get_receiver_status()
        
        # we only set the receiver status for MEDIAPLAYER - so if it is set, the app is currenty running
        if self.receiver_app_status is None:
            data = {"type":"LAUNCH","appId":MEDIAPLAYER_APPID}
            namespace = "urn:x-cast:com.google.cast.receiver"
            self.send_msg_with_response(namespace, data)
            
            # if there is still no receiver app status the launch failed.
            if self.receiver_app_status is None:
                self.close_socket()
                sys.exit("Cannot launch the Media Player app")
                
        
        session_id = str(self.receiver_app_status['sessionId'])
        transport_id = str(self.receiver_app_status['transportId'])

        self.connect(transport_id)

        data = {"type":"LOAD",
                "sessionId":session_id,
                "media":{
                    "contentId":content_url,
                    "streamType":"buffered",
                    "contentType":content_type,
                    },
                "autoplay":True,
                "currentTime":0,
                "customData":{
                    "payload":{
                        "title:":""
                        }
                    }
                }


        if sub:        
            if sub_language is None:
                sub_language = "en-US"
                
            data["media"].update({
                                "textTrackStyle":{
                                    'backgroundColor':'#FFFFFF00'
                                },
                                "tracks": [{"trackId": 1,
                                            "trackContentId": sub,
                                            "type": "TEXT",
                                            "language": sub_language,
                                            "subtype": "SUBTITLES",
                                            "name": "Englishx",
                                            "trackContentType": "text/vtt",
                                           }],
                                })
            data["activeTrackIds"] = [1]

        
        namespace = "urn:x-cast:com.google.cast.media"
        resp = self.send_msg_with_response(namespace, data)


        # wait for the player to return "BUFFERING", "PLAYING" or "IDLE"
        if resp.get("type", "") == "MEDIA_STATUS":            
            player_state = ""
            while player_state != "PLAYING" and player_state != "IDLE" and player_state != "BUFFERING":
                time.sleep(2)        
                
                self.get_media_status()
                
                if self.media_status != None:
                    player_state = self.media_status.get("playerState", "")

                
        self.close_socket()       


            
    def control(self, command, parameters={}):      
        """ send a control command to the player """
          
        self.connect("receiver-0")

        self.get_receiver_status()
        
        if self.receiver_app_status is None:
            print "No media player app running"
            self.close_socket()
            return      
        
        transport_id = str(self.receiver_app_status['transportId'])       
        
        self.connect(transport_id)
        
        self.get_media_status()
        
        media_session_id = 1
        if self.media_status is not None:
            media_session_id = self.media_status['mediaSessionId']
                                                                     
        data = {"type":command, "mediaSessionId":media_session_id}
        data.update(parameters)  # for additional parameters
        
        namespace = "urn:x-cast:com.google.cast.media"
        self.send_msg_with_response(namespace, data)
        
        self.close_socket()
                       
    
    
    def get_status(self):
        """ get the receiver and media status """
        
        self.connect("receiver-0")

        self.get_receiver_status()
        
        if self.receiver_app_status is not None:   
            transport_id = str(self.receiver_app_status['transportId']) 
            self.connect(transport_id)
            self.get_media_status()
        
        application_list = []
        if self.current_applications is not None:
            for application in self.current_applications:
                application_list.append({
                    'appId':application.get('appId', ""), 
                    'displayName':application.get('displayName', ""),  
                    'statusText':application.get('statusText', "")})
        
        status = {'receiver_status':self.receiver_app_status, 
                  'media_status':self.media_status, 
                  'host':self.host, 
                  'client':self.sock.getsockname(),
                  'applications':application_list}
                
        self.close_socket()
        
        return status
        
        
        
    def is_idle(self):
        """ return the IDLE state of the player """
        
        status = self.get_status()
        
        if status['media_status']  is None:
            if status['receiver_status'] is None:
                return True
            else:    
                return status['receiver_status'].get("statusText", "") == u"Ready To Cast"

        else:    
            return status['media_status'].get("playerState", "") == u"IDLE"
       
       

    def pause(self):
        """ pause """
        self.control("PAUSE") 
        
            
    def play(self):
        """ unpause """
        self.control("PLAY")   
              

    def stop(self):
        """ stop """
        self.control("STOP")         
        
        
        
    def set_volume(self, level):
        """ set the receiver volume - a float value in level for absolute level or "+" / "-" indicates up or down"""
        
        self.connect("receiver-0")

        if level in ("+", "-"):
            self.get_receiver_status()
        
            if self.volume_status is not None:
                curr_level = self.volume_status['level']
                if level == "+":
                    level = 0.1 + curr_level
                elif level == "-":
                    level = curr_level - 0.1
            
        
        data = {"type":"SET_VOLUME", "volume":{"muted":False, "level":level} }
        namespace = "urn:x-cast:com.google.cast.receiver"
        self.send_msg_with_response(namespace, data)  
        
        self.close_socket() 
        
        
        
    def get_volume(self):
        """ get the current volume level """
        self.get_status()
        
        vol = None
        
        if self.volume_status is not None:
            vol = self.volume_status.get('level', None)
                
        return vol
                         
                              
                                
    def set_volume_up(self):
        """ increase volume by one step """
        self.set_volume("+")
            

            
    def set_volume_down(self):
        """ decrease volume by one step """
        self.set_volume("-")    
            

                    
          

        
