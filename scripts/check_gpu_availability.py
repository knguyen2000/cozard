#!/usr/bin/env python3
"""
Check FABRIC GPU Availability
Queries FABRIC sites for Tesla T4 GPU availability
"""
import os
from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib_manager

# Setup FABRIC credentials
fab_dir = os.path.expanduser('~/.fabric')
os.environ['FABRIC_TOKEN_LOCATION'] = os.path.join(fab_dir, 'id_token.json')
os.environ['FABRIC_BASTION_KEY_LOCATION'] = os.path.join(fab_dir, 'bastion_key')
os.environ['FABRIC_SLICE_PRIVATE_KEY_FILE'] = os.path.join(fab_dir, 'slice_key')
os.environ['FABRIC_SLICE_PUBLIC_KEY_FILE'] = os.path.join(fab_dir, 'slice_key.pub')
os.environ['FABRIC_LOG_LEVEL'] = 'CRITICAL'

def check_gpu_availability():
    """Check Tesla T4 availability across FABRIC sites"""
    fablib = fablib_manager()
    
    print("="*70)
    print("FABRIC GPU Availability Check - Tesla T4")
    print("="*70)
    
    # Sites to check
    sites = ['NCSA', 'TACC', 'SALT', 'MAX', 'MICH', 'UTAH', 'GATECH', 'RENC']
    
    available_sites = []
    
    for site in sites:
        try:
            # Query site resources
            site_resources = fablib.show_site(site)
            
            # Check for GPU in output
            gpu_available = 'GPU_TeslaT4' in str(site_resources) or 'Tesla' in str(site_resources)
            
            if gpu_available:
                available_sites.append(site)
                print(f"✓ {site:<10} - Tesla T4 GPUs AVAILABLE")
            else:
                print(f"✗ {site:<10} - No GPUs available")
                
        except Exception as e:
            print(f"? {site:<10} - Unable to query ({str(e)[:40]})")
    
    print("="*70)
    
    if available_sites:
        print(f"\n✓ Found GPUs at: {', '.join(available_sites)}")
        print(f"\nRecommended: Use {available_sites[0]} for your experiment")
    else:
        print("\n No Tesla T4 GPUs currently available")
        print("Try again later or check FABRIC status page")
    
    print("\nNote: Availability changes frequently as other users reserve/release resources")
    print("="*70)

if __name__ == "__main__":
    try:
        check_gpu_availability()
    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure FABRIC credentials are configured in ~/.fabric/")
