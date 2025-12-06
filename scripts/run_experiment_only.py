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
    
    # Get gamer's IP address on the experiment network
    ip_result = gamer.execute("ip addr show")
    logger.info(f"Gamer node network config:\n{ip_result[1]}")
    
    # Use the data plane IP (typically 192.168.10.10)
    gamer_ip = "192.168.10.10"
    logger.info(f"Using gamer IP: {gamer_ip}")
    
    results = []
    
    # Phase 1: Baseline - single flow, no competition
    logger.info("\n[BASELINE] Testing single TCP flow (no competition)...")
    gamer.execute("pkill -f iperf3")  # Clean up any existing
    gamer.execute_thread("iperf3 -s > iperf_server.log 2>&1")
    time.sleep(2)
    
    baseline_result = attacker.execute(f"iperf3 -c {gamer_ip} -t 15 -J")
    time.sleep(2)
    
    # Parse iperf3 JSON output
    try:
        baseline_data = json.loads(baseline_result[1])
        baseline_throughput = baseline_data['end']['sum_received']['bits_per_second'] / 1_000_000  # Mbps
        logger.info(f"✓ Baseline throughput: {baseline_throughput:.2f} Mbps")
        results.append({
            'phase': 'baseline',
            'duration': 15,
            'throughput_mbps': baseline_throughput,
            'flows': 1,
            'congestion_control': 'cubic'
        })
    except Exception as e:
        logger.error(f"Failed to parse baseline: {e}")
        baseline_throughput = 0
    
    # Phase 2: Competition - 10 parallel BBRv3 flows
    logger.info("\n[ATTACK] Testing with 10 parallel BBRv3 flows...")
    gamer.execute("pkill -f iperf3")
    gamer.execute_thread("iperf3 -s > iperf_server.log 2>&1")
    time.sleep(2)
    
    attack_result = attacker.execute(f"iperf3 -c {gamer_ip} -C bbr -P 10 -t 30 -J")
    time.sleep(2)
    
    try:
        attack_data = json.loads(attack_result[1])
        attack_throughput = attack_data['end']['sum_received']['bits_per_second'] / 1_000_000  # Mbps
        logger.info(f"✓ Attack throughput: {attack_throughput:.2f} Mbps")
        results.append({
            'phase': 'attack',
            'duration': 30,
            'throughput_mbps': attack_throughput,
            'flows': 10,
            'congestion_control': 'bbr'
        })
    except Exception as e:
        logger.error(f"Failed to parse attack: {e}")
        attack_throughput = 0
    
    # Generate results CSV
    logger.info("\n" + "="*60)
    logger.info("Generating results CSV...")
    logger.info("="*60)
    
    with open('baseline.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['phase', 'duration', 'throughput_mbps', 'flows', 'congestion_control'])
        writer.writeheader()
        writer.writerows(results)
    
    logger.info("✓ Created baseline.csv")
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("EXPERIMENT RESULTS")
    logger.info("="*60)
    logger.info(f"Baseline (1 flow, CUBIC):  {baseline_throughput:.2f} Mbps")
    logger.info(f"Attack (10 flows, BBRv3):  {attack_throughput:.2f} Mbps")
    
    if baseline_throughput > 0:
        impact = ((attack_throughput - baseline_throughput) / baseline_throughput) * 100
        logger.info(f"Throughput change:         {impact:+.1f}%")
    
    logger.info("="*60)
    
    logger.info("\n✓ Experiment complete!")
    logger.info("\nResults show BBRv3's ability to compete for bandwidth")
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
