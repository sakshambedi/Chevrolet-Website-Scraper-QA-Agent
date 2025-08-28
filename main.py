import os

import click
from dotenv import load_dotenv
from scrapy.crawler import CrawlerProcess

from scrapper.chevy_scrapper import ChevyScapper
from utils.logger import Logger

logger = Logger(__name__).get_logger()


@click.command()
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False),
    default=None,
    help="Set the logging level",
)
@click.option(
    "--save-html",
    "-s",
    type=click.Choice([True, False], case_sensitive=False),
    default=False,
    help="If you want to save the html from the website",
)
def main(save_html, log_level) -> None:
    """Entry point that calls the Click CLI."""
    Logger.configure(log_level=log_level.upper() if log_level is not None else "CRITICAL")
    logger.info("debug mode is on ")

    logger.info(f"Save html : {save_html}")

    # Load environment variables
    load_dotenv()
    DEV_MODE = os.getenv("DEV", "False").lower() == "true"

    # Since we've defined all settings in the Scrapper class, we can use an empty dict here
    # The Spider's custom_settings will be applied automatically
    process = CrawlerProcess(settings={})
    process.crawl(ChevyScapper)
    process.start()


if __name__ == "__main__":
    main()
