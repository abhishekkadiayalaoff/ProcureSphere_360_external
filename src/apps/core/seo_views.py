"""
SEO views — sitemap.xml and robots.txt for ProcureSphere 360.

These views serve search-engine-facing files dynamically so that the
SITE_URL setting is always respected without maintaining static files.
"""
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET


@require_GET
@cache_page(60 * 60)  # Cache for 1 hour
def sitemap_xml(request):
    """
    Dynamic XML sitemap containing only public, indexable landing pages.
    Excludes all authenticated dashboards, API routes, and admin pages.
    """
    site_url = getattr(settings, "SITE_URL", "https://procuresphere.com").rstrip("/")

    # Only public landing pages — no authenticated/private routes
    public_urls = [
        {"loc": "/", "changefreq": "weekly", "priority": "1.0"},
        {"loc": "/about/", "changefreq": "monthly", "priority": "0.8"},
        {"loc": "/solutions/", "changefreq": "monthly", "priority": "0.9"},
        {"loc": "/benefits/", "changefreq": "monthly", "priority": "0.7"},
        {"loc": "/process/", "changefreq": "monthly", "priority": "0.7"},
        {"loc": "/faq/", "changefreq": "monthly", "priority": "0.6"},
    ]

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in public_urls:
        xml_lines.append("  <url>")
        xml_lines.append(f'    <loc>{site_url}{url["loc"]}</loc>')
        xml_lines.append(f'    <changefreq>{url["changefreq"]}</changefreq>')
        xml_lines.append(f'    <priority>{url["priority"]}</priority>')
        xml_lines.append("  </url>")
    xml_lines.append("</urlset>")

    return HttpResponse("\n".join(xml_lines), content_type="application/xml")


@require_GET
@cache_page(60 * 60 * 24)  # Cache for 24 hours
def robots_txt(request):
    """
    Robots.txt — allows crawling of public pages, blocks all private routes.
    """
    site_url = getattr(settings, "SITE_URL", "https://procuresphere.com").rstrip("/")

    lines = [
        "User-agent: *",
        "",
        "# Allow public landing pages",
        "Allow: /",
        "Allow: /about/",
        "Allow: /solutions/",
        "Allow: /benefits/",
        "Allow: /process/",
        "Allow: /faq/",
        "",
        "# Block authenticated dashboards and private routes",
        "Disallow: /admin/",
        "Disallow: /superadmin/",
        "Disallow: /manager/",
        "Disallow: /vendor/",
        "Disallow: /login/",
        "Disallow: /logout/",
        "Disallow: /accounts/",
        "Disallow: /api/",
        "Disallow: /requisitions/",
        "Disallow: /approvals/",
        "Disallow: /vendors/",
        "Disallow: /sourcing-events/",
        "Disallow: /purchase-orders/",
        "Disallow: /invoices/",
        "Disallow: /contracts/",
        "Disallow: /receipts/",
        "Disallow: /orders/",
        "Disallow: /reports/",
        "Disallow: /budgets/",
        "Disallow: /audit/",
        "Disallow: /scorecards/",
        "Disallow: /notifications/",
        "Disallow: /health/",
        "Disallow: /htmx/",
        "",
        f"Sitemap: {site_url}/sitemap.xml",
    ]

    return HttpResponse("\n".join(lines), content_type="text/plain")

