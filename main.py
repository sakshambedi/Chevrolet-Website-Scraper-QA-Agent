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
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False),
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
def main(save_html, log_level, dev) -> None:
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

    process = CrawlerProcess(settings={})
    process.crawl(ChevyScapper, disclosures=disclosures, save_html=save_html)
    process.start()


if __name__ == "__main__":
    main()
