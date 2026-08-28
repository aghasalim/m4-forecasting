.PHONY: setup test data backtest figures
PY := .venv/bin/python

setup:
	python3.12 -m venv .venv && .venv/bin/pip install -U pip -r requirements.txt pytest

data:            ## fetch M4 Hourly + Weekly from the public repo
	$(PY) -m src.fc.fetch

test:
	$(PY) -m pytest tests/ -q

backtest:        ## points and intervals on M4's own holdout
	$(PY) -m src.fc.backtest

figures:         ## redraw the README figures from the committed reports/
	$(PY) scripts/make_figures.py
