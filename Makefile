.PHONY: all clean install install-dev run lint test

VENV = venv
PYTHON = $(VENV)/bin/python3
PIP = $(VENV)/bin/pip

all: run

install:
	@echo "Creating Python virtual environment and installing runtime dependencies..."
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PYTHON) -m playwright install chromium

install-dev: install
	$(PIP) install -r requirements-dev.txt

run:
	@echo "Starting HiveCenter (see hive_app.py)..."
	./start.sh

lint:
	@echo "Running flake8 (syntax / undefined names)..."
	$(PIP) install flake8
	$(VENV)/bin/flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

test:
	@test -f $(PYTHON) || (echo "Run 'make install' or 'make install-dev' first." && exit 1)
	$(PIP) install -q -r requirements-dev.txt
	$(PYTHON) -m pytest tests/ -q

clean:
	@echo "🔥 Immolating Cache & pycache..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf $(VENV) .chrome_app_data
