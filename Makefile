# Hamburg working-student job market dashboard
PYTHON ?= python3

.PHONY: all install collect build export history test serve check-privacy clean-exports rag-install rag-index lint

all: collect build export          ## full pipeline including API calls

install:                           ## install Python dependencies
	$(PYTHON) -m pip install -r requirements.txt

collect:                           ## fetch postings from the Jobsuche API
	$(PYTHON) -m src.collect

build:                             ## clean + skills + load into SQLite
	$(PYTHON) -m src.db

export:                            ## run SQL queries and write docs/data/*.json
	$(PYTHON) -m src.analyse

history:                           ## rebuild data/history.db like CI does (no ad texts)
	JOBS_DATABASE=data/history.db KEEP_DESCRIPTIONS=false $(PYTHON) run.py --skip-collect

rag-install:                       ## install the RAG assistant dependencies
	$(PYTHON) -m pip install -r requirements-rag.txt

rag-index:                         ## build/update data/rag_index.db (incremental)
	$(PYTHON) -m rag.index

lint:                              ## ruff on the RAG code
	$(PYTHON) -m ruff check rag tests/rag

test:                              ## run the test suite
	$(PYTHON) -m pytest -q

serve:                             ## preview the dashboard at http://localhost:8000
	$(PYTHON) -m http.server 8000 --directory docs

check-privacy:                     ## scan tracked files for emails / phone numbers
	$(PYTHON) scripts/check_privacy.py

clean-exports:                     ## delete generated dashboard data
	rm -f docs/data/*.json docs/data/*.csv
