
.PHONY: run scrap scrapd embed agent setup

scrap:
	python scrap.py

scrapd:
	python scrap.py -l INFO

embed:
	python -m embedding.chevy_embed --input output_DEV.json

agent:
	python agent.py

setup:
	python setup.py

setup-and-run:
	python setup.py --run-agent
