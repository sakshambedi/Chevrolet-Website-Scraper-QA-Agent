# from pathlib import Path

import html
import json
import os
from urllib.parse import urljoin

from dotenv import load_dotenv
from parsel import Selector
from scrapy import Request
from scrapy.spiders import Spider
from scrapy_playwright.page import PageMethod


class Scrapper(Spider):
    name = "Chevy Silverado"

    # Load environment variables
    load_dotenv()
    DEV_MODE = os.getenv("DEV", "False").lower() == "true"

    # Define URLs for both dev and production
    LOCAL_URL = (
        f"file://{os.path.join(os.getcwd(), 'samples', 'silverado_simple.html')}"
    )
    PROD_URL = "https://www.chevrolet.ca/en/trucks/silverado-1500"

    # Set start_urls based on DEV_MODE
    start_urls = [LOCAL_URL] if DEV_MODE else [PROD_URL]

    # Define custom settings
    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "LOG_LEVEL": "WARNING",
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-CA,en;q=0.9",
        },
        "USER_AGENT": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36",
    }

    # Add Playwright settings only for production mode
    if not DEV_MODE:
        custom_settings.update(
            {
                "DOWNLOAD_HANDLERS": {
                    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                },
                "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                "PLAYWRIGHT_BROWSER_TYPE": "chromium",
                "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 60000,
                "AUTOTHROTTLE_ENABLED": True,
                "AUTOTHROTTLE_START_DELAY": 1.0,
                "AUTOTHROTTLE_MAX_DELAY": 10.0,
                "CONCURRENT_REQUESTS": 1,
            }
        )

    def start_requests(self):
        for url in self.start_urls:
            if self.DEV_MODE:
                # For local files, use standard request without Playwright
                yield Request(url)
            else:
                # For production, use Playwright for dynamic content
                yield Request(
                    url,
                    meta={
                        "playwright": True,
                        "playwright_context": "default",
                        "playwright_context_kwargs": {
                            "viewport": {"width": 1366, "height": 768},
                            "locale": "en-CA",
                        },
                        "playwright_page_methods": [
                            PageMethod("wait_for_load_state", "domcontentloaded"),
                        ],
                    },
                )

    def parse(self, response):
        self.logger.info(f"Processing {response.url}")

        # Check if playwright_page is available and close it (only in production mode)
        if not self.DEV_MODE and "playwright_page" in response.meta:
            page = response.meta["playwright_page"]
            page.close()

        metadata = self.extract_metadata(response)
        parsed_navbar = self.parse_navbar(response)
        parsed_body = self.dfs_parse_body(response)

        # Yield the complete parsed data with DFS results
        yield {
            "url": response.url,
            "metadata": metadata,
            "navbar": parsed_navbar,
            "body_content": parsed_body,
        }

    def parse_navbar(self, navbar):
        root = navbar.xpath("//gb-global-nav/template[@id='gb-global-nav-content']")[0]
        BASE = "https://www.chevrolet.ca/"
        # tree = [n for n in (dfs(ch, BASE) for ch in root.xpath("./*")) if n is not None]
        # return json.dumps(tree, indent=2, ensure_ascii=False)

    def dfs_parse_body(self, body_html, base_url="https://www.chevrolet.ca/"):
        """
        Parse HTML body using DFS (Depth-First Search) algorithm
        This method extracts structured data from the complete HTML structure
        """

        return {"error": "No parseable content found", "parsing_method": "dfs"}

    def extract_metadata(self, response):
        # Basic metadata
        self.logger.info("Extracting metadata...")
        title = response.xpath("//title/text()").get()
        if title:
            title = title.strip()
        description = response.xpath('//meta[@name="description"]/@content').get()
        canonical = response.xpath('//link[@rel="canonical"]/@href').get()

        # OpenGraph metadata
        og_meta = {}
        og_meta["type"] = response.xpath('//meta[@property="og:type"]/@content').get()
        og_meta["url"] = response.xpath('//meta[@property="og:url"]/@content').get()
        og_meta["site_name"] = response.xpath(
            '//meta[@name="og:site_name"]/@content'
        ).get()

        # Twitter metadata
        twitter_meta = {}
        twitter_meta["card"] = response.xpath(
            '//meta[@name="twitter:card"]/@content'
        ).get()
        twitter_meta["site"] = response.xpath(
            '//meta[@name="twitter:site"]/@content'
        ).get()

        # Language metadata
        lang = response.xpath("//html/@lang").get()

        # Template information
        template = response.xpath('//meta[@name="template"]/@content').get()

        # Viewport
        viewport = response.xpath('//meta[@name="viewport"]/@content').get()

        self.logger.info(f"Extracted metadata from {response.url}")

        return {
            "title": title,
            "description": description,
            "canonical": canonical,
            "language": lang,
            "template": template,
            "viewport": viewport,
            "opengraph": og_meta,
            "twitter": twitter_meta,
        }

    EXCLUDE = {
        "script",
        "style",
        "noscript",
        "template",
        "gb-adv-grid",
        "gb-wrapper",
        "gb-responsive-image",
        "adv-col",
        "span",
        "gb-tab-nav",  # usually just adds nodes in tree, wraps an unordered list
    }

    WRAPPERS = {
        "div",
        "section",
        "nav",
        "header",
        "footer",
        "main",
        "article",
        "aside",
        "picture",
    }

    def own_text(self, el):
        parts = [t.strip() for t in el.xpath("./text()").getall()]
        return " ".join(p for p in parts if p)

    def all_text(self, el):
        return " ".join(" ".join(el.css("::text").getall()).split())

    def _append(self, kids, node):
        if node is None:
            return
        if isinstance(node, list):
            kids.extend(node)
        else:
            kids.append(node)

    def is_internal_link(u: str | None) -> bool:
        if not u:
            return False
        u = u.strip().split()[0]
        return u.startswith("/") or not u.startswith(("http://", "https://", "www."))

    def _norm_url(base, u):
        if not u:
            return None
        return urljoin(base, u.strip().split()[0])

    def _attrs(el):
        # keep all attributes verbatim
        return dict(el.attrib)

    def parse_json(raw):
        if not raw:
            return None
        s = html.unescape(raw).replace("\\/", "/")
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            try:
                return json.loads(s.replace("\u00a0", " ").replace("\xa0", " "))
            except json.JSONDecodeError:
                return s

    # -------- serializers (must accept children) --------
    def serialize_a(el, base, children):
        href = el.attrib.get("href")
        return {
            "a": {
                "text": all_text(el),
                "title": el.attrib.get("title", ""),
                "href": _norm_url(base, href),
                "link_type": ("internal" if is_internal_link(href) else "external")
                if href
                else None,
                "classes": el.attrib.get("class", ""),
                "target": el.attrib.get("target"),
                "content": children or None,
            }
        }

    def serialize_button_like(el, base, children):
        act = el.attrib.get("href") or el.attrib.get("formaction")
        return {
            "button": {
                "text": all_text(el),
                "url": _norm_url(base, act),
                "link_type": ("internal" if is_internal_link(act) else "external")
                if act
                else None,
                "classname": el.attrib.get("class", ""),
                "content": children or None,
                **({k: el.attrib[k] for k in el.attrib if k.startswith("data-")}),
                **(
                    {
                        k: el.attrib[k]
                        for k in ("title", "aria-haspopup", "aria-expanded")
                        if k in el.attrib
                    }
                ),
            }
        }

    def serialize_img(el, base, _children):
        src = el.attrib.get("src")
        return {
            "img": {
                "src": _norm_url(base, src),
                "classes": el.attrib.get("class", ""),
                "alt": el.attrib.get("alt"),
                "title": el.attrib.get("title"),
                "link_type": ("internal" if is_internal_link(src) else "external")
                if src
                else None,
                "loading": el.attrib.get("loading"),
                **({k: el.attrib[k] for k in el.attrib if k.startswith("data-")}),
            }
        }

    def serialize_source(el, base, _children):
        srcset = (el.attrib.get("srcset") or "").replace("\n", " ")
        urls = []
        for part in srcset.split(","):
            tok = part.strip().split()
            if tok:
                urls.append(_norm_url(base, tok[0]))
        return {
            "source": {
                "media": el.attrib.get("media"),
                "height": el.attrib.get("height"),
                "width": el.attrib.get("width"),
                "srcset": [u for u in urls if u],
                "classes": el.attrib.get("class", ""),
                "data_aspectratio": el.attrib.get("data-aspectratio"),
            }
        }

    def serialize_heading(el, _base, _children):
        return {"heading": own_text(el)}

    def serialize_gb_dynamic_text(el, _base, _children):
        return {
            "gb-dynamic-text": {
                "text": all_text(el) or None,
                "class": el.attrib.get("class", ""),
                "country": el.attrib.get("country"),
                "regional_information": parse_json(
                    el.attrib.get("regional-information-json")
                ),
            }
        }

    def serialize_myaccount_flyout(el, base, children):
        # reuse JSON attr parser
        def _parse(attr):
            return parse_json(el.attrib.get(attr))

        return {
            "gb-myaccount-flyout": {
                "class": el.attrib.get("class", ""),
                "flyoutstate": el.attrib.get("flyoutstate"),
                "auth_flyout": _parse("authflyoutdata"),
                "auth_links": _parse("authlinkdata"),
                "fallback": _parse("fallbackdata"),
                "content": children or None,  # preserve nested nodes if any
            }
        }

    def _attrs_copy(el):
        return dict(el.attrib) if el.attrib else {}

    def _pop_cls(attrs):
        cls = attrs.pop("class", None)
        return cls, attrs

    def serialize_li(el, _base, children):
        attrs = _attrs_copy(el)
        li_class, rest = _pop_cls(attrs)
        txt = own_text(el)
        node = {
            "item": {
                **({"li_class": li_class} if li_class else {}),
                **({"attrs": rest} if rest else {}),
                **({"text": txt} if txt else {}),
                **({"content": children} if children else {}),
            }
        }
        return node

    def _serialize_list(kind, el, base, children):
        # children already serialized by dfs; pick out only LI entries
        items = []
        other = []
        for ch in children:
            if isinstance(ch, dict) and "item" in ch:
                items.append(ch["item"])
            else:
                other.append(ch)
        attrs = _attrs_copy(el)
        cls, rest = _pop_cls(attrs)
        node = {
            kind: {
                **({"class": cls} if cls else {}),
                **({"attrs": rest} if rest else {}),
                **({"items": items} if items else {"items": []}),
                **({"content": other} if other else {}),
            }
        }
        return node

    def serialize_ul(el, base, children):
        return _serialize_list("ul", el, base, children)

    def serialize_ol(el, base, children):
        return _serialize_list("ol", el, base, children)

    NATIVE = {
        "a": serialize_a,
        "button": serialize_button_like,
        "input": serialize_button_like,  # gated below
        "img": serialize_img,
        "source": serialize_source,
        "gb-dynamic-text": serialize_gb_dynamic_text,
        "h1": serialize_heading,
        "h2": serialize_heading,
        "h3": serialize_heading,
        "h4": serialize_heading,
        "h5": serialize_heading,
        "h6": serialize_heading,
        "ul": serialize_ul,
        "ol": serialize_ol,
        "li": serialize_li,
        "gb-myaccount-flyout": serialize_myaccount_flyout,
    }

    def serialize_generic(el, children):
        node = {"tag": el.root.tag.lower()}
        attrs = _attrs(el)
        if attrs:
            node["attrs"] = attrs
        txt = own_text(el)
        if txt:
            node["text"] = txt
        if children:
            node["content"] = children
        return node

    # -------- unified DFS --------
    def dfs(el, base):
        tag = el.root.tag.lower()

        # 1) drop excluded wrappers but keep their children
        if tag in EXCLUDE:
            kids = []
            for ch in el.xpath("./*"):
                _append(kids, dfs(ch, base))
            return kids or None

        # 2) always build children first
        children = []
        for ch in el.xpath("./*"):
            _append(children, dfs(ch, base))

        # 3) special handling when needed, but never block children
        if tag in NATIVE:
            if tag == "input" and el.attrib.get("type") not in {
                "button",
                "submit",
                "reset",
            }:
                # non-button inputs fall back to generic
                pass
            else:
                try:
                    return NATIVE[tag](el, base, children)
                except Exception as _:
                    # fall through to generic if a serializer fails
                    return serialize_generic(el, children)

        # 4) flatten trivial wrappers
        if tag in WRAPPERS:
            cls = el.attrib.get("class", "").strip()
            if not cls and not own_text(el) and len(children) == 1:
                return children[0]

        # 5) generic element
        return serialize_generic(el, children)
