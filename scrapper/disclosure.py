import html
import json
import os
from typing import Any

import click
from scrapy import Request
from scrapy.crawler import CrawlerProcess

from scrapper.scrapper import Scrapper
from utils.logger import Logger

logger = Logger(__name__).get_logger()


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
        # For disclosures, in DEV we rely on a projected local JSON file
        # placed under samples. Point to that JSON file.
        samples_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "samples"
        )
        return os.path.join(samples_dir, "disclosurespurejson.json")

    @property
    def prod_url(self) -> str:
        return "https://www.chevrolet.ca/content/chevrolet/na/ca/en/index.disclosurespurejson.html"

    def __init__(self, save_json_to: str | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._save_json_to = save_json_to

    async def start(self):
        """
        In DEV, load from the local projected JSON file so code can read it.
        In PROD, fetch from the remote endpoint and parse it.
        """
        if self.DEV_MODE:
            path = self.local_url
            file_url = f"file://{os.path.abspath(path)}"
            self.logger.info(f"DEV mode: loading disclosures from {file_url}")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw_text = f.read()
                data = self.parse_body(raw_text)
                if not isinstance(data, dict):
                    self.logger.warning(
                        "Local disclosures file did not contain a JSON object; emitting raw text."
                    )
                    yield {"url": file_url, "raw_text": raw_text, "parsed": data}
                else:
                    yield {"url": file_url, "disclosures": data}
            except FileNotFoundError:
                self.logger.warning(
                    f"Local disclosures file not found at {path}; emitting empty mapping."
                )
                yield {"url": file_url, "disclosures": {}}
        else:
            url = self.prod_url
            self.logger.info(f"Fetching disclosures from: {url}")
            yield Request(url, callback=self.parse, dont_filter=True)

    def parse(self, response):
        """Parse the response body into a dictionary suitable for lookups."""
        raw_text = response.text or ""
        data = self.parse_body(raw_text)

        # Optionally persist parsed JSON to a file (e.g., samples folder)
        if isinstance(data, dict) and self._save_json_to:
            try:
                out_path = self._save_json_to
                out_dir = os.path.dirname(os.path.abspath(out_path))
                os.makedirs(out_dir, exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.logger.info(f"Saved disclosures JSON to {out_path}")
            except Exception as e:
                self.logger.warning(f"Failed to save disclosures JSON: {e}")

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
    @staticmethod
    def parse_body(raw: str) -> Any:
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
                return s

        # Remove <p> and <sup> tags from content fields
        if isinstance(data, dict):
            for _, value in data.items():
                if isinstance(value, dict) and "content" in value:
                    content = value["content"]
                    if isinstance(content, str):
                        content = (
                            content.replace("<p>", "")
                            .replace("</p>", "")
                            .replace("<sup>", "")
                            .replace("</sup>", "")
                        )
                        value["content"] = content

        return data


def _default_samples_path(file_name: str = "disclosurespurejson.json") -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Use the module-level logger instance
    logger.info(f"repo root : {repo_root}")
    return os.path.join(repo_root, "samples", file_name)


def load_disclosures(
    dev_mode: bool | None = True,
    file_path: str | None = None,
    url: str | None = None,
    save_json_to: str | None = None,
) -> dict:
    """
    Load the disclosures as a Python dict for direct use in code.

    - In DEV (or when ``dev_mode=True``), read from the local projected JSON file
      under ``samples`` (or a provided ``file_path``).
    - In PROD (or when ``dev_mode=False``), fetch the remote endpoint and parse it.

    Args:
    - dev_mode: Force DEV/PROD behavior. If None, uses Scrapper.DEV_MODE.
    - file_path: Optional path to local disclosures JSON (DEV use).
    - url: Optional URL to fetch disclosures from (PROD use).
    - save_json_to: Optional path to save the resulting dict as JSON.

    Returns:
    - dict mapping disclosure keys to their content entries.
    """
    # Resolve mode
    if dev_mode is None:
        dev_mode = Scrapper.DEV_MODE

    # DEV: read local JSON file
    if dev_mode:
        path = file_path or _default_samples_path()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Local disclosures file did not contain a JSON object")
        return data

    endpoint = (
        url
        or "https://www.chevrolet.ca/content/chevrolet/na/ca/en/index.disclosurespurejson.html"
    )

    import ssl
    import urllib.request

    try:
        import certifi  # type: ignore

        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()

    with urllib.request.urlopen(endpoint, context=ctx) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data_any = DisclosureScrapper.parse_body(raw)
    if not isinstance(data_any, dict):
        raise ValueError("Disclosures endpoint did not return a JSON object")

    # Optionally persist the fetched JSON
    if save_json_to:
        out_dir = os.path.dirname(os.path.abspath(save_json_to))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(save_json_to, "w", encoding="utf-8") as f:
            json.dump(data_any, f, ensure_ascii=False, indent=2)

    return data_any


@click.command()
@click.option(
    "--save-json/--no-save-json",
    default=False,
    help="When set, persist parsed JSON to samples folder or provided path.",
)
@click.option(
    "--file-name",
    "-fn",
    default="disclosurespurejson.json",
    help="Set the filename",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=str),
    default=None,
    help="Optional output path for the saved JSON (defaults to samples/disclosurespurejson.json)",
)
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
    ),
    default=None,
    help="Set the logging level",
)
def main(save_json: bool, out: str | None, log_level: str | None, file_name: str):
    """Run the DisclosureScrapper spider.

    - If --save-json is provided, saves parsed JSON to samples (or --out).
    - Otherwise, emits items via Scrapy FEEDS (output_DEV/PROD.json).
    """
    Logger.configure(log_level=log_level.upper() if log_level else "CRITICAL")

    save_path = _default_samples_path(file_name) if (save_json and not out) else out

    settings = {}
    process = CrawlerProcess(settings=settings)
    process.crawl(DisclosureScrapper, save_json_to=save_path)
    process.start()


if __name__ == "__main__":
    main()
