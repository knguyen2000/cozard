# Two-Workflow Development Pattern

## Workflow 1: Provision Infrastructure (`provision_fabric.yml`)

**Purpose**: Create FABRIC slice once and keep it running

**When to run**:

- First time setup
- After slice expires or gets deleted
- When changing infrastructure (different site, more nodes, etc.)

**What it does**:

- Provisions 4-node FABRIC slice with GPUs
- Configures network
- **Leaves slice running** for reuse

**Runtime**: ~5-10 minutes (waiting for GPU availability)

**GitHub Actions**: Manual trigger → **Provision FABRIC Infrastructure**

---

## Workflow 2: Run Experiment (`run_experiment.yml`)

**Purpose**: Run experiment on existing slice

**When to run**:

- Every time you want to test/run the experiment
- After fixing bugs in experiment logic
- Multiple times to collect more data

**What it does**:

- Uses existing slice (doesn't provision)
- Uploads latest scripts from your repo
- Runs experiment
- Collects results

**Runtime**: ~1-2 minutes (no provisioning wait)

**GitHub Actions**: Manual trigger → **Run Experiment on Existing Slice**

---

## Development Workflow

### Initial Setup (Once)

```
1. Push code to GitHub
2. Run workflow: "Provision FABRIC Infrastructure"
3. Wait ~5-10 min for GPUs
4. ✓ Slice created and kept alive
```

### Iteration Loop (Many Times)

```
1. Fix bugs / update experiment logic locally
2. Push changes to GitHub
3. Run workflow: "Run Experiment on Existing Slice"
4. Wait ~1-2 min
5. Download results
6. Repeat from step 1
```

### Cleanup (When Done)

```
Option A: Let slice auto-expire (slices last 24 hours by default)
Option B: Delete manually via FABRIC portal
Option C: Run: python scripts/delete_slice.py
```

---

## File Structure

```
.github/workflows/
├── provision_fabric.yml     → Creates slice (run once)
└── run_experiment.yml       → Runs experiment (run many times)

scripts/
├── run_experiment_only.py   → Experiment logic only (no provisioning)
├── delete_slice.py          → Cleanup utility
└── ... (other experiment scripts)

provision_fabric.py          → Standalone provisioning script
```

---

## Cost Savings

**Old way** (combined workflow):

- 10 test runs = 10 × 10 minutes = 100 minutes waiting

**New way** (separated):

- 1 provision (10 min) + 10 experiments (10 × 2 min) = 30 minutes total

**Savings**: 70% less time wasted waiting! 🎯

---

## Troubleshooting

**Q: Experiment fails with "slice not found"**

- Run `provision_fabric.yml` workflow first

**Q: Slice got deleted accidentally**

- Just run `provision_fabric.yml` again

**Q: Want to change experiment logic**

- Make changes locally
- Push to GitHub
- Run `run_experiment.yml` (uses existing slice)

**Q: GPU availability issues during provisioning**

- Be patient, try again in 30 min
- Or use off-peak hours (late evening/early morning)
