# FABRIC GPU Unavailability - Quick Fix

## Problem

All Tesla T4 GPUs are currently reserved across FABRIC.

## Solutions (in order of preference)

### ✅ Solution 1: Use RTX6000 GPUs (DONE)

I've updated `provision_fabric.py` to use **RTX6000** instead of Tesla T4:

```python
GPU_MODEL = 'GPU_RTX6000'  # More commonly available
SITE = 'TACC'  # Good GPU availability
```

**Action**: Commit and re-run the workflow. RTX6000 is usually more available.

---

### Solution 2: Run WITHOUT GPUs (CPU Encoding)

If RTX6000 also fails, you can run the experiment with CPU encoding:

**Edit `provision_fabric.py`:**

```python
# At line ~45, change:
GPU_MODEL = None  # ← Set to None to skip GPUs
```

**And comment out GPU additions (lines ~81, ~88):**

```python
# Node A
gamer_a = slice.add_node(name='gamer-a', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
# gamer_a.add_component(model=GPU_MODEL, name='gpu1')  # COMMENTED OUT
```

The `gamer_sender.py` script will automatically use CPU encoding (`x264enc`) as fallback.

**Trade-off**: You lose the "GPU utilization" requirement but can still run the experiment and collect results.

---

### Solution 3: Manual Site Override

If you know a specific site has GPUs, hardcode it:

```python
# Line ~58
SITE = 'MAX'  # or 'MICH', 'UTAH', etc.
GPU_MODEL = 'GPU_RTX6000'
```

---

### Solution 4: Wait and Retry

**Best times for GPU availability:**

- Late evening (after 10 PM EST)
- Early morning (before 8 AM EST)
- Weekends

Set a GitHub Actions schedule to retry automatically:

```yaml
# In .github/workflows/gaming_experiment.yml
on:
  schedule:
    - cron: "0 2 * * *" # 2 AM daily
```

---

## Current Status

✅ Changed to **RTX6000** at **TACC** site  
✅ Simplified availability checking

**Recommendation**: Try re-running now with RTX6000. If it still fails, switch to CPU-only mode and run experiment without GPUs to at least validate the methodology.
