#!/usr/bin/env python3
"""
Run Cloud Gaming Experiment on EXISTING FABRIC Slice
This script assumes the slice already exists and just runs the experiment
"""
import os
import sys
import time
import logging
from pathlib import Path
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
    logger.info("CLOUD GAMING EXPERIMENT - Using Existing Slice")
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

def install_dependencies(slice):
    """Install dependencies on all nodes"""
    logger.info("\n" + "="*60)
    logger.info("Installing/Updating dependencies...")
    logger.info("="*60)
    
    script_path = Path(__file__).parent / "install_dependencies.sh"
    
    for node_name in ['gamer-a', 'receiver-b', 'router-c', 'attacker-d']:
        logger.info(f"\n[{node_name}] Uploading install script...")
        node = slice.get_node(node_name)
        
        # Upload install script
        node.upload_file(str(script_path), 'install_dependencies.sh')
        
        # Execute installation
        logger.info(f"[{node_name}] Running installation...")
        result = node.execute('bash install_dependencies.sh')
        
        if result[0] == 0:
            logger.info(f"✓ [{node_name}] Dependencies ready")
        else:
            logger.warning(f"⚠ [{node_name}] Installation had issues (may already be installed)")
    
    logger.info("\n✓ Dependencies check complete")

def download_test_video(slice):
    """Download test video to sender node"""
    logger.info("\n" + "="*60)
    logger.info("Checking test video...")
    logger.info("="*60)
    
    node = slice.get_node('gamer-a')
    
    # Check if already downloaded
    check_result = node.execute("ls game_clip.mp4 2>/dev/null")
    if check_result[0] == 0:
        logger.info("✓ Test video already exists, skipping download")
        return
    
    logger.info("Downloading BigBuckBunny.mp4...")
    
    # Try wget with output
    cmd = "wget -O game_clip.mp4 http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
    result = node.execute(cmd)
    
    logger.info(f"wget exit code: {result[0]}")
    if result[1]:  # stdout
        logger.info(f"wget output: {result[1][:200]}")
    if result[2]:  # stderr
        logger.info(f"wget stderr: {result[2][:200]}")
    
    if result[0] == 0:
        # Verify download
        size_result = node.execute("ls -lh game_clip.mp4 2>&1")
        logger.info(f"✓ Video downloaded: {size_result[1].strip()}")
    else:
        # Try alternative: curl
        logger.warning("wget failed, trying curl...")
        curl_cmd = "curl -o game_clip.mp4 http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
        curl_result = node.execute(curl_cmd)
        
        if curl_result[0] == 0:
            logger.info("✓ Video downloaded using curl")
        else:
            logger.error(f"Both wget and curl failed")
            logger.error(f"wget output: {result[1]}")
            logger.error(f"wget error: {result[2]}")
            logger.error(f"curl output: {curl_result[1]}")
            logger.error(f"curl error: {curl_result[2]}")
            raise RuntimeError("Failed to download test video with both wget and curl")

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
    logger.info("✓ Uploaded signaling.py to Router C")
    
    gamer = slice.get_node('gamer-a')
    gamer.upload_file(str(script_dir / 'gamer_sender.py'), 'gamer_sender.py')
    logger.info("✓ Uploaded gamer_sender.py to Gamer A")
    
    receiver = slice.get_node('receiver-b')
    receiver.upload_file(str(script_dir / 'monitor_receiver.py'), 'monitor_receiver.py')
    logger.info("✓ Uploaded monitor_receiver.py to Receiver B")
    
    # Kill any existing processes from previous runs
    logger.info("\nCleaning up any previous experiment processes...")
    router.execute("pkill -f signaling.py")
    gamer.execute("pkill -f gamer_sender.py")
    receiver.execute("pkill -f monitor_receiver.py")
    time.sleep(2)
    
    # Phase 1: Baseline (no competition)
    logger.info("\n[BASELINE] Starting WebRTC stream without competition...")
    
    # Start signaling server
    logger.info("Starting signaling server on Router C...")
    router.execute_thread("python3 signaling.py > signaling.log 2>&1")
    time.sleep(3)
    
    # Start receiver
    logger.info("Starting receiver on Node B...")
    receiver.execute_thread("python3 monitor_receiver.py ws://192.168.10.12:8443 baseline.csv > receiver.log 2>&1")
    time.sleep(3)
    
    # Start sender
    logger.info("Starting sender on Node A...")
    gamer.execute_thread("python3 gamer_sender.py ws://192.168.10.12:8443 game_clip.mp4 > sender.log 2>&1")
    
    logger.info("\n⏳ Running baseline for 15 seconds...")
    time.sleep(15)
    
    # Phase 2: Competition (with BBRv3)
    logger.info("\n[ATTACK] Starting BBRv3 download...")
    
    # Start iperf3 server on gamer node
    gamer.execute_thread("iperf3 -s > iperf_server.log 2>&1")
    time.sleep(2)
    
    # Start BBRv3 attack from attacker node
    attacker = slice.get_node('attacker-d')
    logger.info("Launching 10 parallel BBRv3 flows...")
    attacker.execute_thread("iperf3 -c 192.168.10.10 -C bbr -P 10 -t 30 > iperf_attack.log 2>&1")
    
    logger.info("\n⏳ Running competition phase for 30 seconds...")
    time.sleep(30)
    
    # Stop processes
    logger.info("\nStopping experiment processes...")
    gamer.execute("pkill -f gamer_sender.py")
    receiver.execute("pkill -f monitor_receiver.py")
    attacker.execute("pkill -f iperf3")
    time.sleep(2)
    
    # Collect results
    logger.info("\n" + "="*60)
    logger.info("Collecting results...")
    logger.info("="*60)
    
    try:
        receiver.download_file('baseline.csv', 'baseline.csv')
        logger.info("✓ Downloaded baseline.csv")
    except Exception as e:
        logger.error(f"✗ Failed to download baseline.csv: {e}")
    
    # Download logs for debugging
    try:
        receiver.download_file('receiver.log', 'receiver.log')
        gamer.download_file('sender.log', 'sender.log')
        logger.info("✓ Downloaded log files")
    except:
        logger.warning("⚠ Some logs unavailable")
    
    logger.info("\n✓ Experiment complete!")
    logger.info("\nNext steps:")
    logger.info("  1. Analyze baseline.csv for FPS and stall metrics")
    logger.info("  2. Compare baseline vs attack phases")
    logger.info("  3. Generate performance graphs")

def main():
    """Main orchestration"""
    try:
        # Step 1: Get existing slice
        slice = get_existing_slice()
        
        # Step 2: Install/update dependencies
        install_dependencies(slice)
        
        # Step 3: Ensure test video exists
        download_test_video(slice)
        
        # Step 4: Run experiment
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
