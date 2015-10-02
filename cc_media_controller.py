"""
Provides a control interface to the Chromecast Media Player app

version 0.1

"""

import socket, ssl, select
import json
import sys
import time

import cc_device_finder
import cc_message


MEDIAPLAYER_APPID = "CC1AD845"
 

class CCMediaController():
    def __init__(self, device_name=None):
        """ initialise """
        
        self.host, name = cc_device_finder.find_device(name=device_name)
        if self.host is None:
            sys.exit("No Chromecast found on the network")
            
        print "Device:", name

        self.sock = None
        
        self.request_id = 1
        self.source_id = "sender-0"

        self.receiver_app_status = None
        self.media_status = None
        self.volume_status = None
        
        
        
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

        data = self.sock.recv(4)
        
        msg_length, data = cc_message.extract_length_header(data) 
        while len(data) < msg_length:
            data += self.sock.recv(2048)
            
       
        message_dict = cc_message.extract_message(data)
        
        message = json.loads(message_dict['data'])
        
        #print message_dict['namespace']
        #print json.dumps(message, indent=4, separators=(',', ': '))
        
        return message   
        
         
    
    def get_response(self, request_id):
        """ get the response matching the original request id """
        
        resp = None
        while resp is None:
            msg = self.read_message()
            
            msg_type = msg.get("type", msg.get("responseType", ""))
            
            if msg_type == "PING":
                data = {"type":"PONG"}
                namespace = "urn:x-cast:com.google.cast.tp.heartbeat"
                self.send_data(namespace, data) 
                
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
                applications = status['applications']
                for application in applications:
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
            
            
                    
    def load(self, content_url, content_type):
        """ Launch the player app, load & play a URL """
        
        self.connect("receiver-0")

        self.get_receiver_status()
        
        # we only set the receiver status for MEDIAPLAYER - so if it is set, the app is currenty running
        if self.receiver_app_status is None:
            data = {"type":"LAUNCH","appId":MEDIAPLAYER_APPID}
            namespace = "urn:x-cast:com.google.cast.receiver"
            resp = self.send_msg_with_response(namespace, data)
            
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
        
        namespace = "urn:x-cast:com.google.cast.media"
        resp = self.send_msg_with_response(namespace, data)

        # wait for the player to return either "PLAYING" or "IDLE"
        if resp.get("type", "") == "MEDIA_STATUS":            
            player_state = ""
            while player_state != "PLAYING" and player_state != "IDLE":
                time.sleep(2)        
                
                self.get_media_status()
                
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
        resp = self.send_msg_with_response(namespace, data)
        
        self.close_socket()
                       
    
    
    def get_status(self):
        """ get the receiver and media status """
        
        self.connect("receiver-0")

        self.get_receiver_status()
        
        if self.receiver_app_status is not None:   
            transport_id = str(self.receiver_app_status['transportId']) 
            self.connect(transport_id)
            self.get_media_status()
        
        
        status = {'receiver_status':self.receiver_app_status, 
                  'media_status':self.media_status, 
                  'host':self.host, 
                  'client':self.sock.getsockname()}
                
        self.close_socket()
        
        return status
        
        
        
    def is_idle(self):
        """ return the IDLE state of the player """
        
        status = self.get_status()
        
        if status['receiver_status'] is None:
            return True
            
        if status['media_status']  is None:
            return True
            
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
            

                    
          

        
