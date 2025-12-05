#!/bin/bash
# Dependency Installation for Cloud Gaming Experiment
# Installs GStreamer, WebRTC plugins, Python dependencies, and iperf3

set -e

echo "======================================"
echo "Cloud Gaming Experiment - Dependencies"
echo "======================================"

# Update package list
echo "[1/5] Updating package list..."
sudo apt-get update -qq

# Install GStreamer and essential plugins
echo "[2/5] Installing GStreamer..."
sudo apt-get install -y \
    gstreamer1.0-tools \
    gstreamer1.0-nice \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    libgstreamer-plugins-bad1.0-dev \
    gir1.2-gst-plugins-base-1.0 \
    gir1.2-gstreamer-1.0 \
    python3-gi \
    python3-gi-cairo

# Install NVENC support (for Tesla T4 GPU)
echo "[3/5] Installing NVIDIA GStreamer plugins..."
sudo apt-get install -y \
    gstreamer1.0-plugins-bad-nvcodec \
    nvidia-utils-470 || echo "Note: NVENC may not be available on this node"

# Install Python dependencies
echo "[4/5] Installing Python packages..."
pip3 install --user websockets

# Install iperf3 for BBRv3 testing
echo "[5/5] Installing iperf3..."
sudo apt-get install -y iperf3

# Verify installations
echo ""
echo "======================================"
echo "Verification"
echo "======================================"

# Check GStreamer
if gst-inspect-1.0 --version > /dev/null 2>&1; then
    echo "✓ GStreamer installed: $(gst-inspect-1.0 --version | head -n1)"
else
    echo "✗ GStreamer installation failed"
    exit 1
fi

# Check WebRTC plugin
if gst-inspect-1.0 webrtcbin > /dev/null 2>&1; then
    echo "✓ WebRTC plugin available"
else
    echo "✗ WebRTC plugin not found"
    exit 1
fi

# Check NVENC (optional)
if gst-inspect-1.0 nvh264enc > /dev/null 2>&1; then
    echo "✓ NVENC (GPU encoding) available"
    export HAS_GPU=1
else
    echo "⚠ NVENC not available (will use CPU encoding)"
    export HAS_GPU=0
fi

# Check Python packages
if python3 -c "import websockets" 2>/dev/null; then
    echo "✓ Python websockets installed"
else
    echo "✗ Python websockets not found"
    exit 1
fi

# Check iperf3
if command -v iperf3 > /dev/null 2>&1; then
    echo "✓ iperf3 installed: $(iperf3 --version | head -n1)"
else
    echo "✗ iperf3 not found"
    exit 1
fi

echo ""
echo "======================================"
echo "✓ All dependencies installed successfully"
echo "======================================"
