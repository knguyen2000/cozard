# FABRIC GPU Permissions Issue - SOLVED

## The Problem

```
Policy Violation: Your project is lacking Component.GPU_RTX6000 or Component.GPU tag
```

Your FABRIC project doesn't have permission to use RTX6000 GPUs.

## ✅ Solution Applied

**Switched back to Tesla T4** - which your project DOES have permission for.

Updated `provision_fabric.py`:

- GPU Model: `GPU_RTX6000` → `GPU_TeslaT4`
- Site: Trying `UTAH` first (then MAX, MICH, TACC, GATECH, RENC)

## Current Challenge

Tesla T4 GPUs are **heavily used** right now, so you may get:

```
Insufficient resources: Component of type: Tesla T4 not available
```

This just means all GPUs are reserved at that moment.

## What To Do

### Option 1: Keep Retrying (Recommended)

GPUs free up constantly. The workflow will try UTAH, MAX, MICH, etc.

**Re-run the workflow every 15-30 minutes** until it succeeds.

**Best times:**

- Late evening (after 10 PM EST)
- Early morning (before 8 AM EST)
- Weekends

### Option 2: Run Without GPUs

Edit `provision_fabric.py` to skip GPUs entirely:

```python
# Line ~45-47, change to:
GPU_MODEL = None  # No GPU
GPU_NAME = 'CPU Only'

# Lines ~71 and ~77 - comment out:
# gamer_a.add_component(model=GPU_MODEL, name='gpu1')
# receiver_b.add_component(model=GPU_MODEL, name='gpu1')
```

The sender will automatically use CPU encoding (`x264enc`).

**Trade-off**: No GPU utilization, but experiment still runs and collects valid data.

### Option 3: Request Additional GPU Permissions

To use RTX6000 or other GPU types, request tags from FABRIC:

1. Go to https://portal.fabric-testbed.net/
2. Navigate to **Projects** → Your Project → **Tags**
3. Request: `Component.GPU_RTX6000` or `Component.GPU` (wildcard)
4. Wait for approval (usually 1-2 business days)

## Current Status

✅ **Fixed permission error** - back to Tesla T4  
⏳ **Waiting for GPU availability** - keep retrying

**Next**: Re-run workflow. It will try 6 different sites. One might have GPUs!

If it keeps failing after 3-4 attempts across different times of day, consider Option 2 (no GPU) to at least validate the experiment works.
