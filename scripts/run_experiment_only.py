#!/usr/bin/env python3
"""
Run Iperf3 Network Competition Experiment on EXISTING FABRIC Slice
Measures throughput impact of BBRv3 congestion control competition
"""
import os
import sys
import time
import json
import csv
import logging
from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# FABRIC configuration
fab_dir = os.path.expanduser('~/.fabric')
os.environ['FABRIC_TOKEN_LOCATION'] = os.path.join(fab_dir, 'id_token.json')
os.environ['FABRIC_BASTION_KEY_LOCATION'] = os.path.join(fab_dir, 'bastion_key')
os.environ['FABRIC_SLICE_PRIVATE_KEY_FILE'] = os.path.join(fab_dir, 'slice_key')
os.environ['FABRIC_SLICE_PUBLIC_KEY_FILE'] = os.path.join(fab_dir, 'slice_key.pub')
os.environ['FABRIC_LOG_LEVEL'] = os.environ.get('FABRIC_LOG_LEVEL', 'INFO')

def get_existing_slice(slice_name="cloud_gaming_experiment"):
    """Get handle to existing slice"""
    logger.info("="*60)
    logger.info("IPERF3 NETWORK COMPETITION EXPERIMENT")
    logger.info("="*60)
    
    fablib = fablib_manager()
    
    try:
        slice = fablib.get_slice(name=slice_name)
        logger.info(f"✓ Found existing slice: {slice_name}")
        
        # List nodes
        nodes = slice.get_nodes()
        logger.info(f"Nodes in slice: {[n.get_name() for n in nodes]}")
        
        return slice
    except Exception as e:
        logger.error(f"✗ Could not find slice '{slice_name}'")
        logger.error(f"Error: {e}")
        logger.error("\nPlease run provision_fabric.yml workflow first to create the slice!")
        sys.exit(1)

def run_experiment(slice):
    """Execute iperf3-based network competition experiment"""
    logger.info("\n" + "="*60)
    logger.info("RUNNING IPERF3 NETWORK COMPETITION EXPERIMENT")
    logger.info("="*60)
    
    gamer = slice.get_node('gamer-a')
    attacker = slice.get_node('attacker-d')
    receiver = slice.get_node('receiver-b')
    
    # --- BBRv3 KERNEL INSTALLATION ---
    logger.info("\n[SETUP] Checking kernel version for BBRv3 support...")
    nodes_to_reboot = []
    
    for node_name, node in [('gamer', gamer), ('attacker', attacker), ('receiver', receiver)]:
        kernel_version = node.execute("uname -r")[1].strip()
        logger.info(f"{node_name} kernel: {kernel_version}")
        
        if "bbrv3" not in kernel_version:
            logger.info(f"Installing BBRv3 kernel on {node_name}...")
            
            # Download packages
            base_url = "https://github.com/Zxilly/bbr-v3-pkg/releases/download/2024-10-08-104853"
            headers_deb = "linux-headers-6.4.0-bbrv3_6.4.0-g7542cc7c41c0-1_amd64.deb"
            image_deb = "linux-image-6.4.0-bbrv3_6.4.0-g7542cc7c41c0-1_amd64.deb"
            
            node.execute(f"wget -q {base_url}/{headers_deb}")
            node.execute(f"wget -q {base_url}/{image_deb}")
            
            # Install kernel (non-interactive)
            logger.info(f"Installing packages on {node_name}...")
            node.execute(f"sudo DEBIAN_FRONTEND=noninteractive dpkg -i {headers_deb} {image_deb}")
            
            nodes_to_reboot.append(node)
    
    if nodes_to_reboot:
        logger.info("\n[SETUP] Rebooting nodes to load BBRv3 kernel (this takes ~60s)...")
        for node in nodes_to_reboot:
            # Issue reboot command but don't wait for result (connection closes)
            try:
                node.execute("sudo reboot", quiet=True)
            except Exception:
                pass # Expected connection drop
        
        # Wait for nodes to come back
        logger.info("Waiting for nodes to reboot...")
        time.sleep(60)
        slice.wait_ssh(timeout=300, interval=10)
        logger.info("✓ Nodes back online with BBRv3!")
    else:
        logger.info("✓ All nodes already verified with BBRv3 kernel")

    # Ensure iperf3 is installed on ALL nodes
    logger.info("\n[SETUP] Checking iperf3 installation...")
    for node_name, node in [('gamer', gamer), ('attacker', attacker), ('receiver', receiver)]:
        check = node.execute("which iperf3")
        if not check[1].strip():
            logger.warning(f"iperf3 not found on {node_name}, installing...")
            # Use non-interactive mode to prevent debconf hangs
            node.execute("sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq")
            node.execute("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iperf3")
            logger.info(f"✓ Installed iperf3 on {node_name}")
        else:
            logger.info(f"✓ iperf3 already installed on {node_name}")
    
    # Enable BBRv3 congestion control
    logger.info("\n[SETUP] Enabling BBRv3 congestion control...")
    for node_name, node in [('gamer', gamer), ('attacker', attacker), ('receiver', receiver)]:
        # Load BBR module (v3 is backward compatible with tcp_bbr name)
        node.execute("sudo modprobe tcp_bbr")
        
        # Configure sysctl
        node.execute("echo 'net.core.default_qdisc=fq' | sudo tee -a /etc/sysctl.conf")
        node.execute("echo 'net.ipv4.tcp_congestion_control=bbr' | sudo tee -a /etc/sysctl.conf")
        node.execute("sudo sysctl -p")
        
        # Verify BBR is available
        result = node.execute("sysctl net.ipv4.tcp_available_congestion_control")
        if "bbr" in result[1]:
            logger.info(f"✓ BBR verified on {node_name}")
        else:
            logger.warning(f"⚠ BBR may not be available on {node_name}: {result[1]}")
    
    # Get gamer's IP address on the experiment network
    ip_result = gamer.execute("ip addr show")
    logger.info(f"\nGamer node network config:\n{ip_result[1]}")
    
    # Use the data plane IP (typically 192.168.10.10)
    gamer_ip = "192.168.10.10"
    logger.info(f"Using gamer IP: {gamer_ip}")
    
    results = []
    
    # Phase 1: Baseline - gaming stream with no competition
    logger.info("\n[BASELINE] Testing gaming stream (1 CUBIC flow, NO competition)...")
    gamer.execute("pkill -f iperf3")  # Clean up any existing
    
    # Start iperf3 server on receiver (simulates gaming client)
    receiver_ip = "192.168.10.11"
    receiver.execute("pkill -f iperf3")
    receiver.execute_thread("iperf3 -s > iperf_server.log 2>&1")
    time.sleep(5)  # Wait for server to start
    
    # Gaming stream: gamer -> receiver (CUBIC, represents gaming traffic)
    baseline_result = gamer.execute(f"iperf3 -c {receiver_ip} -t 15 -J 2>&1")
    time.sleep(2)
    
    # Parse iperf3 JSON output
    try:
        # Handle fabric execute return values (can be 2 or 3 elements)
        if len(baseline_result) == 3:
            json_output = baseline_result[1] if baseline_result[1].strip() else baseline_result[2]
        else:
            json_output = baseline_result[0] if baseline_result[0].strip() else baseline_result[1]
            
        baseline_data = json.loads(json_output)
        baseline_throughput = baseline_data['end']['sum_received']['bits_per_second'] / 1_000_000  # Mbps
        logger.info(f"✓ Baseline gaming throughput: {baseline_throughput:.2f} Mbps")
        results.append({
            'phase': 'baseline',
            'duration': 15,
            'throughput_mbps': baseline_throughput,
            'flows': 1,
            'congestion_control': 'cubic',
            'description': 'Gaming stream (no competition)'
        })
    except Exception as e:
        logger.error(f"Failed to parse baseline: {e}")
        logger.error(f"Output: {baseline_result}")
        baseline_throughput = 0
    
    # Phase 2: Attack - gaming stream WITH BBR competition
    logger.info("\n[ATTACK] Testing gaming stream WITH 10 BBR competing flows...")
    receiver.execute("pkill -f iperf3")
    receiver.execute_thread("iperf3 -s > iperf_server.log 2>&1")
    time.sleep(5)  # Wait for server to start
    
    # Start BBR competition from attacker -> gamer (simulates attack traffic)
    gamer.execute("pkill -f iperf3")
    gamer.execute_thread("iperf3 -s -p 5202 > iperf_attack_server.log 2>&1")
    time.sleep(5)  # Wait for server to start
    
    # Launch BBR competing flows in background
    attacker.execute_thread(f"iperf3 -c {gamer_ip} -p 5202 -C bbr -P 10 -t 30 > iperf_attack_client.log 2>&1")
    logger.info("✓ BBR competition started (10 flows attacking gamer)")
    time.sleep(2)  # Let BBR flows ramp up
    
    # Now measure gaming stream throughput WITH competition
    attack_result = gamer.execute(f"iperf3 -c {receiver_ip} -t 15 -J 2>&1")
    time.sleep(2)
    
    try:
        if len(attack_result) == 3:
            json_output = attack_result[1] if attack_result[1].strip() else attack_result[2]
        else:
            json_output = attack_result[0] if attack_result[0].strip() else attack_result[1]
            
        attack_data = json.loads(json_output)
        attack_throughput = attack_data['end']['sum_received']['bits_per_second'] / 1_000_000  # Mbps
        logger.info(f"✓ Gaming throughput under attack: {attack_throughput:.2f} Mbps")
        results.append({
            'phase': 'attack',
            'duration': 15,
            'throughput_mbps': attack_throughput,
            'flows': 1,
            'congestion_control': 'cubic',
            'description': 'Gaming stream (with 10 BBR flows competing)'
        })
    except Exception as e:
        logger.error(f"Failed to parse attack: {e}")
        logger.error(f"Output: {attack_result}")
        attack_throughput = 0
    
    # Clean up
    attacker.execute("pkill -f iperf3")
    gamer.execute("pkill -f iperf3")
    receiver.execute("pkill -f iperf3")
    
    # Generate results CSV
    logger.info("\n" + "="*60)
    logger.info("Generating results CSV...")
    logger.info("="*60)
    
    with open('baseline.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['phase', 'duration', 'throughput_mbps', 'flows', 'congestion_control', 'description'])
        writer.writeheader()
        writer.writerows(results)
    
    logger.info("✓ Created baseline.csv")
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("EXPERIMENT RESULTS - BBR COMPETITION IMPACT")
    logger.info("="*60)
    logger.info(f"Gaming stream (baseline):       {baseline_throughput:.2f} Mbps")
    logger.info(f"Gaming stream (under attack):   {attack_throughput:.2f} Mbps")
    
    if baseline_throughput > 0:
        impact = ((attack_throughput - baseline_throughput) / baseline_throughput) * 100
        degradation = baseline_throughput - attack_throughput
        logger.info(f"Throughput degradation:         {degradation:.2f} Mbps ({impact:.1f}%)")
        logger.info("")
        logger.info("This shows how BBR competing traffic impacts gaming performance!")
    
    logger.info("="*60)
    
    logger.info("\n✓ Experiment complete!")
    logger.info("\nResults show impact of BBR competition on gaming traffic")
    logger.info("baseline.csv contains the throughput measurements")

def main():
    """Main orchestration"""
    try:
        # Step 1: Get existing slice
        slice = get_existing_slice()
        
        # Step 2: Run experiment
        run_experiment(slice)
        
        logger.info("\n" + "="*60)
        logger.info("✓ EXPERIMENT COMPLETED SUCCESSFULLY")
        logger.info("="*60)
        logger.info("\nSlice is still running. To delete it, run:")
        logger.info("  python scripts/delete_slice.py")
        logger.info("Or manually via FABRIC portal")
        
    except Exception as e:
        logger.error(f"\n✗ Experiment failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
