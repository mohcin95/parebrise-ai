#!/bin/bash
# Stop all V-Glass Auto services
echo "Stopping V-Glass Auto..."
pkill -f "vllm.entrypoints" 2>/dev/null
pkill -f "voice_agent" 2>/dev/null
echo "Done."
