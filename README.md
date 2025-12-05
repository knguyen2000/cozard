# Cloud Gaming Kill-Switch Experiment

> **Testing if BBRv3 downloads "kill" WebRTC cloud gaming streams on L4S networks**

This experiment uses real WebRTC video encoded on Tesla T4 GPUs to test network competition, moving beyond synthetic iperf3 traffic used in most L4S research.

## Overview

**Hypothesis**: A massive BBRv3 TCP download will starve a low-latency WebRTC gaming stream, causing frame stalls and FPS drops, even though L4S promises low latency.

**Hardware**: FABRIC testbed with Tesla T4 GPUs for NVENC hardware encoding

**Metrics**: FPS, stall duration (frame gaps >100ms), bitrate

## Architecture

```
4-Node Topology:
┌─────────────┐     ┌─────────────┐
│  Gamer A    │────▶│ Receiver B  │  WebRTC Stream
│  (GPU+NVENC)│     │  (Monitor)  │  (L4S marked)
└─────────────┘     └─────────────┘
      │                    │
      └────────┬───────────┘
               │
         ┌─────┴──────┐
         │  Router C  │  (Signaling + Legacy FIFO)
         └─────┬──────┘
               │
        ┌──────┴────────┐
        │  Attacker D   │  (BBRv3 iperf3)
        └───────────────┘
```

## Quick Start

### Local Setup (Manual)

```bash
# 1. Install dependencies
cd scripts
bash install_dependencies.sh

# 2. Download test video
wget -O game_clip.mp4 http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4

# 3. Start signaling server
python3 signaling.py

# 4. Start receiver (in another terminal)
python3 monitor_receiver.py ws://192.168.10.12:8443 baseline.csv

# 5. Start sender (in another terminal)
python3 gamer_sender.py ws://192.168.10.12:8443 game_clip.mp4

# 6. Launch BBRv3 attack (in another terminal)
iperf3 -c <gamer_ip> -C bbr -P 10 -t 30
```

### GitHub Actions (Automated)

1. Configure FABRIC secrets in GitHub repository
2. Manually trigger workflow: **Actions** → **Cloud Gaming Kill-Switch Experiment** → **Run workflow**
3. Wait ~30-45 minutes for provisioning + experiment
4. Download artifacts: `baseline.csv`, `gaming_performance.png`

## Scripts

| File                       | Description                                         |
| -------------------------- | --------------------------------------------------- |
| `signaling.py`             | WebRTC signaling server (WebSocket broker)          |
| `gamer_sender.py`          | GPU-accelerated video sender (NVENC)                |
| `monitor_receiver.py`      | Performance monitor with FPS/stall tracking         |
| `run_gaming_experiment.py` | Main orchestrator (FABRIC provisioning + execution) |
| `install_dependencies.sh`  | Dependency installer (GStreamer, WebRTC, iperf3)    |

## Experiment Phases

1. **Baseline (15s)**: WebRTC stream without competition

   - Measure steady-state FPS (target: 30-60 FPS)
   - Record baseline latency and bitrate

2. **Attack (30s)**: BBRv3 download starts
   - 10 parallel iperf3 flows from Attacker D
   - Monitor FPS drops, stall events, bitrate changes

## Output

- **`baseline.csv`**: Frame-by-frame metrics

  ```csv
  timestamp,frame_number,delta_ms,fps,is_stall,bitrate_kbps,elapsed_sec
  1733456789.123,1,0.00,0.0,0,0.0,0.0
  1733456789.156,2,33.20,30.1,0,4523.2,0.0
  1733456789.503,3,347.50,2.9,1,4892.1,0.4  # STALL!
  ```

- **`gaming_performance.png`**: Visualization graphs
  - FPS over time
  - Stall events scatter plot
  - Bitrate timeline

## Expected Results

**If BBRv3 causes stalls**:

- Multiple frame gaps >100ms during attack phase
- FPS drops below 20
- Proves BBRv3 breaks gaming streams on legacy routers

**If L4S survives**:

- Steady FPS throughout
- <5% frame loss
- Validates L4S robustness

## Hardware Requirements

- **GPU**: Tesla T4 with NVENC support
- **Disk**: ~1GB per node (GStreamer + dependencies)
- **Network**: L2 network (single FABRIC site)

## Research Significance

This moves beyond synthetic iperf3 tests to **real-world WebRTC traffic**, making results more meaningful for:

- Cloud gaming platforms (Stadia, GeForce NOW)
- Video conferencing (Zoom, Teams)
- Live streaming applications

**Novel contribution**: First work testing BBRv3 competition against GPU-encoded WebRTC streams.

## References

- [FABRIC Testbed](https://portal.fabric-testbed.net/)
- [L4S Architecture](https://datatracker.ietf.org/doc/html/rfc9330)
- [BBRv3 Spec](https://datatracker.ietf.org/doc/draft-cardwell-iccrg-bbr-congestion-control/)
- [GStreamer WebRTC](https://gstreamer.freedesktop.org/documentation/webrtc/index.html)

## License

MIT
