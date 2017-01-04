#!/usr/bin/env python
"""
stream2chromecast.py: Chromecast media streamer for Linux

author: Pat Carter - https://github.com/Pat-Carter/stream2chromecast

version: 0.6.3

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


VERSION = "0.6.3"


import sys, os, errno
import signal

from cc_media_controller import CCMediaController
import cc_device_finder
import time

import BaseHTTPServer
import urllib
import mimetypes
from threading import Thread

import subprocess

import httplib
import urlparse

import socket

import tempfile



script_name = (sys.argv[0].split(os.sep))[-1]

USAGETEXT = """
Usage

Play a file:-
    %s <file>
    

Pause the current file:-
    %s -pause


Continue (un-pause) the current file:-
    %s -continue

        
Stop the current file playing:-
    %s -stop


Set the volume to a value between 0 & 1.0  (e.g. 0.5 = half volume):-
    %s -setvol <volume>


Adjust the volume up or down by 0.1:-
    %s -volup
    %s -voldown
    

Mute the volume:-
    %s -mute
    
           
Play an unsupported media type (e.g. an mpg file) using ffmpeg or avconv as a realtime transcoder (requires ffmpeg or avconv to be installed):-
    %s -transcode <file> 


Play remote file using a URL (e.g. a web video):
    %s -playurl <URL>

    
Display Chromecast status:-
    %s -status    
    
    
Search for all Chromecast devices on the network:-
    %s -devicelist
    
    
Additional option to specify an Chromecast device by name (or ip address) explicitly:
    e.g. to play a file on a specific device
    %s -devicename <chromecast device name> <file>
    
    
Additional option to specify the preferred transcoder tool when both ffmpeg & avconv are available
    e.g. to play and transcode a file using avconv
    %s -transcoder avconv -transcode <file>
    
    
Additional option to specify the port from which the media is streamed. This can be useful in a firewalled environment.
    e.g. to serve the media on port 8765
    %s -port 8765 <file>


Additional option to specify subtitles. Only WebVTT format is supported.
    e.g. to cast the subtitles on /path/to/subtitles.vtt
    %s -subtitles /path/to/subtitles.vtt <file>


Additional option to specify the port from which the subtitles is streamed. This can be useful in a firewalled environment.
    e.g. to serve the subtitles on port 8765
    %s -subtitles_port 8765 <file>


Additional option to specify the subtitles language. The language format is defined by RFC 5646.
    e.g. to serve the subtitles french subtitles
    %s -subtitles_language fr <file>

    
Additional option to supply custom parameters to the transcoder (ffmpeg or avconv) output
    e.g. to transcode the media with an output video bitrate of 1000k
    %s -transcode -transcodeopts '-b:v 1000k' <file>

    
Additional option to supply custom parameters to the transcoder input
    e.g. to transcode the media and seek to a position 15 minutes from the start of playback
    %s -transcode -transcodeinputopts '-ss 00:15:00' <file>
    
    
Additional option to specify the buffer size of the data returned from the transcoder. Increasing this can help when on a slow network.
    e.g. to specify a buffer size of 5 megabytes
    %s -transcode -transcodebufsize 5242880 <file>
    
""" % ((script_name,) * 21)




PIDFILE = os.path.join(tempfile.gettempdir(), "stream2chromecast_%s.pid") 

FFMPEG = 'ffmpeg %s -i "%s" -preset ultrafast -f mp4 -frag_duration 3000 -b:v 2000k -loglevel error %s -'
AVCONV = 'avconv %s -i "%s" -preset ultrafast -f mp4 -frag_duration 3000 -b:v 2000k -loglevel error %s -'



class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    content_type = "video/mp4"
    
    """ Handle HTTP requests for files which do not need transcoding """
    
    def do_GET(self):
        
        query = self.path.split("?",1)[-1]
        filepath = urllib.unquote_plus(query)
        
        self.suppress_socket_error_report = None
        
        self.send_headers(filepath)       
        
        print "sending data"      
        try: 
            self.write_response(filepath)
        except socket.error, e:     
            if isinstance(e.args, tuple):
                if e[0] in (errno.EPIPE, errno.ECONNRESET):
                   print "disconnected"
                   self.suppress_socket_error_report = True
                   return
            
            raise


    def handle_one_request(self):
        try:
            return BaseHTTPServer.BaseHTTPRequestHandler.handle_one_request(self)
        except socket.error:
            if not self.suppress_socket_error_report:
                raise


    def finish(self):
        try:
            return BaseHTTPServer.BaseHTTPRequestHandler.finish(self)
        except socket.error:
            if not self.suppress_socket_error_report:
                raise


    def send_headers(self, filepath):
        self.protocol_version = "HTTP/1.1"
        self.send_response(200)
        self.send_header("Content-type", self.content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()    


    def write_response(self, filepath):
        with open(filepath, "rb") as f:           
            while True:
                line = f.read(1024)
                if len(line) == 0:
                    break
            
                chunk_size = "%0.2X" % len(line)
                self.wfile.write(chunk_size)
                self.wfile.write("\r\n")
                self.wfile.write(line) 
                self.wfile.write("\r\n")  
                
        self.wfile.write("0")
        self.wfile.write("\r\n\r\n")                             



class TranscodingRequestHandler(RequestHandler):
    """ Handle HTTP requests for files which require realtime transcoding with ffmpeg """
    transcoder_command = FFMPEG
    transcode_options = ""
    transcode_input_options = ""    
    bufsize = 0
                    
    def write_response(self, filepath):
        if self.bufsize != 0:
            print "transcode buffer size:", self.bufsize
        
        ffmpeg_command = self.transcoder_command % (self.transcode_input_options, filepath, self.transcode_options) 
        
        ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, shell=True, bufsize=self.bufsize)       

        for line in ffmpeg_process.stdout:
            chunk_size = "%0.2X" % len(line)
            self.wfile.write(chunk_size)
            self.wfile.write("\r\n")
            self.wfile.write(line) 
            self.wfile.write("\r\n")            
            
        self.wfile.write("0")
        self.wfile.write("\r\n\r\n")



class SubRequestHandler(RequestHandler):
    """ Handle HTTP requests for subtitles files """
    content_type = "text/vtt;charset=utf-8"



            
def get_transcoder_cmds(preferred_transcoder=None):
    """ establish which transcoder utility to use depending on what is installed """
    probe_cmd = None
    transcoder_cmd = None
    
    ffmpeg_installed = is_transcoder_installed("ffmpeg")
    avconv_installed = is_transcoder_installed("avconv")  
    
    # if anything other than avconv is preferred, try to use ffmpeg otherwise use avconv    
    if preferred_transcoder != "avconv":
        if ffmpeg_installed:
            transcoder_cmd = "ffmpeg"
            probe_cmd = "ffprobe"
        elif avconv_installed:
            print "unable to find ffmpeg - using avconv"
            transcoder_cmd = "avconv"
            probe_cmd = "avprobe"
    
    # otherwise, avconv is preferred, so try to use avconv, followed by ffmpeg  
    else:
        if avconv_installed:
            transcoder_cmd = "avconv"
            probe_cmd = "avprobe"
        elif ffmpeg_installed:
            print "unable to find avconv - using ffmpeg"
            transcoder_cmd = "ffmpeg"
            probe_cmd = "ffprobe"
            
    return transcoder_cmd, probe_cmd
    
    
                

def is_transcoder_installed(transcoder_application):
    """ check for an installation of either ffmpeg or avconv """
    try:
        subprocess.check_output([transcoder_application, "-version"])
        return True
    except OSError:
        return False
       



def kill_old_pid(device_ip):
    """ attempts to kill a previously running instance of this application casting to the specified device. """
    pid_file = PIDFILE % device_ip
    try:
        with open(pid_file, "r") as pidfile:
            pid = int(pidfile.read())
            os.killpg(pid, signal.SIGTERM)    
    except:
        pass
               


def save_pid(device_ip):
    """ saves the process id of this application casting to the specified device in a pid file. """
    pid_file = PIDFILE % device_ip
    with open(pid_file, "w") as pidfile:
        pidfile.write("%d" %  os.getpid())




def get_mimetype(filename, ffprobe_cmd=None):
    """ find the container format of the file """
    # default value
    mimetype = "video/mp4"
    
    
    # guess based on filename extension
    guess = mimetypes.guess_type(filename)[0]
    if guess is not None:
        if guess.lower().startswith("video/") or guess.lower().startswith("audio/"):
            mimetype = guess
      
        
    # use the OS file command...
    try:
        file_cmd = 'file --mime-type -b "%s"' % filename
        file_mimetype = subprocess.check_output(file_cmd, shell=True).strip().lower()
        
        if file_mimetype.startswith("video/") or file_mimetype.startswith("audio/"):
            mimetype = file_mimetype
            
            print "OS identifies the mimetype as :", mimetype
            return mimetype
    except:
        pass
    
    
    # use ffmpeg/avconv if installed
    if ffprobe_cmd is None:
        return mimetype
    
    # ffmpeg/avconv is installed
    has_video = False
    has_audio = False
    format_name = None
    
    ffprobe_cmd = '%s -show_streams -show_format "%s"' % (ffprobe_cmd, filename)
    ffmpeg_process = subprocess.Popen(ffprobe_cmd, stdout=subprocess.PIPE, shell=True)

    for line in ffmpeg_process.stdout:
        if line.startswith("codec_type=audio"):
            has_audio = True
        elif line.startswith("codec_type=video"):
            has_video = True    
        elif line.startswith("format_name="):
            name, value = line.split("=")
            format_name = value.strip().lower().split(",")


    # use the default if it isn't possible to identify the format type
    if format_name is None:
        return mimetype
    
    
    if has_video:
        mimetype = "video/"
    else:
        mimetype = "audio/"
        
    if "mp4" in format_name:
        mimetype += "mp4"            
    elif "webm" in format_name:
        mimetype += "webm"
    elif "ogg" in format_name:
        mimetype += "ogg"        
    elif "mp3" in format_name:
        mimetype = "audio/mpeg"
    elif "wav" in format_name:
        mimetype = "audio/wav" 
    else:   
        mimetype += "mp4"     
        
    return mimetype
    
            
            
def play(filename, transcode=False, transcoder=None, transcode_options=None, transcode_input_options=None,
         transcode_bufsize=0, device_name=None, server_port=None,
         subtitles=None, subtitles_port=None, subtitles_language=None):
    """ play a local file or transcode from a file or URL and stream to the chromecast """
    
    print_ident()
    
    
    cast = CCMediaController(device_name=device_name)
    
    kill_old_pid(cast.host)
    save_pid(cast.host)    


    if os.path.isfile(filename):
        filename = os.path.abspath(filename)
        print "source is file: %s" % filename
    else:
        if transcode and (filename.lower().startswith("http://") or filename.lower().startswith("https://") or filename.lower().startswith("rtsp://")):
            print "source is URL: %s" % filename
        else: 
            sys.exit("media file %s not found" % filename)
        

    
    transcoder_cmd, probe_cmd = get_transcoder_cmds(preferred_transcoder=transcoder)
    

    status = cast.get_status()
    webserver_ip = status['client'][0]
    
    print "local ip address:", webserver_ip
        
    
    req_handler = RequestHandler
    
    if transcode:
        if transcoder_cmd in ("ffmpeg", "avconv"):
            req_handler = TranscodingRequestHandler
            
            if transcoder_cmd == "ffmpeg":  
                req_handler.transcoder_command = FFMPEG
            else:
                req_handler.transcoder_command = AVCONV
                
            if transcode_options is not None:    
                req_handler.transcode_options = transcode_options
                
            if transcode_input_options is not None:    
                req_handler.transcode_input_options = transcode_input_options                
                
            req_handler.bufsize = transcode_bufsize
        else:
            print "No transcoder is installed. Attempting standard playback"
   
    
    
    if req_handler == RequestHandler:
        req_handler.content_type = get_mimetype(filename, probe_cmd)
        
    
    # create a webserver to handle a single request for the media file on either a free port or on a specific port if passed in the port parameter   
    port = 0    
    
    if server_port is not None:
        port = int(server_port)
        
    server = BaseHTTPServer.HTTPServer((webserver_ip, port), req_handler)
    
    thread = Thread(target=server.handle_request)
    thread.start()


    url = "http://%s:%s?%s" % (webserver_ip, str(server.server_port), urllib.quote_plus(filename, "/"))

    print "URL & content-type: ", url, req_handler.content_type


    # create another webserver to handle a request for the subtitles file, if specified in the subtitles parameter
    sub = None

    if subtitles:
        if os.path.isfile(subtitles):
            sub_port = 0

            if subtitles_port is not None:
                sub_port = int(subtitles_port)

            sub_server = BaseHTTPServer.HTTPServer((webserver_ip, sub_port), SubRequestHandler)
            thread2 = Thread(target=sub_server.handle_request)
            thread2.start()

            sub = "http://%s:%s?%s" % (webserver_ip, str(sub_server.server_port), urllib.quote_plus(subtitles, "/"))
            print "sub URL: ", sub
        else:
            print "Subtitles file %s not found" % subtitles


    load(cast, url, req_handler.content_type, sub, subtitles_language)

    
    

def load(cast, url, mimetype, sub=None, sub_language=None):
    """ load a chromecast instance with a url and wait for idle state """
    try:
        print "loading media..."
        
        cast.load(url, mimetype, sub, sub_language)
        
        # wait for playback to complete before exiting
        print "waiting for player to finish - press ctrl-c to stop..."    
        
        idle = False
        while not idle:
            time.sleep(1)
            idle = cast.is_idle()
   
    except KeyboardInterrupt:
        print
        print "stopping..."
        cast.stop()
        
    finally:
        print "done"
    
    
    
def playurl(url, device_name=None):
    """ play a remote HTTP resource on the chromecast """
    
    print_ident()

    def get_resp(url):
        url_parsed = urlparse.urlparse(url)
    
        scheme = url_parsed.scheme
        host = url_parsed.netloc
        path = url.split(host, 1)[-1]
        
        conn = None
        if scheme == "https":
            conn = httplib.HTTPSConnection(host)
        else:
            conn = httplib.HTTPConnection(host)
        
        conn.request("HEAD", path)
    
        resp = conn.getresponse()
        return resp


    def get_full_url(url, location):
        url_parsed = urlparse.urlparse(url)

        scheme = url_parsed.scheme
        host = url_parsed.netloc

        if location.startswith("/") is False:
            path = url.split(host, 1)[-1] 
            if path.endswith("/"):
                path = path.rsplit("/", 2)[0]
            else:
                path = path.rsplit("/", 1)[0] + "/"
            location = path + location

        full_url = scheme + "://" + host + location

        return full_url


    resp = get_resp(url)

    if resp.status != 200:
        redirect_codes = [ 301, 302, 303, 307, 308 ]
        if resp.status in redirect_codes:
            redirects = 0
            while resp.status in redirect_codes:
                redirects += 1
                if redirects > 9:
                    sys.exit("HTTP Error: Too many redirects")
                headers = resp.getheaders()
                for header in headers:
                    if len(header) > 1:
                        if header[0].lower() == "location":
                            redirect_location = header[1]
                if redirect_location.startswith("http") is False:
                    redirect_location = get_full_url(url, redirect_location)
                print "Redirecting to " + redirect_location
                resp = get_resp(redirect_location)
            if resp.status != 200:
                sys.exit("HTTP error:" + str(resp.status) + " - " + resp.reason)
        else:
            sys.exit("HTTP error:" + str(resp.status) + " - " + resp.reason)
        
    print "Found HTTP resource"
    
    headers = resp.getheaders()
    
    mimetype = None
    
    for header in headers:
        if len(header) > 1:
            if header[0].lower() == "content-type":
                mimetype = header[1]
    
    if mimetype != None:            
        print "content-type:", mimetype
    else:
        mimetype = "video/mp4"
        print "resource does not specify mimetype - using default:", mimetype
    
    cast = CCMediaController(device_name=device_name)
    load(cast, url, mimetype)    
    

            
    
def pause(device_name=None):
    """ pause playback """
    CCMediaController(device_name=device_name).pause()


def unpause(device_name=None):
    """ continue playback """
    CCMediaController(device_name=device_name).play()    

        
def stop(device_name=None):
    """ stop playback and quit the media player app on the chromecast """
    CCMediaController(device_name=device_name).stop()


def get_status(device_name=None):
    """ print the status of the chromecast device """
    print CCMediaController(device_name=device_name).get_status()

def volume_up(device_name=None):
    """ raise the volume by 0.1 """
    CCMediaController(device_name=device_name).set_volume_up()


def volume_down(device_name=None):
    """ lower the volume by 0.1 """
    CCMediaController(device_name=device_name).set_volume_down()


def set_volume(v, device_name=None):
    """ set the volume to level between 0 and 1 """
    CCMediaController(device_name=device_name).set_volume(v)
    
    
def list_devices():
    print "Searching for devices, please wait..."
    device_ips = cc_device_finder.search_network(device_limit=None, time_limit=10)
    
    print "%d devices found" % len(device_ips)
    
    for device_ip in device_ips:
        print device_ip, ":", cc_device_finder.get_device_name(device_ip)
        

def print_ident():
    """ display initial messages """
    print
    print "-----------------------------------------"   
    print     
    print "Stream2Chromecast version:%s" % VERSION        
    print 
    print "Copyright (C) 2014-2016 Pat Carter"
    print "GNU General Public License v3.0" 
    print "https://www.gnu.org/licenses/gpl-3.0.html"
    print    
    print "-----------------------------------------"
    print 
    

def validate_args(args):
    """ validate that there are the correct number of arguments """
    if len(args) < 1:
        sys.exit(USAGETEXT)
        
    if args[0] == "-setvol" and len(args) < 2:
        sys.exit(USAGETEXT) 
    


def get_named_arg_value(arg_name, args, integer=False):
    """ get a argument value by name """
    arg_val = None
    if arg_name in args:

        arg_pos = args.index(arg_name)
        arg_name = args.pop(arg_pos)
        
        if len(args) > (arg_pos + 1):
            arg_val = args.pop(arg_pos)
    
    if integer:
        int_arg_val = 0
        if arg_val is not None:
            try:
                int_arg_val = int(arg_val)
            except ValueError:
                print "Invalid integer parameter, defaulting to zero. Parameter name:", arg_name
                
        arg_val = int_arg_val
                
    return arg_val
    
        

def run():
    """ main execution """
    args = sys.argv[1:]
    
    
    # optional device name parm. if not specified, device_name = None (the first device found will be used).
    device_name = get_named_arg_value("-devicename", args)
    
    # optional transcoder parm. if not specified, ffmpeg will be used, if installed, otherwise avconv.
    transcoder = get_named_arg_value("-transcoder", args)    
    
    # optional server port parm. if not specified, a random available port will be used
    server_port = get_named_arg_value("-port", args)     
    
    # optional transcode options parm. if specified, these options will be passed to the transcoder to be applied to the output
    transcode_options = get_named_arg_value("-transcodeopts", args)     
    
    # optional transcode options parm. if specified, these options will be passed to the transcoder to be applied to the input data
    transcode_input_options = get_named_arg_value("-transcodeinputopts", args)      
    
    # optional transcode bufsize parm. if specified, the transcoder will buffer approximately this many bytes of output
    transcode_bufsize = get_named_arg_value("-transcodebufsize", args, integer=True)

    # optional subtitle parm. if specified, the specified subtitles will be played.
    subtitles = get_named_arg_value("-subtitles", args)

    # optional subtitle_port parm. if not specified, a random available port will be used.
    subtitles_port = get_named_arg_value("-subtitles_port", args)

    # optional subtitle_language parm. if not specified en-US will be used.
    subtitles_language = get_named_arg_value("-subtitles_language", args)


        
    validate_args(args)
    
    if args[0] == "-stop":
        stop(device_name=device_name)
        
    elif args[0] == "-pause":
        pause(device_name=device_name)        
    
    elif args[0] == "-continue":
        unpause(device_name=device_name)           
    
    elif args[0] == "-status":
        get_status(device_name=device_name)

    elif args[0] == "-setvol":
        set_volume(float(args[1]), device_name=device_name)

    elif args[0] == "-volup":
        volume_up(device_name=device_name)

    elif args[0] == "-voldown":
        volume_down(device_name=device_name)

    elif args[0] == "-mute":
        set_volume(0, device_name=device_name)

    elif args[0] == "-transcode":    
        arg2 = args[1]  
        play(arg2, transcode=True, transcoder=transcoder, transcode_options=transcode_options, transcode_input_options=transcode_input_options, transcode_bufsize=transcode_bufsize,
             device_name=device_name, server_port=server_port, subtitles=subtitles, subtitles_port=subtitles_port,
             subtitles_language=subtitles_language)
        
    elif args[0] == "-playurl":    
        arg2 = args[1]  
        playurl(arg2, device_name=device_name)                          
        
    elif args[0] == "-devicelist":
        list_devices()
            
    else:
        play(args[0], device_name=device_name, server_port=server_port, subtitles=subtitles,
             subtitles_port=subtitles_port, subtitles_language=subtitles_language)
        
            
if __name__ == "__main__":
    run()
