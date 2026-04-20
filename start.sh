#!/bin/bash
# Fusion 360 MCP Server - Quick Start

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

header() {
    clear
    echo ""
    echo -e "${GREEN}${BOLD}  ========================================"
    echo "   FUSION 360 MCP SERVER - Quick Start"
    echo -e "  ========================================${NC}"
    echo ""
}

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}  [X] Node.js not found. Install it from https://nodejs.org${NC}"
    exit 1
fi

# Check dependencies
if [ ! -d "$SCRIPT_DIR/server/node_modules" ]; then
    echo "  [!] Installing dependencies..."
    cd "$SCRIPT_DIR/server" && npm install --silent
    echo "  [OK] Dependencies installed."
fi

show_menu() {
    header
    echo "  [1] START SERVER    - Launch the MCP server"
    echo "  [2] SETUP GUIDE     - First-time setup instructions"
    echo "  [3] QUIT"
    echo ""
    read -p "  Your choice (1/2/3): " choice
    case $choice in
        1) start_server ;;
        2) show_guide ;;
        3) exit 0 ;;
        *) start_server ;;
    esac
}

show_guide() {
    header
    echo -e "  ${CYAN}STEP 1 - Fusion 360 Add-in${NC}"
    echo "  Copy: $SCRIPT_DIR/fusion_script/fusion_mcp_server/"
    echo "  To:   ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/"
    echo ""
    echo "  In Fusion 360: Tools > Add-Ins > Enable \"Fusion MCP Server\""
    echo "  Click START in the MCP panel."
    echo ""
    echo -e "  ${CYAN}STEP 2 - Claude Desktop${NC}"
    echo "  Edit: ~/Library/Application Support/Claude/claude_desktop_config.json"
    echo ""
    echo "  {\"mcpServers\":{\"fusion_mcp\":{\"command\":\"node\","
    echo "  \"args\":[\"$SCRIPT_DIR/server/server.mjs\"],\"protocol\":\"stdio\"}}}"
    echo ""
    echo "  Then restart Claude Desktop."
    echo ""
    echo -e "  ${CYAN}STEP 3 - Start working${NC}"
    echo "  1. Open Fusion 360 + start the add-in"
    echo "  2. Run this script and press [1]"
    echo "  3. Open Claude Desktop and start talking!"
    echo ""
    read -p "  Press Enter to go back..." _
    show_menu
}

start_server() {
    header
    echo "  CHECKLIST:"
    echo "    [?] Fusion 360 is open"
    echo "    [?] Add-in is running (click START)"
    echo "    [?] Claude Desktop is open"
    echo ""
    echo "  Starting server... (Ctrl+C to stop)"
    echo "  ----------------------------------------"
    cd "$SCRIPT_DIR/server"
    node server.mjs
    echo "  ----------------------------------------"
    echo "  Server stopped."
}

show_menu
