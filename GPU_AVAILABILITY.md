# FABRIC GPU Availability Issue - Solutions

## Problem

```
Exception: Insufficient resources : Component of type: Tesla T4 not available
```

**Cause**: Tesla T4 GPUs are currently unavailable at the requested FABRIC site (SALT).

## Solution 1: Auto-Retry Multiple Sites (DONE ✓)

I've updated `provision_fabric.py` to automatically try multiple sites:

1. NCSA (best GPU availability)
2. TACC
3. SALT
4. MAX
5. MICH
6. UTAH

The script will now check each site and use the first one with available GPUs.

## Solution 2: Manual Site Check

Before running the experiment, check GPU availability:

```bash
# Locally (if you have FABRIC credentials configured)
python scripts/check_gpu_availability.py
```

Or use FABRIC portal:

1. Go to https://portal.fabric-testbed.net/
2. Navigate to **Resources** → **Site Status**
3. Look for sites showing "Tesla T4" available

## Solution 3: Retry Later

GPU availability changes as other users release resources. Try:

- **Off-peak hours**: Late evening/early morning (US time zones)
- **Weekends**: Less academic usage
- **After 5-10 minutes**: Resources may free up

## Solution 4: Fallback Without GPUs

If GPUs remain unavailable, you can still run the experiment using CPU encoding:

### Modify provision_fabric.py

Comment out GPU requests temporarily:

```python
# Node A: Gamer/Sender (CPU only for now)
gamer_a = slice.add_node(name='gamer-a', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
# gamer_a.add_component(model='GPU_TeslaT4', name='gpu1')  # COMMENTED OUT
```

The `gamer_sender.py` script will automatically fall back to CPU encoding (`x264enc`).

**Note**: This defeats the "GPU utilization" requirement but proves the experiment methodology.

## Current Status

✅ **Updated**: `provision_fabric.py` now tries multiple sites automatically

**Next step**: Re-run the GitHub Actions workflow. It should now find an available GPU site.

## Recommended Immediate Action

**Option A - Re-run workflow now**
The updated script will try 6 different sites. One likely has GPUs available.

**Option B - Wait 30-60 minutes**
Resources at SALT may free up. The auto-retry will then succeed.

**Option C - Manual check first**
Run `python scripts/check_gpu_availability.py` locally to see exactly which sites have GPUs right now.
