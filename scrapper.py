# from pathlib import Path

from scrapy import Request
from scrapy.spiders import Spider
from scrapy_playwright.page import PageMethod


class Scrapper(Spider):
    name = "Chevy Silverado"
    start_urls = ["https://www.chevrolet.ca/en/trucks/silverado-1500"]

    custom_settings = {
        "ROBOTSTXT_OBEY": True,  # keep on unless you have permission
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
        "CONCURRENT_REQUESTS": 2,
        "LOG_LEVEL": "WARNING",
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-CA,en;q=0.9",
        },
        "USER_AGENT": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36",
    }

    async def start(self):
        for url in self.start_urls:
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

        # Check if playwright_page is available and close it
        if "playwright_page" in response.meta:
            page = response.meta["playwright_page"]
            page.close()

        metadata = self.extract_metadata(response)
        yield {"url": response.url, "metadata": metadata}

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
        og_meta["site_name"] = response.xpath('//meta[@name="og:site_name"]/@content').get()

        # Twitter metadata
        twitter_meta = {}
        twitter_meta["card"] = response.xpath('//meta[@name="twitter:card"]/@content').get()
        twitter_meta["site"] = response.xpath('//meta[@name="twitter:site"]/@content').get()

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
