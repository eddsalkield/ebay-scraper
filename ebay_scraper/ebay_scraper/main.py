import typer
from termcolor import colored
import sys
import traceback
import pathlib

from . import db_interface

app = typer.Typer()
state = {'db_path': None, 'base_url': None, 'image_location': None, 
        'verbose': None, 'data_location': None}

def setup():
    try:
        e = db_interface.EbayScraper(state['db_path'], state['data_location'])
    except Exception as e:
        # Print the setup exception cleanly and exit
        print(e)
        sys.exit(1)
    return e

@app.callback()
def main(db_path: str, data_location: str, verbose: bool = False, \
        base_url: str = 'https://www.ebay.com'):
    state['db_path'] = db_path
    state['verbose'] = verbose
    state['base_url'] = base_url
    state['data_location'] = data_location

@app.command()
def auction(auction: str):
    e = setup()
    try:
        e.scrape_auction_to_db(auction, state['base_url'])
    except Exception as e:
        if state['verbose']:
            print(colored(traceback.format_exc(), 'red'))
        else:
            print(colored(e, 'red'))

@app.command()
def profile(profile: str):
    e = setup()
    try:
        e.scrape_profile_to_db(profile, state['base_url'])
    except Exception as e:
        if state['verbose']:
            print(colored(traceback.format_exc(), 'red'))
        else:
            print(colored(e, 'red'))

@app.command()
def search(query_string: str, n_results: int, auction_save_dir: str = None):
    e = setup()
    try:
        e.scrape_search_to_db(query_string, n_results, state['base_url'])
    except Exception as e:
        if state['verbose']:
            print(colored(traceback.format_exc(), 'red'))
        else:
            print(colored(e, 'red'))

def main():
    app()
