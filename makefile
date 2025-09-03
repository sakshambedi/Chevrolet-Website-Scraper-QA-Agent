
.PHONY: run scrap scrapd embed embed-latest agent setup setup-and-run

scrap:
	python3 scrap.py

scrapd:
	python3 scrap.py -l INFO

embed:
	python3 -m embedding.chevy_embed --input output_DEV.json

# Build normalized graph from the most recent crawl output (output_*.json)
embed-latest:
	@set -e; \
	SRC=$$(ls -t output_*.json 2>/dev/null | head -n1); \
	if [ -z "$$SRC" ]; then \
		echo "No crawl outputs found (expected files matching output_*.json)." 1>&2; \
		echo "Run 'make scrapd' or 'python3 scrap.py --prod' first." 1>&2; \
		exit 1; \
	fi; \
	echo "Using latest crawl: $$SRC"; \
	python3 -m embedding.chevy_embed --input "$$SRC" --normalized-json output_embedding/embedding.json

agent:
	python3 agent.py

setup:
	python3 setup.py

setup-and-run:
	python3 setup.py --run-agent
