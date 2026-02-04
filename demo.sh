#!/bin/bash
# ============================================================================
# Jarvis-Bot Demo Script
# ============================================================================
# This script demonstrates the Jarvis-Bot system by sending a sequence of
# commands and showing the robot's response.
#
# Usage:
#   1. In Terminal 1: ros2 launch jarvis_agent jarvis_sim.launch.py
#   2. In Terminal 2: ./demo.sh
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}     JARVIS-BOT DEMONSTRATION${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

send_command() {
    local cmd="$1"
    local wait_time="${2:-2}"
    
    echo -e "${YELLOW}>>> Sending: ${NC}${GREEN}$cmd${NC}"
    ros2 topic pub --once /jarvis/nl_raw std_msgs/String "data: '$cmd'"
    sleep "$wait_time"
    echo ""
}

echo -e "${BLUE}Starting demo sequence...${NC}"
echo ""

# Demo sequence
send_command "move forward 2" 3
send_command "turn left 1" 2
send_command "move forward 1" 2
send_command "turn right 2" 3
send_command "circle left 3" 4
send_command "stop" 1
send_command "say Demo complete!" 1

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}     DEMO COMPLETE${NC}"
echo -e "${BLUE}============================================${NC}"
