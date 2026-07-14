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

setup:
	uv sync --no-dev --extra analyze

setup-dev:
	uv sync --all-extras

export:
	uv run --no-sync lar-export-php-deploy --config $(CONFIG) --outdir $(DEPLOY)

export-force:
	uv run --no-sync lar-export-php-deploy --config $(CONFIG) --outdir $(DEPLOY) --overwrite

export-copy:
	uv run --no-sync lar-export-php-deploy --config $(CONFIG) --outdir $(DEPLOY) --copy-audio

export-copy-force:
	uv run --no-sync lar-export-php-deploy --config $(CONFIG) --outdir $(DEPLOY) --overwrite --copy-audio

serve:
	LISTEN_AND_RATE_CONFIG=$(CONFIG) uv run --no-sync uvicorn $(PROJECT).main:app --host $(HOST) --port $(PORT)

report:
	uv run --no-sync lar-analyze-results --config $(CONFIG) $(if $(REPORT_CONFIG),--report-config $(REPORT_CONFIG)) $(if $(DEPLOY),--root $(DEPLOY))

lint: tool
	uv run --no-sync ruff check $(PROJECT) tests
	uv run --no-sync ruff format --check $(PROJECT) tests
	uv run --no-sync pyright $(PROJECT)
	uv run --no-sync djlint --check frontend/*.html
	uv run --no-sync mdformat --check *.md
	(cd frontend && ../$(BIOME) check .)
	$(PINACT) run --check .github/workflows/*.yaml
	$(TAPLO) format --check pyproject.toml
	$(YAMLFMT) --lint examples .yamlfmt.yaml .github/workflows/*.yaml
	php $(PHP_CS_FIXER) check --config frontend/.php-cs-fixer.php --no-ansi

format: tool
	uv run --no-sync ruff check --fix $(PROJECT) tests
	uv run --no-sync ruff format $(PROJECT) tests
	uv run --no-sync djlint --reformat frontend/*.html
	uv run --no-sync mdformat *.md
	(cd frontend && ../$(BIOME) format --write .)
	$(PINACT) run -u --min-age 14 .github/workflows/*.yaml
	$(TAPLO) format pyproject.toml
	$(YAMLFMT) examples .yamlfmt.yaml .github/workflows/*.yaml
	php $(PHP_CS_FIXER) fix --config frontend/.php-cs-fixer.php --no-ansi

test: tool
	uv run --no-sync pytest -s -x
	php $(PHPUNIT) --configuration frontend/phpunit.xml

tool:
	$(MAKE) -C tools

tool-clean:
	$(MAKE) -C tools clean

clean: tool-clean
	rm -rf .venv

.PHONY: setup setup-dev export export-force export-copy export-copy-force serve report lint format test tool tool-clean clean
