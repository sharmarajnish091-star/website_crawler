#!/usr/bin/env python3
"""
generate_dashboard.py - GA4 Analytics Audit Dashboard Generator

Converts crawl output JSON files from crawler.py into a beautiful, self-contained
HTML dashboard for GA4 analytics auditing.

Usage:
    python generate_dashboard.py --input ./crawl_output --output ./ga4_audit_report.html --title "Site Name"

Arguments:
    --input: Directory containing crawl output JSON files (required)
    --output: Path to output HTML file (default: ga4_audit_report.html)
    --title: Dashboard title (auto-detected from crawl data if not provided)

Features:
    - Executive Summary with key metrics and data confidence
    - Analytics Tools Audit with coverage analysis
    - Interactive URL tree visualization
    - Page template analysis with screenshots
    - Redirect chain diagrams and analysis
    - Performance distribution charts (pure CSS/SVG, no external libs)
    - Errors and issues report
    - GA4 Implementation Roadmap with 4 phases
    - Professional design, print-friendly, mobile-responsive
    - Single self-contained HTML file with inline CSS/JS

Requirements:
    - Python 3.8+
    - No external dependencies (uses only stdlib: json, os, argparse, datetime, base64, html)

Author: GA4 Audit Automation
License: MIT
"""

import json
import argparse
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
import base64
import html as html_module


# ============================================================================
# LOGGING
# ============================================================================

def setup_logging(debug: bool = False) -> logging.Logger:
    """Setup logging."""
    logger = logging.getLogger(__name__)
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)

    ch = logging.StreamHandler()
    ch.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def load_json(filepath: str) -> Dict[str, Any]:
    """Load JSON file safely, return empty dict if missing/invalid."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def encode_image_to_base64(filepath: str) -> Optional[str]:
    """Encode image to base64 for embedding in HTML."""
    try:
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'rb') as f:
            data = f.read()
        ext = Path(filepath).suffix.lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        mime = mime_types.get(ext, 'image/png')
        encoded = base64.b64encode(data).decode('utf-8')
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return None


def escape_html(text: str) -> str:
    """Escape HTML special characters using html module."""
    return html_module.escape(str(text))


def truncate_url(url: str, max_len: int = 60) -> str:
    """Truncate URL for display."""
    if len(url) > max_len:
        return url[:max_len-3] + '...'
    return url


def calculate_data_confidence(sample_size: int) -> str:
    """Calculate confidence level based on sample size."""
    if sample_size < 50:
        return 'low'
    elif sample_size < 100:
        return 'medium'
    else:
        return 'high'


def calculate_coverage_color(coverage: float) -> str:
    """Return CSS color class based on coverage percentage."""
    if coverage >= 90:
        return 'coverage-green'
    elif coverage >= 50:
        return 'coverage-amber'
    else:
        return 'coverage-red'


# ============================================================================
# DASHBOARD DATA PROCESSOR
# ============================================================================

class DashboardDataProcessor:
    """Process crawl data for dashboard display."""

    def __init__(self, crawl_output_dir: str):
        """Initialize processor with crawl output directory."""
        self.output_dir = crawl_output_dir

        # Load all JSON files (graceful handling of missing files)
        self.crawl_data = load_json(os.path.join(crawl_output_dir, 'crawl_data.json'))
        self.analytics_audit = load_json(os.path.join(crawl_output_dir, 'analytics_audit.json'))
        self.redirect_report = load_json(os.path.join(crawl_output_dir, 'redirect_report.json'))
        self.template_map = load_json(os.path.join(crawl_output_dir, 'template_map.json'))
        self.performance_report = load_json(os.path.join(crawl_output_dir, 'performance_report.json'))
        self.errors_report = load_json(os.path.join(crawl_output_dir, 'errors.json'))
        self.site_tree = load_json(os.path.join(crawl_output_dir, 'site_tree.json'))

    def get_seed_url(self) -> str:
        """Get seed URL from crawl data."""
        return self.crawl_data.get('metadata', {}).get('seed_url', 'https://example.com')

    def get_site_name(self) -> str:
        """Extract site name from URL."""
        url = self.get_seed_url()
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            return domain.replace('www.', '')
        except Exception:
            return 'Website'

    def get_crawl_timestamp(self) -> str:
        """Get crawl timestamp."""
        ts = self.crawl_data.get('metadata', {}).get('crawl_end')
        if ts:
            return ts
        return datetime.utcnow().isoformat()

    def get_executive_summary(self) -> Dict[str, Any]:
        """Prepare executive summary data."""
        metadata = self.crawl_data.get('metadata', {})
        audit_summary = self.analytics_audit.get('summary', {})
        perf = self.performance_report

        total_pages = metadata.get('total_pages_crawled', 0)

        return {
            'total_pages': total_pages,
            'unique_templates': self.template_map.get('total_templates', len(self.template_map.get('templates', {}))),
            'total_redirects': self.redirect_report.get('total_redirects', 0),
            'ga4_coverage': audit_summary.get('ga4_coverage_percent', 0),
            'avg_load_time_ms': perf.get('average_load_time_ms', 0),
            'analytics_tools': len(audit_summary.get('analytics_tools_detected', [])),
            'data_confidence': calculate_data_confidence(total_pages)
        }

    def get_analytics_tools_table(self) -> List[Dict[str, Any]]:
        """Prepare analytics tools table data."""
        tools = self.analytics_audit.get('tools', {})
        total_pages = self.crawl_data.get('metadata', {}).get('total_pages_crawled', 1)

        result = []
        for tool_name, tool_data in sorted(tools.items()):
            pages_with_tool = len(tool_data.get('pages_detected_on', []))
            coverage = (pages_with_tool / total_pages * 100) if total_pages > 0 else 0

            result.append({
                'name': tool_data.get('name', tool_name),
                'property_id': tool_data.get('property_id', 'N/A'),
                'request_count': tool_data.get('request_count', 0),
                'coverage_percent': coverage,
                'pages_detected': pages_with_tool,
                'status': 'Active' if coverage > 0 else 'Inactive'
            })

        return sorted(result, key=lambda x: x['coverage_percent'], reverse=True)

    def get_ga4_events_summary(self) -> Dict[str, Any]:
        """Prepare GA4 events summary."""
        events = self.analytics_audit.get('ga4_events', {})

        all_events = set()
        event_pages = defaultdict(list)

        for page_url, page_events in events.items():
            for event in page_events:
                all_events.add(event)
                event_pages[event].append(page_url)

        # Create event summary table
        event_summary = []
        for event_name in sorted(all_events):
            pages = event_pages.get(event_name, [])
            event_summary.append({
                'name': event_name,
                'count': len(pages),
                'pages': pages[:3]  # Show first 3 pages
            })

        return {
            'unique_events': sorted(list(all_events)),
            'event_count': len(all_events),
            'event_summary': event_summary,
            'property_ids': self.analytics_audit.get('ga4_property_ids', [])
        }

    def get_datalayer_summary(self) -> Dict[str, Any]:
        """Prepare dataLayer summary."""
        datalayer_vars = self.analytics_audit.get('datalayer_variables', [])
        ecommerce_vars = [v for v in datalayer_vars if 'ecommerce' in v.lower() or 'purchase' in v.lower() or 'product' in v.lower()]

        return {
            'total_variables': len(datalayer_vars),
            'variables': sorted(datalayer_vars),
            'ecommerce_enabled': len(ecommerce_vars) > 0,
            'ecommerce_variables': ecommerce_vars
        }

    def get_url_tree(self) -> Dict[str, Any]:
        """Build URL tree structure."""
        pages = self.crawl_data.get('pages', [])

        tree = {
            'name': self.get_site_name(),
            'url': self.get_seed_url(),
            'children': []
        }

        # Group by first path segment
        url_tree = defaultdict(list)
        for page in pages:
            url = page.get('url', '')
            try:
                from urllib.parse import urlparse
                path = urlparse(url).path
                parts = path.strip('/').split('/')
                key = '/' + parts[0] if parts and parts[0] else '/'
                url_tree[key].append(url)
            except Exception:
                url_tree['other'].append(url)

        # Build tree structure
        for key in sorted(url_tree.keys()):
            urls = url_tree[key]
            branch = {
                'name': key,
                'count': len(urls),
                'urls': urls[:10]
            }
            tree['children'].append(branch)

        return tree

    def get_template_data(self) -> List[Dict[str, Any]]:
        """Prepare template cards data."""
        templates = self.template_map.get('templates', {})

        result = []

        # Handle both dict format {name: data} and list format [{type: ..., count: ...}]
        if isinstance(templates, list):
            items = [(t.get('type', t.get('name', 'unknown')), t) for t in templates]
        elif isinstance(templates, dict):
            items = sorted(templates.items())
        else:
            items = []

        for template_name, template_data in items:
            # Try to load screenshot
            screenshot_b64 = None
            if template_data.get('screenshots'):
                screenshot_path = template_data['screenshots'][0]
                full_path = os.path.join(self.output_dir, 'screenshots', os.path.basename(screenshot_path))
                screenshot_b64 = encode_image_to_base64(full_path)
            elif template_data.get('screenshot_path'):
                full_path = os.path.join(self.output_dir, 'screenshots', os.path.basename(template_data['screenshot_path']))
                screenshot_b64 = encode_image_to_base64(full_path)

            result.append({
                'name': template_name,
                'count': template_data.get('count', 0),
                'example_urls': template_data.get('example_urls', [])[:5],
                'screenshot': screenshot_b64,
                'recommended_events': self._get_recommended_events(template_name)
            })

        return sorted(result, key=lambda x: x['count'], reverse=True)

    def _get_recommended_events(self, template_type: str) -> List[str]:
        """Get recommended GA4 events for template type."""
        recommendations = {
            'homepage': ['page_view', 'session_start'],
            'product_detail': ['page_view', 'view_item', 'view_item_list'],
            'search_results': ['page_view', 'search', 'view_item_list'],
            'booking': ['page_view', 'begin_checkout', 'add_to_cart'],
            'checkout': ['page_view', 'begin_checkout', 'add_payment_info', 'purchase'],
            'contact': ['page_view', 'form_submit'],
            'blog_post': ['page_view', 'scroll', 'click'],
            'login': ['page_view', 'login'],
            'registration': ['page_view', 'sign_up']
        }
        return recommendations.get(template_type, ['page_view'])

    def get_redirect_chains(self) -> List[Dict[str, Any]]:
        """Prepare redirect chain data."""
        chains = self.redirect_report.get('redirect_chains', [])
        return [
            {
                'final_url': chain.get('final_url', ''),
                'chain_length': chain.get('chain_length', 0),
                'hops': chain.get('hops', []),
                'is_flagged': chain.get('chain_length', 0) > 2
            }
            for chain in chains
        ]

    def get_performance_data(self) -> Dict[str, Any]:
        """Prepare performance data for charts."""
        pages = self.crawl_data.get('pages', [])
        load_times = [p.get('load_time_ms', 0) for p in pages if p.get('load_time_ms', 0) > 0]

        # Create load time distribution buckets
        buckets = [0, 1000, 2000, 3000, 5000, 10000, float('inf')]
        bucket_labels = ['<1s', '1-2s', '2-3s', '3-5s', '5-10s', '10s+']
        distribution = [0] * len(bucket_labels)

        for time_ms in load_times:
            for i, bucket in enumerate(buckets[:-1]):
                if bucket <= time_ms < buckets[i+1]:
                    distribution[i] += 1
                    break

        slowest = self.performance_report.get('slowest_pages', [])

        return {
            'avg_load_ms': self.performance_report.get('average_load_time_ms', 0),
            'median_load_ms': self.performance_report.get('median_load_time_ms', 0),
            'p95_load_ms': self.performance_report.get('p95_load_time_ms', 0),
            'p99_load_ms': self.performance_report.get('p99_load_time_ms', 0),
            'avg_requests': self.performance_report.get('average_requests_per_page', 0),
            'avg_transfer_bytes': self.performance_report.get('average_transfer_size_bytes', 0),
            'distribution_labels': bucket_labels,
            'distribution_values': distribution,
            'slowest_pages': slowest[:10]
        }

    def get_errors_summary(self) -> Dict[str, Any]:
        """Prepare errors summary."""
        errors = self.errors_report

        js_errors = errors.get('js_errors_by_message', {})
        console_issues = errors.get('console_issues', {})

        # Build error detail list
        js_error_list = [
            {'message': msg, 'count': count}
            for msg, count in list(js_errors.items())[:10]
        ]
        console_issue_list = [
            {'message': msg, 'count': count}
            for msg, count in list(console_issues.items())[:10]
        ]

        return {
            'total_js_errors': errors.get('total_js_errors', 0),
            'total_console_issues': errors.get('total_console_issues', 0),
            'js_error_messages': js_error_list,
            'console_issues': console_issue_list,
            'pages_with_errors': len(errors.get('pages_with_errors', {}))
        }

    def get_ga4_roadmap(self) -> Dict[str, List[Dict[str, str]]]:
        """Prepare GA4 implementation roadmap."""
        return {
            'phase_1_critical': [
                {
                    'event': 'page_view',
                    'description': 'Track every page load',
                    'implementation': 'Enable GA4 tag in GTM or gtag.js'
                },
                {
                    'event': 'view_item',
                    'description': 'Product/service detail page views',
                    'implementation': 'Populate ecommerce data layer and send event'
                },
                {
                    'event': 'add_to_cart / begin_checkout',
                    'description': 'User intent to purchase',
                    'implementation': 'Trigger on form display or button click'
                },
                {
                    'event': 'purchase',
                    'description': 'Completed transactions',
                    'implementation': 'Send with transaction ID, value, currency'
                }
            ],
            'phase_2_high': [
                {
                    'event': 'search',
                    'description': 'User search activity',
                    'implementation': 'Trigger on search submission with search term'
                },
                {
                    'event': 'view_item_list',
                    'description': 'Search results/category pages',
                    'implementation': 'Send with category, items list'
                },
                {
                    'event': 'select_item',
                    'description': 'Item selection from list',
                    'implementation': 'Track clicks on search/category results'
                },
                {
                    'event': 'view_promotion',
                    'description': 'Marketing promotions displayed',
                    'implementation': 'Send when promo banner/email is shown'
                }
            ],
            'phase_3_medium': [
                {
                    'event': 'scroll',
                    'description': 'Page engagement - scroll depth',
                    'implementation': 'Use scroll event listener or GTM scroll trigger'
                },
                {
                    'event': 'click',
                    'description': 'General link/button clicks',
                    'implementation': 'Use click event listener or GTM element tracker'
                },
                {
                    'event': 'form_start / form_submit',
                    'description': 'Contact/booking form interactions',
                    'implementation': 'Trigger on form focus and submission'
                },
                {
                    'event': 'video_start / video_complete',
                    'description': 'Video engagement',
                    'implementation': 'Integrate with video player API'
                }
            ],
            'phase_4_low': [
                {
                    'event': 'add_to_wishlist',
                    'description': 'Wishlist additions',
                    'implementation': 'Trigger on wishlist button click'
                },
                {
                    'event': 'share',
                    'description': 'Content sharing',
                    'implementation': 'Trigger on share button click'
                },
                {
                    'event': 'login / sign_up',
                    'description': 'Authentication events',
                    'implementation': 'Trigger on successful auth completion'
                }
            ]
        }


# ============================================================================
# HTML DASHBOARD GENERATOR
# ============================================================================

class DashboardHTMLGenerator:
    """Generate self-contained HTML dashboard without external dependencies."""

    def __init__(self):
        """Initialize generator."""
        pass

    def _generate_analytics_tools_table(self, tools: List[Dict[str, Any]]) -> str:
        """Generate analytics tools table HTML."""
        if not tools:
            return '<div class="no-data">No analytics tools detected</div>'

        html = '<table><thead><tr>'
        html += '<th>Tool Name</th><th>Property/Container ID</th><th>Pages Detected</th>'
        html += '<th>Coverage %</th></tr></thead><tbody>'

        for tool in tools:
            coverage = tool['coverage_percent']
            coverage_class = calculate_coverage_color(coverage)
            html += f'<tr>'
            html += f'<td><strong>{escape_html(tool["name"])}</strong></td>'
            html += f'<td>{escape_html(tool["property_id"])}</td>'
            html += f'<td>{tool["pages_detected"]} pages</td>'
            html += f'<td><div class="coverage-bar {coverage_class}">'
            html += f'<div class="coverage-fill" style="width: {coverage}%;">{coverage:.0f}%</div>'
            html += f'</div></td>'
            html += f'</tr>'

        html += '</tbody></table>'
        return html

    def _generate_ga4_events_section(self, ga4_events: Dict[str, Any]) -> str:
        """Generate GA4 events section HTML."""
        html = '<h3 style="font-size: 16px; margin-bottom: 15px; color: #1a1a2e;">GA4 Events Detected</h3>'

        if ga4_events['unique_events']:
            html += f'<p style="margin-bottom: 15px; font-size: 13px; color: #666;">'
            html += f'{ga4_events["event_count"]} unique events detected</p>'

            if ga4_events['event_summary']:
                html += '<table style="font-size: 13px;"><thead><tr>'
                html += '<th>Event Name</th><th>Occurrences</th><th>Sample Pages</th></tr>'
                html += '</thead><tbody>'

                for event in ga4_events['event_summary']:
                    sample_urls = ', '.join([truncate_url(p, 40) for p in event['pages'][:2]])
                    html += f'<tr><td><code>{escape_html(event["name"])}</code></td>'
                    html += f'<td>{event["count"]}</td>'
                    html += f'<td style="font-size: 12px;">{escape_html(sample_urls)}</td></tr>'

                html += '</tbody></table>'
            else:
                html += '<div style="display: flex; flex-wrap: wrap; gap: 8px;">'
                for event in ga4_events['unique_events'][:15]:
                    html += f'<span class="event-tag">{escape_html(event)}</span>'
                html += '</div>'
        else:
            html += '<div class="no-data">No GA4 events detected</div>'

        return html

    def _generate_datalayer_section(self, datalayer: Dict[str, Any]) -> str:
        """Generate dataLayer section HTML."""
        html = '<div style="border-top: 2px solid #f0f0f0; padding-top: 20px;">'
        html += '<h3 style="font-size: 16px; margin-bottom: 15px; color: #1a1a2e;">dataLayer Variables</h3>'

        if datalayer['variables']:
            html += f'<p style="margin-bottom: 15px; font-size: 13px; color: #666;">'
            html += f'{datalayer["total_variables"]} variables found</p>'

            if datalayer['ecommerce_enabled']:
                html += '<div class="alert-box alert-success">✓ eCommerce dataLayer detected</div>'

            html += '<div style="display: flex; flex-wrap: wrap; gap: 8px;">'
            for var in datalayer['variables'][:20]:
                html += f'<span class="event-tag" style="background: #e8f4f8; color: #0066cc;">'
                html += f'{escape_html(var)}</span>'
            html += '</div>'
        else:
            html += '<div class="no-data">No dataLayer variables detected</div>'

        html += '</div>'
        return html

    def _generate_url_tree(self, url_tree: Dict[str, Any]) -> str:
        """Generate URL tree HTML."""
        if not url_tree.get('children'):
            return '<div class="no-data">No URLs found</div>'

        html = '<div class="url-tree">'
        html += f'<div><strong>{escape_html(url_tree["name"])}</strong></div>'

        for branch in url_tree['children']:
            html += f'<div class="url-item">📁 <strong>{escape_html(branch["name"])}</strong> '
            html += f'({branch["count"]} pages)'

            if branch['urls']:
                html += '<div style="margin-left: 10px; font-size: 11px;">'
                for url in branch['urls'][:5]:
                    html += f'<div>→ {escape_html(truncate_url(url, 70))}</div>'
                if branch['count'] > 5:
                    html += f'<div style="color: #999;">... and {branch["count"] - 5} more</div>'
                html += '</div>'

            html += '</div>'

        html += '</div>'
        return html

    def _generate_template_cards(self, templates: List[Dict[str, Any]]) -> str:
        """Generate template cards grid HTML."""
        if not templates:
            return '<div class="no-data">No templates found</div>'

        html = '<div class="grid-3">'

        for template in templates:
            html += '<div class="template-card">'

            if template['screenshot']:
                html += f'<img src="{template["screenshot"]}" alt="{escape_html(template["name"])}" class="template-screenshot">'
            else:
                html += '<div class="template-screenshot" style="display: flex; align-items: center; justify-content: center; color: #999;">No screenshot</div>'

            html += f'<div class="template-name">{escape_html(template["name"])}</div>'
            html += f'<div class="template-count">{template["count"]} page{"s" if template["count"] != 1 else ""}</div>'
            html += '<div class="template-events"><strong style="font-size: 12px;">Recommended events:</strong>'
            html += '<div style="margin-top: 6px;">'

            for event in template['recommended_events']:
                html += f'<span class="event-tag">{escape_html(event)}</span>'

            html += '</div></div></div>'

        html += '</div>'
        return html

    def _generate_redirect_chains(self, chains: List[Dict[str, Any]]) -> str:
        """Generate redirect chains HTML."""
        if not chains:
            return ''

        html = '<div class="section">'
        html += '<h2 class="section-title">Redirect Analysis</h2>'
        html += '<p style="margin-bottom: 20px; font-size: 14px; color: #666;">'
        html += 'Redirect chains with more than 2 hops are flagged as they may impact analytics tracking.'
        html += '</p>'

        for chain in chains:
            flagged = chain['is_flagged']
            flag_class = 'flagged' if flagged else ''
            html += f'<div class="redirect-chain {flag_class}">'
            html += f'<strong style="{"color: #ff6b6b;" if flagged else ""}">'

            if flagged:
                html += '⚠ '

            html += f'Chain: {chain["chain_length"]} hop{"s" if chain["chain_length"] != 1 else ""}</strong>'
            html += f'<div style="margin-top: 8px; font-size: 11px;">'
            html += f'Final: {escape_html(truncate_url(chain["final_url"], 80))}'
            html += '</div></div>'

        html += '</div>'
        return html

    def _generate_performance_section(self, performance: Dict[str, Any]) -> str:
        """Generate performance analysis HTML."""
        html = '<div class="grid-2">'

        # Stats section
        html += '<div><h3 style="font-size: 14px; margin-bottom: 15px; color: #1a1a2e;">Load Time Statistics</h3>'
        html += '<table style="font-size: 12px;"><tr><td>Average Load Time:</td>'
        html += f'<td><strong>{performance["avg_load_ms"]:.0f}ms</strong></td></tr>'
        html += '<tr><td>Median Load Time:</td>'
        html += f'<td><strong>{performance["median_load_ms"]:.0f}ms</strong></td></tr>'
        html += '<tr><td>P95 Load Time:</td>'
        html += f'<td><strong>{performance["p95_load_ms"]:.0f}ms</strong></td></tr>'
        html += '<tr><td>Avg Requests/Page:</td>'
        html += f'<td><strong>{performance["avg_requests"]:.0f}</strong></td></tr>'
        html += '<tr><td>Avg Transfer Size:</td>'
        html += f'<td><strong>{performance["avg_transfer_bytes"] / 1024:.0f}KB</strong></td></tr>'
        html += '</table></div>'

        # Distribution section
        html += '<div><h3 style="font-size: 14px; margin-bottom: 15px; color: #1a1a2e;">Load Time Distribution</h3>'
        html += '<table style="font-size: 12px;">'

        for label, value in zip(performance['distribution_labels'], performance['distribution_values']):
            html += f'<tr><td>{escape_html(label)}</td><td>'
            html += '<div class="coverage-bar" style="width: 150px;">'

            if value > 0:
                max_val = max(performance['distribution_values'])
                bar_width = (value / max_val * 100) if max_val > 0 else 0
                html += f'<div class="coverage-fill" style="width: {bar_width}%; background: #8fd3f4;">{value}</div>'

            html += '</div></td></tr>'

        html += '</table></div>'
        html += '</div>'

        # Slowest pages
        if performance['slowest_pages']:
            html += '<div style="margin-top: 25px; border-top: 2px solid #f0f0f0; padding-top: 20px;">'
            html += '<h3 style="font-size: 14px; margin-bottom: 15px; color: #1a1a2e;">Slowest Pages</h3>'
            html += '<table style="font-size: 12px;"><thead><tr><th>URL</th><th style="text-align: right;">Load Time</th></tr></thead><tbody>'

            for page_data in performance['slowest_pages'][:10]:
                if isinstance(page_data, (list, tuple)):
                    url, load_time = page_data
                else:
                    url = page_data.get('url', '')
                    load_time = page_data.get('load_time_ms', 0)

                html += f'<tr><td>{escape_html(truncate_url(url, 70))}</td>'
                html += f'<td style="text-align: right;"><strong>{load_time:.0f}ms</strong></td></tr>'

            html += '</tbody></table></div>'

        return html

    def _generate_errors_section(self, errors: Dict[str, Any]) -> str:
        """Generate errors section HTML."""
        html = '<div class="grid-2">'

        # JS Errors
        html += '<div><h3 style="font-size: 14px; margin-bottom: 15px; color: #1a1a2e;">JavaScript Errors</h3>'
        html += f'<p style="font-size: 13px; margin-bottom: 10px;">Total: <strong>{errors["total_js_errors"]}</strong></p>'

        if errors['js_error_messages']:
            html += '<div style="font-size: 12px;">'
            for err in errors['js_error_messages']:
                msg = err['message'] if isinstance(err, dict) else err
                html += f'<div style="background: #fff3cd; padding: 8px; border-radius: 3px; margin-bottom: 8px;">'
                html += f'{escape_html(truncate_url(msg, 60))}</div>'
            html += '</div>'
        else:
            html += '<div class="no-data" style="padding: 15px;">No JS errors detected</div>'

        html += '</div>'

        # Console Issues
        html += '<div><h3 style="font-size: 14px; margin-bottom: 15px; color: #1a1a2e;">Console Issues</h3>'
        html += f'<p style="font-size: 13px; margin-bottom: 10px;">Total: <strong>{errors["total_console_issues"]}</strong></p>'

        if errors['console_issues']:
            html += '<div style="font-size: 12px;">'
            for issue in errors['console_issues']:
                msg = issue['message'] if isinstance(issue, dict) else issue
                html += f'<div style="background: #f8d7da; padding: 8px; border-radius: 3px; margin-bottom: 8px;">'
                html += f'{escape_html(truncate_url(msg, 60))}</div>'
            html += '</div>'
        else:
            html += '<div class="no-data" style="padding: 15px;">No console issues detected</div>'

        html += '</div></div>'
        return html

    def _generate_roadmap_section(self, roadmap: Dict[str, List[Dict[str, str]]]) -> str:
        """Generate GA4 roadmap HTML."""
        phase_order = ['phase_1_critical', 'phase_2_high', 'phase_3_medium', 'phase_4_low']
        phase_titles = {
            'phase_1_critical': 'Phase 1 - Critical Priority',
            'phase_2_high': 'Phase 2 - High Priority',
            'phase_3_medium': 'Phase 3 - Medium Priority',
            'phase_4_low': 'Phase 4 - Low Priority'
        }

        html = ''

        for phase_key in phase_order:
            if phase_key not in roadmap:
                continue

            items = roadmap[phase_key]
            html += '<div class="roadmap-phase">'
            html += f'<div class="roadmap-phase-title">{phase_titles[phase_key]}</div>'

            for item in items:
                html += '<div class="roadmap-item">'
                html += f'<div class="roadmap-event">{escape_html(item["event"])}</div>'
                html += f'<div class="roadmap-description">{escape_html(item["description"])}</div>'
                html += f'<div class="roadmap-implementation">📌 {escape_html(item["implementation"])}</div>'
                html += '</div>'

            html += '</div>'

        return html

    def generate(self, processor: DashboardDataProcessor, output_file: str, title: Optional[str] = None) -> str:
        """Generate complete HTML dashboard."""

        # Get all data
        summary = processor.get_executive_summary()
        analytics_tools = processor.get_analytics_tools_table()
        ga4_events = processor.get_ga4_events_summary()
        datalayer = processor.get_datalayer_summary()
        url_tree = processor.get_url_tree()
        templates = processor.get_template_data()
        redirect_chains = processor.get_redirect_chains()
        performance = processor.get_performance_data()
        errors = processor.get_errors_summary()
        roadmap = processor.get_ga4_roadmap()

        # Determine title
        if not title:
            title = processor.get_site_name()

        # Generate timestamp
        audit_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

        # Determine confidence badge
        confidence = summary['data_confidence']
        confidence_colors = {
            'high': '#27ae60',
            'medium': '#f39c12',
            'low': '#e74c3c'
        }
        confidence_color = confidence_colors.get(confidence, '#999')

        # Build HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape_html(title)} - GA4 Analytics Audit Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }}

        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            padding: 30px 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}

        .header-content {{
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .header h1 {{
            font-size: 28px;
            font-weight: 600;
        }}

        .header-meta {{
            text-align: right;
            font-size: 13px;
            opacity: 0.9;
        }}

        .badge {{
            display: inline-block;
            background: #0f3460;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            margin-top: 8px;
        }}

        .container {{
            max-width: 1400px;
            margin: 30px auto;
            padding: 0 20px;
        }}

        .section {{
            background: white;
            border-radius: 8px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}

        .section-title {{
            font-size: 22px;
            font-weight: 600;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 2px solid #f0f0f0;
            color: #1a1a2e;
        }}

        .grid-2 {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}

        .grid-3 {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }}

        .metric-card {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}

        .metric-card.success {{
            background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%);
        }}

        .metric-card.warning {{
            background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
        }}

        .metric-card.danger {{
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e8e 100%);
        }}

        .metric-value {{
            font-size: 36px;
            font-weight: 700;
            color: #1a1a2e;
            margin-bottom: 8px;
        }}

        .metric-label {{
            font-size: 13px;
            color: #555;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}

        th {{
            background: #f5f5f5;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            font-size: 13px;
            color: #555;
            border-bottom: 2px solid #e0e0e0;
        }}

        td {{
            padding: 12px;
            border-bottom: 1px solid #f0f0f0;
            font-size: 14px;
        }}

        tr:hover {{
            background: #fafafa;
        }}

        .status-badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}

        .status-active {{
            background: #d4edda;
            color: #155724;
        }}

        .status-inactive {{
            background: #f8d7da;
            color: #721c24;
        }}

        .coverage-bar {{
            background: #e0e0e0;
            height: 24px;
            border-radius: 4px;
            overflow: hidden;
            margin: 8px 0;
        }}

        .coverage-fill {{
            background: linear-gradient(90deg, #84fab0 0%, #8fd3f4 100%);
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 600;
            color: white;
        }}

        .coverage-green .coverage-fill {{
            background: #27ae60;
        }}

        .coverage-amber .coverage-fill {{
            background: #f39c12;
        }}

        .coverage-red .coverage-fill {{
            background: #e74c3c;
        }}

        .url-tree {{
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 12px;
            background: #f5f5f5;
            padding: 15px;
            border-radius: 6px;
            max-height: 400px;
            overflow-y: auto;
            line-height: 1.8;
        }}

        .url-item {{
            margin-left: 20px;
            color: #0066cc;
        }}

        .template-card {{
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            padding: 15px;
            text-align: center;
        }}

        .template-screenshot {{
            width: 100%;
            height: 150px;
            background: #f5f5f5;
            border-radius: 4px;
            margin-bottom: 10px;
            object-fit: cover;
        }}

        .template-name {{
            font-weight: 600;
            color: #1a1a2e;
            margin-bottom: 5px;
            font-size: 14px;
        }}

        .template-count {{
            font-size: 12px;
            color: #888;
            margin-bottom: 10px;
        }}

        .template-events {{
            font-size: 11px;
            background: #f0f0f0;
            padding: 8px;
            border-radius: 4px;
            text-align: left;
        }}

        .event-tag {{
            display: inline-block;
            background: #dde8f5;
            color: #0066cc;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
            margin: 2px 2px 2px 0;
        }}

        .redirect-chain {{
            background: #f9f9f9;
            padding: 12px;
            border-left: 3px solid #ddd;
            margin-bottom: 10px;
            border-radius: 3px;
            font-size: 12px;
            font-family: monospace;
        }}

        .redirect-chain.flagged {{
            border-left-color: #ff6b6b;
            background: #ffe5e5;
        }}

        .roadmap-phase {{
            margin-bottom: 25px;
        }}

        .roadmap-phase-title {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            padding: 12px 15px;
            border-radius: 4px 4px 0 0;
            font-weight: 600;
            font-size: 14px;
        }}

        .roadmap-item {{
            border: 1px solid #e0e0e0;
            border-top: none;
            padding: 15px;
            margin-bottom: 10px;
        }}

        .roadmap-item:last-child {{
            border-radius: 0 0 4px 4px;
        }}

        .roadmap-event {{
            font-weight: 600;
            color: #0066cc;
            margin-bottom: 5px;
            font-size: 14px;
        }}

        .roadmap-description {{
            font-size: 13px;
            color: #666;
            margin-bottom: 8px;
        }}

        .roadmap-implementation {{
            background: #f5f5f5;
            padding: 10px;
            border-radius: 4px;
            font-size: 12px;
            color: #555;
            font-style: italic;
        }}

        .methodology {{
            background: #e8f4f8;
            padding: 20px;
            border-left: 4px solid #0099cc;
            border-radius: 4px;
            font-size: 13px;
            line-height: 1.7;
        }}

        .methodology h4 {{
            margin-bottom: 10px;
            color: #0066cc;
        }}

        .methodology ul {{
            margin-left: 20px;
            margin-top: 10px;
        }}

        .methodology li {{
            margin-bottom: 6px;
        }}

        .confidence-indicator {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            background: {confidence_color};
            color: white;
        }}

        .alert-box {{
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 15px;
            border-left: 4px solid;
        }}

        .alert-success {{
            background: #d4edda;
            border-color: #28a745;
            color: #155724;
        }}

        .alert-warning {{
            background: #fff3cd;
            border-color: #ffc107;
            color: #856404;
        }}

        .alert-danger {{
            background: #f8d7da;
            border-color: #dc3545;
            color: #721c24;
        }}

        .footer {{
            background: #f5f5f5;
            padding: 20px;
            text-align: center;
            font-size: 12px;
            color: #999;
            margin-top: 40px;
            border-top: 1px solid #e0e0e0;
        }}

        .no-data {{
            color: #999;
            text-align: center;
            padding: 30px;
            font-style: italic;
        }}

        code {{
            background: #f5f5f5;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: monospace;
            font-size: 12px;
        }}

        @media print {{
            body {{
                background: white;
            }}
            .section {{
                page-break-inside: avoid;
                box-shadow: none;
                border: 1px solid #e0e0e0;
            }}
            .header {{
                page-break-after: avoid;
            }}
        }}

        @media (max-width: 768px) {{
            .header-content {{
                flex-direction: column;
                text-align: center;
            }}
            .header-meta {{
                text-align: center;
                margin-top: 10px;
            }}
            .grid-2, .grid-3 {{
                grid-template-columns: 1fr;
            }}
            .header h1 {{
                font-size: 22px;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <div>
                <h1>{escape_html(title)} - GA4 Audit Dashboard</h1>
                <div class="badge">Data Source: Live Playwright Crawl</div>
            </div>
            <div class="header-meta">
                <div>Audit Date: {audit_date}</div>
                <div>Pages Analyzed: {summary['total_pages']}</div>
            </div>
        </div>
    </div>

    <div class="container">
        <!-- EXECUTIVE SUMMARY -->
        <div class="section">
            <h2 class="section-title">Executive Summary</h2>

            <div class="grid-2">
                <div class="metric-card {"success" if summary["ga4_coverage"] >= 80 else "warning" if summary["ga4_coverage"] >= 50 else "danger"}">
                    <div class="metric-value">{summary["ga4_coverage"]:.1f}%</div>
                    <div class="metric-label">GA4 Coverage</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{summary["total_pages"]}</div>
                    <div class="metric-label">Pages Crawled</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{summary["unique_templates"]}</div>
                    <div class="metric-label">Unique Templates</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{summary["analytics_tools"]}</div>
                    <div class="metric-label">Tracking Tools</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{summary["avg_load_time_ms"]:.0f}ms</div>
                    <div class="metric-label">Avg Load Time</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{summary["total_redirects"]}</div>
                    <div class="metric-label">Total Redirects</div>
                </div>
            </div>

            <div style="margin-top: 20px;">
                <p><strong>Data Confidence Level:</strong> <span class="confidence-indicator">{confidence.upper()}</span></p>
                <p style="margin-top: 10px; font-size: 13px; color: #666;">Based on {summary["total_pages"]} analyzed pages. Higher sample sizes indicate more reliable findings.</p>
            </div>
        </div>

        <!-- KEY FINDINGS -->
        <div class="section">
            <h2 class="section-title">Key Findings</h2>
"""

        # GA4 Coverage alert
        if summary['ga4_coverage'] >= 80:
            html += f'<div class="alert-box alert-success">✓ Excellent GA4 coverage ({summary["ga4_coverage"]:.1f}%)</div>'
        elif summary['ga4_coverage'] >= 50:
            html += f'<div class="alert-box alert-warning">⚠ Moderate GA4 coverage ({summary["ga4_coverage"]:.1f}%)</div>'
        else:
            html += f'<div class="alert-box alert-danger">✗ Low GA4 coverage ({summary["ga4_coverage"]:.1f}%)</div>'

        if summary['total_redirects'] > 0:
            html += f'<div class="alert-box alert-warning">⚠ {summary["total_redirects"]} redirect{"s" if summary["total_redirects"] != 1 else ""} detected</div>'

        if summary['analytics_tools'] > 1:
            html += f'<div class="alert-box alert-warning">⚠ {summary["analytics_tools"]} tracking tools detected</div>'

        html += f"""
        </div>

        <!-- ANALYTICS TOOLS AUDIT -->
        <div class="section">
            <h2 class="section-title">Analytics Tools Audit</h2>
            <p style="margin-bottom: 20px; font-size: 14px; color: #666;">Summary of tracking tools detected via network interception.</p>
            {self._generate_analytics_tools_table(analytics_tools)}
        </div>

        <!-- GA4 EVENTS & DATALAYER -->
        <div class="section">
            <h2 class="section-title">GA4 Events & dataLayer Analysis</h2>
            <div style="margin-bottom: 30px;">
                {self._generate_ga4_events_section(ga4_events)}
            </div>
            {self._generate_datalayer_section(datalayer)}
        </div>

        <!-- URL TREE -->
        <div class="section">
            <h2 class="section-title">URL Structure & Coverage</h2>
            {self._generate_url_tree(url_tree)}
        </div>

        <!-- PAGE TEMPLATES -->
        <div class="section">
            <h2 class="section-title">Page Templates & Recommendations</h2>
            <p style="margin-bottom: 20px; font-size: 14px; color: #666;">Discovered page templates with recommended GA4 events.</p>
            {self._generate_template_cards(templates)}
        </div>
"""

        # Redirect chains (only if present)
        if redirect_chains:
            html += self._generate_redirect_chains(redirect_chains)

        html += f"""
        <!-- PERFORMANCE -->
        <div class="section">
            <h2 class="section-title">Performance Analysis</h2>
            {self._generate_performance_section(performance)}
        </div>

        <!-- ERRORS & ISSUES -->
        <div class="section">
            <h2 class="section-title">Errors & Issues</h2>
            {self._generate_errors_section(errors)}
        </div>

        <!-- GA4 IMPLEMENTATION ROADMAP -->
        <div class="section">
            <h2 class="section-title">GA4 Implementation Roadmap</h2>
            <p style="margin-bottom: 20px; font-size: 14px; color: #666;">Phased approach to implementing comprehensive GA4 tracking.</p>
            {self._generate_roadmap_section(roadmap)}
        </div>

        <!-- METHODOLOGY -->
        <div class="section">
            <h2 class="section-title">Data Collection Methodology</h2>
            <div class="methodology">
                <h4>How This Data Was Collected</h4>
                <ul>
                    <li><strong>Headless Chromium Rendering:</strong> Pages loaded in headless Chromium for full JavaScript execution</li>
                    <li><strong>Network Interception:</strong> All HTTP/HTTPS requests intercepted and logged, including analytics beacons</li>
                    <li><strong>Event Payload Analysis:</strong> GA4 requests parsed to extract event names and parameters directly from network payloads</li>
                    <li><strong>Console & Error Capture:</strong> JavaScript console messages and page errors captured</li>
                    <li><strong>Performance Metrics:</strong> Page load times and resource transfer sizes measured</li>
                    <li><strong>DOM Analysis:</strong> Rendered DOM analyzed for forms, CTAs, and link patterns</li>
                </ul>

                <h4 style="margin-top: 20px;">Important Notes</h4>
                <ul>
                    <li><strong>Real Data, Not Estimates:</strong> All numbers represent actual observed requests</li>
                    <li><strong>One-Time Snapshot:</strong> This audit represents a single point-in-time crawl</li>
                    <li><strong>Sample Limitations:</strong> Analyzed {summary["total_pages"]} pages. Findings should be extrapolated with sample size in mind</li>
                </ul>
            </div>
        </div>

        <!-- FOOTER -->
        <div class="footer">
            <p>GA4 Analytics Audit Dashboard | Generated: {audit_date} | Data Source: Playwright Web Crawler</p>
            <p>Self-contained HTML file with no external dependencies. Can be saved, printed, or emailed.</p>
        </div>
    </div>

</body>
</html>
"""

        # Write to file
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            return output_file
        except Exception as e:
            raise Exception(f"Error writing dashboard to {output_file}: {e}")


# ============================================================================
# CLI
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate GA4 audit dashboard from crawler output',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    python generate_dashboard.py --input ./crawl_output
    python generate_dashboard.py --input ./crawl_output --output ./my_audit.html --title "My Site"
        '''
    )

    parser.add_argument('--input', required=True,
                        help='Directory containing crawl output JSON files')
    parser.add_argument('--output', default='ga4_audit_report.html',
                        help='Output HTML file (default: ga4_audit_report.html)')
    parser.add_argument('--title', default=None,
                        help='Dashboard title (auto-detected if not provided)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')

    args = parser.parse_args()

    # Setup logging
    logger = setup_logging(debug=args.debug)

    # Validate input directory
    if not os.path.isdir(args.input):
        logger.error(f"Input directory not found: {args.input}")
        sys.exit(1)

    # Warn about missing files but don't fail
    expected_files = ['crawl_data.json', 'analytics_audit.json', 'redirect_report.json',
                      'template_map.json', 'performance_report.json', 'errors.json']
    for filename in expected_files:
        filepath = os.path.join(args.input, filename)
        if not os.path.exists(filepath):
            logger.warning(f"Expected file not found: {filename} (will show 'No data' in dashboard)")

    try:
        # Process data
        logger.info(f"Processing crawl data from {args.input}")
        processor = DashboardDataProcessor(args.input)

        # Generate dashboard
        logger.info("Generating HTML dashboard...")
        generator = DashboardHTMLGenerator()
        output_path = generator.generate(processor, args.output, args.title)

        # Print summary
        file_size_kb = os.path.getsize(output_path) / 1024
        print("\n" + "="*70)
        print("DASHBOARD GENERATION COMPLETE")
        print("="*70)
        print(f"Output file: {output_path}")
        print(f"File size: {file_size_kb:.1f} KB")
        print(f"\nOpen in browser: {os.path.abspath(output_path)}")
        print("\nThis is a self-contained HTML file:")
        print("  ✓ No external dependencies (all CSS/JS inline)")
        print("  ✓ Can be saved, emailed, or printed")
        print("  ✓ Works offline")
        print("="*70 + "\n")

    except Exception as e:
        logger.error(f"Dashboard generation failed: {e}", exc_info=args.debug)
        sys.exit(1)


if __name__ == '__main__':
    main()
