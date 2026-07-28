PROJECT := listen_and_rate

CONFIG        := examples/config.mos.yaml
REPORT_CONFIG := examples/report-config.yaml

DEPLOY  :=
HOST    := 0.0.0.0
PORT    := 8000

BIOME        := tools/biome/biome
PHP_CS_FIXER := tools/php-cs-fixer/php-cs-fixer.phar
PHPUNIT      := tools/phpunit/phpunit.phar
PINACT       := tools/pinact/pinact
TAPLO        := tools/taplo/taplo
YAMLFMT      := tools/yamlfmt/yamlfmt

.DEFAULT_GOAL := setup-dev

.PHONY: setup
setup:
	uv sync --no-dev --extra analyze

.PHONY: setup-dev
setup-dev:
	uv sync --all-extras

.PHONY: export
export:
	uv run --no-sync lar-export --config $(CONFIG) --outdir $(DEPLOY)

.PHONY: export-force
export-force:
	uv run --no-sync lar-export --config $(CONFIG) --outdir $(DEPLOY) --overwrite

.PHONY: export-copy
export-copy:
	uv run --no-sync lar-export --config $(CONFIG) --outdir $(DEPLOY) --copy-audio

.PHONY: export-copy-force
export-copy-force:
	uv run --no-sync lar-export --config $(CONFIG) --outdir $(DEPLOY) --overwrite --copy-audio

.PHONY: serve
serve:
	LISTEN_AND_RATE_CONFIG=$(CONFIG) uv run --no-sync uvicorn $(PROJECT).main:app --host $(HOST) --port $(PORT)

.PHONY: report
report:
	uv run --no-sync lar-report --config $(CONFIG) $(if $(REPORT_CONFIG),--report-config $(REPORT_CONFIG)) $(if $(DEPLOY),--root $(DEPLOY))

.PHONY: examples
examples:
	uv run --no-sync python scripts/generate_examples.py

.PHONY: screenshots
screenshots:
	uv run --no-sync playwright install chromium
	uv run --no-sync python scripts/capture_screenshots.py

.PHONY: lint
lint: tool
	uv run --no-sync python scripts/generate_examples.py --check
	uv run --no-sync ruff check $(PROJECT) scripts tests
	uv run --no-sync ruff format --check $(PROJECT) scripts tests
	uv run --no-sync pyright $(PROJECT) scripts
	uv run --no-sync djlint --check frontend/*.html
	uv run --no-sync mdformat --check *.md
	(cd frontend && ../$(BIOME) check .)
	(cd frontend && php ../$(PHP_CS_FIXER) check --config .php-cs-fixer.php --no-ansi)
	$(PINACT) run --check .github/*/*.yaml
	$(TAPLO) format --check pyproject.toml
	$(YAMLFMT) --lint scripts/examples examples .yamlfmt.yaml .github/*/*.yaml

.PHONY: format
format: tool
	uv run --no-sync ruff check --fix $(PROJECT) scripts tests
	uv run --no-sync ruff format $(PROJECT) scripts tests
	uv run --no-sync djlint --reformat frontend/*.html
	uv run --no-sync mdformat *.md
	(cd frontend && ../$(BIOME) format --write .)
	(cd frontend && php ../$(PHP_CS_FIXER) fix --config .php-cs-fixer.php --no-ansi)
	$(PINACT) run -u --min-age 14 .github/*/*.yaml
	$(TAPLO) format pyproject.toml
	$(YAMLFMT) scripts/examples examples .yamlfmt.yaml .github/*/*.yaml

.PHONY: test
test: tool
	uv run --no-sync pytest -s -x
	php $(PHPUNIT) --configuration frontend/phpunit.xml

.PHONY: tool
tool:
	$(MAKE) -C tools

.PHONY: tool-clean
tool-clean:
	$(MAKE) -C tools clean

.PHONY: clean
clean: tool-clean
	rm -rf .venv
