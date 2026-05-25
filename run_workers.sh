# NOTE: Important that only 1 worker can run for scraping.
# If more than one runs at the same time, then results may be lost.

# Run syncronously:
# (still uses gevent via monkey patching)
pipenv run python -m dramatiq --processes 1 --threads 1 api.tasks.scrape

# Run with gevent:
# Not using this for now, since we need only one scrape/update task to run at
# any given time to avoid potentially losing data.
# pipenv run dramatiq-gevent --processes 1 --threads 30 api.tasks.scrape
