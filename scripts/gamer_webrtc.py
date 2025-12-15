import argparse
import asyncio
import logging
import time
import json
import threading
import os
import sys

import gi
import numpy as np
import fractions
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

gi.require_version('Gst', '1.0')
from gi.repository import Gst
Gst.init(None)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("gamer_sender")

class GStreamerVideoTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self, filename="game_clip.mp4"):
        super().__init__()
        
        if not os.path.exists(filename):
            logger.error(f"FATAL: Video file {filename} NOT FOUND! Falling back to videotestsrc")
            self.source_str = "videotestsrc pattern=ball"
        else:
            abs_path = os.path.abspath(filename).replace("\\", "/")
            # filesrc -> qtdemux -> h264parse -> nvh264dec -> videoconvert -> videoscale -> videorate -> format -> appsink
            
            self.gpu_pipeline_str = (
                f"filesrc location={abs_path} ! qtdemux ! h264parse ! nvh264dec ! "
                "videoconvert ! videoscale ! videorate ! "
                "video/x-raw,format=RGB,width=1280,height=720,framerate=60/1 ! "
                "queue ! "
                "appsink name=sink emit-signals=False max-buffers=1 drop=True"
            )
            
            # CPU Fallback
            uri = f"file://{abs_path}"
            self.cpu_pipeline_str = (
                f"uridecodebin uri={uri} caps=video/x-raw ! videoconvert ! videoscale ! videorate ! "
                "video/x-raw,format=RGB,width=1280,height=720,framerate=60/1 ! "
                "queue ! "
                "appsink name=sink emit-signals=False max-buffers=1 drop=True"
            )

        # Attempt to launch GPU pipeline first
        logger.info("Attempting to launch GPU Pipeline...")
        try:
            self.pipeline = Gst.parse_launch(self.gpu_pipeline_str)
            self.using_gpu = True
        except Exception as e:
            logger.warning(f"GPU Pipeline failed to construct: {e}. Falling back to CPU.")
            self.pipeline = Gst.parse_launch(self.cpu_pipeline_str)
            self.using_gpu = False

        self.sink = self.pipeline.get_by_name("sink")
        self.bus = self.pipeline.get_bus()
        
        self.running = True
        self.current_frame = None
        self.pump_thread = threading.Thread(target=self.pump_loop, daemon=True)
        
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            # If GPU failed at runtime (not just parse), try fallback?
            if self.using_gpu:
                 logger.warning("GPU Pipeline failed validation (State Change). Falling back to CPU...")
                 self.pipeline = Gst.parse_launch(self.cpu_pipeline_str)
                 self.sink = self.pipeline.get_by_name("sink")
                 self.bus = self.pipeline.get_bus()
                 self.using_gpu = False
                 ret = self.pipeline.set_state(Gst.State.PLAYING)

            if ret == Gst.StateChangeReturn.FAILURE:
                logger.error("Failed to set pipeline to PLAYING (CPU Fallback failed too)")
                self.running = False
            else:
                self.pump_thread.start()
        else:
             logger.info(f"Pipeline started successfully. Using GPU: {self.using_gpu}")
             self.pump_thread.start()

    def pump_loop(self):
        logger.info("GStreamer Pump Thread Started")
        while self.running:
            # 1. Message Handling
            msg = self.bus.pop() 
            if msg:
                self.handle_message(msg)

            # 2. Sample Pulling
            try:
                sample = self.sink.emit("try-pull-sample", 5000000) 
                if sample:
                   self.process_sample(sample)
            except Exception as e:
                logger.warning(f"Pull error: {e}")
            
            if not self.pipeline.get_state(0)[1] == Gst.State.PLAYING:
                 time.sleep(0.1)

    def handle_message(self, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            logger.info("EOS. Looping...")
            self.pipeline.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 0)
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"GStreamer Error: {err} - {debug}")
            self.running = False # Don't stop thread, just signal? Or try to recover?

    def process_sample(self, sample):
        buffer = sample.get_buffer()
        if not buffer: return

        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success: return

        try:
            array = np.ndarray(
                shape=(720, 1280, 3),
                dtype=np.uint8,
                buffer=map_info.data
            )
            frame = VideoFrame.from_ndarray(array, format="rgb24")
            self.current_frame = frame
        except Exception as e:
            logger.error(f"Frame creation error: {e}")
        finally:
            buffer.unmap(map_info)

    async def recv(self):
        # await asyncio.sleep(1/60)
        # 60FPS Pacing
        pts_step = 1500
        if not hasattr(self, "_pts"): self._pts = 0
        else: self._pts += pts_step
        pts = self._pts
        
        # Wait logic
        if self.current_frame is None:
            retries = 0
            while self.current_frame is None and retries < 100:
                await asyncio.sleep(0.05)
                retries += 1
            
        if self.current_frame is None:
             logger.warning("No frame available! Sending BLACK frame.")
             frame = VideoFrame(width=1280, height=720, format="rgb24")
        else:
             frame = self.current_frame
        
        frame.pts = int(pts)
        frame.time_base = fractions.Fraction(1, 90000)
        return frame
    
    def stop(self):
        self.running = False
        self.pipeline.set_state(Gst.State.NULL)
        if self.pump_thread.is_alive():
            self.pump_thread.join(timeout=1.0)

async def run(pc, signaling_ip, signaling_port):
    logger.info(f"Connecting to {signaling_ip}:{signaling_port}")
    try:
        reader, writer = await asyncio.open_connection(signaling_ip, signaling_port)
    except OSError as e:
        logger.error(f"Failed to connect signaling: {e}")
        return

    logger.info("Initializing GStreamer Track...")
    try:
        video_track = GStreamerVideoTrack("game_clip.mp4")
        pc.addTrack(video_track)
    except Exception as e:
        logger.error(f"Failed to create track: {e}")
        return

    await pc.setLocalDescription(await pc.createOffer())
    payload = json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
    writer.write(payload.encode() + b"\n")
    await writer.drain()

    data = await reader.readline()
    if not data:
        return
        
    answer_json = json.loads(data.decode())
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer_json["sdp"], type=answer_json["type"]))
    
    logger.info("Streaming Started. Checking NV-SMI...")
    os.system("nvidia-smi") # Check if GPU is visible

    try:
        while True:
            await asyncio.sleep(1)
            if not video_track.running:
                break
    except asyncio.CancelledError:
        pass
    finally:
        video_track.stop()
        writer.close()
        await pc.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--receiver-ip", required=True)
    parser.add_argument("--port", type=int, default=8888)
    args = parser.parse_args()

    pc = RTCPeerConnection()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run(pc, args.receiver_ip, args.port))
    except KeyboardInterrupt:
        pass
