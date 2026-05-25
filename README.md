# Punterpal Backend

**Warning:** This is no longer being actively maintained.

## Installation

* Install Python 3
    - Need version 3.9 or later
* Install Pipenv
    - Install dependencies with `pipenv install`

## Usage

### Web UI

The scripts `run.sh` and `run_workers.sh` will start the backend and worker thread respectively.

See the corresponding README for instructions on starting the frontend.

### CLI

View commands, help:

    `pipenv run python main.py`
    `pipenv run python main.py scrape --help`
    `pipenv run python main.py evaluate --help`

Example: scrape data from Sportsbet and update markets:

    `pipenv run python main.py scrape sportsbet`

Example: evaluate arbitrage opportunities for soccer:

    `pipenv run python main.py evaluate --sportkey="Soccer"`

### Schema

The "schema" contains both a hierachy of category information (sports, leagues, teams, events) as well as market data, and is used by the matcher. It is currently just stored as a JSON blob in Redis.

An example schema with extensive edits is provided in `schema.json`. You can use this as a starting point by writing it with write-schema as described below.

#### Manual Updates

It is necessary to periodically add to the synonyms lists to address instances when automatic matching fails.

Write the schema to file with:

    `pipenv run python main.py read-schema`

This will write the schema to `schema.json`.

Review match failures under stats (or via the interface) and add to the synonyms lists as needed, then write the schema file with:

    `pipenv run python main.py write-schema`
