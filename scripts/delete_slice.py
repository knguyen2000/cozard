#!/usr/bin/env python3
"""
Delete FABRIC Slice
Simple utility to clean up the cloud gaming experiment slice
"""
import os
from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib_manager

fab_dir = os.path.expanduser('~/.fabric')
os.environ['FABRIC_TOKEN_LOCATION'] = os.path.join(fab_dir, 'id_token.json')
os.environ['FABRIC_BASTION_KEY_LOCATION'] = os.path.join(fab_dir, 'bastion_key')
os.environ['FABRIC_SLICE_PRIVATE_KEY_FILE'] = os.path.join(fab_dir, 'slice_key')
os.environ['FABRIC_SLICE_PUBLIC_KEY_FILE'] = os.path.join(fab_dir, 'slice_key.pub')

def delete_slice(slice_name="cloud_gaming_experiment"):
    """Delete the experiment slice"""
    fablib = fablib_manager()
    
    try:
        slice = fablib.get_slice(name=slice_name)
        print(f"Deleting slice '{slice_name}'...")
        slice.delete()
        print(f"✓ Slice '{slice_name}' deleted successfully")
    except Exception as e:
        print(f"Slice '{slice_name}' not found or already deleted")
        print(f"Details: {e}")

if __name__ == "__main__":
    delete_slice()
