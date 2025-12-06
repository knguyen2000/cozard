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

def configure_network(slice):
    """
    Configures IP addresses on data plane interfaces after reboot.
    Uses robust Python-side filtering to find the correct interface.
    """
    logger.info("\n[NETWORK] Configuring Data Plane IPs...")
    
    # Define the IP scheme for the experiment
    node_configs = {
        'gamer-a':    '192.168.10.10',
        'receiver-b': '192.168.10.11',
        'attacker-d': '192.168.10.12'
    }

    for node_name, ip_address in node_configs.items():
        try:
            node = slice.get_node(node_name)
        except Exception:
            logger.warning(f"Node {node_name} not found, skipping config.")
            continue
        
        # 1. Get list of all interfaces directly from sysfs
        # This avoids issues with 'ip' command formatting or awk/grep failures
        stdout, stderr = node.execute("ls /sys/class/net/")
        if not stdout:
            logger.error(f"Failed to list interfaces on {node_name}")
            continue
            
        all_interfaces = stdout.strip().split()
        
        # 2. Filter in Python (safer than shell pipes)
        # We look for interfaces that are NOT 'lo' (loopback) and NOT 'enp3s0' (management)
        # distinct from the management interface (usually enp3s0 or eth0)
        valid_ifaces = [iface for iface in all_interfaces 
                        if iface != 'lo' 
                        and 'enp3s0' not in iface 
                        and 'eth0' not in iface]
        
        if not valid_ifaces:
            logger.error(f"Could not find data interface for {node_name}. Found only: {all_interfaces}")
            continue
            
        # Pick the first valid interface (likely enp7s0 or enp8s0)
        iface_name = valid_ifaces[0]

        logger.info(f"Configuring {node_name}: Found {iface_name} -> Assigning {ip_address}")
        
        # 3. Configure IP and bring interface UP
        node.execute(f"sudo ip addr flush dev {iface_name}")
        node.execute(f"sudo ip addr add {ip_address}/24 dev {iface_name}")
        node.execute(f"sudo ip link set dev {iface_name} up")

    # 4. Verify connectivity (Ping test)
    logger.info("Verifying connectivity (Gamer -> Receiver)...")
    gamer = slice.get_node('gamer-a')
    
    # Allow a few seconds for links to come up
    time.sleep(2)
    ping_res = gamer.execute("ping -c 3 192.168.10.11")
    
    if "0% packet loss" in ping_res[1]:
        logger.info("✓ Network is reachable")
    else:
        logger.error("✗ Network is still unreachable")
        logger.error(ping_res[1])

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
    
    # Configure network after potential reboot
    configure_network(slice)
    
    # Get gamer's IP address on the experiment network
    ip_result = gamer.execute("ip addr show")
    logger.info(f"\nGamer node network config:\n{ip_result[1]}")
    
    # Use the data plane IP (typically 192.168.10.10)
    gamer_ip = "192.168.10.10"
    logger.info(f"Using gamer IP: {gamer_ip}")
    
    # --- EXPERIMENT PHASES ---
    phases = [
        {'name': 'baseline', 'cc': None, 'desc': 'Baseline (No Competition)'},
        {'name': 'attack_bbr1', 'cc': 'bbr1', 'desc': 'Competition (10 BBRv1 flows)'},
        {'name': 'attack_bbr3', 'cc': 'bbr', 'desc': 'Competition (10 BBRv3 flows)'}
    ]
    
    experiment_results = []
    
    for phase in phases:
        logger.info("\n" + "="*60)
        logger.info(f"PHASE: {phase['desc']}")
        logger.info("="*60)
        
        # Cleanup previous runs
        gamer.execute("pkill -f iperf3")
        attacker.execute("pkill -f iperf3")
        receiver.execute("pkill -f iperf3")
        time.sleep(2)
        
        # 1. Start Receiver (Gamer Stream Server)
        # Receiver listens for gaming stream
        receiver_ip = "192.168.10.11"
        receiver.execute_thread("iperf3 -s > iperf_server.log 2>&1")
        time.sleep(5)
        
        # 2. Setup Competition (if not baseline)
        if phase['cc']:
            logger.info(f"Starting {phase['desc']}...")
            
            # Start Server on Gamer (to receive attack traffic from Attacker)
            # Attacker -> Gamer
            gamer.execute_thread("iperf3 -s -p 5202 > iperf_attack_server.log 2>&1")
            time.sleep(5)
            
            # Start Attacker Clients (10 flows)
            # Note: We use the specific CC algorithm here (-C bbr1 or -C bbr)
            attacker.execute_thread(f"iperf3 -c {gamer_ip} -p 5202 -C {phase['cc']} -P 10 -t 30 > iperf_attack_client.log 2>&1")
            logger.info(f"Started 10 competing flows using {phase['cc']}")
            time.sleep(5) # Allow ramp up
            
        # 3. Measurement (Gamer Client -> Receiver)
        # We always use CUBIC for the gamer stream (simulating standard app)
        logger.info("Measuring Gamer Throughput (CUBIC)...")
        # Ensure we capture standard error too
        result = gamer.execute(f"iperf3 -c {receiver_ip} -t 15 -C cubic -J 2>&1")
        
        try:
            # Handle potential 2 or 3 tuple return
            if len(result) == 3:
                json_out = result[1] if result[1].strip() else result[2]
            else:
                json_out = result[0] if result[0].strip() else result[1]
                
            data = json.loads(json_out)
            throughput = data['end']['sum_received']['bits_per_second'] / 1_000_000
            
            logger.info(f"✓ Result: {throughput:.2f} Mbps")
            
            experiment_results.append({
                'phase': phase['name'],
                'throughput_mbps': throughput,
                'competition': phase['cc'] if phase['cc'] else 'none',
                'description': phase['desc']
            })
            
        except Exception as e:
            logger.error(f"Failed to parse result: {e}")
            logger.error(result)

    # Clean up
    attacker.execute("pkill -f iperf3")
    gamer.execute("pkill -f iperf3")
    receiver.execute("pkill -f iperf3")
    
    # Generate CSV
    logger.info("\nGenerating comparisons.csv...")
    with open('comparisons.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['phase', 'throughput_mbps', 'competition', 'description'])
        writer.writeheader()
        writer.writerows(experiment_results)
        
    logger.info("✓ Created comparisons.csv")

    # Generate Local Graph (if possible)
    try:
        import matplotlib.pyplot as plt
        
        df = experiment_results
        names = ['Baseline', 'BBRv1 Attack', 'BBRv3 Attack']
        # Helper to get values safely
        def get_val(pname):
            for x in df:
                if x['phase'] == pname:
                    return x['throughput_mbps']
            return 0
            
        values = [get_val('baseline'), get_val('attack_bbr1'), get_val('attack_bbr3')]
        colors = ['green', 'orange', 'red']
        
        plt.figure(figsize=(10, 6))
        bars = plt.bar(names, values, color=colors, edgecolor='black')
        plt.title('Network Throughput: BBRv1 vs BBRv3 Competition')
        plt.ylabel('User Throughput (Mbps)')
        plt.grid(axis='y', alpha=0.3)
        
        # Add labels
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                plt.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height:.0f} Mbps', ha='center', va='bottom', fontweight='bold')
                     
        plt.savefig('comparison_graph.png')
        logger.info("✓ Generated comparison_graph.png locally")
        
        # Print summary table
        logger.info("\nSummary:")
        for res in experiment_results:
            logger.info(f"{res['description']:<30}: {res['throughput_mbps']:.2f} Mbps")
            
    except ImportError:
        logger.warning("matplotlib not found, skipping local graph generation. apt-get install python3-matplotlib if needed.")

    logger.info("\n✓ Experiment complete!")

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
