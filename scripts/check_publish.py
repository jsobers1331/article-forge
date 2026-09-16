"""Live-page publish gate for an article that is ALREADY published.

`check_article.py` gates a draft before it goes out; this gates the URL
afterwards. Same shape as that script — a CHECK, not a rewrite tool — and the
same PASS/WARN/FAIL vocabulary, but applied to what a crawler actually
receives: the served HTML, the head, and the links and images inside the body.

    python3 scripts/check_publish.py --config site-config.<project>.json \\
        --url https://example.com/blog/some-article --type standard

    python3 scripts/check_publish.py --config site-config.<project>.json \\
        --sitemap-url https://example.com/sitemap.xml --json-out report.json

Exit code is non-zero when any HARD check fails.

What is HARD (blocks, exit 1) vs WARN (soft, human judgment):

  HARD  non-200 response; a redirect chain that lands on a different path;
        zero or multiple <title> tags; missing or homepage-duplicate meta
        description; missing/non-self-referencing canonical; a robots
        directive that forbids indexing; missing or relative og:image;
        twitter:title identical to the homepage's; JSON-LD that does not
        parse; a JSON-LD `@id` reference (author/publisher) with no node to
        resolve it against; an in-body internal link that returns non-200;
        zero or multiple <h1>; an unsupported claim in the claim-verification
        ledger.
  WARN  everything else: a missing, stale, or inconclusive claim-verification
        ledger; title/description length, missing twitter:image,
        og:type not matching the page kind, missing Article.type/image,
        non-ISO or identical dates, thin internal linking, no hub link,
        external/competitor links, missing alt text, hero without
        width/height, no visible date, word count outside the type's band,
        banned words.

`scripts/verify_facts.py` writes its verdicts to
`claim-verification.<project>.json` next to the site config; this gate reads
that ledger. An `unsupported` claim is HARD, while a missing, stale, or
`inconclusive` ledger is WARN. Pass --no-ledger to skip the check.

Two judgment calls worth naming, because they are the difference between a
gate that gets used and one that gets ignored:

  * The `@id` resolution failure is HARD. RULES.md §4 requires an Article node
    whose author/publisher resolve to an Organization; a dangling reference is
    not a missing nicety, it is a schema block that says nothing (found live on
    homeweal.com on 2026-09-15 — `"@id": "https://homeweal.com#org"` with no
    such node on the page).
  * Only parse errors, dangling refs, and the head/status items above are
    HARD. Everything a human might reasonably disagree about is WARN, because
    a gate that reddens on taste gets bypassed.

The homepage is fetched once per run and cached, so meta description and
twitter:title uniqueness can be checked against it (the "article inherits
homepage copy" defect class). Internal-link targets are cached too, so a link
hit from ten articles is fetched once.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from xml.etree import ElementTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_article import (  # noqa: E402
    DEFAULT_BAN_WORDS,
    WORD_COUNT_RANGES,
    check_claim_ledger,
    word_count,
)
from generate_prompt import load_config  # noqa: E402

USER_AGENT = "article-forge-publish-gate/1.0 (+https://github.com/article-forge)"
FETCH_TIMEOUT = 20
LINK_TIMEOUT = 10
MAX_LINK_CHECKS = 30
DEFAULT_DELAY = 0.3
TITLE_MIN, TITLE_MAX = 15, 70
DESC_MIN, DESC_MAX = 50, 160
ARTICLE_SCHEMA_TYPES = {"Article", "BlogPosting", "NewsArticle", "TechArticle"}
SITE_SCHEMA_TYPES = {
    "Organization",
    "WebSite",
    "LocalBusiness",
    "SoftwareApplication",
    "WebPage",
}
SKIP_HREF_PREFIXES = ("mailto:", "tel:", "javascript:", "data:", "#")
MARKERS = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


@dataclass
class Response:
    """Everything a check needs from one HTTP round trip."""

    status: int
    final_url: str
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    error: str = ""
    redirect_chain: list = field(default_factory=list)

    @property
    def text(self):
        ctype = self.headers.get("content-type", "")
        match = re.search(r"charset=([\w-]+)", ctype, re.IGNORECASE)
        encoding = match.group(1) if match else "utf-8"
        try:
            return self.body.decode(encoding, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


@dataclass
class Result:
    area: str
    name: str
    status: str
    detail: str

    def as_dict(self):
        return {
            "area": self.area,
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
        }


class _RedirectRecorder(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.chain = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.chain.append({"status": code, "url": newurl})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_LAST_REQUEST_AT = 0.0
_HOMEPAGE_CACHE = {}
_LINK_CACHE = {}


def _throttle(delay):
    global _LAST_REQUEST_AT
    if delay:
        if _LAST_REQUEST_AT:
            wait = delay - (time.monotonic() - _LAST_REQUEST_AT)
            if wait > 0:
                time.sleep(wait)
        _LAST_REQUEST_AT = time.monotonic()


def _http_request(url, method="GET", timeout=FETCH_TIMEOUT, delay=DEFAULT_DELAY):
    """The single seam every outbound request goes through — tests replace this."""
    _throttle(delay)
    recorder = _RedirectRecorder()
    opener = urllib.request.build_opener(recorder)
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT}, method=method
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            headers = {}
            for key, value in response.headers.items():
                key = key.lower()
                headers[key] = f"{headers[key]}, {value}" if key in headers else value
            return Response(
                status=getattr(response, "status", 200),
                final_url=response.url,
                headers=headers,
                body=response.read(),
                redirect_chain=recorder.chain,
            )
    except urllib.error.HTTPError as exc:
        headers = {}
        if exc.headers is not None:
            for key, value in exc.headers.items():
                headers[key.lower()] = value
        return Response(
            status=exc.code,
            final_url=exc.url or url,
            headers=headers,
            error="" if exc.code else str(exc),
            redirect_chain=recorder.chain,
        )
    except Exception as exc:  # network-level: DNS, TLS, timeout, connection reset
        return Response(
            status=0,
            final_url=url,
            error=f"{type(exc).__name__}: {exc}",
            redirect_chain=recorder.chain,
        )


class PageParser(HTMLParser):
    """Collects only what the gate checks — no DOM, no dependencies.

    The "main content" region is `<article>` or `<main>` when the page has one
    (so nav/footer links and chrome images stay out of the link and image
    counts); otherwise the whole document is treated as content. Both the
    region-scoped and the document-wide collections are kept, so a page with an
    empty region still gets a meaningful fallback instead of a false "0 links".
    """

    MAIN_TAGS = ("article", "main")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titles = []
        self.metas = []
        self.canonicals = []
        self.jsonld_blocks = []
        self.h1s = []
        self.main_hrefs = []
        self.all_hrefs = []
        self.main_images = []
        self.all_images = []
        self.main_text_parts = []
        self.body_text_parts = []
        self._capture = None
        self._capture_parts = []
        self._cdata = 0
        self._main_depth = 0
        self._saw_main = False
        self._h1_depth = 0
        self._h1_parts = []

    @property
    def in_main(self):
        return self._main_depth > 0

    @property
    def has_main_region(self):
        return self._saw_main

    @property
    def hrefs(self):
        return self.main_hrefs or self.all_hrefs

    @property
    def images(self):
        return self.main_images or self.all_images

    @property
    def text(self):
        parts = self.main_text_parts or self.body_text_parts
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    def meta(self, key):
        for attrs in self.metas:
            for name_field in ("name", "property", "http-equiv", "itemprop"):
                if attrs.get(name_field, "").strip().lower() == key.lower():
                    return attrs.get("content", "")
        return ""

    def meta_all(self, key):
        values = []
        for attrs in self.metas:
            for name_field in ("name", "property", "http-equiv", "itemprop"):
                if attrs.get(name_field, "").strip().lower() == key.lower():
                    content = attrs.get("content")
                    if content is not None:
                        values.append(content)
        return values

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = {
            key.lower(): (value if value is not None else "") for key, value in attrs
        }
        if tag in self.MAIN_TAGS:
            self._saw_main = True
            self._main_depth += 1
        if tag in ("script", "style"):
            self._cdata += 1
        if tag == "title":
            self._capture = "title"
            self._capture_parts = []
        elif (
            tag == "script"
            and attrs.get("type", "").strip().lower() == "application/ld+json"
        ):
            self._capture = "jsonld"
            self._capture_parts = []
        elif tag == "meta":
            self.metas.append(attrs)
        elif tag == "link":
            rel = attrs.get("rel", "").lower()
            if "canonical" in rel and attrs.get("href"):
                self.canonicals.append(attrs["href"].strip())
        elif tag == "h1":
            self._h1_depth += 1
            self._h1_parts = []
        elif tag == "a":
            href = attrs.get("href", "").strip()
            if href:
                self.all_hrefs.append(href)
                if self.in_main:
                    self.main_hrefs.append(href)
        elif tag == "img":
            record = {
                "src": (attrs.get("src") or attrs.get("data-src") or "").strip(),
                "alt": attrs.get("alt"),
                "width": attrs.get("width", ""),
                "height": attrs.get("height", ""),
                "style": attrs.get("style", ""),
            }
            self.all_images.append(record)
            if self.in_main:
                self.main_images.append(record)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.MAIN_TAGS and self._main_depth > 0:
            self._main_depth -= 1
        if tag in ("script", "style") and self._cdata > 0:
            self._cdata -= 1
        if tag == "title" and self._capture == "title":
            self.titles.append(
                re.sub(r"\s+", " ", "".join(self._capture_parts)).strip()
            )
            self._capture = None
        elif tag == "script" and self._capture == "jsonld":
            self.jsonld_blocks.append("".join(self._capture_parts))
            self._capture = None
        elif tag == "h1" and self._h1_depth:
            self._h1_depth -= 1
            self.h1s.append(re.sub(r"\s+", " ", "".join(self._h1_parts)).strip())

    def handle_data(self, data):
        if self._capture == "title":
            self._capture_parts.append(data)
        elif self._capture == "jsonld":
            self._capture_parts.append(data)
        elif self._h1_depth:
            self._h1_parts.append(data)
        if self._cdata == 0 and data.strip():
            self.body_text_parts.append(data.strip())
            if self.in_main:
                self.main_text_parts.append(data.strip())


def parse_page(html_text):
    parser = PageParser()
    parser.feed(html_text)
    parser.close()
    return parser


def normalize_host(host):
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def normalize_url(url):
    parts = urllib.parse.urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return f"{parts.scheme.lower()}://{normalize_host(parts.netloc)}{path}"


def same_site(url, site_domain):
    return normalize_host(urllib.parse.urlsplit(url).netloc) == normalize_host(
        site_domain
    )


def is_absolute(url):
    return urllib.parse.urlsplit(url).scheme.lower() in ("http", "https")


def parse_iso(value):
    if not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


@dataclass
class PageContext:
    url: str
    response: Response
    parser: PageParser
    config: dict
    kind: str = "article"
    article_type: str = "standard"
    target_query: str = ""
    homepage: dict = None
    check_links: bool = True
    delay: float = DEFAULT_DELAY

    @property
    def site_domain(self):
        return self.config.get("domain", "")

    @property
    def hub_path(self):
        hub = self.config.get("hub_path", "")
        return hub.rstrip("/") if hub else ""


def homepage_facts(page_url, config, delay=DEFAULT_DELAY):
    """Fetch the site homepage once per process — the reference point for the
    "this article's meta description is the homepage's" duplicate class."""
    parts = urllib.parse.urlsplit(page_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin in _HOMEPAGE_CACHE:
        return _HOMEPAGE_CACHE[origin]
    response = _http_request(origin + "/", "GET", FETCH_TIMEOUT, delay)
    facts = None
    if response.status == 200:
        parser = parse_page(response.text)
        facts = {
            "url": response.final_url or origin + "/",
            "description": parser.meta("description"),
            "twitter_title": parser.meta("twitter:title"),
            "og_title": parser.meta("og:title"),
        }
    _HOMEPAGE_CACHE[origin] = facts
    return facts


def refers_to_same_page(homepage, page_url):
    """True when the homepage facts describe the very page being checked.

    The duplicate-title/description checks compare a page against the homepage
    fetched for its origin; on the homepage itself that comparison must be
    skipped or every homepage run reports itself as a duplicate."""
    return bool(homepage and homepage.get("url")) and normalize_url(
        homepage["url"]
    ) == normalize_url(page_url)


# --- checks -----------------------------------------------------------------


def check_http_status(ctx):
    response = ctx.response
    if response.status == 0:
        return [("FAIL", f"could not fetch the page: {response.error}")]
    if response.status != 200:
        return [("FAIL", f"HTTP {response.status} for {ctx.url} (expected 200)")]
    return [("PASS", "HTTP 200")]


def check_redirect(ctx):
    response = ctx.response
    hops = response.redirect_chain
    final = response.final_url or ctx.url
    if not hops:
        return [("PASS", "served directly, no redirects")]
    chain = " -> ".join([ctx.url] + [hop["url"] for hop in hops])
    if normalize_url(final) != normalize_url(ctx.url):
        return [
            (
                "FAIL",
                f"redirect chain lands on a different path ({len(hops)} hop(s)): {chain}",
            )
        ]
    if (
        urllib.parse.urlsplit(final).netloc.lower()
        != urllib.parse.urlsplit(ctx.url).netloc.lower()
    ):
        return [
            (
                "WARN",
                f"host-level redirect before serving the same path: {chain} — confirm the canonical tag and the sitemap use the same host",
            )
        ]
    return [("PASS", f"redirects, but stays on this path: {chain}")]


def check_title(ctx):
    titles = [title for title in ctx.parser.titles]
    if not titles:
        return [("FAIL", "no <title> tag in the served HTML")]
    if len(titles) > 1:
        return [
            ("FAIL", f"{len(titles)} <title> tags (expected exactly one): {titles[:3]}")
        ]
    title = titles[0]
    if not title:
        return [("FAIL", "empty <title> tag")]
    length = len(title)
    if length < TITLE_MIN or length > TITLE_MAX:
        return [
            (
                "WARN",
                f"{length} chars, outside the {TITLE_MIN}-{TITLE_MAX} guidance: {title!r}",
            )
        ]
    return [("PASS", f"{length} chars: {title!r}")]


def check_meta_description(ctx):
    descriptions = ctx.parser.meta_all("description")
    if not descriptions:
        return [("FAIL", "no meta description")]
    description = descriptions[0]
    results = []
    length = len(description)
    if length < DESC_MIN or length > DESC_MAX:
        results.append(
            (
                "WARN",
                f"{length} chars, outside the {DESC_MIN}-{DESC_MAX} guidance: {description!r}",
            )
        )
    else:
        results.append(("PASS", f"{length} chars: {description!r}"))
    homepage = ctx.homepage
    if homepage and homepage.get("description"):
        if refers_to_same_page(homepage, ctx.url):
            pass
        elif description.strip().lower() == homepage["description"].strip().lower():
            results.append(
                (
                    "FAIL",
                    "meta description is identical to the homepage's — duplicate description across pages",
                )
            )
        else:
            results.append(("PASS", "description differs from the homepage's"))
    return results


def check_canonical(ctx):
    canonicals = ctx.parser.canonicals
    if not canonicals:
        return [("FAIL", "no <link rel=canonical>")]
    canonical = canonicals[0]
    results = []
    if len(canonicals) > 1:
        results.append(
            ("WARN", f"{len(canonicals)} canonical tags found: {canonicals}")
        )
    if not is_absolute(canonical):
        results.append(
            (
                "WARN",
                f"canonical is relative ({canonical!r}) — it resolves, but absolute is safer",
            )
        )
    resolved = urllib.parse.urljoin(ctx.url, canonical)
    if normalize_url(resolved) != normalize_url(ctx.url):
        results.append(
            (
                "FAIL",
                f"canonical points at another URL: {canonical} (page is {ctx.url})",
            )
        )
    else:
        results.append(("PASS", f"self-referencing canonical: {canonical}"))
        if (
            urllib.parse.urlsplit(resolved).netloc.lower()
            != urllib.parse.urlsplit(ctx.url).netloc.lower()
        ):
            results.append(
                (
                    "WARN",
                    f"canonical host ({urllib.parse.urlsplit(resolved).netloc}) differs from the served host",
                )
            )
    return results


def check_robots(ctx):
    results = []
    x_robots = ctx.response.headers.get("x-robots-tag", "")
    if "noindex" in x_robots.lower():
        results.append(("FAIL", f"X-Robots-Tag forbids indexing: {x_robots!r}"))
    robots = ctx.parser.meta("robots")
    if not robots:
        results.append(
            (
                "WARN",
                "no meta robots directive (treated as index,follow, but say so explicitly)",
            )
        )
    else:
        lowered = robots.lower()
        if "noindex" in lowered or "none" in lowered:
            results.append(("FAIL", f"meta robots forbids indexing: {robots!r}"))
        elif "index" not in lowered:
            results.append(("WARN", f"meta robots is {robots!r} — no explicit 'index'"))
        elif "follow" not in lowered:
            results.append(
                ("WARN", f"meta robots is {robots!r} — no explicit 'follow'")
            )
        else:
            results.append(("PASS", f"indexable: {robots!r}"))
    if len(ctx.parser.meta_all("robots")) > 1:
        results.append(
            (
                "WARN",
                "multiple meta robots tags — crawlers combine them, which is usually unintended",
            )
        )
    return results


def check_social(ctx):
    parser = ctx.parser
    results = []
    og_image = parser.meta("og:image")
    if not og_image:
        results.append(
            ("FAIL", "og:image missing — social/link previews have no image")
        )
    elif not is_absolute(og_image):
        results.append(("FAIL", f"og:image is not an absolute URL: {og_image!r}"))
    else:
        results.append(("PASS", f"og:image: {og_image}"))
    twitter_image = parser.meta("twitter:image") or parser.meta("twitter:image:src")
    twitter_card = parser.meta("twitter:card")
    if not twitter_image:
        detail = "twitter:image missing"
        if "summary_large_image" in twitter_card.lower():
            detail += f" while twitter:card is {twitter_card!r} — the card claims a large image it cannot render"
        results.append(("WARN", detail))
    elif not is_absolute(twitter_image):
        results.append(("WARN", f"twitter:image is not absolute: {twitter_image!r}"))
    else:
        results.append(("PASS", f"twitter:image: {twitter_image}"))
    twitter_title = parser.meta("twitter:title")
    homepage = ctx.homepage or {}
    duplicates_homepage = (
        homepage.get("twitter_title")
        and twitter_title.strip() == homepage["twitter_title"].strip()
        and not refers_to_same_page(homepage, ctx.url)
    )
    if not twitter_title:
        results.append(("WARN", "twitter:title missing (falls back to og:title/title)"))
    elif duplicates_homepage:
        results.append(
            (
                "FAIL",
                "twitter:title is identical to the homepage's — the card shows the wrong page name",
            )
        )
    else:
        results.append(("PASS", f"twitter:title: {twitter_title!r}"))
    og_type = parser.meta("og:type")
    expected = "article" if ctx.kind == "article" else "website"
    if not og_type:
        results.append(("WARN", "og:type missing"))
    elif og_type.strip().lower() != expected:
        if expected == "article" and og_type.strip().lower() in ("website", "webpage"):
            results.append(("WARN", f"og:type is {og_type!r}, expected 'article'"))
        elif expected == "website" and og_type.strip().lower() in (
            "article",
            "blogposting",
            "newsarticle",
        ):
            results.append(("WARN", f"og:type is {og_type!r} on a non-article page"))
        else:
            results.append(("PASS", f"og:type: {og_type!r}"))
    else:
        results.append(("PASS", f"og:type: {og_type!r}"))
    return results


def _flatten_nodes(data):
    nodes = []
    if isinstance(data, dict):
        nodes.append(data)
        for value in data.values():
            nodes.extend(_flatten_nodes(value))
    elif isinstance(data, list):
        for item in data:
            nodes.extend(_flatten_nodes(item))
    return nodes


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _ref_ids(value):
    ids = []
    for item in _as_list(value):
        if isinstance(item, str) and item.startswith("http"):
            ids.append(item)
        elif isinstance(item, dict) and isinstance(item.get("@id"), str):
            ids.append(item["@id"])
    return ids


def _image_url(value):
    for item in _as_list(value):
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            if isinstance(item.get("url"), str):
                return item["url"]
            if isinstance(item.get("@id"), str):
                return item["@id"]
    return ""


def check_jsonld(ctx):
    blocks = ctx.parser.jsonld_blocks
    if not blocks:
        return [("FAIL", "no application/ld+json block in the served HTML")]
    results = []
    nodes = []
    errors = []
    for index, raw in enumerate(blocks):
        stripped = raw.strip()
        if not stripped:
            errors.append(f"block {index + 1}: empty <script type=application/ld+json>")
            continue
        try:
            nodes.extend(_flatten_nodes(json.loads(stripped)))
        except json.JSONDecodeError as exc:
            errors.append(f"block {index + 1}: {exc}")
    if errors:
        results.append(("FAIL", "JSON-LD does not parse: " + "; ".join(errors)))
        return results
    results.append(
        ("PASS", f"{len(blocks)} JSON-LD block(s) parse; {len(nodes)} node(s)")
    )

    id_map = {}
    for node in nodes:
        # A dict whose only key is @id is a *reference* to a node, not the
        # declaration of it. Counting those as declarations would make every
        # dangling reference satisfy itself, which is the false negative this
        # check exists to catch.
        if isinstance(node.get("@id"), str) and len(node) > 1:
            id_map[node["@id"]] = node

    types = set()
    for node in nodes:
        for node_type in _as_list(node.get("@type")):
            if isinstance(node_type, str):
                types.add(node_type)

    article_nodes = [
        node
        for node in nodes
        if ARTICLE_SCHEMA_TYPES
        & {t for t in _as_list(node.get("@type")) if isinstance(t, str)}
    ]
    if ctx.kind == "article":
        if not article_nodes:
            results.append(
                (
                    "WARN",
                    f"no Article/BlogPosting node (types present: {sorted(types) or 'none'})",
                )
            )
        else:
            results.append(
                ("PASS", f"article node: {sorted(ARTICLE_SCHEMA_TYPES & types)[0]}")
            )
        for node in article_nodes:
            for rel in ("author", "publisher"):
                raw_value = node.get(rel)
                if raw_value is None:
                    results.append(("WARN", f"Article.{rel} missing"))
                    continue
                targets = _ref_ids(raw_value)
                dangling = [target for target in targets if target not in id_map]
                if dangling:
                    results.append(
                        (
                            "FAIL",
                            f"Article.{rel} references @id {dangling[0]!r} but no such node exists on this page (dangling reference)",
                        )
                    )
                elif targets:
                    results.append(
                        (
                            "PASS",
                            f"Article.{rel} -> {targets[0]} (resolves on this page)",
                        )
                    )
                else:
                    inline = _as_list(raw_value)[0]
                    name = inline.get("name") if isinstance(inline, dict) else ""
                    results.append(
                        (
                            "PASS",
                            f"Article.{rel} is inline{f' ({name})' if name else ''}",
                        )
                    )
            image = _image_url(node.get("image"))
            if not image:
                results.append(("WARN", "Article.image missing"))
            elif not is_absolute(image):
                results.append(("WARN", f"Article.image is not absolute: {image!r}"))
            else:
                results.append(("PASS", f"Article.image: {image}"))
            published = node.get("datePublished")
            modified = node.get("dateModified")
            for label, value in (
                ("datePublished", published),
                ("dateModified", modified),
            ):
                if value is None:
                    results.append(("WARN", f"{label} missing"))
                elif parse_iso(value) is None:
                    results.append(("WARN", f"{label} is not ISO-8601: {value!r}"))
            if published and modified:
                published_dt, modified_dt = parse_iso(published), parse_iso(modified)
                if published_dt and modified_dt and published_dt == modified_dt:
                    results.append(
                        (
                            "WARN",
                            f"dateModified == datePublished ({published}) — modified date carries no signal",
                        )
                    )
        if "BreadcrumbList" not in types:
            results.append(
                (
                    "WARN",
                    "no BreadcrumbList node (RULES.md §4 requires one on every article)",
                )
            )
    else:
        if SITE_SCHEMA_TYPES & types:
            results.append(
                (
                    "PASS",
                    f"site-level node present: {sorted(SITE_SCHEMA_TYPES & types)}",
                )
            )
        else:
            results.append(
                (
                    "WARN",
                    f"no Organization/WebSite node (types present: {sorted(types) or 'none'})",
                )
            )
    article_node_ids = {id(node) for node in article_nodes}
    for node in nodes:
        if id(node) in article_node_ids:
            continue
        for rel in ("author", "publisher"):
            dangling = [
                target for target in _ref_ids(node.get(rel)) if target not in id_map
            ]
            if dangling:
                results.append(
                    (
                        "FAIL",
                        f"{rel} references missing @id {dangling[0]!r} (dangling reference)",
                    )
                )
    return results


def check_internal_links(ctx):
    parser = ctx.parser
    hrefs = []
    for href in parser.hrefs:
        if (
            not href
            or href.startswith("#")
            or href.lower().startswith(SKIP_HREF_PREFIXES)
        ):
            continue
        hrefs.append(urllib.parse.urljoin(ctx.url, href))
    seen = set()
    unique = []
    for url in hrefs:
        key = normalize_url(url)
        if key not in seen:
            seen.add(key)
            unique.append(url)
    internal = [url for url in unique if same_site(url, ctx.site_domain)]
    external = [url for url in unique if not same_site(url, ctx.site_domain)]
    results = []
    if len(internal) < 2:
        results.append(
            (
                "WARN",
                f"only {len(internal)} in-body internal link(s) — RULES.md wants the article to link back into the site: {internal}",
            )
        )
    else:
        results.append(("PASS", f"{len(internal)} in-body internal link(s)"))
    hub = ctx.hub_path
    if hub:
        hub_normalized = normalize_url(urllib.parse.urljoin(ctx.url, hub))
        if any(normalize_url(url) == hub_normalized for url in internal):
            results.append(("PASS", f"links up to the hub ({hub})"))
        else:
            results.append(("WARN", f"no in-body link up to the hub ({hub})"))
    if external:
        results.append(
            (
                "WARN",
                f"{len(external)} external/competitor link(s) in the body: {external[:3]}",
            )
        )
    if not internal:
        return results
    if ctx.check_links:
        to_check = internal[:MAX_LINK_CHECKS]
        if len(internal) > MAX_LINK_CHECKS:
            results.append(
                (
                    "PASS",
                    f"link check capped at {MAX_LINK_CHECKS} of {len(internal)} links",
                )
            )
        broken = []
        unverified = []
        for url in to_check:
            if url not in _LINK_CACHE:
                response = _http_request(url, "HEAD", LINK_TIMEOUT, ctx.delay)
                if response.status in (403, 405, 501):
                    response = _http_request(url, "GET", LINK_TIMEOUT, ctx.delay)
                _LINK_CACHE[url] = response
            response = _LINK_CACHE[url]
            if response.status == 0:
                unverified.append(f"{url} ({response.error})")
            elif response.status not in (200, 301, 302, 307, 308):
                broken.append(f"{url} -> HTTP {response.status}")
        if broken:
            results.append(
                (
                    "FAIL",
                    f"{len(broken)} internal link(s) do not resolve: "
                    + "; ".join(broken),
                )
            )
        if unverified:
            results.append(
                (
                    "WARN",
                    f"could not verify {len(unverified)} link(s): "
                    + "; ".join(unverified),
                )
            )
        if not broken and not unverified:
            results.append(
                ("PASS", f"all {len(to_check)} checked internal link(s) return 200")
            )
    else:
        results.append(("PASS", "link checks skipped (--no-link-check)"))
    return results


def check_images(ctx):
    images = ctx.parser.images
    results = []
    if not images:
        results.append(
            (
                "WARN",
                "no <img> in the article content — IMAGES.md expects at least a hero",
            )
        )
        return results
    missing_alt = [image for image in images if not (image.get("alt") or "").strip()]
    if missing_alt:
        sample = ", ".join(image["src"] or "(no src)" for image in missing_alt[:3])
        results.append(
            (
                "WARN",
                f"{len(missing_alt)} of {len(images)} image(s) have no alt text: {sample}",
            )
        )
    else:
        results.append(("PASS", f"all {len(images)} image(s) have alt text"))
    hero = images[0]
    has_dimensions = bool(hero.get("width") and hero.get("height"))
    has_aspect = "aspect-ratio" in hero.get("style", "").lower()
    if not has_dimensions and not has_aspect:
        results.append(
            (
                "WARN",
                f"hero image has no width/height or aspect-ratio: {hero['src'] or '(no src)'}",
            )
        )
    else:
        results.append(
            (
                "PASS",
                f"hero image has explicit dimensions or aspect ratio: {hero['src']}",
            )
        )
    return results


def check_visible_dates(ctx):
    parser = ctx.parser
    text = parser.text
    pattern = re.compile(
        rf"\b(updated|published|last modified|reviewed|posted)\b|\b({MONTHS})\s+\d{{1,2}},\s+\d{{4}}\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        body_match = pattern.search(
            re.sub(r"\s+", " ", " ".join(parser.body_text_parts))
        )
        if body_match:
            return [
                (
                    "WARN",
                    f"date-like text exists on the page ({body_match.group(0)!r}) but not in the article content — readers may not see a publish/update date",
                )
            ]
        return [("WARN", "no visible publish or update date anywhere in the page text")]
    start = max(0, match.start() - 40)
    return [
        ("PASS", f"visible date text: ...{text[start : match.end() + 40].strip()}...")
    ]


def check_h1(ctx):
    if ctx.kind != "article":
        if not ctx.parser.h1s:
            return [("WARN", "no <h1>")]
        return [("PASS", f"{len(ctx.parser.h1s)} <h1>: {ctx.parser.h1s[0]!r}")]
    h1s = ctx.parser.h1s
    if not h1s:
        return [("FAIL", "no <h1> in the served HTML")]
    if len(h1s) > 1:
        return [("FAIL", f"{len(h1s)} <h1> tags (expected exactly one): {h1s[:3]}")]
    results = [("PASS", f"one <h1>: {h1s[0]!r}")]
    if ctx.target_query:
        query_words = set(re.findall(r"\w+", ctx.target_query.lower()))
        h1_words = set(re.findall(r"\w+", h1s[0].lower()))
        overlap = len(query_words & h1_words) / max(len(query_words), 1)
        if overlap < 0.5:
            results.append(
                (
                    "WARN",
                    f"H1 overlaps only {overlap:.0%} with the target query ({ctx.target_query!r})",
                )
            )
        else:
            results.append(
                (
                    "PASS",
                    f"H1 matches the target query closely ({overlap:.0%} word overlap)",
                )
            )
    return results


def check_word_count(ctx):
    if ctx.kind != "article":
        return [("PASS", "word count skipped for non-article pages")]
    text = ctx.parser.text
    count = word_count(text)
    low, high = WORD_COUNT_RANGES.get(ctx.article_type, WORD_COUNT_RANGES["standard"])
    if count == 0:
        return [("WARN", "no readable body text found in the article content region")]
    if count < low:
        return [
            (
                "WARN",
                f"{count} words in the content region, below the {low}-{high} band for '{ctx.article_type}' (region extraction is heuristic — confirm by eye)",
            )
        ]
    if count > high:
        return [
            (
                "WARN",
                f"{count} words in the content region, above the {low}-{high} band for '{ctx.article_type}' (region extraction is heuristic — confirm by eye)",
            )
        ]
    return [("PASS", f"{count} words, within {low}-{high} for '{ctx.article_type}'")]


def check_banned_words(ctx):
    if ctx.kind != "article":
        return [("PASS", "banned words skipped for non-article pages")]
    text = ctx.parser.text.lower()
    extra = ctx.config.get("voice", {}).get("extra_ban_words", [])
    hits = [word for word in DEFAULT_BAN_WORDS + list(extra) if word.lower() in text]
    if hits:
        return [("WARN", f"banned words present in the served copy: {', '.join(hits)}")]
    return [("PASS", "no banned words in the served copy")]


CHECKS = [
    ("HTTP status & redirects", "HTTP status", check_http_status),
    ("HTTP status & redirects", "Redirect chain", check_redirect),
    ("Title & meta description", "Title", check_title),
    ("Title & meta description", "Meta description", check_meta_description),
    ("Canonical & robots", "Canonical", check_canonical),
    ("Canonical & robots", "Robots directives", check_robots),
    ("Social cards", "Open Graph / Twitter", check_social),
    ("Structured data", "JSON-LD", check_jsonld),
    ("Internal links", "Internal links", check_internal_links),
    ("Images", "Images", check_images),
    ("Visible dates", "Visible dates", check_visible_dates),
    ("H1 & word count", "H1", check_h1),
    ("H1 & word count", "Word count", check_word_count),
    ("Banned words", "Banned words", check_banned_words),
]


def analyze_page(
    url,
    config,
    kind="article",
    article_type="standard",
    target_query="",
    check_links=True,
    delay=DEFAULT_DELAY,
):
    """Run every check against one live URL and return its Results."""
    response = _http_request(url, "GET", FETCH_TIMEOUT, delay)
    parser = (
        parse_page(response.text)
        if response.status == 200 and response.body
        else PageParser()
    )
    homepage = None
    if kind == "article" and response.status == 200:
        homepage = homepage_facts(url, config, delay)
    ctx = PageContext(
        url=url,
        response=response,
        parser=parser,
        config=config,
        kind=kind,
        article_type=article_type,
        target_query=target_query,
        homepage=homepage,
        check_links=check_links,
        delay=delay,
    )
    results = []
    for area, name, check in CHECKS[:2]:
        results.extend(
            Result(area, name, status, detail) for status, detail in check(ctx)
        )
    if response.status != 200:
        results.append(
            Result(
                "Page body",
                "Remaining checks",
                "FAIL",
                "skipped — the page did not return 200",
            )
        )
        return results
    for area, name, check in CHECKS[2:]:
        results.extend(
            Result(area, name, status, detail) for status, detail in check(ctx)
        )
    return results


def print_results(results, url=""):
    if url:
        print(f"\n── {url}")
    for result in results:
        print(
            f"{MARKERS[result.status]} [{result.status}] {result.name}: {result.detail}"
        )


def summarize(results):
    return {
        "hard": [result.as_dict() for result in results if result.status == "FAIL"],
        "warn": [result.as_dict() for result in results if result.status == "WARN"],
        "pass": sum(1 for result in results if result.status == "PASS"),
    }


def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def fetch_sitemap_urls(sitemap_url, delay=DEFAULT_DELAY, depth=0):
    response = _http_request(sitemap_url, "GET", FETCH_TIMEOUT, delay)
    if response.status != 200:
        raise SystemExit(
            f"could not fetch sitemap {sitemap_url}: HTTP {response.status} {response.error}"
        )
    try:
        root = ElementTree.fromstring(response.text)
    except ElementTree.ParseError as exc:
        raise SystemExit(f"sitemap {sitemap_url} is not valid XML: {exc}")
    kind = local_name(root.tag)
    locs = [
        element.text.strip()
        for element in root.iter()
        if local_name(element.tag) == "loc" and element.text
    ]
    if kind == "sitemapindex":
        if depth >= 1:
            raise SystemExit(
                f"sitemap index nesting deeper than one level at {sitemap_url}: {kind}"
            )
        urls = []
        for child in locs:
            urls.extend(fetch_sitemap_urls(child, delay, depth + 1))
        return urls
    if kind != "urlset":
        raise SystemExit(f"unsupported sitemap root element <{kind}> in {sitemap_url}")
    return locs


def article_prefixes(config):
    prefixes = config.get("article_path_prefixes")
    if prefixes:
        return [
            prefix if prefix.startswith("/") else "/" + prefix for prefix in prefixes
        ]
    hub = config.get("hub_path")
    if hub:
        return [hub.rstrip("/") + "/"]
    return []


def select_article_urls(urls, config):
    prefixes = article_prefixes(config)
    if not prefixes:
        raise SystemExit(
            "config has neither article_path_prefixes nor hub_path — add one so the sitemap run knows which URLs are articles"
        )
    domain = config.get("domain", "")
    selected = []
    for url in urls:
        parts = urllib.parse.urlsplit(url)
        if domain and not same_site(url, domain):
            continue
        if any(parts.path.startswith(prefix) for prefix in prefixes):
            selected.append(url)
    return selected


def run_sitemap(sitemap_url, config, args):
    urls = fetch_sitemap_urls(sitemap_url, args.delay)
    article_urls = select_article_urls(urls, config)
    if args.limit:
        article_urls = article_urls[: args.limit]
    print(
        f"Sitemap {sitemap_url}: {len(urls)} URL(s), {len(article_urls)} match {article_prefixes(config)}"
    )
    pages = []
    for index, url in enumerate(article_urls, start=1):
        print(f"[{index}/{len(article_urls)}] {url}", flush=True)
        results = analyze_page(
            url,
            config,
            kind=args.kind,
            article_type=args.type,
            target_query=args.query,
            check_links=not args.no_link_check,
            delay=args.delay,
        )
        summary = summarize(results)
        pages.append({"url": url, "results": [r.as_dict() for r in results], **summary})
        if summary["hard"] or args.verbose:
            print_results(results)
        else:
            print(
                f"    {'⚠' if summary['warn'] else '✓'} {len(summary['hard'])} hard, {len(summary['warn'])} warn"
            )
    print("\nSTATUS  HARD  WARN  URL")
    for page in pages:
        status = "FAIL" if page["hard"] else ("WARN" if page["warn"] else "PASS")
        print(
            f"{status:<6}  {len(page['hard']):>4}  {len(page['warn']):>4}  {page['url']}"
        )
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "config": args.config,
        "site": config.get("domain", ""),
        "sitemap_url": sitemap_url,
        "kind": args.kind,
        "article_type": args.type,
        "article_prefixes": article_prefixes(config),
        "pages": pages,
        "summary": {
            "pages_checked": len(pages),
            "pages_with_hard_failures": sum(1 for page in pages if page["hard"]),
            "pages_with_warnings": sum(1 for page in pages if page["warn"]),
            "hard_items": sum(len(page["hard"]) for page in pages),
            "warn_items": sum(len(page["warn"]) for page in pages),
        },
    }
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Live-page publish gate: check a published article URL (or every article URL in a sitemap) against the head, schema, link, and image rules"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to your project's config, e.g. site-config.<project>.json",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--url", help="The live article URL to check")
    target.add_argument(
        "--sitemap-url", help="Sitemap to enumerate and check every article URL in it"
    )
    parser.add_argument(
        "--type", default="standard", choices=["pillar", "standard", "supporting"]
    )
    parser.add_argument(
        "--kind",
        default="article",
        choices=["article", "page"],
        help="'page' for homepages and hubs: skips H1/word-count/banned-words and expects site-level schema",
    )
    parser.add_argument(
        "--query", default="", help="The target query, for the H1-overlap check"
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Write the full result set as JSON (per-page results included)",
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Cap how many sitemap URLs to check"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Seconds between requests (politeness)",
    )
    parser.add_argument(
        "--no-link-check",
        action="store_true",
        help="Skip the HEAD/GET probe of every internal link",
    )
    parser.add_argument(
        "--no-ledger",
        action="store_true",
        help="Skip the claim-verification ledger check (bypasses the unsupported-claim hard fail)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print every check for every sitemap URL"
    )
    args = parser.parse_args()

    config = load_config(args.config)

    ledger_status, ledger_message = "PASS", ""
    if not args.no_ledger:
        ledger_status, ledger_message = check_claim_ledger(config, args.config)

    if args.url:
        results = analyze_page(
            args.url,
            config,
            kind=args.kind,
            article_type=args.type,
            target_query=args.query,
            check_links=not args.no_link_check,
            delay=args.delay,
        )
        print_results(results)
        summary = summarize(results)
        report = {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "config": args.config,
            "site": config.get("domain", ""),
            "kind": args.kind,
            "article_type": args.type,
            "claim_ledger": {"status": ledger_status, "message": ledger_message},
            "pages": [
                {"url": args.url, "results": [r.as_dict() for r in results], **summary}
            ],
            "summary": {
                "pages_checked": 1,
                "pages_with_hard_failures": 1 if summary["hard"] else 0,
                "pages_with_warnings": 1 if summary["warn"] else 0,
                "hard_items": len(summary["hard"]),
                "warn_items": len(summary["warn"]),
            },
        }
        print()
        if not args.no_ledger:
            print(
                f"{MARKERS[ledger_status]} [{ledger_status}] Claim verification ledger: {ledger_message}"
            )
        for result in results:
            if result.status == "FAIL":
                print(f"HARD FAIL — {result.name}: {result.detail}")
        print(
            f"{len(summary['hard'])} hard failure(s), {len(summary['warn'])} warning(s), {summary['pass']} passing check(s)."
        )
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2)
                handle.write("\n")
            print(f"JSON report written to {args.json_out}")
        sys.exit(1 if summary["hard"] or ledger_status == "FAIL" else 0)

    report = run_sitemap(args.sitemap_url, config, args)
    report["claim_ledger"] = {"status": ledger_status, "message": ledger_message}
    print()
    if not args.no_ledger:
        print(
            f"{MARKERS[ledger_status]} [{ledger_status}] Claim verification ledger: {ledger_message}"
        )
    if report["summary"]["hard_items"]:
        print(
            f"HARD FAILURES on {report['summary']['pages_with_hard_failures']} of {report['summary']['pages_checked']} page(s) — fix before treating this set as publishable."
        )
    else:
        print(f"No hard failures across {report['summary']['pages_checked']} page(s).")
    print(
        f"Warnings: {report['summary']['warn_items']} across {report['summary']['pages_with_warnings']} page(s)."
    )
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        print(f"JSON report written to {args.json_out}")
    sys.exit(1 if report["summary"]["hard_items"] or ledger_status == "FAIL" else 0)


if __name__ == "__main__":
    main()
