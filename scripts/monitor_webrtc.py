import argparse
import asyncio
import logging
import json
import time
import os
import csv
import cv2
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("monitor_receiver")

class MetricsRecorder:
    def __init__(self, filename):
        self.filename = filename
        self.start_time = time.time()
        self.frames_received = 0
        self.bytes_received = 0
        self.last_bytes_received = 0
        self.last_frame_time = time.time()
        self.stalls = 0
        self.total_stall_duration = 0.0
        self.fps_history = []
        self.loss_history = [] # Use this for BBRv3 correlation
        
        # CSV init
        abs_path = os.path.abspath(self.filename)
        logger.info(f"Initializing MetricsRecorder. Writing to: {abs_path}")
        with open(self.filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['timestamp', 'fps', 'stall_duration_ms', 'bitrate_mbps'])
            writer.writeheader()

    def update(self):
        pass

    def on_frame(self):
        now = time.time()
        inter_frame_time = now - self.last_frame_time
        self.frames_received += 1
        
        # Stall detection (> 200ms freeze)
        if inter_frame_time > 0.2:
            self.stalls += 1
            self.total_stall_duration += inter_frame_time
            
        self.last_frame_time = now

    async def log_periodically(self, pc):
        while True:
            await asyncio.sleep(1.0) # Log every second
            now = time.time()
            fps = self.frames_received
            
            # Get Bitrate from WebRTC Stats
            current_bytes = 0
            stats = await pc.getStats()
            for key, report in stats.items():
                if report.type == 'inbound-rtp' and report.kind == 'video':
                    # Safe access to bytesReceived
                    current_bytes = getattr(report, 'bytesReceived', 0)
                    break
            
            # Calculate Mbps
            if self.last_bytes_received > 0:
                bitrate = ((current_bytes - self.last_bytes_received) * 8) / 1_000_000
            else:
                bitrate = 0.0
            
            self.last_bytes_received = current_bytes
            self.frames_received = 0 
            self.bytes_received = 0
                        
            # Log to CSV
            with open(self.filename, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['timestamp', 'fps', 'stall_duration_ms', 'bitrate_mbps'])
                writer.writerow({
                    'timestamp': now - self.start_time,
                    'fps': fps,
                    'stall_duration_ms': self.total_stall_duration * 1000,
                    'bitrate_mbps': bitrate
                })
            
            logger.info(f"Stats: FPS={fps}, Stalls={self.stalls}, Total Stall Time={self.total_stall_duration*1000:.1f}ms")
            self.total_stall_duration = 0 
            self.stalls = 0

async def handle_client(reader, writer, pc, metrics):
    logger.info("Signaling connection accepted")
    
    # Receive Offer
    data = await reader.readline()
    if not data:
        return
    offer_json = json.loads(data.decode())
    offer = RTCSessionDescription(sdp=offer_json["sdp"], type=offer_json["type"])
    
    await pc.setRemoteDescription(offer)
    
    # Create Answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    # Send Answer
    payload = json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
    writer.write(payload.encode() + b"\n")
    await writer.drain()
    
    logger.info("Sent Answer. Waiting for track...")

    # Wait until connection closes
    try:
        await reader.read()
    except:
        pass

def run_server(ip, port, metrics):
    pc = RTCPeerConnection()

    @pc.on("track")
    def on_track(track):
        logger.info(f"Track received: {track.kind}")
        if track.kind == "video":
            async def consume():
                while True:
                    try:
                        frame = await track.recv()
                        metrics.on_frame()
                    except Exception as e:
                        logger.warning(f"Track ended: {e}")
                        break
            asyncio.ensure_future(consume())

    # Start Metrics Logger
    asyncio.ensure_future(metrics.log_periodically(pc))

    # TCP Server for Signaling
    server_coro = asyncio.start_server(
        lambda r, w: handle_client(r, w, pc, metrics), 
        ip, port
    )
    return server_coro, pc

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC Monitor Receiver")
    parser.add_argument("--port", type=int, default=8888, help="Signaling port")
    parser.add_argument("--output", default="gaming_metrics.csv", help="Output CSV file")
    args = parser.parse_args()

    metrics = MetricsRecorder(args.output)
    
    loop = asyncio.get_event_loop()
    server_coro, pc = run_server("0.0.0.0", args.port, metrics)
    server = loop.run_until_complete(server_coro)
    
    logger.info(f"Monitor listening on 0.0.0.0:{args.port}")

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.run_until_complete(pc.close())
