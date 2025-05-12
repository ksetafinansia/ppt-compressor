#!/bin/bash

# Install FFmpeg
echo "Installing FFmpeg..."
apt-get update
apt-get install -y ffmpeg

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Build script completed successfully!"