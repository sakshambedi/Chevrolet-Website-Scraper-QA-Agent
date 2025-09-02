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
    "--save-html",
    "-s",
    type=click.Choice([True, False], case_sensitive=False),
    default=False,
    help="If you want to save the html from the website",
)
@click.option(
    "--dev/--prod",
    default=True,
    help="Run in DEV mode (use local files) or PROD mode (fetch live site)",
)
@click.option(
    "--urls-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Optional file with JSON array of vehicle URLs to crawl.",
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
def main(save_html, log_level, dev, urls_file, discover_vehicles, category) -> None:
    """Entry point that calls the Click CLI."""
    Logger.configure(log_level=log_level.upper())

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
    if urls_file:
        import json

        with open(urls_file, "r", encoding="utf-8") as f:
            arr = json.load(f)
        if not isinstance(arr, list):
            raise click.ClickException("--urls-file must contain a JSON array of URLs")
        seed_urls = [str(u) for u in arr if isinstance(u, str)]
        logger.info(f"Loaded {len(seed_urls)} URLs from file")

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

    process = CrawlerProcess(
        settings={
            "LOG_LEVEL": log_level.upper(),
        }
    )
    process.crawl(
        ChevyScapper,
        disclosures=disclosures,
        save_html=save_html,
        seed_urls=seed_urls,
    )
    process.start()


if __name__ == "__main__":
    main()
