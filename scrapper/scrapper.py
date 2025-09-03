import datetime
import os
from abc import ABC, abstractmethod

from scrapy import Request
from scrapy.spiders import Spider
from scrapy_playwright.page import PageMethod


class Scrapper(Spider, ABC):
    """
    Abstract base class for web scrapers.
    Provides common functionality for scraping websites with optional Playwright support.
    """

    chevy_website = "https://www.chevrolet.ca"

    # Logging is configured at the application entrypoint; Scrapy's
    # LOG_LEVEL is passed via CrawlerProcess(settings=...).

    @classmethod
    def settings_for_mode(cls, dev_mode: bool) -> dict:
        """Return Scrapy settings for the requested mode (DEV or PROD)."""
        settings: dict = {
            "FEEDS": {
                f"output_{'DEV' if dev_mode else 'PROD'}.json": {
                    "format": "json",
                    "overwrite": True,
                }
            },
            "ROBOTSTXT_OBEY": True,
            "DEFAULT_REQUEST_HEADERS": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-CA,en;q=0.9",
            },
            "USER_AGENT": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
        }
        if not dev_mode:
            settings.update(
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
        return settings

    @property
    @abstractmethod
    def spider_name(self) -> str:
        """Spider name - must be implemented by child classes"""
        pass

    @property
    @abstractmethod
    def local_url(self) -> str:
        """Local development URL - must be implemented by child classes"""
        pass

    @property
    @abstractmethod
    def prod_url(self) -> str:
        """Production URL - must be implemented by child classes"""
        pass

    def __init__(self, save_html: bool = False, dev_mode: bool | None = None, *args, **kwargs):
        # Determine mode per-instance
        if dev_mode is None:
            dev_mode = os.getenv("DEV", "false").lower() == "true"
        self.dev_mode = bool(dev_mode)

        # Set spider name based on mode before calling super().__init__
        if not hasattr(self, "name"):
            self.name = self.spider_name

        self.save_html = save_html
        super().__init__(*args, **kwargs)

    @property
    def start_urls(self):
        """Get the list of URLs to start crawling from"""
        return [self.local_url] if self.dev_mode else [self.prod_url]

    async def start(self):
        """Generate initial requests (supports local files in DEV)."""
        self.logger.info("Starting requests")
        for url in self.start_urls:
            if self.dev_mode:
                file_url = f"file://{os.path.abspath(url)}"
                self.logger.info(f"Using local file: {file_url}")
                yield Request(file_url, callback=self.parse)
            else:
                yield Request(
                    url,
                    callback=self.parse,
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

    def save_response_html(self, response, url):
        """Save HTML content to samples directory."""
        if not self.save_html:
            return

        # Create filename based on URL
        url_parts = url.split("/")
        filename = url_parts[-1] if url_parts[-1] else url_parts[-2]

        # If it doesn't have .html extension, add it
        if not filename.endswith(".html"):
            filename = f"{filename}.html"

        # Add timestamp to avoid overwriting
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename.split('.')[0]}_{timestamp}.html"

        # Get path to samples directory
        samples_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples"
        )

        # Create samples directory if it doesn't exist
        if not os.path.exists(samples_dir):
            os.makedirs(samples_dir)

        # Full path to save the file
        file_path = os.path.join(samples_dir, filename)

        # Save the HTML content
        with open(file_path, "wb") as f:
            f.write(response.body)

        self.logger.info(f"Saved HTML content to {file_path}")
        return file_path

    @abstractmethod
    def parse(self, response):
        """Main parsing method - can be overridden by child classes"""
        pass

    def parse_body(self, response):
        """Parse body content - must be implemented by child classes"""
        pass

    def extract_metadata(self, response):
        """Extract common metadata from response"""
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
            '//meta[@property="og:site_name" or @name="og:site_name"]/@content'
        ).get()

        # Twitter metadata
        twitter_meta = {}
        twitter_meta["card"] = response.xpath(
            '//meta[@name="twitter:card"]/@content'
        ).get()
        twitter_meta["site"] = response.xpath(
            '//meta[@name="twitter:site"]/@content'
        ).get()

        lang = response.xpath("//html/@lang").get()
        template = response.xpath('//meta[@name="template"]/@content').get()
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
