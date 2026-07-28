.PHONY: check clean clean-build clean-pyc clean-test coverage install pylint pylint-quick pyre test publish poetry-check publish isort isort-check


VERSION := `cat VERSION`
package := "src/pdfserve"
packagename := "pdfserve"

help:
	@echo "clean - remove all build, test, coverage and Python artifacts"
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "clean-test - remove test and coverage artifacts"
	@echo "lint - check style with flake8"
	@echo "test - run tests quickly with the default Python"
	@echo "test-all - run tests on every Python version with tox"
	@echo "coverage - check code coverage quickly with the default Python"
	@echo "docs - generate Sphinx HTML documentation, including API docs"
	@echo "release - package and upload a release"
	@echo "dist - package"
	@echo "install - install the package to the active Python's site-packages"

clean: clean-build clean-pyc clean-test

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name 'flycheck_*' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +
	find . -name '.mypy_cache' -exec rm -fr {} +
	find . -name '.pyre' -exec rm -fr {} +

clean-test:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -f coverage.xml
	rm -f report.xml
test:
	PDFSERVE_CONFIG=tests/data/test_config.yaml uv run py.test --cov=$(package) --verbose tests --cov-report=html --cov-report=term --cov-report xml:coverage.xml --cov-report=term-missing --junitxml=report.xml --asyncio-mode=auto

coverage:
	poetry run coverage run --source $(package) setup.py test
	poetry run coverage report -m
	poetry run coverage html
	$(BROWSER) htmlcov/index.html

install: clean
	uv install

pylint-quick:
	uv run pylint --rcfile=.pylintrc $(package)  -E -r y

pylint:
	uv run pylint --rcfile=".pylintrc" $(package)


lint: format-test isort-check ruff uv-check
small-check: format-test isort-check uv-check
check: lint

pyre: pyre-check


pyre-check:
	uv run pyre --noninteractive check 2>/dev/null

format:
	uv run ruff format $(package)

format-test:
	uv run ruff format $(package) --check

uv-check:
	uv lock --locked --offline

publish: clean
	uv build
	uv publish

isort:
	uv run isort .
	uv run ruff check --select I $(package) tests --fix

isort-check:
	uv run ruff check --select I $(package) tests
	uv run isort --diff --check .

ruff:
	uv run ruff check

fix: format isort
	uv run ruff check --fix

.ONESHELL:
pyrightconfig:
	jq \
      --null-input \
      --arg venv "$$(basename $$(uv env info -p))" \
      --arg venvPath "$$(dirname $$(uv env info -p))" \
      '{ "venv": $$venv, "venvPath": $$venvPath }' \
      > pyrightconfig.json

rename:
	ack pdfs -l | xargs -i{} sed -r -i "s/pdfserve/pdfserve/g" {}
	ack Pdfs -i -l | xargs -i{} sed -r -i "s/Pdfs/PDFServe/g" {}
	ack Pdfs -i -l | xargs -i{} sed -r -i "s/PDFS/PDFSERVE/g" {}

run-server:
	./bin/pdfserve server --config localconfig.yaml


CONTAINER_REGISTRY=ghcr.io/ant31/$(packagemame)


docker-push-local: docker-build-local
	docker push $(CONTAINER_REGISTRY):latest

docker-build-local:
	docker build --network=host -t $(CONTAINER_REGISTRY):latest .

docker-push:
	docker buildx build --push -t $(CONTAINER_REGISTRY):latest .

BUMP ?= patch
bump:
	uv run bump-my-version bump $(BUMP)


upgrade-dep:
	uv sync --upgrade
	uv lock -U --resolution=highest
