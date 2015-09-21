Stream2Chromecast
=================

A Chromecast media streamer for Linux.

Stream2Chromecast casts media files to a Chromecast device from Linux.

It will also transcode any unsupported files in real time and play them on the Chromecast.

It is written in Python 2.7 and uses the PyChromecast library to control the device: https://github.com/balloob/pychromecast (Thanks Paulus!)




Installation
------------
We need the python packages requests and protobuf installed.

So, for example, on Ubuntu run:-

    sudo apt-get install python-protobuf python-requests
   
   
   
To play media file types that are unsupported by Chromecast, we need either ffmpeg or avconv installed to do the transcoding.

On Ubuntu we can either install avconv:-

    sudo apt-get install libav-tools
   
...or install ffmpeg

    sudo add-apt-repository ppa:mc3man/trusty-media
    apt-get install ffmpeg
   



Functionality
-------------
To stream supported media files to a Chromecast.

        stream2chromecast.py my_media.mp4


To transcode and stream unsupported media files to a Chromecast.
    (This requires either ffmpeg or avconv to be installed. See Dependencies.)

        stream2chromecast.py -transcode my_mpeg_file.mpg


###Control playback

 - pause playback (currently only works when not transcoding)
   
        stream2chromecast.py -pause
       
 - continue (unpause) playback (currently only works when not transcoding)
   
        stream2chromecast.py -continue
       
 - stop playback
   
        stream2chromecast.py -stop  


###Volume control

 - set volume (takes a value between 0.0 and 1.0)

        stream2chromecast.py -setvol <volume>

 - increase or decrease volume by 0.1
 
        stream2chromecast.py -volup
        stream2chromecast.py -voldown
        
 - mute volume

        stream2chromecast.py -mute
        

###Enqueuing & caching.

By default, playing a media file will not wait for the Chromecast to become idle before playing.
To wait for the Chromecast to finish playing its current media before starting the next one, use the -enqueue parameter.

 - enqueue a supported media file
 
        stream2chromecast.py -enqueue my_media.mp4
        
 - enqueue and transcode an unsupported media file 

        stream2chromecast.py -enqueue -transcode my_mpeg_file.mpg
        
N.B. The Chromecast caches around a minute of media before playing it. This means that the stream2chromecast command completes significantly before the end of media being played.
So, if we then played a second file without the -enqueue parameter, it would terminate the first one about a minute before the end.

For example, imagine a script that plays a list of music videos by running stream2chromecast on each one.
The first instance of the command would complete around a minute before the end of the first video.
The next command would use the -enqueue parameter to wait for the first video to complete playback before starting.


###Configuration

 - set the preferred transcoder (if both ffmpeg and avconv are installed)
    
        stream2chromecast.py -set_transcoder <transcoder command>
        
 The transcoder command value mst be one of ffmpeg or avconv
    

 - set the transcoding quality preset and bitrate

        stream2chromecast.py -set_transcode_quality <preset> <bitrate>       
    
 The preset value must be one of:-
   ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow, placebo.
   
 The bitrate must be an integer (optionally ending with k) e.g. 2000k
      
            
 - reset the transcoding quality and bitrate to defaults:-
        stream2chromecast.py -reset_transcode_quality              
          
###Status

 - get Chromecast status

        stream2chromecast.py -status
        
        
Notes
-----
The real-time transcoding is done by ffmpeg (or avconv) using the ultrafast preset by default. Consequently, by default, the video quality is not as good as it would be if slower presets were used. However, it does allow even modestly powered machines to serve video without buffering. The transcoding preset and bitrate can be adjusted using the "set_transcode_quality" function to improve the quality on more highly powered processors.

avconv is a fork of ffmpeg. It appears that the Ubuntu packagers included avconv in the repositories rather than ffmpeg. However there is a PPA repository available which contains the latest builds of ffmpeg. See the installation notes.


To Do
-----
    Handle multiple Chromecast devices.
    Automatic identification of media types that need transcoding.


License
-------
stream2chromecast.py is GPLv3 licensed.

It depends on the PyChromecast library which is MIT licensed - see https://github.com/balloob/pychromecast


Thanks
------
This project uses the PyChromecast library by Paulus Schoutsen to do the difficult bits.

Thanks to [dohliam](https://github.com/dohliam) for bug fixes and additional functionality.
