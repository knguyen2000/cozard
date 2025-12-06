# Network Throughput Competition Experiment

> **Testing how BBR congestion control affects competing network traffic on FABRIC testbed**

This experiment measures the impact of BBR TCP flows on baseline network throughput using the FABRIC research infrastructure.

## Overview

**Hypothesis**: Multiple BBR TCP flows will compete aggressively for bandwidth, demonstrating BBR's competitive behavior against standard CUBIC flows.

**Hardware**: FABRIC testbed with 4-node topology

**Metrics**: Network throughput (Mbps) for baseline vs competition scenarios

## Architecture

```
4-Node Topology:
┌─────────────┐     ┌─────────────┐
│  Gamer A    │────▶│ Receiver B  │  Baseline Traffic
│  (Sender)   │     │  (Monitor)  │
└─────────────┘     └─────────────┘
      │                    │
      └────────┬───────────┘
               │
         ┌─────┴──────┐
         │  Router C  │  (L2 Bridge)
         └─────┬──────┘
               │
        ┌──────┴────────┐
        │  Attacker D   │  (BBR Competition)
        └───────────────┘
```

## Quick Start

### GitHub Actions (Automated)

1. Configure FABRIC secrets in GitHub repository
2. Manually trigger workflow: **Actions** → **Run Experiment on Existing Slice** → **Run workflow**
3. Wait ~2-3 minutes for experiment completion
4. Download artifacts: `baseline.csv`, `gaming_performance.png`

### Local Execution

```bash
# Run experiment on existing FABRIC slice
python scripts/run_experiment_only.py
```

## Experiment Phases

1. **Baseline (15s)**: Single TCP flow without competition

   - Measures maximum achievable throughput
   - Uses CUBIC congestion control

2. **Attack (15s)**: 10 parallel BBR flows competing
   - BBR flows launched from Attacker node
   - Baseline traffic continues during competition
   - Measures throughput degradation

## Output

- **`baseline.csv`**: Throughput measurements

  ```csv
  phase,duration,throughput_mbps,flows,congestion_control,description
  baseline,15,18500.5,1,cubic,Gaming stream (no competition)
  attack,15,2341.2,1,cubic,Gaming stream (with 10 BBR flows competing)
  ```

- **`gaming_performance.png`**: Bar chart comparing baseline vs attack throughput

## Expected Results

**BBR Competition Impact**:

- Significant throughput degradation during attack phase
- Demonstrates BBR's aggressive bandwidth competition
- Quantifies impact on concurrent traffic

## Hardware Requirements

- **Nodes**: 4 FABRIC nodes (any CPU)
- **Network**: L2 network (single FABRIC site)
- **Software**: iperf3, Python 3.8+

## Scripts

| File                     | Description                              |
| ------------------------ | ---------------------------------------- |
| `run_experiment_only.py` | Main experiment script (no provisioning) |
| `provision_fabric.py`    | FABRIC slice provisioning                |
| `delete_slice.py`        | Cleanup script                           |

## Workflows

- `.github/workflows/provision_fabric.yml`: Provision FABRIC infrastructure
- `.github/workflows/run_experiment.yml`: Run experiment on existing slice

## References

- [FABRIC Testbed](https://portal.fabric-testbed.net/)
- [BBR Congestion Control](https://github.com/google/bbr)
- [iperf3](https://iperf.fr/)

## License

MIT
