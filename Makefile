.PHONY: install verify test demo clean

PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
PYTEST ?= .venv/bin/pytest
FLASHFRAME ?= .venv/bin/flashframe

.venv:
	python3 -m venv .venv

install: .venv
	$(PIP) install -e ".[dev]"

test: install
	$(PYTEST) -q

demo: install
	$(FLASHFRAME) demo --outdir evidence

verify: test demo
	@echo "verify ok"

clean:
	rm -rf .venv .pytest_cache src/*.egg-info *.egg-info evidence/demo_* evidence/roundtrip.json
