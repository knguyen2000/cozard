#!/usr/bin/env python3
"""
Cloud Gaming Video Sender
GPU-accelerated WebRTC video streaming using GStreamer and Tesla T4
"""
import gi
import asyncio
import websockets
import json
import sys
import os
import logging

gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp, GLib

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Pipeline with GPU encoding (NVENC on Tesla T4)
PIPELINE_DESC = '''
webrtcbin name=sendrecv bundle-policy=max-bundle stun-server=stun://stun.l.google.com:19302
 filesrc location={video_file} ! 
 qtdemux ! h264parse ! avdec_h264 ! 
 videoscale ! video/x-raw,width=1280,height=720 ! 
 nvh264enc preset=low-latency-hq bitrate=5000 zerolatency=true ! 
 h264parse ! 
 rtph264pay config-interval=-1 pt=96 ! 
 queue max-size-buffers=10 ! 
 application/x-rtp,media=video,encoding-name=H264,payload=96 ! 
 sendrecv.
'''

# Fallback pipeline if GPU encoding fails
PIPELINE_DESC_FALLBACK = '''
webrtcbin name=sendrecv bundle-policy=max-bundle stun-server=stun://stun.l.google.com:19302
 filesrc location={video_file} ! 
 qtdemux ! h264parse ! avdec_h264 ! 
 videoscale ! video/x-raw,width=1280,height=720 ! 
 x264enc tune=zerolatency bitrate=5000 speed-preset=ultrafast ! 
 h264parse ! 
 rtph264pay config-interval=-1 pt=96 ! 
 queue max-size-buffers=10 ! 
 application/x-rtp,media=video,encoding-name=H264,payload=96 ! 
 sendrecv.
'''

class WebRTCClient:
    def __init__(self, server_uri, video_file, use_gpu=True):
        self.server_uri = server_uri
        self.conn = None
        self.loop = None
        
        # Try GPU pipeline first
        pipeline_str = PIPELINE_DESC if use_gpu else PIPELINE_DESC_FALLBACK
        pipeline_str = pipeline_str.format(video_file=video_file)
        
        logger.info(f"Creating GStreamer pipeline...")
        logger.info(f"Video source: {video_file}")
        logger.info(f"Encoder: {'nvh264enc (GPU)' if use_gpu else 'x264enc (CPU)'}")
        
        try:
            self.pipe = Gst.parse_launch(pipeline_str)
        except Exception as e:
            if use_gpu:
                logger.warning(f"GPU pipeline failed: {e}")
                logger.info("Falling back to CPU encoding...")
                pipeline_str = PIPELINE_DESC_FALLBACK.format(video_file=video_file)
                self.pipe = Gst.parse_launch(pipeline_str)
            else:
                raise
        
        self.webrtc = self.pipe.get_by_name('sendrecv')
        self.webrtc.connect('on-negotiation-needed', self.on_negotiation_needed)
        self.webrtc.connect('on-ice-candidate', self.send_ice)
        self.webrtc.connect('on-ice-gathering-state-notify', self.on_ice_gathering_state)
        
        # Bus for error handling
        bus = self.pipe.get_bus()
        bus.add_signal_watch()
        bus.connect('message::error', self.on_error)
        bus.connect('message::eos', self.on_eos)
        bus.connect('message::state-changed', self.on_state_changed)
    
    def on_error(self, bus, msg):
        err, debug = msg.parse_error()
        logger.error(f"GStreamer error: {err.message}")
        logger.error(f"Debug info: {debug}")
        self.pipe.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.stop()
    
    def on_eos(self, bus, msg):
        logger.info("End of stream - looping video...")
        self.pipe.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, 0)
    
    def on_state_changed(self, bus, msg):
        if msg.src == self.pipe:
            old_state, new_state, pending = msg.parse_state_changed()
            logger.info(f"Pipeline state: {old_state.value_nick} -> {new_state.value_nick}")
    
    def on_ice_gathering_state(self, webrtc, pspec):
        state = webrtc.get_property('ice-gathering-state')
        logger.info(f"ICE gathering state: {state}")
    
    async def connect(self):
        """Connect to signaling server"""
        logger.info(f"Connecting to signaling server: {self.server_uri}")
        self.conn = await websockets.connect(self.server_uri)
        logger.info("✓ Connected to signaling server")
        
        async for message in self.conn:
            msg = json.loads(message)
            
            if 'sdp' in msg:
                logger.info(f"Received SDP {msg['sdp']['type']}")
                sdp_type = msg['sdp']['type']
                
                if sdp_type == 'answer':
                    _, sdpmsg = GstSdp.SDPMessage.new_from_text(msg['sdp']['sdp'])
                    answer = GstWebRTC.WebRTCSessionDescription.new(
                        GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg
                    )
                    promise = Gst.Promise.new()
                    self.webrtc.emit('set-remote-description', answer, promise)
                    logger.info("✓ Set remote answer")
            
            elif 'ice' in msg:
                ice = msg['ice']
                logger.info(f"Received ICE candidate: {ice['candidate'][:50]}...")
                self.webrtc.emit('add-ice-candidate', ice['sdpMLineIndex'], ice['candidate'])
    
    def on_negotiation_needed(self, element):
        """Create and send offer"""
        logger.info("Negotiation needed - creating offer...")
        promise = Gst.Promise.new_with_change_callback(self.on_offer_created, element, None)
        element.emit('create-offer', None, promise)
    
    def on_offer_created(self, promise, element, _):
        """Send offer to signaling server"""
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value('offer')
        
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', offer, promise)
        
        text = offer.sdp.as_text()
        msg = json.dumps({'sdp': {'type': 'offer', 'sdp': text}})
        
        logger.info("Sending offer to signaling server...")
        asyncio.run_coroutine_threadsafe(self.conn.send(msg), self.loop)
        logger.info("✓ Offer sent")
    
    def send_ice(self, webrtc, mlineindex, candidate):
        """Send ICE candidate to signaling server"""
        msg = json.dumps({
            'ice': {
                'candidate': candidate,
                'sdpMLineIndex': mlineindex
            }
        })
        logger.info(f"Sending ICE candidate {mlineindex}...")
        asyncio.run_coroutine_threadsafe(self.conn.send(msg), self.loop)
    
    def start(self):
        """Start pipeline"""
        logger.info("Starting GStreamer pipeline...")
        ret = self.pipe.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            logger.error("Failed to start pipeline")
            sys.exit(1)
        logger.info("✓ Pipeline started")

async def main():
    if len(sys.argv) < 3:
        print("Usage: python gamer_sender.py <signaling_server_ws_url> <video_file>")
        print("Example: python gamer_sender.py ws://192.168.10.12:8443 game_clip.mp4")
        sys.exit(1)
    
    server_uri = sys.argv[1]
    video_file = sys.argv[2]
    
    if not os.path.exists(video_file):
        logger.error(f"Video file not found: {video_file}")
        sys.exit(1)
    
    Gst.init(None)
    
    client = WebRTCClient(server_uri, video_file, use_gpu=True)
    client.start()
    
    client.loop = asyncio.get_event_loop()
    
    try:
        await client.connect()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        client.pipe.set_state(Gst.State.NULL)

if __name__ == "__main__":
    asyncio.run(main())
