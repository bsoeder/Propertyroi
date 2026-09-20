# PropertyROI convenience targets. Standard-library app; `ruff` is the only
# dev dependency. Override PORT/PROVIDER as needed, e.g. `make serve PORT=9000`.

PYTHON ?= python3
PORT ?= 8000
PROVIDER ?= json
IMAGE ?= propertyroi:latest

.PHONY: help install lint fmt test serve scan accuracy docker-build up down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the dev tooling (ruff)
	$(PYTHON) -m pip install --upgrade ruff

lint: ## Run the linter
	$(PYTHON) -m ruff check .

fmt: ## Auto-fix lint issues
	$(PYTHON) -m ruff check --fix .

test: ## Run the unit test suite
	$(PYTHON) -m unittest discover -s tests -v

serve: ## Run the web GUI locally (PORT, PROVIDER overridable)
	PROPERTYROI_PROVIDER=$(PROVIDER) $(PYTHON) -m propertyroi serve --port $(PORT)

scan: ## CLI scan of the sample data (ZIP=... to filter)
	$(PYTHON) -m propertyroi scan $(if $(ZIP),--zip $(ZIP),) --limit 10

accuracy: ## Run the accuracy tester on the labeled data
	$(PYTHON) -m propertyroi test --verbose

docker-build: ## Build the Docker image
	docker build -t $(IMAGE) .

up: ## Start the app with docker compose (http://localhost:8000)
	docker compose up --build

down: ## Stop docker compose
	docker compose down

clean: ## Remove caches and build artifacts
	rm -rf .ruff_cache .pytest_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
