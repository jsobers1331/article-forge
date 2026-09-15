"""Tests for the live-page publish gate.

Every test runs against a fake HTTP layer: `check_publish._http_request` is
replaced by a route table that records requests, so nothing here touches the
network. One fixture per failure mode, plus a clean article page and a clean
`page`-kind run that together pin the PASS contract.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_publish  # noqa: E402
from check_publish import analyze_page, run_sitemap, summarize  # noqa: E402

PAGE_URL = "https://example.com/blog/what-is-a-widget"
HUB_URL = "https://example.com/blog"
HOMEPAGE_URL = "https://example.com/"
SITEMAP_URL = "https://example.com/sitemap.xml"
ARTICLE_A = "https://example.com/blog/article-a"
ARTICLE_B = "https://example.com/blog/article-b"
CONFIG = {"domain": "example.com", "hub_path": "/blog"}
ORG_ID = "https://example.com/#org"

PAGE_TITLE = "What Is a Widget: A Practical Guide for Small Teams"
PAGE_DESCRIPTION = (
    "A practical guide to widgets for small teams, with worked examples "
    "and a reusable checklist."
)
HOMEPAGE_DESCRIPTION = (
    "Example builds widgets for small teams that plan repeatable work every day."
)
HOMEPAGE_TWITTER_TITLE = "Example - Widgets for small teams"

DEFAULT_IMAGE = {
    "src": "https://example.com/images/hero.jpg",
    "alt": "A widget on a desk",
    "width": "1200",
    "height": "630",
}

CHECK_NAMES = [
    "HTTP status",
    "Redirect chain",
    "Title",
    "Meta description",
    "Meta description",
    "Canonical",
    "Robots directives",
    "Open Graph / Twitter",
    "Open Graph / Twitter",
    "Open Graph / Twitter",
    "Open Graph / Twitter",
    "JSON-LD",
    "JSON-LD",
    "JSON-LD",
    "JSON-LD",
    "JSON-LD",
    "Internal links",
    "Internal links",
    "Internal links",
    "Images",
    "Images",
    "Visible dates",
    "H1",
    "Word count",
    "Banned words",
]


# --- fake HTTP layer ---------------------------------------------------------


class FakeSite:
    """Stands in for `check_publish._http_request` and serves a route table."""

    def __init__(self, monkeypatch):
        self.routes = {}
        self.requests = []
        check_publish._HOMEPAGE_CACHE.clear()
        check_publish._LINK_CACHE.clear()
        monkeypatch.setattr(check_publish, "_http_request", self)

    def add(
        self,
        url,
        status=200,
        body=b"",
        headers=None,
        final_url=None,
        redirect_chain=(),
        error="",
    ):
        self.routes[url] = check_publish.Response(
            status=status,
            final_url=final_url or url,
            headers=dict(headers or {}),
            body=body,
            error=error,
            redirect_chain=list(redirect_chain),
        )

    def add_html(self, url, html, **kwargs):
        headers = {"content-type": "text/html; charset=utf-8"}
        headers.update(kwargs.pop("headers", {}))
        self.add(url, body=html.encode("utf-8"), headers=headers, **kwargs)

    def __call__(self, url, method="GET", timeout=0, delay=0.0):
        self.requests.append((method, url))
        if url in self.routes:
            return self.routes[url]
        return check_publish.Response(status=404, final_url=url, error="")


@pytest.fixture
def site(monkeypatch):
    return FakeSite(monkeypatch)


def results_named(results, name):
    return [result for result in results if result.name == name]


def details_named(results, name):
    return [result.detail for result in results_named(results, name)]


def gate(site, html, url=PAGE_URL, homepage=None, config=None, **options):
    site.add_html(url, html)
    if homepage is None:
        homepage = homepage_html()
    if homepage:
        site.add_html(HOMEPAGE_URL, homepage)
    options.setdefault("kind", "article")
    options.setdefault("article_type", "standard")
    options.setdefault("check_links", False)
    options.setdefault("delay", 0)
    return analyze_page(url, config or CONFIG, **options)


# --- page builder ------------------------------------------------------------


def filler_text(words):
    block = (
        "Widgets help small teams plan repeatable work without extra tools "
        "or meetings daily"
    )
    return " ".join([block] * max(1, -(-words // 13)))


def homepage_html():
    return (
        '<!doctype html><html lang="en"><head>'
        f"<title>{HOMEPAGE_TWITTER_TITLE}</title>"
        f'<meta name="description" content="{HOMEPAGE_DESCRIPTION}">'
        f'<meta property="og:title" content="{HOMEPAGE_TWITTER_TITLE}">'
        f'<meta name="twitter:title" content="{HOMEPAGE_TWITTER_TITLE}">'
        "</head><body><main><h1>Example</h1></main></body></html>"
    )


def organization_node(**overrides):
    node = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": ORG_ID,
        "name": "Example",
        "url": "https://example.com/",
    }
    node.update(overrides)
    return node


def website_node(**overrides):
    node = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": "https://example.com/#website",
        "publisher": {"@id": ORG_ID},
    }
    node.update(overrides)
    return node


def blog_posting(**overrides):
    node = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "@id": PAGE_URL + "#article",
        "headline": "What Is a Widget",
        "author": {"@id": ORG_ID},
        "publisher": {"@id": ORG_ID},
        "image": "https://example.com/images/hero.jpg",
        "datePublished": "2026-09-01T09:00:00+00:00",
        "dateModified": "2026-09-10T12:00:00+00:00",
    }
    node.update(overrides)
    return node


def breadcrumb_node(**overrides):
    node = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "@id": PAGE_URL + "#breadcrumbs",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Blog", "item": HUB_URL},
            {"@type": "ListItem", "position": 2, "name": "What Is a Widget"},
        ],
    }
    node.update(overrides)
    return node


def clean_graph():
    return [organization_node(), website_node(), blog_posting(), breadcrumb_node()]


def _tags(values, template):
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    return [template(value) for value in values]


def build_page(**overrides):
    options = {
        "title": PAGE_TITLE,
        "description": PAGE_DESCRIPTION,
        "canonical": PAGE_URL,
        "robots": "index, follow",
        "og_image": "https://example.com/images/hero.jpg",
        "og_type": "article",
        "twitter_image": "https://example.com/images/hero.jpg",
        "twitter_title": PAGE_TITLE,
        "twitter_card": "summary_large_image",
        "h1s": ["What Is a Widget"],
        "images": [DEFAULT_IMAGE],
        "links": ["/blog", "/blog/what-is-a-widget-basics"],
        "dates": "Published September 1, 2026",
        "body": filler_text(1200),
        "main": True,
        "outside_main": "",
        "extra_head": "",
    }
    options.update(overrides)
    options.setdefault("jsonld", clean_graph())

    def image_tag(image):
        attrs = "".join(f' {key}="{value}"' for key, value in image.items() if value)
        return f"<img{attrs}>"

    head = []
    head += _tags(options["title"], lambda value: f"<title>{value}</title>")
    head += _tags(
        options["description"],
        lambda value: f'<meta name="description" content="{value}">',
    )
    head += _tags(
        options["robots"], lambda value: f'<meta name="robots" content="{value}">'
    )
    head += _tags(
        options["canonical"],
        lambda value: f'<link rel="canonical" href="{value}">',
    )
    head += _tags(
        options["og_image"],
        lambda value: f'<meta property="og:image" content="{value}">',
    )
    head += _tags(
        options["og_type"], lambda value: f'<meta property="og:type" content="{value}">'
    )
    head += _tags(
        options["twitter_image"],
        lambda value: f'<meta name="twitter:image" content="{value}">',
    )
    head += _tags(
        options["twitter_title"],
        lambda value: f'<meta name="twitter:title" content="{value}">',
    )
    head += _tags(
        options["twitter_card"],
        lambda value: f'<meta name="twitter:card" content="{value}">',
    )
    for block in options["jsonld"] or []:
        raw = block if isinstance(block, str) else json.dumps(block)
        head.append(f'<script type="application/ld+json">{raw}</script>')
    head.append(options["extra_head"])

    body = []
    if options["main"]:
        body.append("<main>")
    body += [f"<h1>{heading}</h1>" for heading in options["h1s"]]
    if options["dates"]:
        body.append(f"<p>{options['dates']}</p>")
    body += [f'<a href="{href}">read more</a>' for href in options["links"]]
    body += [image_tag(image) for image in options["images"]]
    body.append(f"<p>{options['body']}</p>")
    if options["main"]:
        body.append("</main>")
    body.append(options["outside_main"])

    return (
        '<!doctype html><html lang="en"><head>'
        + "".join(head)
        + "</head><body>"
        + "".join(body)
        + "</body></html>"
    )


def sitemap_args(**overrides):
    defaults = {
        "config": "site-config.example.json",
        "delay": 0,
        "limit": 0,
        "kind": "article",
        "type": "standard",
        "query": "",
        "no_link_check": True,
        "verbose": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def urlset(*urls):
    entries = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>"
    )


def sitemap_index(*urls):
    entries = "".join(f"<sitemap><loc>{url}</loc></sitemap>" for url in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</sitemapindex>"
    )


# --- clean runs --------------------------------------------------------------


def test_clean_article_page_passes_every_check(site):
    results = gate(site, build_page())

    assert [result.name for result in results] == CHECK_NAMES
    assert {result.status for result in results} == {"PASS"}
    assert len(results) == 25
    assert any(
        "Article.author -> https://example.com/#org (resolves on this page)" in detail
        for detail in details_named(results, "JSON-LD")
    )
    assert "description differs from the homepage's" in details_named(
        results, "Meta description"
    )


def test_clean_page_kind_run_passes_and_skips_article_only_checks(site):
    results = gate(site, build_page(og_type="website"), kind="page")

    assert {result.status for result in results} == {"PASS"}
    assert "word count skipped for non-article pages" in details_named(
        results, "Word count"
    )
    assert "banned words skipped for non-article pages" in details_named(
        results, "Banned words"
    )
    assert any(
        detail.startswith("site-level node present:")
        for detail in details_named(results, "JSON-LD")
    )
    assert not any("Article." in detail for detail in details_named(results, "JSON-LD"))


def test_the_parser_scopes_content_to_the_main_region():
    html = build_page(
        links=["/blog"],
        outside_main='<footer><a href="/blog/from-footer">footer copy</a></footer>',
    )
    parser = check_publish.parse_page(html)

    assert parser.has_main_region
    assert parser.main_hrefs == ["/blog"]
    assert "/blog/from-footer" in parser.all_hrefs
    assert parser.hrefs == ["/blog"]
    assert "Published September 1, 2026" in parser.text
    assert "footer copy" not in parser.text

    no_region = check_publish.parse_page(build_page(main=False))
    assert no_region.has_main_region is False
    assert "/blog" in no_region.hrefs


# --- HTTP status -------------------------------------------------------------


def test_non_200_page_reports_only_the_head_and_stops(site):
    site.add_html(PAGE_URL, "<html><head><title>Gone</title></head></html>", status=410)
    results = analyze_page(PAGE_URL, CONFIG, check_links=False, delay=0)

    assert [result.name for result in results] == [
        "HTTP status",
        "Redirect chain",
        "Remaining checks",
    ]
    assert results[0].status == "FAIL"
    assert "HTTP 410 for https://example.com/blog/what-is-a-widget" in results[0].detail
    assert results[2].status == "FAIL"
    assert "skipped" in results[2].detail


def test_network_error_is_reported_as_could_not_fetch(site):
    site.add(PAGE_URL, status=0, error="URLError: name or service not known")
    results = analyze_page(PAGE_URL, CONFIG, check_links=False, delay=0)

    assert results[0].status == "FAIL"
    assert "could not fetch the page: URLError" in results[0].detail
    assert len(results) == 3


# --- redirects ---------------------------------------------------------------


def test_redirect_landing_on_another_path_is_hard(site):
    site.add_html(
        PAGE_URL,
        build_page(),
        final_url="https://example.com/blog/moved",
        redirect_chain=[{"status": 301, "url": "https://example.com/blog/moved"}],
    )
    site.add_html(HOMEPAGE_URL, homepage_html())
    results = analyze_page(PAGE_URL, CONFIG, check_links=False, delay=0)

    redirect = results_named(results, "Redirect chain")[0]
    assert redirect.status == "FAIL"
    assert "different path" in redirect.detail


def test_host_level_redirect_is_a_warning(site):
    final_url = "https://www.example.com/blog/what-is-a-widget"
    site.add_html(
        PAGE_URL,
        build_page(),
        final_url=final_url,
        redirect_chain=[{"status": 301, "url": final_url}],
    )
    site.add_html(HOMEPAGE_URL, homepage_html())
    results = analyze_page(PAGE_URL, CONFIG, check_links=False, delay=0)

    redirect = results_named(results, "Redirect chain")[0]
    assert redirect.status == "WARN"
    assert "host-level redirect" in redirect.detail


def test_redirect_that_stays_on_the_same_path_passes(site):
    site.add_html(
        PAGE_URL,
        build_page(),
        final_url=PAGE_URL,
        redirect_chain=[{"status": 307, "url": PAGE_URL}],
    )
    site.add_html(HOMEPAGE_URL, homepage_html())
    results = analyze_page(PAGE_URL, CONFIG, check_links=False, delay=0)

    redirect = results_named(results, "Redirect chain")[0]
    assert redirect.status == "PASS"
    assert "stays on this path" in redirect.detail


# --- title -------------------------------------------------------------------


def test_missing_title_is_hard(site):
    title = results_named(gate(site, build_page(title=None)), "Title")[0]
    assert title.status == "FAIL"
    assert "no <title> tag" in title.detail


def test_empty_title_is_hard(site):
    title = results_named(gate(site, build_page(title="")), "Title")[0]
    assert title.status == "FAIL"
    assert "empty <title>" in title.detail


def test_multiple_titles_are_hard(site):
    title = results_named(gate(site, build_page(title=[PAGE_TITLE, "Other"])), "Title")[
        0
    ]
    assert title.status == "FAIL"
    assert "2 <title> tags" in title.detail


def test_title_outside_the_length_guidance_warns(site):
    title = results_named(gate(site, build_page(title="Short title")), "Title")[0]
    assert title.status == "WARN"
    assert "outside the 15-70 guidance" in title.detail


# --- meta description --------------------------------------------------------


def test_missing_meta_description_is_hard(site):
    description = results_named(
        gate(site, build_page(description=None)), "Meta description"
    )
    assert description[0].status == "FAIL"
    assert description[0].detail == "no meta description"


def test_description_identical_to_the_homepage_is_hard(site):
    details = details_named(
        gate(site, build_page(description=HOMEPAGE_DESCRIPTION)), "Meta description"
    )
    assert any("identical to the homepage's" in detail for detail in details)


def test_description_length_outside_the_guidance_warns(site):
    description = results_named(
        gate(site, build_page(description="Too short.")), "Meta description"
    )
    assert description[0].status == "WARN"
    assert "outside the 50-160 guidance" in description[0].detail


def test_a_homepage_run_does_not_flag_its_own_description(site):
    site.add_html(HOMEPAGE_URL, homepage_html())
    results = analyze_page(
        HOMEPAGE_URL, CONFIG, kind="article", check_links=False, delay=0
    )

    assert not any(
        "identical to the homepage's" in detail
        for detail in details_named(results, "Meta description")
    )
    assert not any(
        "identical to the homepage's" in detail
        for detail in details_named(results, "Open Graph / Twitter")
    )


# --- canonical ---------------------------------------------------------------


def test_missing_canonical_is_hard(site):
    canonical = results_named(gate(site, build_page(canonical=None)), "Canonical")[0]
    assert canonical.status == "FAIL"
    assert "no <link rel=canonical>" in canonical.detail


def test_canonical_pointing_at_another_url_is_hard(site):
    canonical = results_named(
        gate(site, build_page(canonical="https://example.com/blog/other")), "Canonical"
    )[0]
    assert canonical.status == "FAIL"
    assert "canonical points at another URL" in canonical.detail


def test_relative_canonical_warns_but_still_resolves(site):
    canonical = results_named(
        gate(site, build_page(canonical="/blog/what-is-a-widget")), "Canonical"
    )
    statuses = {result.status for result in canonical}
    assert statuses == {"WARN", "PASS"}
    assert "canonical is relative" in canonical[0].detail
    assert "self-referencing canonical" in canonical[1].detail


def test_multiple_canonical_tags_warn(site):
    canonical = results_named(
        gate(site, build_page(canonical=[PAGE_URL, PAGE_URL + "?utm=1"])), "Canonical"
    )
    assert any("2 canonical tags found" in result.detail for result in canonical)


# --- robots ------------------------------------------------------------------


def test_meta_robots_noindex_is_hard(site):
    robots = results_named(
        gate(site, build_page(robots="noindex, follow")), "Robots directives"
    )[0]
    assert robots.status == "FAIL"
    assert "forbids indexing" in robots.detail


def test_x_robots_tag_noindex_is_hard(site):
    site.add_html(
        PAGE_URL,
        build_page(),
        headers={"x-robots-tag": "noindex"},
    )
    site.add_html(HOMEPAGE_URL, homepage_html())
    results = analyze_page(PAGE_URL, CONFIG, check_links=False, delay=0)

    robots = results_named(results, "Robots directives")[0]
    assert robots.status == "FAIL"
    assert "X-Robots-Tag forbids indexing" in robots.detail


def test_missing_robots_directive_warns(site):
    robots = results_named(gate(site, build_page(robots=None)), "Robots directives")[0]
    assert robots.status == "WARN"
    assert "no meta robots directive" in robots.detail


def test_multiple_robots_tags_warn(site):
    robots = results_named(
        gate(site, build_page(robots=["index, follow", "max-snippet:-1"])),
        "Robots directives",
    )
    assert any("multiple meta robots tags" in result.detail for result in robots)


# --- social cards ------------------------------------------------------------


def test_missing_og_image_is_hard(site):
    social = results_named(
        gate(site, build_page(og_image=None)), "Open Graph / Twitter"
    )[0]
    assert social.status == "FAIL"
    assert "og:image missing" in social.detail


def test_relative_og_image_is_hard(site):
    social = results_named(
        gate(site, build_page(og_image="/images/hero.jpg")), "Open Graph / Twitter"
    )[0]
    assert social.status == "FAIL"
    assert "not an absolute URL" in social.detail


def test_missing_twitter_image_warns_and_names_the_card(site):
    social = results_named(
        gate(site, build_page(twitter_image=None)), "Open Graph / Twitter"
    )
    assert any(
        "twitter:image missing while twitter:card is 'summary_large_image'"
        in result.detail
        for result in social
    )
    assert {result.status for result in social} >= {"WARN"}


def test_twitter_title_matching_the_homepage_is_hard(site):
    social = results_named(
        gate(site, build_page(twitter_title=HOMEPAGE_TWITTER_TITLE)),
        "Open Graph / Twitter",
    )
    assert any(
        "twitter:title is identical to the homepage's" in result.detail
        and result.status == "FAIL"
        for result in social
    )


def test_og_type_website_on_an_article_warns(site):
    social = results_named(
        gate(site, build_page(og_type="website")), "Open Graph / Twitter"
    )
    assert any(
        "expected 'article'" in result.detail and result.status == "WARN"
        for result in social
    )


def test_og_type_article_on_a_page_warns(site):
    results = gate(site, build_page(og_type="article"), kind="page")
    social = results_named(results, "Open Graph / Twitter")
    assert any(
        "on a non-article page" in result.detail and result.status == "WARN"
        for result in social
    )


def test_missing_og_type_warns(site):
    social = results_named(gate(site, build_page(og_type=None)), "Open Graph / Twitter")
    assert any(result.detail == "og:type missing" for result in social)


# --- JSON-LD -----------------------------------------------------------------


def test_no_jsonld_block_is_hard(site):
    jsonld = results_named(gate(site, build_page(jsonld=None)), "JSON-LD")[0]
    assert jsonld.status == "FAIL"
    assert "no application/ld+json block" in jsonld.detail


def test_unparseable_jsonld_is_hard(site):
    jsonld = results_named(gate(site, build_page(jsonld=["{not json"])), "JSON-LD")[0]
    assert jsonld.status == "FAIL"
    assert "JSON-LD does not parse" in jsonld.detail


def test_empty_jsonld_block_is_hard(site):
    jsonld = results_named(gate(site, build_page(jsonld=[" "])), "JSON-LD")[0]
    assert jsonld.status == "FAIL"
    assert "empty <script type=application/ld+json>" in jsonld.detail


def test_a_reference_only_id_does_not_declare_its_own_node(site):
    # Regression, found live on homeweal.com (2026-09-15): nested
    # {"@id": ...} refs used to satisfy themselves, so a genuinely dangling
    # author/publisher read as a PASS. A dict whose only key is @id is a
    # reference; only a node that declares the id counts.
    results = gate(site, build_page(jsonld=[blog_posting(), breadcrumb_node()]))
    details = details_named(results, "JSON-LD")

    assert any(
        "Article.author references @id 'https://example.com/#org'" in detail
        and "dangling reference" in detail
        for detail in details
    )
    assert any("Article.publisher references @id" in detail for detail in details)


def test_a_dangling_reference_written_as_a_string_is_hard(site):
    graph = [
        organization_node(),
        website_node(),
        blog_posting(author="https://example.com/#missing"),
        breadcrumb_node(),
    ]
    details = details_named(gate(site, build_page(jsonld=graph)), "JSON-LD")

    assert any(
        "Article.author references @id 'https://example.com/#missing'" in detail
        for detail in details
    )


def test_a_dangling_reference_on_a_non_article_node_is_hard(site):
    graph = [
        organization_node(),
        website_node(publisher={"@id": "https://example.com/#missing"}),
        blog_posting(),
        breadcrumb_node(),
    ]
    details = details_named(gate(site, build_page(jsonld=graph)), "JSON-LD")

    assert any(
        "publisher references missing @id 'https://example.com/#missing'" in detail
        for detail in details
    )


def test_missing_article_node_warns(site):
    details = details_named(
        gate(site, build_page(jsonld=[organization_node(), website_node()])), "JSON-LD"
    )
    assert any("no Article/BlogPosting node" in detail for detail in details)


def test_missing_breadcrumb_warns(site):
    graph = [organization_node(), website_node(), blog_posting()]
    details = details_named(gate(site, build_page(jsonld=graph)), "JSON-LD")
    assert any("no BreadcrumbList node" in detail for detail in details)


def test_missing_article_image_warns(site):
    graph = clean_graph()
    graph[2] = blog_posting(image=None)
    details = details_named(gate(site, build_page(jsonld=graph)), "JSON-LD")
    assert any(detail == "Article.image missing" for detail in details)


def test_non_iso_date_warns(site):
    graph = clean_graph()
    graph[2] = blog_posting(datePublished="September 1, 2026")
    details = details_named(gate(site, build_page(jsonld=graph)), "JSON-LD")
    assert any("datePublished is not ISO-8601" in detail for detail in details)


def test_identical_published_and_modified_dates_warn(site):
    graph = clean_graph()
    graph[2] = blog_posting(dateModified="2026-09-01T09:00:00+00:00")
    details = details_named(gate(site, build_page(jsonld=graph)), "JSON-LD")
    assert any("dateModified == datePublished" in detail for detail in details)


# --- internal links ----------------------------------------------------------


def test_broken_internal_link_is_hard(site):
    site.add("https://example.com/blog", status=200)
    results = gate(site, build_page(), check_links=True)

    links = results_named(results, "Internal links")
    failures = [result for result in links if result.status == "FAIL"]
    assert len(failures) == 1
    assert "1 internal link(s) do not resolve" in failures[0].detail
    assert "https://example.com/blog/what-is-a-widget-basics -> HTTP 404" in (
        failures[0].detail
    )


def test_all_internal_links_resolving_passes(site):
    site.add("https://example.com/blog", status=200)
    site.add("https://example.com/blog/what-is-a-widget-basics", status=200)
    results = gate(site, build_page(), check_links=True)

    links = results_named(results, "Internal links")
    assert {result.status for result in links} == {"PASS"}
    assert any(
        "all 2 checked internal link(s) return 200" in result.detail for result in links
    )


def test_unverifiable_internal_link_warns(site):
    site.add("https://example.com/blog", status=200)
    site.add(
        "https://example.com/blog/what-is-a-widget-basics",
        status=0,
        error="URLError: timed out",
    )
    links = results_named(gate(site, build_page(), check_links=True), "Internal links")

    assert any(
        "could not verify 1 link(s)" in result.detail and result.status == "WARN"
        for result in links
    )


def test_thin_internal_linking_warns(site):
    links = results_named(gate(site, build_page(links=["/blog"])), "Internal links")
    assert any("only 1 in-body internal link(s)" in result.detail for result in links)


def test_missing_hub_link_warns(site):
    links = results_named(
        gate(site, build_page(links=["/blog/related-a", "/blog/related-b"])),
        "Internal links",
    )
    assert any(
        "no in-body link up to the hub (/blog)" in result.detail for result in links
    )


def test_external_link_in_the_body_warns(site):
    links = results_named(
        gate(site, build_page(links=["/blog", "https://competitor.example/post"])),
        "Internal links",
    )
    assert any(
        "external/competitor link(s) in the body" in result.detail for result in links
    )


def test_link_checks_can_be_skipped(site):
    links = results_named(gate(site, build_page(), check_links=False), "Internal links")
    assert any(
        result.detail == "link checks skipped (--no-link-check)" for result in links
    )


# --- images ------------------------------------------------------------------


def test_page_without_images_warns(site):
    images = results_named(gate(site, build_page(images=[])), "Images")
    assert images[0].status == "WARN"
    assert "no <img> in the article content" in images[0].detail


def test_image_without_alt_text_warns(site):
    page = build_page(
        images=[
            {
                "src": "https://example.com/images/hero.jpg",
                "width": "10",
                "height": "10",
            }
        ]
    )
    images = results_named(gate(site, page), "Images")
    assert any("1 of 1 image(s) have no alt text" in result.detail for result in images)


def test_hero_without_dimensions_warns(site):
    page = build_page(
        images=[{"src": "https://example.com/images/hero.jpg", "alt": "A widget"}]
    )
    images = results_named(gate(site, page), "Images")
    assert any(
        "hero image has no width/height or aspect-ratio" in result.detail
        for result in images
    )


def test_hero_with_an_aspect_ratio_passes(site):
    page = build_page(
        images=[
            {
                "src": "https://example.com/images/hero.jpg",
                "alt": "A widget",
                "style": "aspect-ratio: 16 / 9",
            }
        ]
    )
    images = results_named(gate(site, page), "Images")
    assert all(result.status == "PASS" for result in images)


# --- visible dates -----------------------------------------------------------


def test_missing_visible_date_warns(site):
    dates = results_named(gate(site, build_page(dates="")), "Visible dates")[0]
    assert dates.status == "WARN"
    assert "no visible publish or update date" in dates.detail


def test_date_only_outside_the_content_region_warns(site):
    page = build_page(dates="", outside_main="<p>Updated September 1, 2026</p>")
    dates = results_named(gate(site, page), "Visible dates")[0]
    assert dates.status == "WARN"
    assert "not in the article content" in dates.detail


# --- H1 ----------------------------------------------------------------------


def test_missing_h1_is_hard(site):
    h1 = results_named(gate(site, build_page(h1s=[])), "H1")[0]
    assert h1.status == "FAIL"
    assert "no <h1> in the served HTML" in h1.detail


def test_multiple_h1s_are_hard(site):
    h1 = results_named(gate(site, build_page(h1s=["One", "Two"])), "H1")[0]
    assert h1.status == "FAIL"
    assert "2 <h1> tags" in h1.detail


def test_page_kind_without_an_h1_only_warns(site):
    results = gate(site, build_page(h1s=[], og_type="website"), kind="page")
    h1 = results_named(results, "H1")[0]
    assert h1.status == "WARN"
    assert h1.detail == "no <h1>"


def test_h1_overlapping_the_target_query_passes(site):
    results = gate(site, build_page(), target_query="what is a widget")
    h1 = results_named(results, "H1")
    assert any("matches the target query closely" in result.detail for result in h1)


def test_h1_missing_the_target_query_warns(site):
    results = gate(site, build_page(), target_query="debt snowball avalanche")
    h1 = results_named(results, "H1")
    assert any(
        "overlaps only" in result.detail and result.status == "WARN" for result in h1
    )


# --- word count --------------------------------------------------------------


def test_short_article_warns_below_the_band(site):
    word_count = results_named(
        gate(site, build_page(body=filler_text(200))), "Word count"
    )[0]
    assert word_count.status == "WARN"
    assert "below the 1000-2000 band for 'standard'" in word_count.detail


def test_long_article_warns_above_the_band(site):
    word_count = results_named(
        gate(site, build_page(body=filler_text(2400))), "Word count"
    )[0]
    assert word_count.status == "WARN"
    assert "above the 1000-2000 band" in word_count.detail


def test_supporting_articles_use_a_narrower_band(site):
    word_count = results_named(
        gate(site, build_page(body=filler_text(1500)), article_type="supporting"),
        "Word count",
    )[0]
    assert word_count.status == "WARN"
    assert "above the 700-1400 band for 'supporting'" in word_count.detail


# --- banned words ------------------------------------------------------------


def test_banned_word_in_the_copy_warns(site):
    page = build_page(body=filler_text(1200) + " We delve into widgets.")
    banned = results_named(gate(site, page), "Banned words")[0]
    assert banned.status == "WARN"
    assert "delve" in banned.detail


def test_config_extra_ban_words_are_honoured(site):
    page = build_page(body=filler_text(1200) + " Our gizmo is best.")
    config = {
        "domain": "example.com",
        "hub_path": "/blog",
        "voice": {"extra_ban_words": ["gizmo"]},
    }
    banned = results_named(gate(site, page, config=config), "Banned words")[0]
    assert banned.status == "WARN"
    assert "gizmo" in banned.detail


def test_ban_words_are_skipped_for_non_article_pages(site):
    results = gate(site, build_page(og_type="website"), kind="page")
    banned = results_named(results, "Banned words")[0]
    assert banned.status == "PASS"
    assert banned.detail == "banned words skipped for non-article pages"


# --- summarize ---------------------------------------------------------------


def test_summarize_splits_results_by_status(site):
    summary = summarize(gate(site, build_page(title=None)))

    assert [item["name"] for item in summary["hard"]] == ["Title"]
    assert summary["hard"][0]["status"] == "FAIL"
    assert summary["warn"] == []
    assert summary["pass"] == 24


# --- sitemap mode ------------------------------------------------------------


def test_sitemap_mode_filters_by_prefix_and_gates_every_article(site):
    site.add_html(ARTICLE_A, build_page(canonical=ARTICLE_A))
    site.add_html(ARTICLE_B, build_page(canonical=None))
    site.add_html(HOMEPAGE_URL, homepage_html())
    site.add_html(
        SITEMAP_URL,
        urlset(
            "https://example.com/",
            HUB_URL,
            ARTICLE_A,
            ARTICLE_B,
            "https://example.com/pricing",
            "https://other.example/blog/foreign",
        ),
    )
    config = {"domain": "example.com", "article_path_prefixes": ["/blog/"]}

    report = run_sitemap(SITEMAP_URL, config, sitemap_args())

    assert [page["url"] for page in report["pages"]] == [ARTICLE_A, ARTICLE_B]
    assert report["article_prefixes"] == ["/blog/"]
    assert report["summary"] == {
        "pages_checked": 2,
        "pages_with_hard_failures": 1,
        "pages_with_warnings": 0,
        "hard_items": 1,
        "warn_items": 0,
    }
    assert report["pages"][0]["hard"] == []
    assert report["pages"][1]["hard"][0]["name"] == "Canonical"
    assert report["generated_at"]
    assert report["site"] == "example.com"


def test_sitemap_limit_caps_the_number_of_pages(site):
    site.add_html(ARTICLE_A, build_page(canonical=ARTICLE_A))
    site.add_html(ARTICLE_B, build_page(canonical=ARTICLE_B))
    site.add_html(HOMEPAGE_URL, homepage_html())
    site.add_html(SITEMAP_URL, urlset(ARTICLE_A, ARTICLE_B))

    report = run_sitemap(SITEMAP_URL, CONFIG, sitemap_args(limit=1))

    assert [page["url"] for page in report["pages"]] == [ARTICLE_A]


def test_sitemap_index_is_followed_one_level(site):
    child = "https://example.com/sitemap-articles.xml"
    site.add_html(ARTICLE_A, build_page(canonical=ARTICLE_A))
    site.add_html(HOMEPAGE_URL, homepage_html())
    site.add_html(SITEMAP_URL, sitemap_index(child))
    site.add_html(child, urlset(ARTICLE_A))

    report = run_sitemap(SITEMAP_URL, CONFIG, sitemap_args())

    assert [page["url"] for page in report["pages"]] == [ARTICLE_A]


def test_unreachable_sitemap_is_fatal(site):
    with pytest.raises(SystemExit) as excinfo:
        run_sitemap(SITEMAP_URL, CONFIG, sitemap_args())

    assert "could not fetch sitemap" in str(excinfo.value)


def test_article_prefixes_falls_back_to_the_hub_path():
    assert check_publish.article_prefixes({"hub_path": "/blog"}) == ["/blog/"]
    assert check_publish.article_prefixes({"article_path_prefixes": ["blog"]}) == [
        "/blog"
    ]
    assert check_publish.article_prefixes({"article_path_prefixes": ["/blog/"]}) == [
        "/blog/"
    ]
    assert check_publish.article_prefixes({}) == []


def test_select_article_urls_needs_a_prefix_source():
    with pytest.raises(SystemExit) as excinfo:
        check_publish.select_article_urls([ARTICLE_A], {"domain": "example.com"})

    assert "neither article_path_prefixes nor hub_path" in str(excinfo.value)


# --- CLI ---------------------------------------------------------------------


def run_cli(monkeypatch, argv):
    monkeypatch.setattr(check_publish, "load_config", lambda path: CONFIG)
    monkeypatch.setattr(sys, "argv", ["check_publish.py"] + argv)
    with pytest.raises(SystemExit) as excinfo:
        check_publish.main()
    return excinfo.value.code


def test_cli_url_mode_writes_a_json_report_and_exits_zero(site, tmp_path, monkeypatch):
    site.add_html(PAGE_URL, build_page())
    site.add_html(HOMEPAGE_URL, homepage_html())
    report_path = tmp_path / "publish-report.json"

    code = run_cli(
        monkeypatch,
        [
            "--config",
            "site-config.example.json",
            "--url",
            PAGE_URL,
            "--no-link-check",
            "--delay",
            "0",
            "--json-out",
            str(report_path),
        ],
    )

    assert code == 0
    report = json.loads(report_path.read_text())
    assert report["pages"][0]["url"] == PAGE_URL
    assert report["pages"][0]["hard"] == []
    assert report["summary"]["pages_checked"] == 1
    assert report["summary"]["warn_items"] == 0


def test_cli_url_mode_exits_one_on_a_hard_failure(site, monkeypatch):
    site.add_html(PAGE_URL, build_page(canonical=None))
    site.add_html(HOMEPAGE_URL, homepage_html())

    code = run_cli(
        monkeypatch,
        [
            "--config",
            "site-config.example.json",
            "--url",
            PAGE_URL,
            "--no-link-check",
            "--delay",
            "0",
        ],
    )

    assert code == 1


def test_cli_exits_zero_when_only_warnings_are_present(site, monkeypatch):
    site.add_html(PAGE_URL, build_page(title="Short title"))
    site.add_html(HOMEPAGE_URL, homepage_html())

    code = run_cli(
        monkeypatch,
        [
            "--config",
            "site-config.example.json",
            "--url",
            PAGE_URL,
            "--no-link-check",
            "--delay",
            "0",
        ],
    )

    assert code == 0


def test_cli_sitemap_mode_writes_a_json_report(site, tmp_path, monkeypatch):
    site.add_html(ARTICLE_A, build_page(canonical=ARTICLE_A))
    site.add_html(HOMEPAGE_URL, homepage_html())
    site.add_html(SITEMAP_URL, urlset(ARTICLE_A))
    report_path = tmp_path / "sitemap-report.json"
    monkeypatch.setattr(
        check_publish,
        "load_config",
        lambda path: {"domain": "example.com", "article_path_prefixes": ["/blog/"]},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_publish.py",
            "--config",
            "site-config.example.json",
            "--sitemap-url",
            SITEMAP_URL,
            "--no-link-check",
            "--delay",
            "0",
            "--json-out",
            str(report_path),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        check_publish.main()

    assert excinfo.value.code == 0
    report = json.loads(report_path.read_text())
    assert report["summary"]["pages_checked"] == 1
    assert report["pages"][0]["url"] == ARTICLE_A


def test_cli_requires_exactly_one_target(site, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_publish.py",
            "--config",
            "site-config.example.json",
            "--url",
            PAGE_URL,
            "--sitemap-url",
            SITEMAP_URL,
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        check_publish.main()

    assert excinfo.value.code == 2
