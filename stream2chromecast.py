#!/usr/bin/env python
"""
stream2chromecast.py: Chromecast media streamer for Linux

version 0.4

=:-)

"""
import sys, os
import signal

from cc_media_controller import CCMediaController
import time

import BaseHTTPServer
import urllib
import mimetypes
from threading import Thread

import subprocess

import httplib
import urlparse

import select


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
    
    
Additional option to specify an Chromecast device by name explicitly:
    e.g. to play a file on a specific device
    %s -devicename <chromecast device name> <file>
    
    
Additional option to specify the preferred transcoder tool when both ffmpeg & avconv are available
    e.g. to play and transcode a file using avconv
    %s -transcoder avconv -transcode <file>
    
    
""" % ((script_name,) * 14)




PIDFILE = "/tmp/stream2chromecast.pid"
FFMPEGPIDFILE = "/tmp/stream2chromecast_ffmpeg.pid"

FFMPEG = 'ffmpeg -i "%s" -preset ultrafast -f mp4 -frag_duration 3000 -b:v 2000k -loglevel error -'
AVCONV = 'avconv -i "%s" -preset ultrafast -f mp4 -frag_duration 3000 -b:v 2000k -loglevel error -'



class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    content_type = "video/mp4"
    
    """ Handle HTTP requests for files which do not need transcoding """
    
    def do_GET(self):
        filepath = urllib.unquote_plus(self.path)
        
        self.send_headers(filepath)       
        
        print "sending file"        
        self.write_response(filepath)


    def send_headers(self, filepath):
        self.protocol_version = "HTTP/1.1"
        self.send_response(200)
        self.send_header("Content-type", self.content_type)
        self.send_header("Content-length", str(os.path.getsize(filepath)))        
        self.end_headers()    


    def write_response(self, filepath):
        with open(filepath, "r") as f: 
            self.wfile.write(f.read())    



class TranscodingRequestHandler(RequestHandler):
    """ Handle HTTP requests for files which require realtime transcoding with ffmpeg """
    transcoder_command = FFMPEG
                    
    def write_response(self, filepath):

        ffmpeg_command = self.transcoder_command % filepath 
        
        ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, shell=True)       

        for line in ffmpeg_process.stdout:
            chunk_size = "%0.2X" % len(line)
            self.wfile.write(chunk_size)
            self.wfile.write("\r\n")
            self.wfile.write(line) 
            self.wfile.write("\r\n")            
            
        self.wfile.write("0")
        self.wfile.write("\r\n\r\n")             
        
        
    def send_headers(self, filepath):
        self.protocol_version = "HTTP/1.1"
        self.send_response(200)
        self.send_header("Content-type", self.content_type)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()             


            
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
       



def kill_old_pid():
    """ attempts to kill a previously running instance of this application. """
    try:
        with open(PIDFILE, "r") as pidfile:
            pid = int(pidfile.read())
            os.killpg(pid, signal.SIGTERM)    
    except:
        pass
               


def save_pid():
    """ saves the process id of this application in a pid file. """
    with open(PIDFILE, "w") as pidfile:
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
    
            
            
def play(filename, transcode=False, transcoder=None, device_name=None):
    """ play a local file on the chromecast """

    if os.path.isfile(filename):
        filename = os.path.abspath(filename)
    else:
        sys.exit("media file %s not found" % filename)
        

    kill_old_pid()
    save_pid()
        
    print "Playing:", filename
    
    transcoder_cmd, probe_cmd = get_transcoder_cmds(preferred_transcoder=transcoder)
        
    mimetype = get_mimetype(filename, probe_cmd)

    
    cast = CCMediaController(device_name=device_name)
    status = cast.get_status()
    webserver_ip = status['client'][0]
    
    print "my ip address:", webserver_ip
        
    
    req_handler = RequestHandler

    
    if transcode:
        if transcoder_cmd == "ffmpeg":  
            req_handler = TranscodingRequestHandler
            req_handler.transcoder_command = FFMPEG
        elif transcoder_cmd == "avconv":   
            req_handler = TranscodingRequestHandler
            req_handler.transcoder_command = AVCONV
    else:
        req_handler.content_type = mimetype
        
    
    # create a webserver to handle a single request on a free port        
    server = BaseHTTPServer.HTTPServer((webserver_ip, 0), req_handler)
    
    thread = Thread(target=server.handle_request)
    thread.start()    

    
    url = "http://%s:%s%s" % (webserver_ip, str(server.server_port), urllib.quote_plus(filename, "/"))
    print "URL & content-type: ", url, req_handler.content_type

    load(cast, url, req_handler.content_type)

    
    

def load(cast, url, mimetype):
    """ load a chromecast instance with a url and wait for idle state """
    try:
        print "loading media..."
        
        cast.load(url, mimetype)
        
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
    
    if resp.status != 200:
        sys.exit("HTTP error:" + resp.status + " - " + resp.reason)
        
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
        
        

def validate_args(args):
    """ validate that there are the correct number of arguments """
    if len(args) < 1:
        sys.exit(USAGETEXT)
        
    if args[0] == "-setvol" and len(args) < 2:
        sys.exit(USAGETEXT) 
    


def get_named_arg_value(arg_name, args):
    """ get a argument value by name """
    arg_val = None
    if arg_name in args:

        arg_pos = args.index(arg_name)
        arg_name = args.pop(arg_pos)
        
        if len(args) > (arg_pos + 1):
            arg_val = args.pop(arg_pos)
            
    return arg_val
    
        

def run():
    """ main execution """
    args = sys.argv[1:]
    
    
    # optional device name parm. if not specified, device_name = None (the first device found will be used).
    device_name = get_named_arg_value("-devicename", args)
    
    # optional transcoder parm. if not specified, ffmpeg will be used, if installed, otherwise avconv.
    transcoder = get_named_arg_value("-transcoder", args)    
    
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
        play(arg2, transcode=True, transcoder=transcoder, device_name=device_name)       
        
    elif args[0] == "-playurl":    
        arg2 = args[1]  
        playurl(arg2, device_name=device_name)                          
        
    elif args[0] == "-devicelist":
        list_devices()
            
    else:
        play(args[0], device_name=device_name)        
        
            
if __name__ == "__main__":
    run()
