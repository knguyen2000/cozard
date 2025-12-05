import pandas as pd
import matplotlib.pyplot as plt
import glob
import os
import re
import pandas as pd
import matplotlib.pyplot as plt
import glob
import os
import re
import math
import numpy as np

def parse_ping_log(filename):
    """Parses ping output: [timestamp] 64 bytes from ... time=X ms"""
    timestamps = []
    rtts = []
    with open(filename, 'r') as f:
        for line in f:
            # Match: [1234.56] ... time=12.3 ms
            match = re.search(r'\[(\d+\.\d+)\]', line)
            time_match = re.search(r'time=([\d\.]+)', line)
            if match and time_match:
                timestamps.append(float(match.group(1)))
                rtts.append(float(time_match.group(1)))
    
    if not timestamps:
        return pd.DataFrame()
    
    # Normalize time start to 0
    start = timestamps[0]
    timestamps = [t - start for t in timestamps]
    return pd.DataFrame({'time': timestamps, 'rtt': rtts})

def plot_fps_series():
    plt.figure(figsize=(10, 5))
    
    files = glob.glob("metrics_*.csv")
    for f in files:
        phase = f.replace("metrics_", "").replace(".csv", "")
        try:
            df = pd.read_csv(f)
            plt.plot(df['timestamp'], df['fps'], label=phase)
        except Exception as e:
            print(f"Skipping {f}: {e}")
            
    plt.title("Gaming FPS over Time")
    plt.xlabel("Time (s)")
    plt.ylabel("FPS")
    plt.legend()
    plt.grid(True)
    plt.savefig("chart_fps_series.png")
    print("Saved chart_fps_series.png")

def plot_rtt_cdf():
    plt.figure(figsize=(10, 5))
    
    files = glob.glob("ping_*.log")
    for f in files:
        phase = f.replace("ping_", "").replace(".log", "")
        df = parse_ping_log(f)
        if df.empty: continue
        
        sorted_rtt = df['rtt'].sort_values()
        yvals = list(range(len(sorted_rtt)))
        yvals = [y/len(sorted_rtt) for y in yvals]
        
        plt.plot(sorted_rtt, yvals, label=phase)
        
    plt.title("RTT CDF (Latency Distribution)")
    plt.xlabel("RTT (ms)")
    plt.ylabel("CDF")
    plt.legend()
    plt.grid(True)
    plt.savefig("chart_rtt_cdf.png")
    print("Saved chart_rtt_cdf.png")

def plot_harm_factor():
    if not os.path.exists("gaming_metrics.csv"):
        print("No summary metrics found.")
        return

    df = pd.read_csv("gaming_metrics.csv")
    baseline = df[df['phase'] == 'baseline']
    if baseline.empty: return
    
    base_stall = baseline.iloc[0]['total_stall_ms']
    
    phases = []
    harms = []
    
    for index, row in df.iterrows():
        if row['phase'] == 'baseline': continue
        
        phases.append(row['phase'])
        if base_stall > 0:
            harm = row['total_stall_ms'] / base_stall
        else:
            harm = 0 if row['total_stall_ms'] == 0 else 999
            
        harms.append(harm)
        
    plt.figure(figsize=(8, 6))
    bars = plt.bar(phases, harms, color=['orange', 'red'])
    
    plt.title("Harm Factor (Relative to Baseline)")
    plt.ylabel("Harm Factor (x times slower)")
    plt.axhline(y=1.0, color='gray', linestyle='--')
    
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}x',
                ha='center', va='bottom')
                
    print("Saved chart_harm_factor.png")

def plot_summary_metrics():
    """Generates the Summary Bar Charts (FPS/Stalls and Throughput/Fairness)"""
    if not os.path.exists("gaming_metrics.csv"):
        print("No gaming_metrics.csv found.")
        return

    try:
        df = pd.read_csv('gaming_metrics.csv')
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

        # Plot 1: FPS and Stalls
        phases = df['phase']
        x = np.arange(len(phases))
        width = 0.6 
        
        # FPS Bar (Primary Y-axis)
        fps = df['avg_fps']
        ax1.bar(x, fps, width=width, color='skyblue', alpha=0.8, label='Avg FPS')
        ax1.set_ylabel('Avg FPS', color='blue')
        ax1.tick_params(axis='y', labelcolor='blue')
        
        # Stall Duration Line (Secondary Y-axis)
        stalls = df['total_stall_ms'] / 1000.0 # Convert milliseconds to seconds
        ax1b = ax1.twinx()
        ax1b.plot(x, stalls, color='red', marker='o', linewidth=3, markersize=8, label='Total Stall Time (s)')
        ax1b.set_ylabel('Total Stall Time (s)', color='red')
        ax1b.tick_params(axis='y', labelcolor='red')
        
        ax1.set_title('Gaming Quality: FPS vs Stalls')
        ax1.set_xticks(x)
        ax1.set_xticklabels(phases, rotation=15)
        ax1.grid(True, alpha=0.3, axis='y')

        # Plot 2: Throughput & Fairness
        if 'attack_mbps' in df.columns and 'j_index' in df.columns:
            attack_rate = df['attack_mbps']
            j_index = df['j_index']

            # Attack Throughput (Bars)
            ax2.bar(x, attack_rate, width=width, color='orange', alpha=0.7, label='BBRv3 Attack Throughput')
            ax2.axhline(y=40.0, color='gray', linestyle='--', linewidth=1, label='Link Capacity (40Mbps)')
            
            # Annotate bars with Jain Index
            for i, j in enumerate(j_index):
                if not math.isnan(j):
                    ax2.text(x[i], attack_rate[i] + 1, f"J={j:.2f}", ha='center', fontsize=10, fontweight='bold', color='purple')
            
            ax2.set_ylabel('Attack Throughput (Mbps)', color='orange')
            ax2.tick_params(axis='y', labelcolor='orange')
            ax2.set_title('Attack Saturation vs. Fairness')
            ax2.set_xticks(x)
            ax2.set_xticklabels(phases, rotation=15)
            ax2.legend(loc='upper left')

            # Jain's Index (Line on secondary axis)
            ax2b = ax2.twinx()
            ax2b.plot(x, j_index, color='purple', marker='s', linewidth=2, label="Jain's Index")
            ax2b.set_ylim(0, 1.2)
            ax2b.set_ylabel('Fairness Index (1.0=Fair)', color='purple')
            ax2b.tick_params(axis='y', labelcolor='purple')
            
        plt.tight_layout()
        plt.savefig('chart_summary_metrics.png')
        print("Saved chart_summary_metrics.png")
    except Exception as e:
        print(f"Summary Graph generation failed: {e}")

if __name__ == "__main__":
    print("Generating Plots...")
    try:
        plot_fps_series()
        plot_rtt_cdf()
        plot_harm_factor()
        plot_summary_metrics()
        print("Done.")
    except Exception as e:
        print(f"Error plotting: {e}")

