#!/bin/bash

# Discord Bot Maintenance Script
# This script cleans up old system logs to save space.

echo "🧹 Starting Daily Cleanup..."

# 1. Clean up Systemd Journal Logs
# Keep only the last 7 days of logs
# AND ensure logs don't exceed 500MB total
if command -v journalctl &> /dev/null; then
    echo "   - Vacuuming journald logs..."
    sudo journalctl --vacuum-time=7d
    sudo journalctl --vacuum-size=500M
else
    echo "   ! journalctl not found, skipping log cleanup."
fi

# 2. Clean up orphaned pycache (optional)
echo "   - Cleaning pycache..."
find /home/discord/Music_bot -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

echo "✅ Cleanup Complete."
