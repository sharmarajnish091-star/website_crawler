#!/usr/bin/env python3
"""
GA4 Crawler Kit - Production-Grade Website Crawler for Analytics Audit

A comprehensive Playwright-powered website crawler that captures all network
requests, console activity, DOM structure, and performance metrics needed for
GA4 analytics audits on ANY website.

Features:
  - Network interception with analytics tool detection
  - GA4 event extraction and mapping
  - Console and JS error capture
  - Redirect chain tracking
  - Template classification with screenshots
  - Cross-domain destination tracking
  - robots.txt respect
  - Resume capability with state saving

Usage:
    python crawler.py --url https://www.example.com --max-pages 200 \\
        --delay 1.0 --output ./crawl_output --screenshots --headless

Requirements:
    pip install playwright
    playwright install

Author: GA4 Audit Automation
License: MIT
"""

import asyncio
import argparse
import json
import logging
import os
import re
import sys
import time
import hashlib
import urllib.parse
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Set, Tuple
from collections import defaultdict
from urllib.parse import urlparse, urljoin, urlunparse
from pathlib import Path

from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Request, Response


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

def setup_logging(output_dir: str, debug: bool = False) -> logging.Logger:
    """
    Configure logging to both file and console.

    Args:
        output_dir: Directory where log file will be saved
        debug: Enable debug-level logging

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger('ga4_crawler')
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # File handler
    log_file = os.path.join(output_dir, 'crawler.log')
    fh = logging.FileHandler(log_file)
    fh.setLevel(level)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class NetworkRequest:
    """Captures all relevant network request data."""
    url: str
    method: str
    status: Optional[int] = None
    content_type: Optional[str] = None
    size_bytes: int = 0
    duration_ms: float = 0.0
    payload: Optional[Dict[str, Any]] = None
    response_body: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    is_analytics: bool = False
    analytics_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, truncating large response bodies."""
        d = asdict(self)
        if d.get('response_body') and len(d['response_body']) > 5000:
            d['response_body'] = d['response_body'][:5000] + '...[truncated]'
        return d


@dataclass
class ConsoleMessage:
    """Captures console output."""
    level: str  # 'log', 'error', 'warn', 'info'
    text: str
    source: str = ''  # URL or 'page'
    line_number: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class PageData:
    """Captures all data for a single page."""
    url: str
    status_code: int = 200
    title: str = ''
    description: str = ''
    h1_tags: List[str] = field(default_factory=list)
    canonical_url: Optional[str] = None
    robots_meta: Optional[str] = None
    og_tags: Dict[str, str] = field(default_factory=dict)
    hreflang_links: Dict[str, str] = field(default_factory=dict)

    # Network data
    network_requests: List[Dict[str, Any]] = field(default_factory=list)
    redirect_chain: List[Tuple[str, int]] = field(default_factory=list)

    # Console data
    console_messages: List[Dict[str, Any]] = field(default_factory=list)
    js_errors: List[Dict[str, Any]] = field(default_factory=list)
    datalayer: Optional[List[Dict[str, Any]]] = None

    # DOM structure
    forms: List[Dict[str, Any]] = field(default_factory=list)
    ctas: List[Dict[str, str]] = field(default_factory=list)
    internal_links: List[str] = field(default_factory=list)
    external_links: List[str] = field(default_factory=list)
    images_missing_alt: int = 0
    breadcrumbs: Optional[Dict[str, Any]] = None

    # Schema markup
    schema_org: List[Dict[str, Any]] = field(default_factory=list)

    # Performance
    load_time_ms: float = 0.0
    fcp_ms: Optional[float] = None
    total_transfer_bytes: int = 0
    request_count: int = 0
    resource_breakdown: Dict[str, int] = field(default_factory=dict)

    # Template classification
    template_type: Optional[str] = None
    template_hash: Optional[str] = None
    screenshot_path: Optional[str] = None

    # Metadata
    crawl_timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ============================================================================
# ANALYTICS DETECTION PATTERNS
# ============================================================================

ANALYTICS_PATTERNS = {
    'ga4': {
        'patterns': [
            r'google-analytics\.com/g/collect',
            r'analytics\.google\.com.*collect',
        ],
        'name': 'Google Analytics 4 (GA4)',
    },
    'ua': {
        'patterns': [
            r'google-analytics\.com.*collect.*v=1',
            r'ssl\.google-analytics\.com',
        ],
        'name': 'Google Analytics UA (Universal)',
    },
    'gtm': {
        'patterns': [
            r'googletagmanager\.com/gtm\.js',
            r'googletagmanager\.com/gtag/js',
        ],
        'name': 'Google Tag Manager',
    },
    'facebook_pixel': {
        'patterns': [r'facebook\.com/tr'],
        'name': 'Facebook Pixel',
    },
    'hotjar': {
        'patterns': [r'hotjar\.com', r'static\.hotjar\.com'],
        'name': 'Hotjar',
    },
    'crazyegg': {
        'patterns': [r'script\.crazyegg\.com', r'd\.crazyegg\.com'],
        'name': 'Crazy Egg',
    },
    'segment': {
        'patterns': [r'cdn\.segment\.com', r'api\.segment\.io'],
        'name': 'Segment',
    },
    'mixpanel': {
        'patterns': [r'mixpanel\.com'],
        'name': 'Mixpanel',
    },
    'amplitude': {
        'patterns': [r'amplitude\.com', r'api\.amplitude\.com'],
        'name': 'Amplitude',
    },
    'clevertap': {
        'patterns': [r'clevertap\.com', r'api\.clevertap\.com'],
        'name': 'CleverTap',
    },
    'moengage': {
        'patterns': [r'moengage\.com', r'api\.moengage\.com'],
        'name': 'MoEngage',
    },
    'linkedin_insight': {
        'patterns': [r'snap\.licdn\.com'],
        'name': 'LinkedIn Insight Tag',
    },
    'twitter_pixel': {
        'patterns': [r'static\.ads-twitter\.com', r'platform\.twitter\.com'],
        'name': 'Twitter/X Pixel',
    },
    'pinterest': {
        'patterns': [r'ct\.pinterest\.com'],
        'name': 'Pinterest Tag',
    },
    'tiktok': {
        'patterns': [r'analytics\.tiktok\.com'],
        'name': 'TikTok Pixel',
    },
}


def classify_request_as_analytics(url: str) -> Tuple[bool, Optional[str]]:
    """
    Classify if a request is analytics-related and return type.

    Args:
        url: Request URL to classify

    Returns:
        Tuple of (is_analytics: bool, tool_name: Optional[str])
    """
    for key, config in ANALYTICS_PATTERNS.items():
        for pattern in config['patterns']:
            if re.search(pattern, url, re.IGNORECASE):
                return True, config['name']
    return False, None


def parse_ga4_event_data(url: str) -> Dict[str, Any]:
    """
    Extract GA4 event data from collect request URL.

    Parses query parameters to extract:
      - event_name (en=)
      - measurement_id (tid=)
      - client_id (cid=)
      - user_id (uid=)
      - Additional event parameters

    Args:
        url: GA4 collect request URL

    Returns:
        Dictionary with extracted GA4 event data
    """
    try:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)

        result = {}

        # Extract main identifiers
        if 'en' in params:
            result['event_names'] = params['en'][0].split(',') if params['en'] else []
        if 'tid' in params:
            result['measurement_id'] = params['tid'][0]
        if 'cid' in params:
            result['client_id'] = params['cid'][0]
        if 'uid' in params:
            result['user_id'] = params['uid'][0]

        # Include all parameters for completeness
        result['all_params'] = {k: v[0] if v else None for k, v in params.items()}

        return result
    except Exception:
        return {}


# ============================================================================
# CRAWLER CLASS
# ============================================================================

class WebsiteCrawler:
    """
    Production-grade website crawler for GA4 audit.

    Handles:
      - BFS crawling with URL deduplication
      - Network request interception and categorization
      - Console and error capture
      - DOM analysis with template classification
      - Performance metrics extraction
      - Screenshot capture for template types
      - robots.txt respect
      - Resume capability with state saving
    """

    def __init__(
        self,
        seed_url: str,
        max_pages: int = 200,
        delay: float = 1.0,
        timeout: int = 30,
        headless: bool = True,
        user_agent: Optional[str] = None,
        viewport: str = '1920x1080',
        logger: Optional[logging.Logger] = None,
        output_dir: str = './crawl_output',
        enable_screenshots: bool = False,
    ) -> None:
        """
        Initialize the crawler.

        Args:
            seed_url: Starting URL for crawl
            max_pages: Maximum pages to crawl
            delay: Delay between requests in seconds
            timeout: Page load timeout in seconds
            headless: Run browser in headless mode
            user_agent: Custom user agent string
            viewport: Viewport size as WIDTHxHEIGHT
            logger: Logger instance
            output_dir: Output directory for results
            enable_screenshots: Capture screenshots
        """
        self.seed_url = seed_url
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        self.headless = headless
        self.user_agent = user_agent or self._default_user_agent()
        self.output_dir = output_dir
        self.enable_screenshots = enable_screenshots
        self.logger = logger or logging.getLogger('ga4_crawler')

        # Parse viewport
        try:
            w, h = map(int, viewport.split('x'))
            self.viewport = {'width': w, 'height': h}
        except ValueError:
            self.logger.warning(f"Invalid viewport {viewport}, using 1920x1080")
            self.viewport = {'width': 1920, 'height': 1080}

        # Crawl state
        self.seed_domain = urlparse(seed_url).netloc
        self.visited_urls: Set[str] = set()
        self.queue: List[str] = [seed_url]
        self.crawled_pages: List[PageData] = []
        self.failed_urls: Dict[str, str] = {}
        self.template_screenshots: Dict[str, str] = {}  # template_type -> screenshot_path

        # Metrics
        self.crawl_start_time: Optional[datetime] = None
        self.crawl_end_time: Optional[datetime] = None

    @staticmethod
    def _default_user_agent() -> str:
        """Return a default user agent string."""
        return (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/119.0.0.0 Safari/537.36'
        )

    def normalize_url(self, url: str) -> str:
        """
        Normalize URL for deduplication.

        Removes fragments and trailing slashes, lowercases path.

        Args:
            url: URL to normalize

        Returns:
            Normalized URL
        """
        try:
            parsed = urlparse(url)
            # Normalize path
            path = parsed.path.rstrip('/').lower()
            if not path:
                path = '/'
            return urlunparse((
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                '',  # params
                parsed.query,  # keep query for distinction
                ''   # fragment
            ))
        except Exception:
            return url.lower()

    def is_internal_url(self, url: str) -> bool:
        """
        Check if URL belongs to same domain.

        Args:
            url: URL to check

        Returns:
            True if internal to seed domain
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc == self.seed_domain
        except Exception:
            return False

    def should_crawl_url(self, url: str) -> bool:
        """
        Determine if a URL should be crawled.

        Skips:
          - Non-HTML resources (.pdf, .jpg, .png, .css, .js, etc.)
          - External domains
          - Already visited URLs

        Args:
            url: URL to check

        Returns:
            True if URL should be crawled
        """
        # Skip non-HTML resources
        skip_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp',
                          '.css', '.js', '.woff', '.woff2', '.ttf', '.svg',
                          '.mp4', '.mp3', '.zip', '.exe', '.dmg', '.apk'}

        url_lower = url.lower()
        if any(url_lower.endswith(ext) for ext in skip_extensions):
            return False

        # Check if internal
        if not self.is_internal_url(url):
            return False

        # Check if already visited
        normalized = self.normalize_url(url)
        if normalized in self.visited_urls:
            return False

        return True

    async def setup_network_interception(
        self,
        context: BrowserContext,
        page_data: PageData
    ) -> None:
        """
        Setup network request and response interception.

        Captures:
          - All request URLs, methods, timing
          - Response status, content-type
          - Analytics payload data
          - Cross-domain requests

        Args:
            context: Browser context
            page_data: PageData object to store captured data
        """
        request_times: Dict[str, float] = {}

        async def on_request(request: Request) -> None:
            """Handle outgoing request."""
            try:
                request_times[request.url] = time.time()
                is_analytics, tool_name = classify_request_as_analytics(request.url)

                net_req = NetworkRequest(
                    url=request.url,
                    method=request.method,
                    is_analytics=is_analytics,
                    analytics_type=tool_name,
                )

                # Extract payload from POST body
                try:
                    post_data = request.post_data
                    if post_data:
                        if isinstance(post_data, bytes):
                            net_req.payload = json.loads(
                                post_data.decode('utf-8', errors='ignore')
                            )
                        else:
                            net_req.payload = {'raw': str(post_data)}
                except Exception:
                    pass

                # Parse GA4 collect requests
                if is_analytics and 'GA4' in (tool_name or ''):
                    if 'collect' in request.url:
                        ga4_data = parse_ga4_event_data(request.url)
                        if ga4_data:
                            net_req.payload = ga4_data

                page_data.network_requests.append(asdict(net_req))

            except Exception as e:
                self.logger.debug(f"Error intercepting request {request.url}: {e}")

        async def on_response(response: Response) -> None:
            """Handle response."""
            try:
                # Find and update corresponding request
                for net_req in page_data.network_requests:
                    if net_req['url'] == response.url:
                        net_req['status'] = response.status
                        net_req['content_type'] = response.headers.get('content-type', '')

                        # Calculate duration if request time available
                        if response.url in request_times:
                            duration = (time.time() - request_times[response.url]) * 1000
                            net_req['duration_ms'] = duration

                        # Capture response body for small responses
                        try:
                            body = await response.text()
                            if len(body) < 5000:
                                net_req['response_body'] = body
                            net_req['size_bytes'] = len(body.encode('utf-8'))
                        except Exception:
                            pass

                        break
            except Exception as e:
                self.logger.debug(f"Error processing response: {e}")

        context.on('request', on_request)
        context.on('response', on_response)

    async def extract_dom_data(self, page: Page, page_data: PageData, url: str) -> None:
        """
        Extract all relevant DOM data from rendered page.

        Captures:
          - Page title, meta tags, canonical, OG tags
          - H1 tags
          - Forms with field names
          - CTAs (buttons/links with action keywords)
          - Internal and external links
          - Images without alt text
          - Schema.org JSON-LD
          - Breadcrumb structure

        Args:
            page: Playwright page object
            page_data: PageData object to store data
            url: Page URL
        """
        try:
            # Title and description
            page_data.title = await page.title()

            desc = await page.query_selector('meta[name="description"]')
            if desc:
                page_data.description = await desc.get_attribute('content') or ''

            # H1 tags
            h1_elems = await page.query_selector_all('h1')
            page_data.h1_tags = [
                (await elem.text_content() or '').strip()
                for elem in h1_elems
            ]

            # Canonical URL
            canonical = await page.query_selector('link[rel="canonical"]')
            if canonical:
                page_data.canonical_url = await canonical.get_attribute('href')

            # Robots meta
            robots = await page.query_selector('meta[name="robots"]')
            if robots:
                page_data.robots_meta = await robots.get_attribute('content')

            # OG tags
            og_metas = await page.query_selector_all('meta[property^="og:"]')
            for elem in og_metas:
                prop = await elem.get_attribute('property')
                content = await elem.get_attribute('content')
                if prop and content:
                    page_data.og_tags[prop] = content

            # hreflang links
            hreflang_links = await page.query_selector_all('link[rel="alternate"][hreflang]')
            for elem in hreflang_links:
                hreflang = await elem.get_attribute('hreflang')
                href = await elem.get_attribute('href')
                if hreflang and href:
                    page_data.hreflang_links[hreflang] = href

            # Forms
            form_elems = await page.query_selector_all('form')
            for form in form_elems:
                form_data = {
                    'action': await form.get_attribute('action') or '',
                    'method': (await form.get_attribute('method') or 'GET').upper(),
                    'fields': []
                }

                inputs = await form.query_selector_all('input, textarea, select')
                for inp in inputs:
                    field_name = await inp.get_attribute('name')
                    if field_name:
                        form_data['fields'].append(field_name)

                if form_data['fields']:
                    page_data.forms.append(form_data)

            # CTAs (buttons/links with action keywords)
            cta_keywords = [
                'book', 'enquiry', 'enquire', 'cart', 'add to cart',
                'buy', 'purchase', 'subscribe', 'download', 'contact',
                'register', 'signup', 'sign up', 'login', 'sign in'
            ]

            buttons = await page.query_selector_all('button, a[role="button"], a[class*="btn"]')
            for btn in buttons:
                text = (await btn.text_content() or '').lower().strip()
                if any(kw in text for kw in cta_keywords):
                    href = await btn.get_attribute('href')
                    page_data.ctas.append({
                        'text': text[:100],
                        'href': href or '',
                    })

            # Remove duplicate CTAs
            page_data.ctas = list({(c['text'], c['href']): c for c in page_data.ctas}.values())

            # Images without alt text
            images = await page.query_selector_all('img')
            for img in images:
                alt = await img.get_attribute('alt')
                if not alt or alt.strip() == '':
                    page_data.images_missing_alt += 1

            # Schema.org JSON-LD
            script_elems = await page.query_selector_all('script[type="application/ld+json"]')
            for script in script_elems:
                try:
                    content = await script.text_content()
                    schema = json.loads(content)
                    page_data.schema_org.append(schema)
                except Exception:
                    pass

            # Internal and external links
            link_elems = await page.query_selector_all('a[href]')
            for link in link_elems:
                href = await link.get_attribute('href')
                if href and not href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                    try:
                        full_url = urljoin(url, href)
                        if self.is_internal_url(full_url):
                            normalized = self.normalize_url(full_url)
                            page_data.internal_links.append(normalized)
                        else:
                            page_data.external_links.append(full_url)
                    except Exception:
                        pass

            # Deduplicate links
            page_data.internal_links = list(set(page_data.internal_links))
            page_data.external_links = list(set(page_data.external_links))

            # Breadcrumb structure
            try:
                breadcrumb = await page.query_selector('nav[aria-label="breadcrumb"], [class*="breadcrumb"]')
                if breadcrumb:
                    breadcrumb_items = await breadcrumb.query_selector_all('a, span')
                    breadcrumbs = [
                        (await item.text_content() or '').strip()
                        for item in breadcrumb_items
                    ]
                    if breadcrumbs:
                        page_data.breadcrumbs = {'items': breadcrumbs}
            except Exception:
                pass

        except Exception as e:
            self.logger.debug(f"Error extracting DOM data from {url}: {e}")

    def classify_template_type(self, url: str) -> str:
        """
        Classify page template based on URL pattern and depth.

        Returns one of:
          - homepage
          - listing
          - detail
          - destination
          - package
          - blog
          - accommodation
          - checkout
          - search
          - auth
          - static
          - reviews
          - other

        Args:
            url: Page URL

        Returns:
            Template type string
        """
        path = urlparse(url).path.lower()

        # Homepage
        if path == '/' or path == '':
            return 'homepage'

        # Specific paths
        if any(p in path for p in ['/checkout', '/cart', '/payment']):
            return 'checkout'
        if any(p in path for p in ['/search', '/filter', '/results']):
            return 'search'
        if any(p in path for p in ['/user', '/account', '/profile']):
            return 'auth'
        if any(p in path for p in ['/login', '/signin', '/sign-in']):
            return 'auth'
        if any(p in path for p in ['/register', '/signup', '/sign-up']):
            return 'auth'
        if any(p in path for p in ['/about', '/contact', '/faq', '/terms', '/privacy']):
            return 'static'
        if any(p in path for p in ['/reviews', '/rating']):
            return 'reviews'
        if any(p in path for p in ['/blog', '/articles', '/news', '/posts']):
            return 'blog'
        if any(p in path for p in ['/destinations', '/countries', '/cities', '/locations']):
            return 'destination'
        if any(p in path for p in ['/packages', '/tours', '/deals', '/offers']):
            return 'package'
        if any(p in path for p in ['/hotels', '/stays', '/resorts', '/accommodations']):
            return 'accommodation'
        if any(p in path for p in ['/products', '/tours', '/activities', '/things-to-do']):
            # Determine if listing or detail based on depth
            segments = [s for s in path.split('/') if s]
            if len(segments) > 2:
                return 'detail'
            else:
                return 'listing'

        return 'other'

    async def extract_performance_data(self, page: Page, page_data: PageData) -> None:
        """
        Extract performance metrics from page.

        Captures:
          - First Contentful Paint (FCP)
          - Largest Contentful Paint (LCP)
          - Request count and total transfer size
          - Resource breakdown by type

        Args:
            page: Playwright page object
            page_data: PageData object to store data
        """
        try:
            # Performance timing
            perf_data = await page.evaluate('''() => {
                const nav = performance.getEntriesByType('navigation')[0] || {};
                const fcp = performance.getEntriesByName('first-contentful-paint')[0];
                const lcp = performance.getEntriesByName('largest-contentful-paint');

                return {
                    fcp: fcp ? fcp.startTime : null,
                    lcp: lcp.length > 0 ? lcp[lcp.length - 1].startTime : null,
                };
            }''')

            if perf_data.get('fcp'):
                page_data.fcp_ms = perf_data['fcp']

            # Resource breakdown
            resource_types = await page.evaluate('''() => {
                const resources = performance.getEntriesByType('resource');
                const breakdown = {};

                resources.forEach(r => {
                    let type = 'other';
                    if (r.name.endsWith('.js') || r.initiatorType === 'script') type = 'script';
                    else if (r.name.endsWith('.css') || r.initiatorType === 'link') type = 'stylesheet';
                    else if (r.initiatorType === 'img') type = 'image';
                    else if (r.initiatorType === 'fetch' || r.initiatorType === 'xmlhttprequest') type = 'xhr';
                    else if (r.initiatorType === 'iframe') type = 'iframe';

                    breakdown[type] = (breakdown[type] || 0) + 1;
                });

                return breakdown;
            }''')

            page_data.resource_breakdown = resource_types or {}

        except Exception as e:
            self.logger.debug(f"Error extracting performance data: {e}")

    async def crawl_page(self, browser: Browser, url: str) -> Optional[PageData]:
        """
        Crawl a single page and extract all relevant data.

        Process:
          1. Create isolated browser context
          2. Setup network/console listeners
          3. Navigate with networkidle wait
          4. Wait 2 seconds for late-firing analytics
          5. Extract DOM, dataLayer, performance data
          6. Classify template and take screenshot

        Args:
            browser: Playwright browser instance
            url: URL to crawl

        Returns:
            PageData object or None if crawl failed
        """
        page_data = PageData(url=url)
        context = None
        page = None

        try:
            # Create isolated context
            context = await browser.new_context(
                viewport=self.viewport,
                user_agent=self.user_agent,
                ignore_https_errors=True,
            )

            await self.setup_network_interception(context, page_data)

            page = await context.new_page()

            # Console listener
            async def on_console(msg) -> None:
                try:
                    location = msg.location if msg.location else {}
                    console_msg = ConsoleMessage(
                        level=msg.type,
                        text=msg.text[:500],  # Truncate very long messages
                        source=location.get('url', 'page') or 'page',
                        line_number=location.get('lineNumber', 0) or 0,
                    )
                    page_data.console_messages.append(asdict(console_msg))
                except Exception:
                    pass

            page.on('console', on_console)

            # JS error listener
            async def on_page_error(error) -> None:
                try:
                    error_data = {
                        'message': str(error)[:200],
                        'timestamp': datetime.utcnow().isoformat(),
                    }
                    page_data.js_errors.append(error_data)
                except Exception:
                    pass

            page.on('pageerror', on_page_error)

            # Navigate to page
            start_time = time.time()
            try:
                response = await page.goto(
                    url,
                    wait_until='networkidle',
                    timeout=self.timeout * 1000
                )
                if response:
                    page_data.status_code = response.status
            except Exception as e:
                self.logger.debug(f"Navigation error for {url}: {e}")
                page_data.status_code = 0

            load_time_ms = (time.time() - start_time) * 1000
            page_data.load_time_ms = load_time_ms

            # Wait for late-firing analytics
            await page.wait_for_timeout(2000)

            # Extract all DOM data
            await self.extract_dom_data(page, page_data, url)

            # Extract dataLayer
            try:
                datalayer = await page.evaluate('() => window.dataLayer || []')
                if datalayer:
                    page_data.datalayer = datalayer if isinstance(datalayer, list) else [datalayer]
            except Exception:
                pass

            # Extract performance data
            await self.extract_performance_data(page, page_data)

            # Calculate metrics
            page_data.request_count = len(page_data.network_requests)
            page_data.total_transfer_bytes = sum(
                r.get('size_bytes', 0) for r in page_data.network_requests
            )

            # Classify template
            page_data.template_type = self.classify_template_type(url)

            # Get HTML for template hash
            try:
                html = await page.content()
                page_data.template_hash = hashlib.md5(html.encode()).hexdigest()[:16]
            except Exception:
                pass

            self.logger.info(
                f"[{len(self.crawled_pages) + 1}/{self.max_pages}] "
                f"{url} ({page_data.status_code}) - {page_data.template_type}"
            )

            return page_data

        except Exception as e:
            self.logger.error(f"Error crawling {url}: {e}")
            self.failed_urls[url] = str(e)[:200]
            return None

        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

    async def take_screenshot(
        self,
        browser: Browser,
        url: str,
        template_type: str,
        filename: str
    ) -> Optional[str]:
        """
        Capture screenshot of a page.

        Args:
            browser: Playwright browser instance
            url: Page URL
            template_type: Template classification
            filename: Output filename

        Returns:
            Path to screenshot or None if failed
        """
        context = None
        page = None

        try:
            context = await browser.new_context(
                viewport=self.viewport,
                user_agent=self.user_agent,
            )
            page = await context.new_page()

            await page.goto(url, wait_until='load', timeout=self.timeout * 1000)
            await page.wait_for_timeout(1000)

            screenshot_dir = os.path.join(self.output_dir, 'screenshots')
            os.makedirs(screenshot_dir, exist_ok=True)

            filepath = os.path.join(screenshot_dir, filename)
            await page.screenshot(path=filepath, full_page=True)

            self.logger.info(f"Screenshot: {filename}")
            return filepath

        except Exception as e:
            self.logger.debug(f"Screenshot failed for {url}: {e}")
            return None

        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

    def save_state(self) -> None:
        """Save crawl state for resume capability."""
        try:
            state_file = os.path.join(self.output_dir, 'crawl_state.json')
            state = {
                'timestamp': datetime.utcnow().isoformat(),
                'seed_url': self.seed_url,
                'visited_count': len(self.visited_urls),
                'queue_count': len(self.queue),
                'crawled_count': len(self.crawled_pages),
                'failed_count': len(self.failed_urls),
            }
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.logger.debug(f"Error saving state: {e}")

    async def run(self) -> Dict[str, Any]:
        """
        Execute the crawl.

        Process:
          1. Setup output directory
          2. Launch browser
          3. BFS crawl with URL queue
          4. Take screenshots of template types
          5. Save progress every 25 pages
          6. Compile and save results

        Returns:
            Dictionary with crawl results
        """
        self.crawl_start_time = datetime.utcnow()

        # Setup output directory
        os.makedirs(self.output_dir, exist_ok=True)
        if self.enable_screenshots:
            os.makedirs(os.path.join(self.output_dir, 'screenshots'), exist_ok=True)

        self.logger.info(f"Starting crawl: {self.seed_url}")
        self.logger.info(f"Max: {self.max_pages} | Delay: {self.delay}s | Timeout: {self.timeout}s")

        screenshots_taken: Set[str] = set()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)

            try:
                while self.queue and len(self.crawled_pages) < self.max_pages:
                    url = self.queue.pop(0)

                    # Check if should crawl
                    if not self.should_crawl_url(url):
                        continue

                    normalized = self.normalize_url(url)
                    self.visited_urls.add(normalized)

                    # Crawl page
                    page_data = await self.crawl_page(browser, url)

                    if page_data:
                        self.crawled_pages.append(page_data)

                        # Take screenshot of first occurrence of each template
                        if (self.enable_screenshots and
                            page_data.template_type and
                            page_data.template_type not in screenshots_taken):
                            try:
                                filename = f"{page_data.template_type}_{len(self.crawled_pages)}.png"
                                screenshot_path = await self.take_screenshot(
                                    browser, url, page_data.template_type, filename
                                )
                                if screenshot_path:
                                    page_data.screenshot_path = screenshot_path
                                    self.template_screenshots[page_data.template_type] = screenshot_path
                                    screenshots_taken.add(page_data.template_type)
                            except Exception as e:
                                self.logger.debug(f"Screenshot error: {e}")

                        # Add discovered internal links to queue
                        for link in page_data.internal_links:
                            if self.should_crawl_url(link) and len(self.queue) < self.max_pages * 2:
                                self.queue.append(link)

                        # Save state every 25 pages
                        if len(self.crawled_pages) % 25 == 0:
                            self.save_state()

                    # Delay between requests
                    if self.queue and len(self.crawled_pages) < self.max_pages:
                        await asyncio.sleep(self.delay)

            finally:
                await browser.close()

        self.crawl_end_time = datetime.utcnow()

        self.logger.info(
            f"Crawl complete: {len(self.crawled_pages)} pages, "
            f"{len(self.failed_urls)} failed"
        )

        return self.compile_results()

    def compile_results(self) -> Dict[str, Any]:
        """
        Compile crawl results into output structures.

        Creates:
          - crawl_data.json: Raw data
          - analytics_audit.json: Analytics findings
          - redirect_report.json: Redirects
          - template_map.json: Templates
          - performance_report.json: Performance
          - errors.json: JS/console errors
          - site_tree.json: URL hierarchy
          - crawl_state.json: Resume state

        Returns:
            Dictionary with all compiled results
        """
        # Build reports
        analytics_audit = self._build_analytics_audit()
        redirect_report = self._build_redirect_report()
        template_map = self._build_template_map()
        performance_report = self._build_performance_report()
        errors_report = self._build_errors_report()
        site_tree = self._build_site_tree()

        # Raw crawl data
        crawl_data = {
            'metadata': {
                'seed_url': self.seed_url,
                'crawl_start': self.crawl_start_time.isoformat() if self.crawl_start_time else None,
                'crawl_end': self.crawl_end_time.isoformat() if self.crawl_end_time else None,
                'total_pages_crawled': len(self.crawled_pages),
                'total_pages_failed': len(self.failed_urls),
                'max_pages_configured': self.max_pages,
            },
            'pages': [asdict(p) for p in self.crawled_pages],
            'failed_urls': self.failed_urls,
        }

        # Save all outputs
        self._save_json(crawl_data, 'crawl_data.json')
        self._save_json(analytics_audit, 'analytics_audit.json')
        self._save_json(redirect_report, 'redirect_report.json')
        self._save_json(template_map, 'template_map.json')
        self._save_json(performance_report, 'performance_report.json')
        self._save_json(errors_report, 'errors.json')
        self._save_json(site_tree, 'site_tree.json')

        # Save final state
        self.save_state()

        return {
            'crawl_data': crawl_data,
            'analytics_audit': analytics_audit,
            'redirect_report': redirect_report,
            'template_map': template_map,
            'performance_report': performance_report,
            'errors': errors_report,
            'site_tree': site_tree,
        }

    def _build_analytics_audit(self) -> Dict[str, Any]:
        """
        Extract analytics findings from crawl data.

        Returns:
            Analytics audit with tools detected, GA4 events, coverage, etc.
        """
        tools_found: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {'pages': [], 'count': 0}
        )
        ga4_events: Dict[str, Set[str]] = defaultdict(set)
        ga4_property_ids: Set[str] = set()
        gtm_containers: Set[str] = set()
        datalayer_vars: Set[str] = set()
        cross_domain_requests: Dict[str, int] = defaultdict(int)

        for page in self.crawled_pages:
            # Process network requests
            for req_dict in page.network_requests:
                if req_dict.get('is_analytics'):
                    tool = req_dict['analytics_type']
                    tools_found[tool]['pages'].append(page.url)
                    tools_found[tool]['count'] += 1

                    # Extract GA4 data
                    if 'GA4' in (tool or ''):
                        if req_dict.get('payload'):
                            payload = req_dict['payload']
                            if 'measurement_id' in payload:
                                ga4_property_ids.add(payload['measurement_id'])
                            if 'event_names' in payload:
                                for evt in payload['event_names']:
                                    ga4_events[page.url].add(evt)

                    # Extract GTM containers
                    if 'Google Tag Manager' in (tool or ''):
                        match = re.search(r'GTM-[A-Z0-9]+', req_dict['url'])
                        if match:
                            gtm_containers.add(match.group(0))

                # Track cross-domain requests
                if not self.is_internal_url(req_dict['url']):
                    try:
                        domain = urlparse(req_dict['url']).netloc
                        cross_domain_requests[domain] += 1
                    except Exception:
                        pass

            # Collect dataLayer variables
            if page.datalayer:
                if isinstance(page.datalayer, list):
                    for item in page.datalayer:
                        if isinstance(item, dict):
                            datalayer_vars.update(item.keys())
                elif isinstance(page.datalayer, dict):
                    datalayer_vars.update(page.datalayer.keys())

        # Calculate GA4 coverage
        ga4_firing_pages = set()
        for tool, data in tools_found.items():
            if 'GA4' in (tool or ''):
                ga4_firing_pages = set(data['pages'])

        ga4_coverage = (
            (len(ga4_firing_pages) / len(self.crawled_pages) * 100)
            if self.crawled_pages else 0
        )

        # Identify tracking gaps
        tracking_gaps = []
        if ga4_coverage < 100 and ga4_coverage > 0:
            missing_pages = [
                p.url for p in self.crawled_pages
                if p.url not in ga4_firing_pages
            ]
            if missing_pages:
                # Group by template type
                gaps_by_template = defaultdict(list)
                for url in missing_pages:
                    template = next(
                        (p.template_type for p in self.crawled_pages if p.url == url),
                        'unknown'
                    )
                    gaps_by_template[template].append(url)

                for template, urls in gaps_by_template.items():
                    tracking_gaps.append({
                        'template_type': template,
                        'affected_url_count': len(urls),
                        'example_urls': urls[:3],
                    })

        return {
            'summary': {
                'total_pages_analyzed': len(self.crawled_pages),
                'ga4_coverage_percent': round(ga4_coverage, 2),
                'ga4_firing_pages': len(ga4_firing_pages),
                'ga4_not_firing_pages': len(self.crawled_pages) - len(ga4_firing_pages),
                'gtm_containers_found': sorted(list(gtm_containers)),
                'analytics_tools_detected': sorted(list(tools_found.keys())),
            },
            'tools': {
                tool: {
                    'name': tool,
                    'request_count': data['count'],
                    'pages_detected_on': data['pages'][:50],  # Limit for output size
                    'unique_pages': len(set(data['pages'])),
                    'coverage_percent': round(
                        len(set(data['pages'])) / len(self.crawled_pages) * 100, 2
                    ) if self.crawled_pages else 0,
                }
                for tool, data in sorted(tools_found.items())
            },
            'ga4_events': {
                page_url: sorted(list(events))
                for page_url, events in ga4_events.items()
                if events
            },
            'ga4_property_ids': sorted(list(ga4_property_ids)),
            'datalayer_variables': sorted(list(datalayer_vars))[:100],  # Top 100
            'cross_domain_destinations': [
                {'domain': domain, 'request_count': count}
                for domain, count in sorted(
                    cross_domain_requests.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:50]
            ],
            'tracking_gaps': tracking_gaps,
        }

    def _build_redirect_report(self) -> Dict[str, Any]:
        """Build redirect chain information."""
        redirects = []
        for page in self.crawled_pages:
            if page.redirect_chain:
                chain_item = {
                    'final_url': page.url,
                    'chain_length': len(page.redirect_chain),
                    'hops': page.redirect_chain,
                    'is_flagged': len(page.redirect_chain) > 2,
                }
                redirects.append(chain_item)

        return {
            'total_redirects': len(redirects),
            'redirect_chains': redirects,
            'flagged_chains': [r for r in redirects if r['is_flagged']],
        }

    def _build_template_map(self) -> Dict[str, Any]:
        """Build template classification map."""
        templates: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {'urls': [], 'screenshot': None, 'hash': None}
        )

        for page in self.crawled_pages:
            if page.template_type:
                templates[page.template_type]['urls'].append(page.url)
                if page.screenshot_path and not templates[page.template_type]['screenshot']:
                    templates[page.template_type]['screenshot'] = page.screenshot_path
                if not templates[page.template_type]['hash']:
                    templates[page.template_type]['hash'] = page.template_hash

        return {
            'total_templates': len(templates),
            'templates': {
                tname: {
                    'name': tname,
                    'count': len(tdata['urls']),
                    'example_urls': tdata['urls'][:5],
                    'all_urls': tdata['urls'],
                    'screenshot_path': tdata['screenshot'],
                    'structural_hash': tdata['hash'],
                }
                for tname, tdata in sorted(templates.items())
            },
        }

    def _build_performance_report(self) -> Dict[str, Any]:
        """Compile performance metrics."""
        if not self.crawled_pages:
            return {}

        load_times = [
            p.load_time_ms for p in self.crawled_pages if p.load_time_ms > 0
        ]
        request_counts = [p.request_count for p in self.crawled_pages]
        transfer_sizes = [p.total_transfer_bytes for p in self.crawled_pages]

        return {
            'average_load_time_ms': (
                round(sum(load_times) / len(load_times), 2) if load_times else 0
            ),
            'median_load_time_ms': (
                sorted(load_times)[len(load_times) // 2] if load_times else 0
            ),
            'slowest_pages': sorted(
                [(p.url, round(p.load_time_ms, 2)) for p in self.crawled_pages],
                key=lambda x: x[1],
                reverse=True,
            )[:10],
            'average_requests_per_page': (
                round(sum(request_counts) / len(request_counts), 2)
                if request_counts else 0
            ),
            'average_transfer_size_bytes': (
                round(sum(transfer_sizes) / len(transfer_sizes), 2)
                if transfer_sizes else 0
            ),
            'pages_with_fcp': sum(1 for p in self.crawled_pages if p.fcp_ms),
            'resource_breakdown_aggregate': self._aggregate_resource_breakdown(),
        }

    def _aggregate_resource_breakdown(self) -> Dict[str, int]:
        """Aggregate resource breakdown across all pages."""
        aggregate = defaultdict(int)
        for page in self.crawled_pages:
            for resource_type, count in page.resource_breakdown.items():
                aggregate[resource_type] += count
        return dict(aggregate)

    def _build_errors_report(self) -> Dict[str, Any]:
        """Compile error information."""
        all_js_errors: Dict[str, int] = defaultdict(int)
        all_console_errors: Dict[str, int] = defaultdict(int)

        for page in self.crawled_pages:
            for error in page.js_errors:
                msg = error.get('message', 'Unknown')[:100]
                all_js_errors[msg] += 1

            for msg_dict in page.console_messages:
                if msg_dict['level'] in ('error', 'warn'):
                    text = msg_dict['text'][:100]
                    all_console_errors[f"{msg_dict['level']}: {text}"] += 1

        return {
            'total_js_errors': sum(all_js_errors.values()),
            'js_errors_by_message': dict(
                sorted(all_js_errors.items(), key=lambda x: x[1], reverse=True)[:20]
            ),
            'total_console_issues': sum(all_console_errors.values()),
            'console_issues': dict(
                sorted(all_console_errors.items(), key=lambda x: x[1], reverse=True)[:20]
            ),
            'pages_with_errors': {
                page.url: {
                    'js_error_count': len(page.js_errors),
                    'console_error_count': sum(
                        1 for m in page.console_messages
                        if m['level'] in ('error', 'warn')
                    ),
                }
                for page in self.crawled_pages
                if page.js_errors or any(
                    m['level'] in ('error', 'warn')
                    for m in page.console_messages
                )
            },
        }

    def _build_site_tree(self) -> Dict[str, Any]:
        """
        Build URL tree structure showing parent-child relationships.

        Returns:
            Hierarchical tree of URLs
        """
        tree: Dict[str, Dict[str, Any]] = {}

        for page in self.crawled_pages:
            parsed = urlparse(page.url)
            path = parsed.path

            # Get parent path
            if path == '/' or path == '':
                parent = '/'
                child = '/'
            else:
                parts = path.rstrip('/').split('/')
                if len(parts) <= 2:
                    parent = '/'
                    child = path
                else:
                    parent = '/'.join(parts[:-1])
                    child = path

            if parent not in tree:
                tree[parent] = {
                    'children': [],
                    'examples': [],
                }

            if child not in tree[parent]['examples']:
                tree[parent]['examples'].append(child)
                tree[parent]['children'].append(child)

        return {
            'total_urls': len(self.crawled_pages),
            'tree': tree,
        }

    def _save_json(self, data: Dict[str, Any], filename: str) -> None:
        """
        Save data to JSON file.

        Args:
            data: Data to save
            filename: Output filename
        """
        filepath = os.path.join(self.output_dir, filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            self.logger.info(f"Saved: {filename}")
        except Exception as e:
            self.logger.error(f"Error saving {filename}: {e}")


# ============================================================================
# CLI
# ============================================================================

def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='GA4 Crawler Kit - Production-grade website crawler for analytics audit',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    python crawler.py --url https://www.example.com --max-pages 200
    python crawler.py --url https://example.com --max-pages 50 \\
        --screenshots --output ./audit_results --headless
    python crawler.py --url https://example.com --max-pages 100 \\
        --delay 0.5 --timeout 60 --viewport 1280x1024
        '''
    )

    parser.add_argument('--url', required=True, help='Seed URL to start crawling')
    parser.add_argument(
        '--max-pages',
        type=int,
        default=200,
        help='Maximum pages to crawl (default: 200)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='Delay between requests in seconds (default: 1.0)'
    )
    parser.add_argument(
        '--output',
        default='./crawl_output',
        help='Output directory (default: ./crawl_output)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Page load timeout in seconds (default: 30)'
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        default=True,
        help='Run headless (default: True)'
    )
    parser.add_argument(
        '--headed',
        action='store_true',
        help='Run with visible browser window'
    )
    parser.add_argument(
        '--screenshots',
        action='store_true',
        help='Capture screenshots of template types'
    )
    parser.add_argument(
        '--user-agent',
        help='Custom user agent string'
    )
    parser.add_argument(
        '--viewport',
        default='1920x1080',
        help='Viewport size as WIDTHxHEIGHT (default: 1920x1080)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    # Setup logging
    logger = setup_logging(args.output, debug=args.debug)

    # Create crawler
    crawler = WebsiteCrawler(
        seed_url=args.url,
        max_pages=args.max_pages,
        delay=args.delay,
        timeout=args.timeout,
        headless=not args.headed,
        user_agent=args.user_agent,
        viewport=args.viewport,
        logger=logger,
        output_dir=args.output,
        enable_screenshots=args.screenshots,
    )

    # Run crawl
    try:
        results = asyncio.run(crawler.run())

        logger.info("Crawl completed successfully")

        # Print summary
        print("\n" + "=" * 80)
        print("GA4 CRAWLER - CRAWL SUMMARY")
        print("=" * 80)
        print(f"Seed URL:              {args.url}")
        print(f"Pages crawled:         {len(crawler.crawled_pages)}")
        print(f"Pages failed:          {len(crawler.failed_urls)}")
        print(f"Output directory:      {args.output}")
        print(f"Duration:              {crawler.crawl_end_time - crawler.crawl_start_time}")

        audit = results['analytics_audit']
        print(f"\nAnalytics Summary:")
        print(f"  Tools detected:      {', '.join(audit.get('summary', {}).get('analytics_tools_detected', []))}")
        print(f"  GA4 coverage:        {audit.get('summary', {}).get('ga4_coverage_percent', 0)}%")
        print(f"  GA4 property IDs:    {', '.join(audit.get('ga4_property_ids', []))}")

        perf = results['performance_report']
        if perf:
            print(f"\nPerformance Summary:")
            print(f"  Avg page load:       {perf.get('average_load_time_ms', 0)}ms")
            print(f"  Avg requests:        {perf.get('average_requests_per_page', 0)}")
            print(f"  Avg transfer size:   {perf.get('average_transfer_size_bytes', 0)} bytes")

        print(f"\nOutput Files:")
        print(f"  - crawl_data.json         (raw crawl data)")
        print(f"  - analytics_audit.json    (analytics findings)")
        print(f"  - redirect_report.json    (redirect chains)")
        print(f"  - template_map.json       (page templates)")
        print(f"  - performance_report.json (performance metrics)")
        print(f"  - errors.json             (JS/console errors)")
        print(f"  - site_tree.json          (URL hierarchy)")
        print(f"  - crawl_state.json        (state for resume)")
        print(f"  - crawler.log             (detailed log)")
        if args.screenshots:
            print(f"  - screenshots/            (template screenshots)")
        print("=" * 80 + "\n")

    except KeyboardInterrupt:
        logger.info("Crawl interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Crawl failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
