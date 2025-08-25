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

DEV = True

# DFS parsing configuration
EXCLUDE = {
    "script",
    "style",
    "noscript",
    "template",
    "gb-adv-grid",
    "gb-wrapper",
    "gb-responsive-image",
    "adv-col",
}

CONTAINERS = {
    "div",
    "section",
    "nav",
    "header",
    "footer",
    "main",
    "article",
    "aside",
    "serialize_gb_button",
    "gb-button",
    "picture",
}


# DFS parsing utility functions
def text_of(elem):
    """Extract cleaned text content from an element"""
    return " ".join(
        text for text in " ".join(elem.css("::text").getall()).strip().split()
    )


def parse_regional_info_json(raw):
    """Parse regional information JSON with error handling"""
    if not raw:
        return None
    s = html.unescape(raw).replace("\\/", "/")
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # try stripping NBSP; otherwise return the raw string
        try:
            return json.loads(s.replace("\u00a0", " ").replace("\xa0", " "))
        except json.JSONDecodeError:
            return s


def serialize_dynamic_text(elem, base):
    """Serialize gb-dynamic-text elements with regional pricing information"""
    regional_info_json = parse_regional_info_json(
        elem.attrib.get("regional-information-json")
    )
    txt = text_of(elem)
    return {
        "gb-dynamic-text": {
            "text": txt if txt else "",
            "class": elem.attrib.get("class", ""),
            "country": elem.attrib.get("country"),
            "regional_information": regional_info_json,
        }
    }


def serialize_heading(elem):
    """Serialize heading elements (h1-h6)"""
    parts = [t.strip() for t in elem.xpath("./text()").getall()]
    text = " ".join(p for p in parts if p)
    return {
        "heading": {
            "classes": elem.attrib.get("class", ""),
            "text": text,
        }
    }


def serialize_a(el, base):
    """Serialize anchor/link elements"""
    href = el.attrib.get("href")
    return {
        "a": {
            "text": text_of(el),
            "title": el.attrib.get("title", ""),
            "href": urljoin(base, href) if href else None,
            "link_type": ("internal" if is_internal_link(href) else "external"),
            "classes": el.attrib.get("class", ""),
            **({"type": el.attrib["type"]} if "type" in el.attrib else {}),
            **({"target": el.attrib.get("target")} if "target" in el.attrib else {}),
        }
    }


def serialize_picture_source(elem, base):
    """Serialize picture source elements"""
    src = elem.attrib.get("srcset")
    if src:
        srcs = [cl_s for ech_s in src.split(",") for cl_s in ech_s.strip().split("\n")]
    else:
        srcs = []

    return {
        "picture_source": {
            "media": elem.attrib.get("media"),
            "height": elem.attrib.get("height"),
            "width": elem.attrib.get("width"),
            "srcset": srcs,
            "link_type": ("internal" if is_internal_link(src) else "external"),
            "classes": elem.attrib.get("class", ""),
            "data_aspectratio": elem.attrib.get("data-aspectratio", "").split(",")
            if elem.attrib.get("data-aspectratio")
            else [],
        }
    }


def serialize_button(el, base):
    """Serialize button and input elements"""
    act = el.attrib.get("href") or el.attrib.get("formaction")
    full_url = urljoin(base, act) if act else None

    return {
        "button": {
            "text": text_of(el),
            "url": full_url,
            "flyout": el.attrib.get("flyout"),
            "data_dtm": el.attrib.get("data-dtm"),
            "data_dtm2": el.attrib.get("data-dtm2"),
            "link_type": ("internal" if is_internal_link(act) else "external")
            if act
            else "NA",
            "classname": el.attrib.get("class", ""),
            **({"type": el.attrib["type"]} if "type" in el.attrib else {}),
            **(
                {"disabled": "disabled"}
                if "disabled" in el.attrib or el.attrib.get("aria-disabled") == "true"
                else {}
            ),
            **({"title": el.attrib["title"]} if "title" in el.attrib else {}),
            **(
                {"data_hamburger_menu": el.attrib["data-hamburger-menu"]}
                if "data-hamburger-menu" in el.attrib
                else {}
            ),
            **(
                {"data_flyout_pagetitle": el.attrib["data-flyout-pagetitle"]}
                if "data-flyout-pagetitle" in el.attrib
                else {}
            ),
            **(
                {"aria-haspopup": el.attrib["aria-haspopup"]}
                if "aria-haspopup" in el.attrib
                else {}
            ),
            **(
                {"aria-expanded": el.attrib["aria-expanded"]}
                if "aria-expanded" in el.attrib
                else {}
            ),
        }
    }


def is_internal_link(link):
    """Check if a link is internal"""
    if link:
        return (
            True
            if link.startswith("/")
            or not any(
                link.startswith(prefix) for prefix in ("http://", "https://", "www.")
            )
            else False
        )
    return False


def serialize_image(el, base):
    """Serialize image elements"""
    src = el.attrib.get("src")
    return {
        "img": {
            "src": urljoin(base, src) if src else None,
            "classes": el.attrib.get("class", ""),
            "alt": el.attrib.get("alt"),
            "title": el.attrib.get("title"),
            "link_type": ("internal" if is_internal_link(src) else "external"),
            **({"imwidth": el.attrib.get("imwidth")} if "imwidth" in el.attrib else {}),
            **({"loading": el.attrib.get("loading")} if "loading" in el.attrib else {}),
        }
    }


# Mapping of HTML tags to their serialization functions
NATIVE = {
    "a": serialize_a,
    "button": serialize_button,
    "input": serialize_button,  # handles type=button/submit/reset
    "img": serialize_image,
    "source": serialize_picture_source,
    "gb-dynamic-text": serialize_dynamic_text,
}


def dfs(el, base):
    """
    Depth-First Search parsing of HTML elements into structured JSON
    """
    tag = el.root.tag.lower()

    # Skip excluded elements but process their children
    if tag in EXCLUDE:
        kids = []
        for ch in el.xpath("./*"):
            node = dfs(ch, base)
            if node is not None:
                kids.append(node)
        return kids if kids else None

    # Handle native elements with specific serializers
    if tag in NATIVE:
        # Gate inputs to button-like only
        if tag == "input" and el.attrib.get("type") not in {
            "button",
            "submit",
            "reset",
        }:
            pass
        else:
            return NATIVE[tag](el, base)

    # Handle lists
    if tag == "ul":
        items = []
        for li in el.xpath("./li"):
            node = dfs(li, base)
            if node is not None:
                items.append(node)
        return {"ul": items} if items else None

    if tag == "li":
        kids = []
        for ch in el.xpath("./*"):
            node = dfs(ch, base)
            if node is not None:
                kids.append(node)
        return (
            {"li": {"text": text_of(el), "content": kids}}
            if (kids or text_of(el))
            else None
        )

    # Handle container elements
    if tag in CONTAINERS:
        kids = []
        for ch in el.xpath("./*"):
            node = dfs(ch, base)
            if node is not None:
                kids.append(node)
        classname = el.attrib.get("class", "")

        # Optional wrapper collapse: if no class and one child, return the child
        if not classname and len(kids) == 1:
            return kids[0]

        result = {
            "type": tag,
            "class": classname,
            "content": kids,
        }

        # Include common attributes if present
        for attr in [
            "data-hamburger-menu",
            "data-province-selector-enabled",
            "role",
            "aria-hidden",
            "aria-label",
            "flyout-id",
            "close-button-label",
        ]:
            if attr in el.attrib:
                result[attr] = el.attrib[attr]
        return result

    # Handle headings and paragraphs
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return {tag: serialize_heading(el)}
    if tag == "p":
        txt = text_of(el)
        return {"p": txt} if txt else None

    # Fallback for generic elements with children
    kids = []
    for ch in el.xpath("./*"):
        node = dfs(ch, base)
        if node is not None:
            kids.append(node)
    txt = text_of(el)
    if kids or txt:
        return {"tag": tag, "components": kids}
    return None


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
        parsed_body = self.dfs_parse_body(response)

        # Yield the complete parsed data with DFS results
        yield {
            "url": response.url,
            "metadata": metadata,
            "body_content": parsed_body,
            "parsing_method": "dfs_enhanced",
        }

    def dfs_parse_body(self, body_html, base_url="https://www.chevrolet.ca/"):
        """
        Parse HTML body using DFS (Depth-First Search) algorithm
        This method extracts structured data from the complete HTML structure
        """
        selector = Selector(text=body_html)

        # Find the main navigation structure (gb-global-nav)
        nav_elements = selector.xpath(
            "//gb-global-nav/template[@id='gb-global-nav-content']"
        )

        if nav_elements:
            output = dfs(nav_elements)

            return {
                "navigation": output,
                # "main_content": content_tree,
                # "parsing_method": "dfs",
            }
        else:
            # Fallback: parse main content only
            main_content = selector.xpath("//main | //body")
            if main_content:
                content_tree = []
                for element in main_content[0].xpath("./*"):
                    parsed_element = dfs(element, base_url)
                    if parsed_element:
                        content_tree.append(parsed_element)

                return {"main_content": content_tree, "parsing_method": "dfs_fallback"}

            return {"error": "No parseable content found", "parsing_method": "dfs"}

    def semantic_parse_body(self, body_html):
        """
        Legacy semantic parsing method - kept for compatibility
        Use dfs_parse_body for better results
        """
        sel = Selector(text=body_html)
        grids = sel.css("gb-adv-grid")

        # print(grids)
        sections = []
        for grid in grids:
            section = {}
            # Extract main heading
            heading = grid.css(
                "h1::text, h2::text, h3::text, h4::text, h5::text, h6::text"
            ).get()
            if heading:
                section["heading"] = " ".join(
                    h.strip() for h in heading.strip().split("\n")
                )

            links = []
            for a in grid.css("a"):
                href = a.attrib.get("href")
                # text = a.css("::text").get()
                text = a.attrib.get("data-dtm2")
                data_link_type = a.attrib.get("data-link-type")
                data_dtm = a.attrib.get("data-dtm")

                if href and text and data_link_type:
                    links.append(
                        {
                            "href": href,
                            "link_type": data_link_type,
                            "text": text.strip(),
                            "data_dtm": data_dtm,
                        }
                    )
            if links:
                section["links"] = links
            # Extract other content as needed (images, lists, etc.)
            # Example: images
            images = []
            for img in grid.css("img"):
                src = img.attrib.get("src")
                alt = img.attrib.get("alt")
                if src:
                    images.append({"src": src, "alt": alt})
            if images:
                section["images"] = images
            sections.append(section)
        return sections

    def get_body(self, response):
        """Extract and parse body content using DFS algorithm"""
        body_html = response.css("body").get()

        # Use the new DFS parsing method
        dfs_parsed_content = self.dfs_parse_body(body_html, response.url)

        # Also keep legacy parsing for comparison (optional)
        semantic_sections = self.semantic_parse_body(body_html)

        # Build final output with DFS results
        final_output = {
            "url": response.url,
            "dfs_content": dfs_parsed_content,
            "legacy_sections": semantic_sections,  # Keep for comparison
            "parsing_timestamp": json.dumps({}, default=str),  # For debugging
        }

        # Save the DFS parsed content
        with open("dfs_scrapy_output.json", "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=2, ensure_ascii=False)

        self.logger.info(
            "✅ DFS parsing completed. Results saved to dfs_scrapy_output.json"
        )

        return final_output

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
