import os

import click
from scrapy.crawler import CrawlerProcess

from scrapper.chevy_scrapper import ChevyScapper
from scrapper.disclosure import load_disclosures
from utils.logger import Logger

logger = Logger(__name__).get_logger()


@click.command()
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
    ),
    default="CRITICAL",
    help="Set the logging level",
)
@click.option(
    "--save-html/--no-save-html",
    "-s/ ",
    is_flag=True,
    default=False,
    help="When set, save fetched HTML to the samples folder",
)
@click.option(
    "--dev/--prod",
    default=True,
    help="Run in DEV mode (use local files) or PROD mode (fetch live site)",
)
@click.option(
    "--url",
    type=str,
    default=None,
    help="Optional single Chevrolet vehicle URL to crawl (overrides default).",
)
@click.option(
    "--discover-vehicles",
    is_flag=True,
    default=False,
    help="Discover vehicle URLs from the Chevrolet simplified nav and crawl them.",
)
@click.option(
    "--category",
    type=click.Choice(
        ["all", "cars", "trucks", "crossovers-suvs", "electric", "performance"],
        case_sensitive=False,
    ),
    default="all",
    help="Optional filter when discovering vehicles.",
)
def main(save_html, log_level, dev, url, discover_vehicles, category) -> None:
    """Entry point that calls the Click CLI."""
    Logger.configure(log_level=log_level.upper())

    # Set mode explicitly (used for external helpers), but spider now reads mode dynamically
    os.environ["DEV"] = "true" if dev else "false"
    logger.info(f"Mode: {'DEV' if dev else 'PROD'}")

    logger.info(f"Save html : {save_html}")

    disclosures = None
    try:
        disclosures = load_disclosures(dev_mode=dev)
        if disclosures is not None:
            logger.info(f"Loaded disclosures entries: {len(disclosures)}")
    except Exception as e:
        logger.warning(f"Failed to load disclosures: {e}")

    # Optional: collect seed URLs
    seed_urls = None
    if url:
        seed_urls = [url]
        logger.info(f"Using single URL: {url}")

    if discover_vehicles:
        import re
        import ssl
        import urllib.request

        endpoint = (
            "https://www.chevrolet.ca/content/chevrolet/na/ca/en/portablenavigation/"
            "simplified-nav/primary-navigation/vehicles/vehicles.html"
        )
        logger.info(f"Discovering vehicles from: {endpoint}")
        try:
            try:
                import certifi  # type: ignore

                ctx = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                ctx = ssl.create_default_context()

            with urllib.request.urlopen(endpoint, context=ctx) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            raise click.ClickException(f"Failed to fetch vehicles menu: {e}")

        # Extract model links heuristically
        hrefs = set(
            m.group(1)
            for m in re.finditer(
                r"href=\"(https://www\.chevrolet\.ca/en/[^']+)\'", html
            )
        )
        # Keep canonical vehicle pages (exclude nav/tool links)
        cats = {
            "all": [
                "/en/trucks/",
                "/en/crossovers-suvs/",
                "/en/electric/",
                "/en/cars/",
                "/en/performance/",
            ],
            "cars": ["/en/cars/"],
            "trucks": ["/en/trucks/"],
            "crossovers-suvs": ["/en/crossovers-suvs/"],
            "electric": ["/en/electric/"],
            "performance": ["/en/performance/"],
        }
        keep_prefixes = tuple(cats.get(category.lower(), cats["all"]))
        seeds = []
        for h in hrefs:
            try:
                path = "/" + h.split(".ca", 1)[1].split("?", 1)[0]
            except Exception:
                continue
            if any(path.startswith(pref) for pref in keep_prefixes):
                seeds.append(h)
        seeds = sorted(dict.fromkeys(seeds))
        logger.info(f"Discovered {len(seeds)} vehicle URLs (category={category})")
        seed_urls = (seed_urls or []) + seeds

    # Build Scrapy settings for the requested mode
    from scrapper.scrapper import Scrapper

    settings = Scrapper.settings_for_mode(dev_mode=dev)
    settings["LOG_LEVEL"] = log_level.upper()
    process = CrawlerProcess(settings=settings)
    process.crawl(
        ChevyScapper,
        disclosures=disclosures,
        save_html=save_html,
        seed_urls=seed_urls,
        dev_mode=dev,
    )
    process.start()


if __name__ == "__main__":
    main()
