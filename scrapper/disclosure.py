import html
import json
import os
from typing import Any, Dict

from scrapy import Request

from scrapper.scrapper import Scrapper


class DisclosureScrapper(Scrapper):
    """
    Scraper for Chevrolet disclosures JSON endpoint.

    Fetches the page body from
    https://www.chevrolet.ca/content/chevrolet/na/ca/en/index.disclosurespurejson.html
    which returns JSON (sometimes HTML-escaped). Cleans and converts it into a
    Python dictionary suitable for lookups.
    """

    @property
    def spider_name(self) -> str:
        return "disclosure_spider" + ("_DEV" if self.DEV_MODE else "_PROD")

    @property
    def local_url(self) -> str:
        # Not used for this spider (we always hit the remote JSON endpoint)
        # but provided to satisfy abstract contract.
        samples_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "samples"
        )
        return os.path.join(samples_dir, "disclosurespurejson.html")

    @property
    def prod_url(self) -> str:
        return "https://www.chevrolet.ca/content/chevrolet/na/ca/en/index.disclosurespurejson.html"

    async def request(self):
        """
        Override to always fetch the remote endpoint. The base implementation
        routes DEV to file:// which doesn't apply here since the endpoint is a
        pure JSON body hosted remotely.
        """
        url = self.prod_url
        self.logger.info(f"Fetching disclosures from: {url}")
        yield Request(url, callback=self.parse, dont_filter=True)

    def parse(self, response):
        """Parse the response body into a dictionary suitable for lookups."""
        raw_text = response.text or ""
        data = self.parse_body(raw_text)

        if not isinstance(data, dict):
            self.logger.warning("Disclosures endpoint did not return a JSON object.")
            yield {
                "url": response.url,
                "raw_text": raw_text,
                "parsed": data,
            }
            return

        yield {
            "url": response.url,
            "disclosures": data,
        }

    # -------------------- helpers --------------------
    def parse_body(self, raw: str) -> Any:
        """
        Clean and parse the endpoint body into Python structures.

        Handles HTML entities, common JSON escaping (e.g. \/), and non-breaking
        spaces (\u00a0/\xa0) that can appear in content payloads.
        """
        if not raw:
            return {}

        s = html.unescape(raw)
        s = s.replace("\\/", "/")
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            try:
                data = json.loads(s.replace("\u00a0", " ").replace("\xa0", " "))
            except json.JSONDecodeError:
                # As a last resort, return best-effort cleaned text
                return s

        # Ensure we return a dictionary for lookups; if it's a list, map indices
        if isinstance(data, list):
            return {str(i): v for i, v in enumerate(data)}

        return data
