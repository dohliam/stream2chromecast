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

Set the transcoder quality preset and bitrate:-
    %s -set_transcode_quality <preset> <bitrate>       
    
    Note: The preset value must be one of:-
              ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow, placebo
          The bitrate must be an integer (optionally ending with k) e.g. 2000k
          
Reset the transcoder quality to defaults:-
    %s -reset_transcode_quality  
""" % ((script_name,) * 8)



PIDFILE = "/tmp/stream2chromecast.pid"

CONFIGFILE = "~/.stream2chromecast"
DEFAULTCONFIG = {'ffmpeg_preset':"ultrafast", 'ffmpeg_bitrate':"2000k"}


FFMPEG = 'ffmpeg -i "%s" -preset %s -c:a libfdk_aac -f mp4 -frag_duration 3600 -b:v %s -'
AVCONV = 'avconv -i "%s" -preset %s -c:a aac -f mp4 -frag_duration 3600 -b:v %s -strict experimental -'


class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    content_type = "video/mp4"
    
    """ Handle HTTP requests for files which do not need transcoding """
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", self.content_type)
        self.end_headers()
        
        filepath = urllib.unquote_plus(self.path)
        
        self.write_response(filepath)

    def write_response(self, filepath):
        with open(filepath, "r") as f: 
            self.wfile.write(f.read())    


class TranscodingRequestHandler(RequestHandler):
    """ Handle HTTP requests for files which require realtime transcoding with ffmpeg """
    transcoder_command = FFMPEG
                    
    def write_response(self, filepath):
        config = load_config()
        ffmpeg_command = self.transcoder_command % (filepath, config['ffmpeg_preset'], config['ffmpeg_bitrate']) 
        
        print "transcoder command:", ffmpeg_command
        
        ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, shell=True)

        for line in ffmpeg_process.stdout:
            self.wfile.write(line) 



            
            

def is_transcoder_installed(transcoder_application):
    """ check for an installation of either ffmpeg or avconv """
    try:
        subprocess.check_output([transcoder_application, "-version"])
        return True
    except OSError:
        return False
    
        
        
def save_transcode_quality(ffmpeg_preset, ffmpeg_bitrate):
    """ store the transcoding quality preset and bitrate """
    if not ffmpeg_preset in ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo"):
        sys.exit("preset value must be one of: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow, placebo")

    check_bitrate_value = ffmpeg_bitrate
    if check_bitrate_value.endswith('k') or check_bitrate_value.endswith('m'):
        check_bitrate_value = check_bitrate_value[:-1]
        
    try:
        int(check_bitrate_value)
    except ValueError:
        sys.exit("bitrate must be an integer value optionally ending with k. For example: 2000k")
        
        
    config = load_config()
    
    config['ffmpeg_preset'] = ffmpeg_preset
    config['ffmpeg_bitrate'] = ffmpeg_bitrate
    
    save_config(config)
    
    
def load_config():
    """ load configuration data from the config file """
    config = DEFAULTCONFIG
    
    filepath = os.path.expanduser(CONFIGFILE)
    print "loading config from: ", filepath    
    
    try:
        with open(filepath, "r") as f:
            lines = f.read().split("\n")
            for line in lines:
                if ":" in line:
                    name, value = line.split(":")
                    if name in config.keys():
                        config[name] = value   
    except IOError:
        print "Unable to load config - using defaults"
        
    return config
    
    
def save_config(config):
    """ store configuration data to the config file """
    filepath = os.path.expanduser(CONFIGFILE)

    try:
        with open(filepath, "w") as f:
            for key in config.keys():
                f.write("%s:%s\n" % (key, config[key]))
    except IOError:
        print "Unable to save config."     



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



def get_mimetype(filename, ffprobe_cmd=None):
    """ find the container format of the file """
    # default value
    mimetype = "video/mp4"
    
    if ffprobe_cmd is None:
        return mimetype
    
    has_video = False
    has_audio = False
    format_name = None
    
    ffprobe_cmd = 'avprobe -show_streams -show_format "%s"' % filename
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
        
    return mimetype
    
            
def play(filename, transcoder=None):
    """ play a local file on the chromecast """

    if os.path.isfile(filename):
        filename = os.path.abspath(filename)
    else:
        sys.exit("media file not found")
        
    kill_old_pid()
    save_pid()
        
    print "Playing: ", filename
    
    ffmpeg_installed = is_transcoder_installed("ffmpeg")
    avprobe_installed = is_transcoder_installed("avconv")
    
    ffprobe_cmd = None
    if ffmpeg_installed:
        ffprobe_cmd = "ffprobe"
    elif avprobe_installed:
        ffprobe_cmd = "avprobe"
        
    mimetype = get_mimetype(filename, ffprobe_cmd)
    
    cast = get_chromecast()
    
    webserver_ip = cast.socket_client.socket.getsockname()[0]
    print "my ip address: ", webserver_ip
    
    if not cast.is_idle:
        print "Killing current running app"
        cast.quit_app()
        time.sleep(5)
        
    
    req_handler = RequestHandler
    req_handler.content_type = mimetype
    
    if transcoder == "-ffmpeg":
        req_handler = TranscodingRequestHandler
        if ffmpeg_installed:
            req_handler.transcoder_command = FFMPEG
        elif avprobe_installed:
            print "unable to find ffmpeg - using avconv"
            req_handler.transcoder_command = AVCONV
        else:
            sys.exit("unable to find ffmpeg (or avconv)")
            
    elif transcoder == "-avconv":
        req_handler = TranscodingRequestHandler
        if avprobe_installed:
            req_handler.transcoder_command = AVCONV
        elif ffmpeg_installed:
            print "unable to find avconv - using ffmpeg"
            req_handler.transcoder_command = FFMPEG
        else:
            sys.exit("unable to find avconv (or ffmpeg)")
        
    
    # create a webserver to handle a single request on a free port        
    server = BaseHTTPServer.HTTPServer((webserver_ip, 0), req_handler)
    
    thread = Thread(target=server.handle_request)
    thread.start()    

    
    url = "http://%s:%s%s" % (webserver_ip, str(server.server_port), urllib.quote_plus(filename, "/"))
    print "Serving media from: ", url


    cast.play_media(url, mimetype) 
    
    

    
    
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


def validate_args():
    """ validate that there are the correct number of arguments """
    if len(sys.argv) < 2:
        sys.exit(USAGETEXT)
        
    arg1 = sys.argv[1]
    
    if arg1 in ("-stop", "-pause", "-continue", "-reset_transcode_quality"):
        return
    elif arg1 in ("-ffmpeg", "-avconv"):
        if len(sys.argv) < 3:
            sys.exit(USAGETEXT) 
    elif arg1 == "-set_transcode_quality":
        if len(sys.argv) < 4:
            sys.exit(USAGETEXT)     
       
        

def run():
    """ main execution """
    
    validate_args()
            
    arg1 = sys.argv[1]
    
    if arg1 == "-stop":
        stop()
        
    elif arg1 == "-pause":
        pause()        
    
    elif arg1 == "-continue":
        unpause()           
    
    elif arg1 in ("-ffmpeg", "-avconv"):
        arg2 = sys.argv[2]  
        play(arg2, transcoder=arg1)   
    
    elif arg1 == "-set_transcode_quality":
        ffmpeg_preset = sys.argv[2].lower()
        ffmpeg_bitrate = sys.argv[3].lower()
        save_transcode_quality(ffmpeg_preset, ffmpeg_bitrate)    

    elif arg1 == "-reset_transcode_quality":
        ffmpeg_preset = DEFAULTCONFIG['ffmpeg_preset']
        ffmpeg_bitrate = DEFAULTCONFIG['ffmpeg_bitrate']
        save_transcode_quality(ffmpeg_preset, ffmpeg_bitrate)                       
    
    else:
        play(arg1)        
        
            
if __name__ == "__main__":
    run()
