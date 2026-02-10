# GA4 Website Crawler & Audit Dashboard

A production-grade Playwright-powered website crawler that captures **everything** needed for a best-in-class Google Analytics 4 setup — network requests, console logs, rendered DOM, redirects, performance metrics — and generates an interactive HTML dashboard you can present to stakeholders.

## What Makes This Different

Most GA4 audits look at source code. This tool **runs the site in a real browser** and captures what actually happens:

| Feature | Source Code Audit | This Tool |
|---|---|---|
| Analytics tags in HTML | ✓ | ✓ |
| Tags that actually **fire** | ✗ | ✓ (network interception) |
| GA4 events & parameters | ✗ | ✓ (parses collect payloads) |
| dataLayer contents | ✗ | ✓ (extracts after JS runs) |
| Redirect chains | ✗ | ✓ (browser-level tracking) |
| Cross-domain tracking | ✗ | ✓ (payment gateway detection) |
| JS errors breaking tracking | ✗ | ✓ (console capture) |
| Page performance | ✗ | ✓ (load times, FCP, sizes) |

## Quick Start

```bash
# One-command setup
chmod +x setup.sh
./setup.sh

# Crawl any website
./setup.sh --crawl https://www.thrillophilia.com

# Or generate demo dashboard from sample data
./setup.sh --demo
```

## Manual Usage

### Step 1: Install

```bash
pip install playwright tenacity
playwright install chromium
```

### Step 2: Crawl

```bash
python3 crawler.py --url https://www.thrillophilia.com \
    --max-pages 200 \
    --delay 1.0 \
    --output ./crawl_output \
    --screenshots
```

### Step 3: Generate Dashboard

```bash
python3 generate_dashboard.py \
    --input ./crawl_output \
    --output ./thrillophilia_ga4_audit.html \
    --title "Thrillophilia.com"
```

## Crawler Options

| Flag | Default | Description |
|---|---|---|
| `--url` | (required) | Website URL to crawl |
| `--max-pages` | 200 | Maximum pages to crawl |
| `--delay` | 1.0 | Seconds between page loads |
| `--output` | ./crawl_output | Output directory |
| `--timeout` | 30 | Page load timeout (seconds) |
| `--screenshots` | off | Capture template screenshots |
| `--headed` | off | Show browser window (debug) |
| `--user-agent` | auto | Custom user agent string |
| `--viewport` | 1920x1080 | Browser viewport size |
| `--debug` | off | Verbose logging |

## What Gets Captured

### Network Interception (16 analytics tools)
- Google Analytics 4 (GA4) — with event name & parameter extraction
- Google Analytics Universal (UA)
- Google Tag Manager (GTM)
- Facebook Pixel
- Hotjar
- Crazy Egg
- Segment
- Mixpanel
- Amplitude
- CleverTap
- MoEngage
- LinkedIn Insight Tag
- Twitter/X Pixel
- Pinterest Tag
- TikTok Pixel
- Any other tracking beacon

### Console & Errors
- `console.log`, `console.error`, `console.warn` with source
- JavaScript errors with stack traces
- `window.dataLayer` contents after full JS execution

### Rendered DOM (after JavaScript)
- Meta tags (title, description, canonical, robots, OG, hreflang)
- Schema.org JSON-LD structured data
- All forms with fields, actions, methods
- CTAs (booking, enquiry, cart buttons)
- Internal/external links
- Breadcrumb structure
- Images missing alt text

### Performance
- Page load time, First Contentful Paint
- Request count and transfer size per page
- Resource breakdown (JS, CSS, images, fonts)

### Redirects
- Full redirect chain with status codes and timing
- Protocol, www, trailing slash, and legacy URL redirects

## Output Files

The crawler generates 8 JSON files in the output directory:

| File | Purpose |
|---|---|
| `crawl_data.json` | Complete raw data — every page, request, console message |
| `analytics_audit.json` | Analytics tools, GA4 events, coverage gaps |
| `redirect_report.json` | All redirect chains with hop details |
| `template_map.json` | Page templates with example URLs |
| `performance_report.json` | Load times, resource breakdown |
| `errors.json` | JS errors, console warnings, failed requests |
| `site_tree.json` | URL hierarchy tree |
| `crawl_state.json` | Resume state (for interrupted crawls) |

## Dashboard Sections

The generated HTML dashboard includes:

1. **Executive Summary** — key metrics, data confidence, methodology
2. **Analytics Tools Audit** — coverage table with color-coded bars
3. **GA4 Events & dataLayer** — events detected, ecommerce status
4. **URL Structure** — interactive collapsible tree
5. **Page Templates** — cards with screenshots and recommended events
6. **Redirect Analysis** — visual chain diagrams
7. **Performance** — load time distribution, slowest pages
8. **Errors & Issues** — JS errors, warnings, failed requests
9. **GA4 Implementation Roadmap** — 4-phase plan with GTM guidance
10. **Methodology** — how data was collected, confidence level

## File Structure

```
ga4_crawler_kit/
├── crawler.py              # Playwright crawler (1,666 lines)
├── generate_dashboard.py   # Dashboard generator (1,493 lines)
├── setup.sh                # One-click setup & run
├── README.md               # This file
└── sample_crawl_output/    # Demo data for Thrillophilia
    ├── crawl_data.json
    ├── analytics_audit.json
    ├── redirect_report.json
    ├── template_map.json
    ├── performance_report.json
    ├── errors.json
    └── site_tree.json
```

## Requirements

- Python 3.8+
- Playwright (`pip install playwright`)
- Chromium (installed via `playwright install chromium`)
- Optional: tenacity (`pip install tenacity`) for retry logic
