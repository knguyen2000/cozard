#!/usr/bin/env python3
"""
Cloud Gaming Kill-Switch Experiment Orchestrator
Provisions FABRIC slice and runs WebRTC + BBRv3 competition experiment
"""
import os
import sys
import time
import json
import logging
from pathlib import Path
from ipaddress import IPv4Network
from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# FABRIC configuration
fab_dir = os.path.expanduser('~/.fabric')
os.makedirs(fab_dir, exist_ok=True)

os.environ['FABRIC_TOKEN_LOCATION'] = os.path.join(fab_dir, 'id_token.json')
os.environ['FABRIC_BASTION_KEY_LOCATION'] = os.path.join(fab_dir, 'bastion_key')
os.environ['FABRIC_SLICE_PRIVATE_KEY_FILE'] = os.path.join(fab_dir, 'slice_key')
os.environ['FABRIC_SLICE_PUBLIC_KEY_FILE'] = os.path.join(fab_dir, 'slice_key.pub')

os.environ['FABRIC_LOG_LEVEL'] = os.environ.get('FABRIC_LOG_LEVEL', 'INFO')

def provision_gaming_slice(slice_name="cloud_gaming_experiment"):
    """Provision 4-node FABRIC slice for cloud gaming experiment"""
    
    logger.info("="*60)
    logger.info("CLOUD GAMING KILL-SWITCH EXPERIMENT")
    logger.info("="*60)
    
    fablib = fablib_manager()
    
    # Delete existing slice if present
    try:
        slice = fablib.get_slice(name=slice_name)
        logger.info(f"Deleting existing slice '{slice_name}'...")
        slice.delete()
        time.sleep(10)
    except:
        pass
    
    logger.info(f"Creating new slice '{slice_name}'...")
    slice = fablib.new_slice(name=slice_name)
    
    # Resource constraints
    CORES = 2
    RAM = 10
    DISK = 10
    IMAGE = 'default_ubuntu_20'
    SITE = 'SALT'  # Force single site for L2 network
    
    logger.info(f"Target site: {SITE}")
    logger.info(f"Resources per node: {CORES} cores, {RAM}GB RAM, {DISK}GB disk")
    
    # Node A: Gamer/Sender (GPU)
    logger.info("Adding Node A (Gamer/Sender with GPU)...")
    node_a = slice.add_node(name='gamer-a', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
    node_a.add_component(model='GPU_TeslaT4', name='gpu1')
    iface_a = node_a.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
    
    # Node B: Receiver/Monitor (GPU for decoding)
    logger.info("Adding Node B (Receiver/Monitor with GPU)...")
    node_b = slice.add_node(name='receiver-b', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
    node_b.add_component(model='GPU_TeslaT4', name='gpu1')
    iface_b = node_b.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
    
    # Node C: Router/Signaling (CPU only)
    logger.info("Adding Node C (Router/Signaling)...")
    node_c = slice.add_node(name='router-c', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
    iface_c = node_c.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
    
    # Node D: Attacker (CPU only)
    logger.info("Adding Node D (BBRv3 Attacker)...")
    node_d = slice.add_node(name='attacker-d', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
    iface_d = node_d.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
    
    # L2 Network connecting all nodes
    logger.info("Creating L2 network...")
    net = slice.add_l2network(name='gaming_net', interfaces=[iface_a, iface_b, iface_c, iface_d])
    
    # Submit slice request
    logger.info("Submitting slice request to FABRIC...")
    logger.info("(This may take 5-10 minutes...)")
    slice.submit()
    
    logger.info("✓ Slice provisioned successfully")
    
    # Configure network interfaces
    logger.info("\nConfiguring network interfaces...")
    
    # IP addressing scheme
    # Gamer A:    192.168.10.10
    # Receiver B: 192.168.10.11
    # Router C:   192.168.10.12
    # Attacker D: 192.168.10.13
    
    iface_a = slice.get_node('gamer-a').get_interface(network_name='gaming_net')
    iface_a.ip_addr_add(addr='192.168.10.10', subnet=IPv4Network('192.168.10.0/24'))
    iface_a.ip_link_up()
    logger.info("✓ Gamer A: 192.168.10.10")
    
    iface_b = slice.get_node('receiver-b').get_interface(network_name='gaming_net')
    iface_b.ip_addr_add(addr='192.168.10.11', subnet=IPv4Network('192.168.10.0/24'))
    iface_b.ip_link_up()
    logger.info("✓ Receiver B: 192.168.10.11")
    
    iface_c = slice.get_node('router-c').get_interface(network_name='gaming_net')
    iface_c.ip_addr_add(addr='192.168.10.12', subnet=IPv4Network('192.168.10.0/24'))
    iface_c.ip_link_up()
    logger.info("✓ Router C: 192.168.10.12")
    
    iface_d = slice.get_node('attacker-d').get_interface(network_name='gaming_net')
    iface_d.ip_addr_add(addr='192.168.10.13', subnet=IPv4Network('192.168.10.0/24'))
    iface_d.ip_link_up()
    logger.info("✓ Attacker D: 192.168.10.13")
    
    logger.info("\n✓ Network configuration complete")
    
    # Save management IPs for SSH access
    details = {
        "gamer-a": str(slice.get_node('gamer-a').get_management_ip()),
        "receiver-b": str(slice.get_node('receiver-b').get_management_ip()),
        "router-c": str(slice.get_node('router-c').get_management_ip()),
        "attacker-d": str(slice.get_node('attacker-d').get_management_ip())
    }
    
    with open("slice_details.json", "w") as f:
        json.dump(details, f, indent=2)
    
    logger.info(f"\n✓ Slice details saved to slice_details.json")
    
    return slice

def install_dependencies(slice):
    """Install dependencies on all nodes"""
    logger.info("\n" + "="*60)
    logger.info("Installing dependencies on all nodes...")
    logger.info("="*60)
    
    script_path = Path(__file__).parent / "install_dependencies.sh"
    
    for node_name in ['gamer-a', 'receiver-b', 'router-c', 'attacker-d']:
        logger.info(f"\n[{node_name}] Installing dependencies...")
        node = slice.get_node(node_name)
        
        # Upload install script
        node.upload_file(str(script_path), 'install_dependencies.sh')
        
        # Execute installation
        result = node.execute('bash install_dependencies.sh')
        
        if result[0] == 0:
            logger.info(f"✓ [{node_name}] Dependencies installed")
        else:
            logger.error(f"✗ [{node_name}] Installation failed")
            logger.error(result[2])  # stderr
            raise RuntimeError(f"Dependency installation failed on {node_name}")
    
    logger.info("\n✓ All dependencies installed")

def download_test_video(slice):
    """Download test video to sender node"""
    logger.info("\n" + "="*60)
    logger.info("Downloading test video...")
    logger.info("="*60)
    
    node = slice.get_node('gamer-a')
    
    logger.info("Downloading BigBuckBunny.mp4...")
    cmd = "wget -q -O game_clip.mp4 http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
    result = node.execute(cmd, quiet=False)
    
    if result[0] == 0:
        # Verify download
        size_result = node.execute("ls -lh game_clip.mp4")
        logger.info(f"✓ Video downloaded: {size_result[1].strip()}")
    else:
        raise RuntimeError("Failed to download test video")

def run_experiment(slice):
    """Execute the cloud gaming experiment"""
    logger.info("\n" + "="*60)
    logger.info("RUNNING EXPERIMENT")
    logger.info("="*60)
    
    # Upload experiment scripts
    logger.info("\nUploading experiment scripts...")
    script_dir = Path(__file__).parent
    
    router = slice.get_node('router-c')
    router.upload_file(str(script_dir / 'signaling.py'), 'signaling.py')
    
    gamer = slice.get_node('gamer-a')
    gamer.upload_file(str(script_dir / 'gamer_sender.py'), 'gamer_sender.py')
    
    receiver = slice.get_node('receiver-b')
    receiver.upload_file(str(script_dir / 'monitor_receiver.py'), 'monitor_receiver.py')
    
    logger.info("✓ Scripts uploaded")
    
    # Phase 1: Baseline (no competition)
    logger.info("\n[BASELINE] Starting WebRTC stream without competition...")
    
    # Start signaling server
    logger.info("Starting signaling server on Router C...")
    router.execute_thread("python3 signaling.py")
    time.sleep(2)
    
    # Start receiver
    logger.info("Starting receiver on Node B...")
    receiver.execute_thread("python3 monitor_receiver.py ws://192.168.10.12:8443 baseline.csv")
    time.sleep(2)
    
    # Start sender
    logger.info("Starting sender on Node A...")
    gamer.execute_thread("python3 gamer_sender.py ws://192.168.10.12:8443 game_clip.mp4")
    
    logger.info("\n⏳ Running baseline for 15 seconds...")
    time.sleep(15)
    
    # Phase 2: Competition (with BBRv3)
    logger.info("\n[ATTACK] Starting BBRv3 download...")
    
    # Start iperf3 server on gamer node
    gamer.execute_thread("iperf3 -s")
    time.sleep(1)
    
    # Start BBRv3 attack from attacker node
    attacker = slice.get_node('attacker-d')
    logger.info("Launching 10 parallel BBRv3 flows...")
    attacker.execute_thread("iperf3 -c 192.168.10.10 -C bbr -P 10 -t 30")
    
    logger.info("\n⏳ Running competition phase for 30 seconds...")
    time.sleep(30)
    
    # Collect results
    logger.info("\n" + "="*60)
    logger.info("Collecting results...")
    logger.info("="*60)
    
    receiver.download_file('baseline.csv', 'baseline.csv')
    logger.info("✓ Downloaded baseline.csv")
    
    logger.info("\n✓ Experiment complete!")
    logger.info("\nNext steps:")
    logger.info("  1. Analyze baseline.csv for FPS and stall metrics")
    logger.info("  2. Compare baseline vs attack phases")
    logger.info("  3. Generate performance graphs")

def main():
    """Main orchestration"""
    try:
        # Step 1: Provision infrastructure
        slice = provision_gaming_slice()
        
        # Step 2: Install dependencies
        install_dependencies(slice)
        
        # Step 3: Download test video
        download_test_video(slice)
        
        # Step 4: Run experiment
        run_experiment(slice)
        
        logger.info("\n" + "="*60)
        logger.info("✓ EXPERIMENT COMPLETED SUCCESSFULLY")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"\n✗ Experiment failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
