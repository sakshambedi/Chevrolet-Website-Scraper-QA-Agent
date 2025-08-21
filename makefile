website=https://www.chevrolet.ca/en/trucks/silverado-1500

phony: run

run :
	python main.py -w $(website)


run-debug:
	python main.py -w $(website) -l INFO
