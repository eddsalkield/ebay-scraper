import toml
import typer

from .ebay_scraper import ebay_scraper

app = typer.Typer()
state = {'db_path': './res/estore.db', 'images_base_dir': './res/images'}

ebay_scraper = ebay_scraper(\
        db_path=state['db_path'], \
        images_base_dir=state['images_base_dir'])

@app.command()
def test():
    print("hello")

@app.callback()
def main(config_path: str = './config.toml'):
    config = toml.load(config_path)
    try:
        state['db_path'] = config['db_path']
    except KeyError:
        pass

    try:
        state['images_base_dir'] = config['images_base_dir']
    except KeyError:
        pass

def main():
    app()
