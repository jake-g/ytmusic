# Detect Python and virtualenv tools
ifeq ($(OS),Windows_NT)
    PYTHON = python
    AUTOPEP8 = autopep8
    ISORT = isort
    PRE_COMMIT = pre-commit
else
    VENV_BIN = $(wildcard ../.venv/bin)
    ifneq ($(VENV_BIN),)
        PYTHON = $(VENV_BIN)/python3
        AUTOPEP8 = $(VENV_BIN)/autopep8
        ISORT = $(VENV_BIN)/isort
        PRE_COMMIT = $(VENV_BIN)/pre-commit
    else
        PYTHON = python3
        AUTOPEP8 = autopep8
        ISORT = isort
        PRE_COMMIT = pre-commit
    endif
endif

.PHONY: help run run-no-backup analytics test format auth auth-update clean commit-playlists

# Default target
help:
	@echo "========================================================="
	@echo "YTMusic Library Automation Console"
	@echo "========================================================="
	@echo "Available commands:"
	@echo "  make run              - Run the full library backup (logged to file)"
	@echo "  make run-no-backup    - Run backup skipping playlist downloads"
	@echo "  make test             - Run the unit test suite"
	@echo "  make format           - Format python files using AUTOPEP8 & ISORT"
	@echo "  make auth-update      - Update browser auth credentials (browser.json)"
	@echo "  make commit-playlists - Git commit updated playlists and logs"
	@echo "  make clean            - Clean up log files, pycache, and temp files"
	@echo "========================================================="

run:
	@echo "Starting YTMusic Library Backup..."
	@$(PYTHON) ytmusic_library.py

run-no-backup:
	@echo "Starting YTMusic Library Backup (skipping playlist backups)..."
	@$(PYTHON) ytmusic_library.py --skip-backup

analytics:
	@echo "Running YTMusic Analytics..."
	@$(PYTHON) ../music-sources-unified/analytics.py --variant ytmusic


test:
	@echo "Running Unit Tests..."
	@$(PYTHON) ytmusic_library_test.py

format:
	@echo "Formatting code with AUTOPEP8 & ISORT (2-space indent)..."
	-@$(AUTOPEP8) -i --indent-size=2 ytmusic_library.py ytmusic_library_test.py
	-@$(ISORT) --profile google ytmusic_library.py ytmusic_library_test.py
	@echo "Running pre-commit validation..."
	-@$(PRE_COMMIT) run --all-files
	@echo "Formatting completed!"

auth: auth-update

auth-update:
	@echo "Launching browser credentials update..."
	@$(PYTHON) browser_auth_update.py

commit-playlists:
	@echo "Committing playlists and logs..."
	-git add playlists/*.tsv
	-git add *.log
	-git commit -m "update ytmusic playlists"

clean:
	@echo "Cleaning up temporary files, caches, and logs..."
	@$(PYTHON) -c "import os, shutil; [os.remove(f) for f in os.listdir('.') if f.endswith('.log')]; [shutil.rmtree(d) for d in ['__pycache__', '.pytest_cache'] if os.path.exists(d)]"
	@echo "Clean completed!"
