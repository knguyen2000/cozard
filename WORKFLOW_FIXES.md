# GitHub Actions Workflow Fixes

## Issues Fixed

### 1. ✅ provision_fabric.yml

**Problem**: Script path was incorrect

```yaml
# BEFORE (incorrect)
python scripts/provision_fabric.py

# AFTER (fixed)
python provision_fabric.py
```

**Reason**: `provision_fabric.py` is in the repository root, not in `scripts/` folder.

### 2. ✅ run_experiment.yml

**Problem**: Referenced non-existent script

```yaml
# BEFORE (incorrect)
python scripts/deploy_and_run.py

# AFTER (fixed)
python scripts/run_gaming_experiment.py
```

**Reason**: The actual orchestration script is `run_gaming_experiment.py`.

### 3. ✅ gaming_experiment.yml

This workflow was already correct - it properly references `scripts/run_gaming_experiment.py`.

## Current Repository Structure

```
cozard/
├── provision_fabric.py           ← Root level (not in scripts/)
├── scripts/
│   ├── signaling.py
│   ├── gamer_sender.py
│   ├── monitor_receiver.py
│   ├── install_dependencies.sh
│   └── run_gaming_experiment.py  ← Main orchestrator
└── .github/
    └── workflows/
        ├── provision_fabric.yml  ← Fixed ✓
        ├── run_experiment.yml    ← Fixed ✓
        └── gaming_experiment.yml ← Correct ✓
```

## Next Steps

1. **Commit and push** these workflow fixes
2. **Configure GitHub Secrets** (if not done yet)
3. **Trigger workflow**: Actions → Cloud Gaming Kill-Switch Experiment → Run workflow

The error should now be resolved!
