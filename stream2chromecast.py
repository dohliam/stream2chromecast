#!/usr/bin/env python
"""
stream2chromecast.py: Chromecast media streamer for Linux

version 0.3

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



script_name = (sys.argv[0].split(os.sep))[-1]

USAGETEXT = """
Usage

Play a file:-
    %s <file>


Enqueue a file (wait for the Chromecast player to be idle before playing):-
    %s -enqueue <file>
    

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


Set the preferred transcoder command (if both ffmpeg and avconv are installed):-
    %s -set_transcoder <transcoder command>
    
    Note: the transcoder command must be one of "ffmpeg" or "avconv"

    
Set the transcoder quality preset and bitrate:-
    %s -set_transcode_quality <preset> <bitrate>       
    
    Note: The preset value must be one of:-
              ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow, placebo
          The bitrate must be an integer (optionally ending with k) e.g. 2000k

          
Reset the transcoder quality to defaults:-
    %s -reset_transcode_quality  
    
    
Display Chromecast status:
    %s -status    
""" % ((script_name,) * 14)



PIDFILE = "/tmp/stream2chromecast.pid"
FFMPEGPIDFILE = "/tmp/stream2chromecast_ffmpeg.pid"

CONFIGFILE = "~/.stream2chromecast"
DEFAULTCONFIG = {'transcoder':"ffmpeg", 'ffmpeg_preset':"ultrafast", 'ffmpeg_bitrate':"2000k"}


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
        
        ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, shell=True)       

        for line in ffmpeg_process.stdout:
            self.wfile.write(line) 



            
def get_transcoder_cmds():
    """ establish which transcoder utility to use depending on what is installed """
    probe_cmd = None
    transcoder_cmd = None
    
    config = load_config()
    preferred_transcoder = config['transcoder']
    
    ffmpeg_installed = is_transcoder_installed("ffmpeg")
    avconv_installed = is_transcoder_installed("avconv")  
        
    if preferred_transcoder == "ffmpeg":
        if ffmpeg_installed:
            transcoder_cmd = "ffmpeg"
            probe_cmd = "ffprobe"
        elif avconv_installed:
            print "unable to find ffmpeg - using avconv"
            transcoder_cmd = "avconv"
            probe_cmd = "avprobe"
      
    elif preferred_transcoder == "avconv":
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
    
        
def save_transcoder(preferred_transcoder):
    """ save the preferred transcoder command: ffmpeg or avconv """
    if not preferred_transcoder in ("ffmpeg", "avconv"):
        sys.exit("transcoder command must be either ffmpeg or avconv")
        
    config = load_config()
    
    config['transcoder'] = preferred_transcoder
    
    save_config(config)
    
    print "transcoder set to", preferred_transcoder
    
    
                 
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
    
    try:
        with open(filepath, "r") as f:
            lines = f.read().split("\n")
            for line in lines:
                if ":" in line:
                    name, value = line.split(":")
                    if name in config.keys():
                        config[name] = value   
    except IOError:
        pass
        
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
    guess = mimetypes.guess_type(filename)[0].lower()
    if guess is not None:
        if guess.startswith("video/") or guess.startswith("audio/"):
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
    
            
            
def play(filename, transcode=False):
    """ play a local file on the chromecast """

    if os.path.isfile(filename):
        filename = os.path.abspath(filename)
    else:
        sys.exit("media file %s not found" % filename)
        

    kill_old_pid()
    save_pid()
        
    print "Playing: ", filename
    
    transcoder_cmd, probe_cmd = get_transcoder_cmds()
        
    mimetype = get_mimetype(filename, probe_cmd)

    
    cast = CCMediaController()
    status = cast.get_status()
    webserver_ip = status['client'][0]
    
    print "my ip address: ", webserver_ip
        
    
    req_handler = RequestHandler
    req_handler.content_type = mimetype
    
    if transcode:
        if transcoder_cmd == "ffmpeg":  
            req_handler = TranscodingRequestHandler
            req_handler.transcoder_command = FFMPEG
        elif transcoder_cmd == "avconv":   
            req_handler = TranscodingRequestHandler
            req_handler.transcoder_command = AVCONV
    
    # create a webserver to handle a single request on a free port        
    server = BaseHTTPServer.HTTPServer((webserver_ip, 0), req_handler)
    
    thread = Thread(target=server.handle_request)
    thread.start()    

    
    url = "http://%s:%s%s" % (webserver_ip, str(server.server_port), urllib.quote_plus(filename, "/"))
    print "Serving media from: ", url


    cast.load(url, mimetype)
    
    # wait for playback to complete before exiting
    print "waiting for player to finish..."    

    idle = False
    while not idle:
        time.sleep(1)
        idle = cast.is_idle()
    
    
def pause():
    """ pause playback """
    CCMediaController().pause()


def unpause():
    """ continue playback """
    CCMediaController().play()    

        
def stop():
    """ stop playback and quit the media player app on the chromecast """
    CCMediaController().stop()


def get_status():
    """ print the status of the chromecast device """
    print CCMediaController().get_status()

def volume_up():
    """ raise the volume by 0.1 """
    CCMediaController().set_volume_up()


def volume_down():
    """ lower the volume by 0.1 """
    CCMediaController().set_volume_down()


def set_volume(v):
    """ set the volume to level between 0 and 1 """
    CCMediaController().set_volume(v)


def validate_args():
    """ validate that there are the correct number of arguments """
    if len(sys.argv) < 2:
        sys.exit(USAGETEXT)
        
    arg1 = sys.argv[1]
    
    if arg1 == "-set_transcoder":
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
    
    elif arg1 == "-status":
        get_status()

    elif arg1 == "-setvol":
        arg2 = float(sys.argv[2])
        set_volume(arg2)

    elif arg1 == "-volup":
        volume_up()

    elif arg1 == "-voldown":
        volume_down()

    elif arg1 == "-mute":
        set_volume(0)

    elif arg1 in ("-transcode"):    
        arg2 = sys.argv[2]  
        play(arg2, transcode=True)   

    elif arg1 == "-set_transcoder":
        transcoder = sys.argv[2].lower()
        save_transcoder(transcoder) 
            
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
