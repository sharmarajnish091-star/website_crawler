#!/bin/bash
# =============================================================================
# GA4 Website Crawler - One-Click Setup & Run
# =============================================================================
# Usage:
#   chmod +x setup.sh
#   ./setup.sh                          # Install dependencies only
#   ./setup.sh --crawl https://example.com   # Install + crawl a site
#   ./setup.sh --demo                   # Generate dashboard from sample data
# =============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'

echo ""
echo "========================================================================"
echo "  GA4 Website Crawler & Audit Dashboard Generator"
echo "  Playwright-powered deep crawl + interactive HTML report"
echo "========================================================================"
echo ""

# Step 1: Check Python
echo -e "${BOLD}[1/4] Checking Python...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON=python3
    echo -e "  ${GREEN}✓${NC} Python3 found: $($PYTHON --version)"
elif command -v python &> /dev/null; then
    PYTHON=python
    echo -e "  ${GREEN}✓${NC} Python found: $($PYTHON --version)"
else
    echo -e "  ${RED}✗${NC} Python not found! Install Python 3.8+ first."
    exit 1
fi

# Step 2: Install dependencies
echo ""
echo -e "${BOLD}[2/4] Installing Python dependencies...${NC}"
$PYTHON -m pip install --quiet playwright tenacity 2>/dev/null || \
    $PYTHON -m pip install playwright tenacity

echo -e "  ${GREEN}✓${NC} Python packages installed"

# Step 3: Install Playwright browsers
echo ""
echo -e "${BOLD}[3/4] Installing Playwright Chromium browser...${NC}"
$PYTHON -m playwright install chromium 2>/dev/null || {
    echo -e "  ${YELLOW}⚠${NC} Chromium install failed. Trying with system deps..."
    $PYTHON -m playwright install --with-deps chromium
}
echo -e "  ${GREEN}✓${NC} Chromium browser installed"

# Step 4: Ready
echo ""
echo -e "${BOLD}[4/4] Setup complete!${NC}"
echo ""
echo "========================================================================"
echo ""

# Handle arguments
if [[ "$1" == "--demo" ]]; then
    echo -e "${BOLD}Running demo with Thrillophilia sample data...${NC}"
    echo ""
    $PYTHON generate_dashboard.py --input ./sample_crawl_output \
        --output ./thrillophilia_demo_audit.html \
        --title "Thrillophilia.com (Demo)"
    echo ""
    echo -e "${GREEN}Demo dashboard created: thrillophilia_demo_audit.html${NC}"
    echo "Open it in your browser to preview!"

elif [[ "$1" == "--crawl" && -n "$2" ]]; then
    URL="$2"
    MAX_PAGES="${3:-200}"
    echo -e "${BOLD}Starting crawl of ${URL}...${NC}"
    echo "  Max pages: $MAX_PAGES"
    echo "  Delay: 1.0s between pages"
    echo ""

    # Run crawler
    $PYTHON crawler.py --url "$URL" --max-pages "$MAX_PAGES" \
        --delay 1.0 --output ./crawl_output --screenshots

    echo ""
    echo -e "${BOLD}Generating dashboard...${NC}"

    # Generate dashboard
    SITE_NAME=$(echo "$URL" | sed 's|https\?://||' | sed 's|www\.||' | sed 's|/.*||')
    $PYTHON generate_dashboard.py --input ./crawl_output \
        --output "./${SITE_NAME}_ga4_audit.html" \
        --title "$SITE_NAME"

    echo ""
    echo -e "${GREEN}✓ Audit complete! Open ${SITE_NAME}_ga4_audit.html in your browser.${NC}"

else
    echo "Ready to use! Here are your options:"
    echo ""
    echo "  ${BOLD}Quick demo (no crawling):${NC}"
    echo "    ./setup.sh --demo"
    echo ""
    echo "  ${BOLD}Crawl Thrillophilia:${NC}"
    echo "    ./setup.sh --crawl https://www.thrillophilia.com"
    echo ""
    echo "  ${BOLD}Crawl any site:${NC}"
    echo "    ./setup.sh --crawl https://www.example.com 200"
    echo ""
    echo "  ${BOLD}Manual usage:${NC}"
    echo "    python3 crawler.py --url https://www.example.com --max-pages 200 --screenshots"
    echo "    python3 generate_dashboard.py --input ./crawl_output --output audit.html"
    echo ""
fi
