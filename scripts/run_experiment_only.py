#!/usr/bin/env python3
import os
import sys
import time
import json
import csv
import logging
import math
from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

fab_dir = os.path.expanduser('~/.fabric')
os.environ['FABRIC_TOKEN_LOCATION'] = os.path.join(fab_dir, 'id_token.json')
os.environ['FABRIC_BASTION_KEY_LOCATION'] = os.path.join(fab_dir, 'bastion_key')
os.environ['FABRIC_SLICE_PRIVATE_KEY_FILE'] = os.path.join(fab_dir, 'slice_key')
os.environ['FABRIC_SLICE_PUBLIC_KEY_FILE'] = os.path.join(fab_dir, 'slice_key.pub')

def get_data_interfaces(node):
    stdout, _ = node.execute("ls /sys/class/net/", quiet=True)
    if not stdout: return []
    return [i for i in stdout.strip().split() 
            if i != 'lo' and 'enp3s' not in i and 'eth0' not in i]

def configure_routed_network(slice):
    logger.info("\n[NETWORK] Configuring L3 Routing...")
    gamer = slice.get_node('gamer-a')
    router = slice.get_node('router-c')
    receiver = slice.get_node('receiver-b')
    attacker = slice.get_node('attacker-d')
    
    r_ifaces = get_data_interfaces(router)
    if not r_ifaces: return
    r_iface = r_ifaces[0]
    router.execute(f"sudo ip addr flush dev {r_iface}")
    router.execute(f"sudo ip addr add 192.168.10.1/24 dev {r_iface}")
    router.execute(f"sudo ip addr add 192.168.20.1/24 dev {r_iface}")
    router.execute(f"sudo ip link set dev {r_iface} up")
    
    # Disable Offloads for accurate TC (Aggressive)
    router.execute(f"sudo ethtool -K {r_iface} tso off gso off gro off sg off", quiet=True)
    
    router.execute("sudo sysctl -w net.ipv4.ip_forward=1")
    router.execute("sudo sysctl -w net.ipv4.conf.all.send_redirects=0")
    
    # Configure Nodes with Retry Logic (Handle SSH Instability after Reboot)
    for node, ip in [(gamer, '10.2'), (attacker, '10.3')]:
        for attempt in range(3):
            try:
                ifaces = get_data_interfaces(node)
                if ifaces:
                    node.execute(f"sudo ip addr flush dev {ifaces[0]}")
                    node.execute(f"sudo ip addr add 192.168.{ip}/24 dev {ifaces[0]}")
                    node.execute(f"sudo ip link set dev {ifaces[0]} up")
                    # Enable IP Forwarding on the router
                    node.execute("sudo sysctl -w net.ipv4.ip_forward=1")
                    node.execute(f"sudo ip route add 192.168.20.0/24 via 192.168.10.1")
                    # Flush IPTABLES to allow ICE/UDP
                    node.execute("sudo iptables -F") 
                    node.execute("sudo iptables -X")
                    node.execute("sudo iptables -P INPUT ACCEPT")
                    node.execute("sudo iptables -P FORWARD ACCEPT")
                    node.execute("sudo iptables -P OUTPUT ACCEPT")
                    # Allow redirected ICMP just in case, but prefer DROP for experiment
                    node.execute("sudo iptables -I INPUT -p icmp --icmp-type redirect -j DROP")
                break # Success
            except Exception as e:
                logger.warning(f"Configuring {node.get_name()} failed (Attempt {attempt+1}/3): {e}")
                time.sleep(5)
        else:
            logger.error(f"Failed to configure {node.get_name()} after 3 attempts.")

    rec_ifaces = get_data_interfaces(receiver)
    if rec_ifaces:
        receiver.execute(f"sudo ip addr flush dev {rec_ifaces[0]}")
        receiver.execute(f"sudo ip addr add 192.168.20.2/24 dev {rec_ifaces[0]}")
        receiver.execute(f"sudo ip link set dev {rec_ifaces[0]} up")
        receiver.execute(f"sudo ip route add 192.168.10.0/24 via 192.168.20.1")
        receiver.execute("sudo iptables -F")
        receiver.execute("sudo iptables -X")
        receiver.execute("sudo iptables -P INPUT ACCEPT")
        receiver.execute("sudo iptables -P FORWARD ACCEPT")
        receiver.execute("sudo iptables -P OUTPUT ACCEPT")
        receiver.execute("sudo iptables -I INPUT -p icmp --icmp-type redirect -j DROP")

    for n in [gamer, router, receiver, attacker]:
        n.execute("sudo ip route flush cache", quiet=True)

    # Verify
    logger.info("Verifying Routing...")
    ping = gamer.execute("ping -c 3 192.168.20.2")
    if "0% packet loss" in ping[0]:
        logger.info("Routing Success")
    else:
        logger.error("Routing Failed")

    logger.info("Checking for ICMP Redirects")
    
    # Check the Kernel's Route Cache
    route_check = gamer.execute("ip route get 192.168.20.2", quiet=True)
    route_output = route_check[0]
    
    # Analyze the Output
    if "cache <redirected>" in route_output:
        logger.error("FAIL: Redirect Detected! The kernel has learned a shortcut.")
        logger.error(route_output)
    elif "via 192.168.10.1" in route_output:
        logger.info("GOOD: Traffic is correctly routed via the Router (10.1).")
    else:
        logger.warning("WARNING: Route path is unclear (Direct link might be active).")
        logger.warning(route_output)

    # ICMP Error Counters
    nstat = gamer.execute("nstat -az | grep IcmpInRedirects", quiet=True)
    if nstat[0]:
        logger.info(f"ICMP Redirect Stats:\n{nstat[0].strip()}")

def check_and_install_gpu_drivers(slice, node):
    logger.info(f"Checking GPU drivers on {node.get_name()}...")
    # Check if nvidia-smi works
    # Check if nvidia-smi works and returns valid status
    stdout, stderr = node.execute("nvidia-smi", quiet=True)
    if stdout and ("Driver Version:" in stdout or "Tesla T4" in stdout):
        logger.info(f"GPU Drivers already operational on {node.get_name()}.")
        return

    logger.info(f"GPU Drivers missing on {node.get_name()}. Installing (this takes ~5-10 mins)...")
    
    # Update and Install
    node.execute("sudo DEBIAN_FRONTEND=noninteractive apt-get update", quiet=True)
    # Install drivers and utils
    node.execute("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-driver-535 nvidia-utils-535 libnvidia-encode-535", quiet=True)
    
    # Reboot
    logger.info(f"Rebooting {node.get_name()} to load drivers...")
    try:
        node.execute("sudo reboot", quiet=True)
    except: pass
    
    time.sleep(20)
    logger.info(f"Waiting for {node.get_name()} to reconnect...")
    slice.wait_ssh(timeout=600) # Give it plenty of time
    
    # Verify
    stdout, stderr = node.execute("nvidia-smi", quiet=True)
    if stdout and ("Driver Version:" in stdout or "Tesla T4" in stdout):
        logger.info(f"SUCCESS: GPU Drivers installed on {node.get_name()}.")
    else:
        logger.warning(f"nvidia-smi failed on {node.get_name()}. Trying 'sudo modprobe nvidia'...")
        node.execute("sudo modprobe nvidia", quiet=True)
        time.sleep(2)
        stdout, stderr = node.execute("nvidia-smi", quiet=True)
        if stdout and ("Driver Version:" in stdout or "Tesla T4" in stdout):
             logger.info(f"SUCCESS: GPU Drivers loaded manually on {node.get_name()}.")
        else:
             logger.error(f"FAIL: GPU Drivers still not working on {node.get_name()} after install/reboot.")
    
    # Verify GStreamer NVENC (Force Registry Rebuild)
    logger.info(f"Rebuilding GStreamer Registry on {node.get_name()}...")
    
    # 1. Clear cache
    node.execute("rm -rf ~/.cache/gstreamer-1.0", quiet=True)
    
    # 2. Trigger re-scan
    node.execute("gst-inspect-1.0 > /dev/null 2>&1", quiet=True) 
    
    # 3. Check for specific plugin availability
    stdout, _ = node.execute("gst-inspect-1.0 nvh264dec", quiet=True)
    if "Factory Details" in stdout:
        logger.info(f"SUCCESS: GStreamer found nvh264dec on {node.get_name()}.")
    else:
        logger.warning(f"FAIL: GStreamer cannot find nvh264dec on {node.get_name()}. checking blacklist...")
        
        # Check blacklist
        stdout, _ = node.execute("gst-inspect-1.0 -b", quiet=True)
        if "nvh264dec" in stdout or "nvcodec" in stdout:
             logger.warning("Plugin IS BLACKLISTED! Possible driver/library mismatch.")
             # Attempt to export drivers path?
        
        # Last ditch: Install bad plugins again
        logger.info("Re-installing gstreamer-plugins-bad...")
        node.execute("sudo apt-get install --reinstall -y gstreamer1.0-plugins-bad", quiet=True)
        node.execute("rm -rf ~/.cache/gstreamer-1.0", quiet=True)
        node.execute("gst-inspect-1.0 > /dev/null", quiet=True)

def setup_nodes(slice):
    """Uploads scripts and installs dependencies on Gamer and Receiver"""
    logger.info("\n[SETUP] Setting up Game Nodes (This may take a while)...")
    gamer = slice.get_node('gamer-a')
    receiver = slice.get_node('receiver-b')
    
    # Files to upload
    script_dir = os.path.dirname(os.path.realpath(__file__))
    root_dir = os.path.dirname(script_dir)
    
    files = [
        (os.path.join(script_dir, "gamer_webrtc.py"), "gamer_webrtc.py"),
        (os.path.join(script_dir, "monitor_webrtc.py"), "monitor_webrtc.py"),
        (os.path.join(root_dir, "requirements.txt"), "requirements.txt")
    ]
    
    for node in [gamer, receiver]:
        logger.info(f"Setting up {node.get_name()}...")
        # Upload
        for local_path, remote_name in files:
            try:
                node.upload_file(local_path, remote_name)
            except Exception as e:
                logger.warning(f"Could not upload {remote_name} (check path): {e}")
        
        # System Deps
        # Install NVIDIA Drivers (Reboot if needed)
        check_and_install_gpu_drivers(slice, node)
        
        node.execute("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-pip libopencv-dev python3-opencv iperf3 libgstreamer1.0-dev gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav python3-gi", quiet=True)
        
        node.execute("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-pip libopencv-dev python3-opencv iperf3 libgstreamer1.0-dev gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav python3-gi", quiet=True)
        # Download Video Clip
        node.execute("wget -O game_clip.mp4 http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4 2>&1", quiet=True)
        
        # Python Deps
        node.execute("pip3 install -r requirements.txt", quiet=True)

def install_bbrv3_kernel(slice, node):
    # 1. Ensure iperf3 is installed (needed for attack)
    node.execute("sudo DEBIAN_FRONTEND=noninteractive apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iperf3", quiet=True)

    # 2. Check Kernel
    kernel = node.execute("uname -r", quiet=True)[0].strip()
    if "bbrv3" in kernel:
        logger.info(f"Node {node.get_name()} already has BBRv3 ({kernel}).")
        return

    logger.info(f"Installing BBRv3 Kernel on {node.get_name()} (Current: {kernel})...")
    base_url = "https://github.com/Zxilly/bbr-v3-pkg/releases/download/2024-10-08-104853"
    headers = "linux-headers-6.4.0-bbrv3_6.4.0-g7542cc7c41c0-1_amd64.deb"
    image = "linux-image-6.4.0-bbrv3_6.4.0-g7542cc7c41c0-1_amd64.deb"
    
    # Download
    node.execute(f"wget -q {base_url}/{headers}")
    node.execute(f"wget -q {base_url}/{image}")
    
    # Install
    logger.info("Installing DEB packages...")
    node.execute(f"sudo DEBIAN_FRONTEND=noninteractive dpkg -i {headers} {image}", quiet=True)
    
    # Reboot to load
    logger.info("Rebooting node... (This will take 1-2 minutes)")
    try:
        node.execute("sudo reboot", quiet=True)
    except: pass 
    
    time.sleep(20) # Give it a moment to go down
    logger.info("Waiting for node to come back online...")
    slice.wait_ssh(timeout=300)
    
    # Verify
    new_kernel = node.execute("uname -r", quiet=True)[0].strip()
    if "bbrv3" in new_kernel:
        logger.info(f"SUCCESS: BBRv3 Kernel Loaded ({new_kernel})")
    else:
        logger.error(f"FAIL: Still running {new_kernel} after reboot!")
        sys.exit(1)

def run_experiment(slice):
    logger.info("\n" + "="*60)
    logger.info("RUNNING EXPERIMENT")
    
    gamer = slice.get_node('gamer-a')
    router = slice.get_node('router-c')
    receiver = slice.get_node('receiver-b')
    attacker = slice.get_node('attacker-d')
    
    setup_nodes(slice)
    
    # Enable BBR on attacker (Check/Install Kernel First)
    install_bbrv3_kernel(slice, attacker)
    attacker.execute("sudo modprobe tcp_bbr && sudo sysctl -w net.ipv4.tcp_congestion_control=bbr", quiet=True)
    
    configure_routed_network(slice)
    
    # Updated Phases with Loss parameter
    phases = [
        {'name': 'baseline', 'attack': False, 'loss': 0, 'desc': 'Baseline (WebRTC Only, 0% Loss)'},
        {'name': 'wired_attack', 'attack': True, 'loss': 0, 'desc': 'Wired Attack (BBRv3, 0% Loss)'},
        {'name': 'lossy_attack', 'attack': True, 'loss': 2, 'desc': 'Lossy Attack (BBRv3, 2% Random Loss)'}
    ]
    
    final_results = []
    
    try:
        for phase in phases:
            logger.info(f"\n--- PHASE: {phase['desc']} ---")
            
            # ROUTER CONFIG
            r_ifaces = get_data_interfaces(router)
            if r_ifaces:
                iface = r_ifaces[0]
                logger.info(f"Configuring Router Queue (Loss: {phase['loss']}%)...")
                router.execute(f"sudo tc qdisc del dev {iface} root", quiet=True)
                
                # 1. Root HTB (Rate Limiter - 40Mbps) - Enforces Hard Cap
                router.execute(f"sudo tc qdisc add dev {iface} root handle 1: htb default 10")
                router.execute(f"sudo tc class add dev {iface} parent 1: classid 1:10 htb rate 40mbit ceil 40mbit")
                
                # Debug: Check if qdisc was applied
                logger.info("TC Configuration Applied:")
                router.execute(f"tc -s qdisc show dev {iface}")

                # 2. FIFO Leaf (NetEm) - Simulates Router Buffer (Drop Tail)
                # limit 1000 packets (~1.5MB) matches typical router buffers
                # 2. FIFO Leaf (NetEm) - Simulates Router Buffer (Drop Tail)
                # limit 1000 packets (~1.5MB) matches typical router buffers
                cmd = f"sudo tc qdisc add dev {iface} parent 1:10 handle 10: netem limit 1000"
                if phase['loss'] > 0:
                     cmd += f" loss {phase['loss']}%"
                
                router.execute(cmd)

            # Cleanup
            for n in [gamer, receiver, attacker]:
                n.execute("pkill -f python3", quiet=True)
                n.execute("pkill -f iperf3", quiet=True)
            time.sleep(2)
            
            # Start Receiver (Monitor) with Logging
            logger.info("Starting WebRTC Monitor (Receiver)...")
            # Redirect stdout/stderr to monitor.log for debugging 0 FPS issue
            receiver.execute_thread("python3 monitor_webrtc.py --port 8888 --local-ip 192.168.20.2 --output gaming_metrics.csv > monitor.log 2>&1")

            if phase['attack']:
                logger.info("Starting iperf3 Server (Receiver)...")
                receiver.execute_thread("iperf3 -s -p 5202")

            time.sleep(5) 
            
            # Start Ping Logger (Background)
            logger.info("Starting Ping Logger (RTT Trends)...")
            ping_cmd = f"ping -i 0.2 -D 192.168.20.2 > ping_{phase['name']}.log"
            gamer.execute_thread(ping_cmd)

            # Start Attack
            attack_throughput = 0.0
            if phase['attack']:
                logger.info("Launching BBRv3 Attack...")
                attacker.execute("rm -f attack.log", quiet=True)
                # Extend attack to 60s to ensure full overlap with 40s game stream (avoiding 'happy ending' bias)
                attacker.execute_thread("iperf3 -c 192.168.20.2 -p 5202 -C bbr -P 5 -t 60 --logfile attack.log")
                time.sleep(5)
            else:
                 # Align baseline timing with attack phases (which have 5s warmup)
                 logger.info("Waiting 5s to align with attack phases...")
                 time.sleep(5)
            
            # Start Gamer (Sender)
            logger.info("Starting WebRTC Stream (Gamer)...")
            gamer.execute_thread(f"python3 gamer_webrtc.py --receiver-ip 192.168.20.2 --port 8888 > gamer.log 2>&1")
            
            rec_iface = get_data_interfaces(receiver)[0]
            start_bytes = int(receiver.execute(f"cat /sys/class/net/{rec_iface}/statistics/rx_bytes", quiet=True)[0].strip())
            
            # Run for 40s
            time.sleep(40)
            
            end_bytes = int(receiver.execute(f"cat /sys/class/net/{rec_iface}/statistics/rx_bytes", quiet=True)[0].strip())
            
            # Stop Everything
            gamer.execute("pkill -f python3", quiet=True)
            gamer.execute("pkill -f ping", quiet=True)
            receiver.execute("pkill -f python3", quiet=True)
            if phase['attack']:
                 attacker.execute("pkill -f iperf3", quiet=True)

            # Log TC stats after run to see if packets were dropped/queued
            if r_ifaces:
                logger.info("TC Stats AFTER run:")
                router.execute(f"tc -s qdisc show dev {iface}")

            time.sleep(2)

            logger.info("Processing metrics...")
            
            # Total Throughput (Receiver Interface)
            total_bytes = end_bytes - start_bytes
            total_mbps = (total_bytes * 8) / (40 * 1_000_000) # Mbps over 40s
            
            try:
                # Ping Logs (from Gamer)
                logger.info(f"Downloading ping log: ping_{phase['name']}.log")
                gamer.download_file(f"ping_{phase['name']}.log", f"ping_{phase['name']}.log")
                
                logger.info(f"Downloading debug logs...")
                receiver.download_file(f"monitor_{phase['name']}.log", "monitor.log") 
                gamer.download_file(f"gamer_{phase['name']}.log", "gamer.log")
            except Exception as e:
                logger.warning(f"Failed to download logs for phase {phase['name']}: {e}")

            # Attack Throughput (iperf3)
            if phase['attack']:
                try:
                    attacker.download_file("attack.log", "attack.log")
                    with open("attack.log", 'r') as f:
                        lines = f.readlines()
                        rates = []
                        
                        # Detect if we have SUM lines (multi-stream)
                        has_sum = any("[SUM]" in line for line in lines)
                        
                        for line in lines:
                            # Determine if we should parse this line
                            parse_line = False
                            if has_sum and "[SUM]" in line:
                                parse_line = True
                            elif not has_sum and "[  " in line: # Standard flow line
                                # Exclude [ ID] lines
                                if "[ ID]" not in line:
                                    parse_line = True
                            
                            if parse_line and "bits/sec" in line:
                                parts = line.split()
                                try:
                                    # Find the number before the unit
                                    # "2.29 Gbits/sec" or "981 Mbits/sec"
                                    for i, part in enumerate(parts):
                                        if "bits/sec" in part: # Mbits/sec, Gbits/sec, Kbits/sec
                                            # Value is at i-1
                                            val_str = parts[i-1]
                                            val = float(val_str)
                                            unit = part
                                            
                                            # Normalize to Mbps
                                            if "Gbits" in unit: val *= 1000
                                            elif "Kbits" in unit: val /= 1000
                                            # Mbits is default
                                            
                                            rates.append(val)
                                            break
                                except: 
                                    pass
                        
                        logger.info(f"Parsed rates: {rates}")
                        if rates:
                            attack_throughput = sum(rates) / len(rates)
                        else:
                            logger.warning("Log empty or parse error, assuming saturation.")
                            attack_throughput = float('nan')

                except Exception as e:
                    logger.warning(f"Could not read attack throughput: {e}")
                    attack_throughput = float('nan')

            # Game Throughput (Derived)
            # Game = Total - Attack (Clamped at 0)
            game_mbps = max(0, total_mbps - attack_throughput)
            
            # Game Quality (FPS/Stalls)
            r_avg_fps = 0
            r_stall_time = 0
            try:
                # Save unique file for this phase
                phase_metrics_file = f"metrics_{phase['name']}.csv"
                receiver.download_file(phase_metrics_file, "gaming_metrics.csv")
                
                with open(phase_metrics_file, 'r') as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    if rows:
                        r_avg_fps = sum(float(r['fps']) for r in rows) / len(rows)
                        r_stall_time = sum(float(r['stall_duration_ms']) for r in rows)
                        # Use Application-Layer Bitrate
                        if 'bitrate_mbps' in rows[0]:
                             game_mbps = sum(float(r['bitrate_mbps']) for r in rows) / len(rows)
                        else:
                             # Fallback if column missing
                             logger.warning("bitrate_mbps column missing in metrics CSV!")
            except Exception as e:
                logger.error(f"Failed to read Game Metrics for {phase['name']}: {e}")

            # Jain's Fairness Index
            j_index = float("nan")

            if phase['attack']:
                game = game_mbps
                attack = attack_throughput

                if math.isnan(game) or (math.isnan(attack) and phase['attack']):
                    logger.warning(
                        f"Skipping Jain index for {phase['name']} due to NaN throughput "
                        f"(game={game}, attack={attack})"
                    )
                elif not phase['attack'] or attack == 0:
                     # Baseline or No Attack -> Perfect Fairness (Single User)
                     j_index = 1.0
                else:
                    total_t = game + attack
                    sum_sq = (game ** 2) + (attack ** 2)

                    if total_t <= 0 or sum_sq <= 0:
                        logger.warning(
                            f"Non-positive throughput when computing Jain index for {phase['name']}: "
                            f"game={game}, attack={attack}"
                        )
                        j_index = float("nan")
                    else:
                        j_index = (total_t ** 2) / (2 * sum_sq)
            
            logger.info(f"Phase Result: FPS={r_avg_fps:.1f}, Stalls={r_stall_time:.0f}ms, Total_Interface={total_mbps:.1f}Mbps, Game_App={game_mbps:.2f}Mbps, Attack={attack_throughput:.2f}Mbps, Jain={j_index:.2f}")

            final_results.append({
                'phase': phase['name'],
                'avg_fps': r_avg_fps,
                'total_stall_ms': r_stall_time,
                'game_mbps': game_mbps,
                'attack_mbps': attack_throughput,
                'j_index': j_index
            })

    finally:
        logger.info("\n[CLEANUP] Stopping processes...")
        for n in [gamer, receiver, attacker]:
             n.execute("pkill -f python3", quiet=True)
             n.execute("pkill -f iperf3", quiet=True)

    # Final Report
    logger.info("Saving 'gaming_metrics.csv'...")
    with open("gaming_metrics.csv", 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['phase', 'avg_fps', 'total_stall_ms', 'game_mbps', 'attack_mbps', 'j_index'])
        writer.writeheader()
        writer.writerows(final_results)

    # Calculate Harm Factor 
    if len(final_results) >= 2:
        baseline = final_results[0]
        wired = final_results[1]
        
        # Kill Switch Logic
        fps_drop = (baseline['avg_fps'] - wired['avg_fps']) / baseline['avg_fps'] if baseline['avg_fps'] > 0 else 0
        if fps_drop > 0.3 or wired['total_stall_ms'] > 1000:
             logger.info("\nACTIVATED!")
        else:
             logger.info("\nFAIL: Stream Survived Attack")

        # Scientific Metrics
        harm_factor = 0
        if baseline['total_stall_ms'] > 0:
            harm_factor = wired['total_stall_ms'] / baseline['total_stall_ms']
        elif wired['total_stall_ms'] > 0:
            harm_factor = 999.0
            
        logger.info(f"\n[RESULT]")
        logger.info(f"Harm Factor (Wired): {harm_factor:.1f}x slower")
        logger.info(f"Fairness Index: {wired['j_index']:.2f} (0=Unfair, 1=Fair)")

    if len(final_results) >= 3:
        lossy = final_results[2]
        l_fps_drop = (baseline['avg_fps'] - lossy['avg_fps']) / baseline['avg_fps'] if baseline['avg_fps'] > 0 else 0
        
        logger.info(f"\n[LOSSY ATTACK RESULT]")
        logger.info(f"Lossy FPS: {lossy['avg_fps']:.1f} (Drop: {l_fps_drop*100:.1f}%)")
        logger.info(f"Lossy Stalls: {lossy['total_stall_ms']:.1f}ms")

def main():
    try:
        fablib = fablib_manager()
        slice = fablib.get_slice(name="cloud_gaming_experiment")
        run_experiment(slice)
    except Exception as e:
        logger.error(e)
        sys.exit(1)

if __name__ == "__main__":
    main()