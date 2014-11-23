#!/usr/bin/env python
"""
stream2chromecast.py: Chromecast media streamer for Linux
version 0.1  :-)
"""
import sys, os
import signal
import pychromecast
import time

import BaseHTTPServer
import urllib
from threading import Thread

import subprocess



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
    
Play an unsupported media type (e.g. an mpg file) using ffmpeg as a realtime transcoder (requires ffmpeg installed):-
    %s -ffmpeg <file>
    
Play an unsupported media type (e.g. an mpg file) using avconv as a realtime transcoder (requires avconv installed):-
    %s -avconv <file>    
        
""" % ((script_name,) * 6)

PIDFILE = "/tmp/stream2chromecast.pid"

webserver_ip = None
webserver_port = 8020

FFMPEG = 'ffmpeg -i "%s" -preset ultrafast -c:a libfdk_aac -f mp4 -frag_duration 3600 -b:v 2000k -'
AVCONV = 'avconv -i "%s" -preset ultrafast -c:a aac -f mp4 -frag_duration 3600 -b:v 2000k -strict experimental -'


class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """ Handle HTTP requests for mp4 files which do not need transcoding """
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "video/mp4")
        self.end_headers()
        
        filepath = urllib.unquote_plus(self.path)
        
        self.write_response(filepath)

    def write_response(self, filepath):
        with open(filepath, "r") as f: 
            self.wfile.write(f.read())    


class TranscodingRequestHandler(RequestHandler):
    """ Handle HTTP requests for non mp4 files which require realtime transcoding with ffmpeg """
    transcoder_command = FFMPEG
                    
    def write_response(self, filepath):
        ffmpeg_command = self.transcoder_command % filepath #FFMPEG % filepath
        
        ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, shell=True)

        for line in ffmpeg_process.stdout:
            self.wfile.write(line) 


class AVConvTranscodingRequestHandler(TranscodingRequestHandler):
    """ Handle HTTP requests for non mp4 files which require realtime transcoding with avconv """
    transcoder_command = AVCONV


            
            

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
            os.kill(pid, signal.SIGTERM)    
    except:
        pass
               


def save_pid():
    """ saves the process id of this application in a pid file. """
    with open(PIDFILE, "w") as pidfile:
        pidfile.write("%d" %  os.getpid())
           

def get_chromecast():
    """ create an instance of the chromecast device """
    cast = pychromecast.get_chromecast()

    time.sleep(1)
    print    
    print cast.device
    print
    print cast.status
    print
    print cast.media_controller.status
    print    
    
    return cast



            
def play(filename, transcoder=None):
    """ play a local file on the chromecast """
    global webserver_ip, webserver_port

    if os.path.isfile(filename):
        filename = os.path.abspath(filename)
    else:
        sys.exit("media file not found")
        
    kill_old_pid()
    save_pid()
        
    print "Playing: ", filename
    
    cast = get_chromecast()
    
    webserver_ip = cast.socket_client.socket.getsockname()[0]
    print "my ip address: ", webserver_ip
    
    if not cast.is_idle:
        print "Killing current running app"
        cast.quit_app()
        time.sleep(5)
        
    
    req_handler = RequestHandler
    
    if transcoder == "-ffmpeg":
        if is_transcoder_installed("ffmpeg"):
            req_handler = TranscodingRequestHandler
        elif is_transcoder_installed("avconv"):
            print "unable to find ffmpeg - using avconv"
            req_handler = AVConvTranscodingRequestHandler
        else:
            sys.exit("unable to find ffmpeg (or avconv)")
            
    elif transcoder == "-avconv":
        if is_transcoder_installed("avconv"):
            req_handler = AVConvTranscodingRequestHandler
        elif is_transcoder_installed("ffmpeg"):
            print "unable to find avconv - using ffmpeg"
            req_handler = TranscodingRequestHandler
        else:
            sys.exit("unable to find avconv (or ffmpeg)")
        
            
    server = BaseHTTPServer.HTTPServer((webserver_ip, webserver_port), req_handler)
    
    thread = Thread(target=server.handle_request)
    thread.start()    

    
    url = "http://%s:%s%s" % (webserver_ip, str(webserver_port), urllib.quote_plus(filename, "/"))
    print "Serving media from: ", url


    cast.play_media(url, "video/mp4") 
    
    

    
    
def pause():
    """ pause playback """
    cast = get_chromecast()

    cast.media_controller.pause()
    time.sleep(3)


def unpause():
    """ continue playback """
    cast = get_chromecast()

    cast.media_controller.play()
    time.sleep(3)    

        
def stop():
    """ stop playback and quit the media player app on the chromecast """
    cast = get_chromecast()

    cast.media_controller.stop()
    time.sleep(3)
    
    cast.quit_app()


def run():
    """ main execution """
    
    if len(sys.argv) < 2:
        sys.exit(USAGETEXT)
            
    arg1 = sys.argv[1]
    
    if arg1 == "-stop":
        stop()
    elif arg1 == "-pause":
        pause()        
    elif arg1 == "-continue":
        unpause()           
    elif arg1 in ("-ffmpeg", "-avconv"):
        if len(sys.argv) < 3:
            sys.exit(USAGETEXT) 

        arg2 = sys.argv[2]  
        
        play(arg2, transcoder=arg1)   
    elif arg1 == "-screencast":
        screencast()                 
    else:
        play(arg1)        
        
            
if __name__ == "__main__":
    run()
