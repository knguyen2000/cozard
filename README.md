# Cozard: Cloud Gaming vs BBRv3 Coexistence Study

This repository contains the experimental artifacts and code for analyzing the coexistence of WebRTC (Cloud Gaming) and BBRv3 traffic.

## View Results

Check the **[results/](./results)** directory for the latest experimental data, including:

- **Metrics**: `gaming_metrics.csv` (FPS, Throughput, Stalls)
- **Plots**: `chart_*.png` (Visualizations)

## How to Run

**Note:** This experiment runs on the [FABRIC Testbed](https://fabric-testbed.net/).

### Prerequisite: Token Update

The FABRIC credential token expires every **4 hours**.
If you wish to run this experiment, you **must contact the repository owner** to update the `FABRIC_TOKEN_JSON` secret in GitHub Actions. The workflows will fail with authentication errors otherwise.

### Execution Steps

The experiment is orchestrated via GitHub Actions in two stages:

1.  **Step 1: Provision Infrastructure**

    - Go to Actions -> Select **Provision FABRIC Infrastructure**.
    - Run this workflow manually to reserve the compute resources/slice.
    - _Wait for this to complete successfully._

2.  **Step 2: Run Experiment**
    - Go to Actions -> Select **Run Experiment on Existing Slice**.
    - Run this workflow to deploy the latest code, execute the Baseline/Attack trials, and upload new artifacts.
