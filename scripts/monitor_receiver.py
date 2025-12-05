#!/usr/bin/env python3
"""
Gaming Performance Monitor (WebRTC Receiver)
Measures FPS, stall duration, and bitrate of incoming WebRTC video stream
"""
import gi
import asyncio
import websockets
import json
import sys
import time
import csv
import logging
from collections import deque

gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp, GLib

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PIPELINE_DESC = '''
webrtcbin name=sendrecv bundle-policy=max-bundle stun-server=stun://stun.l.google.com:19302
'''

class PerformanceMonitor:
    """Tracks video streaming performance metrics"""
    
    def __init__(self, output_file='performance.csv'):
        self.output_file = output_file
        self.last_frame_time = None
        self.frame_count = 0
        self.start_time = time.time()
        self.stall_events = []
        self.frame_deltas = deque(maxlen=60)  # Last 60 frames for FPS calculation
        self.total_bytes = 0
        
        # CSV output
        self.csv_file = open(output_file, 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow([
            'timestamp', 'frame_number', 'delta_ms', 'fps', 
            'is_stall', 'bitrate_kbps', 'elapsed_sec'
        ])
        
        logger.info(f"Performance logging to: {output_file}")
    
    def on_frame(self, buffer_size):
        """Called when a frame is received"""
        now = time.time()
        self.frame_count += 1
        self.total_bytes += buffer_size
        
        delta_ms = 0
        is_stall = False
        
        if self.last_frame_time is not None:
            delta_ms = (now - self.last_frame_time) * 1000
            self.frame_deltas.append(delta_ms)
            
            # Detect stall (>100ms between frames at 30fps = ~33ms normal)
            if delta_ms > 100:
                is_stall = True
                self.stall_events.append({
                    'time': now - self.start_time,
                    'duration_ms': delta_ms,
                    'frame': self.frame_count
                })
                logger.warning(f"⚠️  STALL DETECTED: {delta_ms:.1f}ms (frame {self.frame_count})")
        
        self.last_frame_time = now
        
        # Calculate current FPS (average of last 60 frames)
        fps = 0
        if len(self.frame_deltas) > 1:
            avg_delta = sum(self.frame_deltas) / len(self.frame_deltas)
            fps = 1000 / avg_delta if avg_delta > 0 else 0
        
        # Calculate bitrate (last second)
        elapsed = now - self.start_time
        bitrate_kbps = (self.total_bytes * 8) / (elapsed * 1000) if elapsed > 0 else 0
        
        # Log to CSV
        self.csv_writer.writerow([
            f"{now:.3f}",
            self.frame_count,
            f"{delta_ms:.2f}",
            f"{fps:.1f}",
            1 if is_stall else 0,
            f"{bitrate_kbps:.1f}",
            f"{elapsed:.1f}"
        ])
        
        # Periodic console update
        if self.frame_count % 30 == 0:
            logger.info(f"📊 Frame {self.frame_count} | FPS: {fps:.1f} | "
                       f"Bitrate: {bitrate_kbps:.0f} kbps | Stalls: {len(self.stall_events)}")
    
    def print_summary(self):
        """Print final statistics"""
        elapsed = time.time() - self.start_time
        avg_fps = self.frame_count / elapsed if elapsed > 0 else 0
        total_stall_time = sum(s['duration_ms'] for s in self.stall_events)
        
        # Calculate jitter statistics
        import statistics
        jitter_stats = {}
        if len(self.frame_deltas) > 1:
            deltas_list = list(self.frame_deltas)
            jitter_stats['mean'] = statistics.mean(deltas_list)
            jitter_stats['median'] = statistics.median(deltas_list)
            jitter_stats['stdev'] = statistics.stdev(deltas_list) if len(deltas_list) > 1 else 0
            jitter_stats['min'] = min(deltas_list)
            jitter_stats['max'] = max(deltas_list)
            jitter_stats['p95'] = statistics.quantiles(deltas_list, n=20)[18] if len(deltas_list) >= 20 else max(deltas_list)
            jitter_stats['p99'] = statistics.quantiles(deltas_list, n=100)[98] if len(deltas_list) >= 100 else max(deltas_list)
        
        logger.info("\n" + "="*60)
        logger.info("PERFORMANCE SUMMARY")
        logger.info("="*60)
        logger.info(f"Total duration:     {elapsed:.1f} seconds")
        logger.info(f"Total frames:       {self.frame_count}")
        logger.info(f"Average FPS:        {avg_fps:.1f}")
        logger.info(f"Stall events:       {len(self.stall_events)}")
        logger.info(f"Total stall time:   {total_stall_time:.0f} ms")
        logger.info(f"Stall percentage:   {(total_stall_time / (elapsed * 1000) * 100):.1f}%")
        logger.info(f"Average bitrate:    {(self.total_bytes * 8) / (elapsed * 1000):.0f} kbps")
        logger.info("="*60)
        
        # Jitter Analysis (Inter-frame Arrival Time)
        if jitter_stats:
            logger.info("\nJITTER ANALYSIS (Inter-Frame Arrival Time)")
            logger.info("="*60)
            logger.info(f"Mean delta:         {jitter_stats['mean']:.2f} ms")
            logger.info(f"Median delta:       {jitter_stats['median']:.2f} ms")
            logger.info(f"Std deviation:      {jitter_stats['stdev']:.2f} ms")
            logger.info(f"Min delta:          {jitter_stats['min']:.2f} ms")
            logger.info(f"Max delta:          {jitter_stats['max']:.2f} ms")
            logger.info(f"95th percentile:    {jitter_stats['p95']:.2f} ms")
            logger.info(f"99th percentile:    {jitter_stats['p99']:.2f} ms")
            logger.info(f"Jitter variance:    {jitter_stats['stdev']**2:.2f} ms²")
            logger.info("="*60)
            
            # Quality assessment
            if jitter_stats['stdev'] < 5:
                logger.info("✓ Excellent: Very low jitter (< 5ms stdev)")
            elif jitter_stats['stdev'] < 10:
                logger.info("✓ Good: Low jitter (< 10ms stdev)")
            elif jitter_stats['stdev'] < 20:
                logger.info("⚠ Moderate: Noticeable jitter (10-20ms stdev)")
            else:
                logger.info("✗ Poor: High jitter (> 20ms stdev) - Unplayable")
        
        if self.stall_events:
            logger.info("\nTop 5 longest stalls:")
            sorted_stalls = sorted(self.stall_events, key=lambda x: x['duration_ms'], reverse=True)[:5]
            for i, stall in enumerate(sorted_stalls, 1):
                logger.info(f"  {i}. {stall['duration_ms']:.0f}ms at t={stall['time']:.1f}s (frame {stall['frame']})")
    
    def close(self):
        """Close CSV file"""
        self.csv_file.close()
        logger.info(f"✓ Performance data saved to {self.output_file}")

class WebRTCReceiver:
    def __init__(self, server_uri, output_file):
        self.server_uri = server_uri
        self.conn = None
        self.loop = None
        self.monitor = PerformanceMonitor(output_file)
        
        logger.info("Creating GStreamer pipeline...")
        self.pipe = Gst.parse_launch(PIPELINE_DESC)
        self.webrtc = self.pipe.get_by_name('sendrecv')
        
        self.webrtc.connect('pad-added', self.on_incoming_stream)
        self.webrtc.connect('on-ice-candidate', self.send_ice)
        
        # Bus for error handling
        bus = self.pipe.get_bus()
        bus.add_signal_watch()
        bus.connect('message::error', self.on_error)
        bus.connect('message::eos', self.on_eos)
    
    def on_error(self, bus, msg):
        err, debug = msg.parse_error()
        logger.error(f"GStreamer error: {err.message}")
        logger.error(f"Debug info: {debug}")
        self.pipe.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.stop()
    
    def on_eos(self, bus, msg):
        logger.info("End of stream")
        self.monitor.print_summary()
        self.monitor.close()
    
    def on_incoming_stream(self, webrtc, pad):
        """Handle incoming video stream"""
        if pad.direction == Gst.PadDirection.SRC:
            logger.info("✓ Incoming video stream detected")
            
            # Create decode -> measure -> fakesink pipeline
            decode = Gst.ElementFactory.make("decodebin", "decode")
            videoconvert = Gst.ElementFactory.make("videoconvert", "convert")
            sink = Gst.ElementFactory.make("fakesink", "sink")
            sink.set_property("sync", True)  # Sync to clock for realistic timing
            
            self.pipe.add(decode)
            self.pipe.add(videoconvert)
            self.pipe.add(sink)
            
            # Connect elements
            decode.connect("pad-added", self._on_decode_pad, videoconvert)
            videoconvert.link(sink)
            
            # Add probe to measure frames
            sink_pad = sink.get_static_pad("sink")
            sink_pad.add_probe(Gst.PadProbeType.BUFFER, self.on_frame_probe)
            
            # Link and sync
            pad.link(decode.get_static_pad("sink"))
            decode.sync_state_with_parent()
            videoconvert.sync_state_with_parent()
            sink.sync_state_with_parent()
            
            logger.info("✓ Monitoring pipeline ready")
    
    def _on_decode_pad(self, decode, pad, videoconvert):
        """Link decoder to videoconvert when pad is ready"""
        pad.link(videoconvert.get_static_pad("sink"))
    
    def on_frame_probe(self, pad, info):
        """Called for each video frame"""
        buffer = info.get_buffer()
        self.monitor.on_frame(buffer.get_size())
        return Gst.PadProbeReturn.OK
    
    async def connect(self):
        """Connect to signaling server and handle WebRTC signaling"""
        logger.info(f"Connecting to signaling server: {self.server_uri}")
        self.conn = await websockets.connect(self.server_uri)
        logger.info("✓ Connected to signaling server")
        
        async for message in self.conn:
            msg = json.loads(message)
            
            if 'sdp' in msg:
                logger.info(f"Received SDP {msg['sdp']['type']}")
                sdp_type = msg['sdp']['type']
                
                if sdp_type == 'offer':
                    # Set remote offer
                    _, sdpmsg = GstSdp.SDPMessage.new_from_text(msg['sdp']['sdp'])
                    offer = GstWebRTC.WebRTCSessionDescription.new(
                        GstWebRTC.WebRTCSDPType.OFFER, sdpmsg
                    )
                    promise = Gst.Promise.new()
                    self.webrtc.emit('set-remote-description', offer, promise)
                    logger.info("✓ Set remote offer")
                    
                    # Create answer
                    promise = Gst.Promise.new_with_change_callback(self.on_answer_created, None, None)
                    self.webrtc.emit('create-answer', None, promise)
            
            elif 'ice' in msg:
                ice = msg['ice']
                logger.info(f"Received ICE candidate: {ice['candidate'][:50]}...")
                self.webrtc.emit('add-ice-candidate', ice['sdpMLineIndex'], ice['candidate'])
    
    def on_answer_created(self, promise, _, __):
        """Send answer to signaling server"""
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value('answer')
        
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', answer, promise)
        
        text = answer.sdp.as_text()
        msg = json.dumps({'sdp': {'type': 'answer', 'sdp': text}})
        
        logger.info("Sending answer to signaling server...")
        asyncio.run_coroutine_threadsafe(self.conn.send(msg), self.loop)
        logger.info("✓ Answer sent")
    
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
    if len(sys.argv) < 2:
        print("Usage: python monitor_receiver.py <signaling_server_ws_url> [output_csv]")
        print("Example: python monitor_receiver.py ws://192.168.10.12:8443 baseline.csv")
        sys.exit(1)
    
    server_uri = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'performance.csv'
    
    Gst.init(None)
    
    receiver = WebRTCReceiver(server_uri, output_file)
    receiver.start()
    
    receiver.loop = asyncio.get_event_loop()
    
    try:
        await receiver.connect()
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        receiver.monitor.print_summary()
    finally:
        receiver.monitor.close()
        receiver.pipe.set_state(Gst.State.NULL)

if __name__ == "__main__":
    asyncio.run(main())
