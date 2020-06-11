import typer
from typing import Optional
from termcolor import colored
import sys

from . import db_interface

app = typer.Typer()
state = {'db_path': None, 'base_url': None, 'image_location': None}

def setup():
    try:
        e = db_interface.EbayScraper(state['db_path'], state['image_location'])
    except Exception as e:
        # Print the setup exception cleanly and exit
        print(e)
        sys.exit(1)
    return e

@app.callback()
def main(db_path: str, base_url: str = 'https://www.ebay.com', \
        image_location: Optional[str] = None):
    state['db_path'] = db_path
    state['base_url'] = base_url
    state['image_location'] = image_location

@app.command()
def auction(auction: str):
    e = setup()
    try:
        e.scrape_auction_to_db(auction, state['base_url'])
    except Exception as e:
        print(colored(e, 'red'))

@app.command()
def profile(profile: str):
    e = setup()
    try:
        e.scrape_profile_to_db(profile, state['base_url'])
    except Exception as e:
        print(colored(e, 'red'))

@app.command()
def search(query_string: str, n_results: int):
    e = setup()
    try:
        e.scrape_search_to_db(query_string, n_results, state['base_url'])
    except Exception as e:
        print(colored(e, 'red'))

def main():
    app()
