import click
from scrapy.crawler import CrawlerProcess

from scrapper import Scrapper
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
    "--website", "-w", required=True, multiple=True, help="list all the website you want to scrape"
)
@click.option(
    "--save-html",
    "-s",
    type=click.Choice([True, False], case_sensitive=False),
    default=False,
    help="If you want to save the html from the website",
)
def main(website, save_html, log_level) -> None:
    """Entry point that calls the Click CLI."""
    Logger.configure(log_level=log_level.upper() if log_level is not None else "CRITICAL")
    logger.info("debug mode is on ")

    if len(website) == 1 and "," in website[0]:
        website_list = website[0].split(",")
    else:
        website_list = list(website)
    logger.info(f"website list: {website_list}")
    logger.info(f"Save html : {save_html}")

    # now lets work on the cleaning the scrapped part of the html
    #
    #
    process = CrawlerProcess(
        settings={
            "FEEDS": {"output.json": {"format": "json", "overwrite": True}},
        }
    )
    process.crawl(Scrapper)
    process.start()


if __name__ == "__main__":
    main()
