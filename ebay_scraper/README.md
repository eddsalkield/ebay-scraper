# eBay Scraper

> Scrapes eBay auctions, profiles, and searches into a sqlite database

> Can be used as a CLI tool, or interfaced with directly

## Building and installation

Ensure poetry is [installed](https://python-poetry.org/docs/#installation).  Then from this directory install dependencies into the poetry virtual environment and build:

```bash
poetry install
poetry build
```

Source and wheel files are built into `ebay_scraper/dist`.

Install it across your user with `pip`, outside the venv:
```bash
cd ./dist
python3 -m pip install --user ./ebay_scraper-0.0.1-py3-none-any.whl
```

or

```bash
cd ./dist
pip install ./ebay_scraper-0.0.1-py3-none-any.whl
```

Run `ebay-scraper` to invoke the utility.

## Usage

`ebay-scraper` will scrape data from auctions, profiles, and searches on eBay.  Resulting textual data is written to a `sqlite3` database, with images and backup web pages optionally being written to a _data directory_.

The tool is invoked as:

```
ebay-scraper [OPTIONS] DB_PATH DATA_LOCATION COMMAND [ARGS]...

Options:
  --verbose / --no-verbose
  --base-url TEXT
  --install-completion      Install completion for the current shell.
  --show-completion         Show completion for the current shell, to copy it
                            or customize the installation.

  --help                    Show this message and exit.

Commands:
  auction
  profile
  search
```

* `DB_PATH` is the path to the `sqlite3` database.
* `DATA_LOCATION` is the path to the _data directory_.
* `--base-url`, initially set to `https://www.ebay.com`, can be used to specify an alternative URL to scrape from (e.g. `https://www.ebay.co.uk`).

### Auction mode
In auction mode, an auction must be specified as either a unique _eBay auction ID_ or as a URL.  The textual data is scraped into the `ebay_auctions` table of `DB_PATH`, the page is scraped into `DATA_LOCATION/ebay/auctions`, and the images into `DATA_LOCATION/ebay/images`.  The `--base-url` option determines the base URL from which to resolve _eBay auction IDs_ if specified, defaulting to `https://www.ebay.com`.

Example usage:

```bash
# Scraping from a US URL
ebay-scraper db.db ./data/ auction https://www.ebay.com/itm/Chubby-Blob-Seal-Plush-Toy-Animal-Cute-Ocean-Pillow-Pet-Stuffed-Doll-Kids-Gift/362995774962?hash=item54843bf5f2:g:euoAAOSwmnFd50KP

# Equivalently scraping from an auction ID, from the US site (--base-url defaults to https://www.ebay.com):
ebay-scraper db.db ./data/ auction 362995774962

# Scraping from a UK URL
ebay-scraper db.db ./data/ auction https://www.ebay.co.uk/itm/Chubby-Blob-Seal-Plush-Toy-Animal-Cute-Ocean-Pillow-Pet-Stuffed-Doll-Kids-Gift/362995774962?hash=item54843bf5f2:g:euoAAOSwmnFd50KP

# Equivalently scraping from an auction ID, from the UK site:
ebay-scraper --base-url https://www.ebay.co.uk/ db.db ./data/ auction 362995774962
```

### Profile mode
In profile mode, a profile must be specified as either a unique _eBay username_ or as a URL.  The textual data is scraped into the `ebay_profiles` table of `DB_PATH`, and the page is scraped into `DATA_LOCATION/ebay/profiles`.  The `--base-url` option determines the base URL from which to resolve _eBay username_ if specified, defaulting to `https://www.ebay.com`.

Example usage:

```bash
# Scraping from a US URL
ebay-scraper db.db ./data/ profile https://www.ebay.com/usr/lolypops6e7

# Equivalently scraping from a username, from the US site (--base-url defaults to https://www.ebay.com):
ebay-scraper db.db ./data/ profile lolypops6e7

# Scraping from a UK URL
ebay-scraper db.db ./data/ profile https://www.ebay.co.uk/usr/lolypops6e7

# Equivalently scraping from a username, from the UK site:
ebay-scraper --base-url https://www.ebay.co.uk/ db.db ./data/ profile lolypops6e7
```

### Search mode
In search mode, a `QUERY_STRING` must be provided alongside `N_RESULTS`.  It will scrape the auctions pertaining to the top `N_RESULTS` results from the `QUERY_STRING`.  The `--base-url` option determines the base URL from which to resolve the search specified, defaulting to `https://www.ebay.com`.

Example usage:
```bash
# Searching from a US URL
ebay-scraper db.db ./data search "mambila art"

# Searching from a UK URL
ebay-scraper --base-url https://www.ebay.co.uk/ db.db ./data search "mambila art"
```

## Interfacing with the API
`ebay-scraper` can also be invoked as a Python library to automate its operation, or build your own database backend.  `scraper` and `db_interface`.

### scraper
Provides methods to scrape auction, profile, and search pages, returning the results in a dict.

Import with:

```python3
from ebay_scraper import scraper
```

Provides the following methods:

`scrape_auction_page(auction, base: str = 'https://www.ebay.com', raw: bool = False, page_save_path=None)`

`scrape_profile_page(profile: str, base: str = 'https://www.ebay.com', page_save_path=None)`

`scrape_search_page(query_string: str, n_results: int = 50, base: str = 'https://www.ebay.com')`

Example usage:

```python3
from ebay_scraper import scraper
es.scrape_auction_page(362995774962)
```

### db_interface
Provides the `EbayScraper` class, for the scraping of auctions, profiles, and searches into the database.  For searches, it parses the results to invoke calls to the discovered auctions and profiles.

Import with:

```python3
from ebay_scraper import db_interface
```

The `EbayScraper` class requires, upon initialisation, `db_path`, and optionally a `save_location`.  It provides the following methods:

```python3
class EbayScraper():
    def __init__(self, db_path, save_location=None)
    
    def scrape_auction_to_db(self, auction, base: str = 'https://www.ebay.com')
    
    def scrape_profile_to_db(self, profile: str, base: str = 'https://www.ebay.com')
    
    def scrape_search_to_db(self, query_string, n_results, base: str = 'https://www.ebay.com') 
```

## Database schema
`ebay_scraper` creates tables `ebay_auctions` and `ebay_profiles` within `DB_PATH`.  These tables take the following schemata:

```
ebay_auctions (
    auction_id INTEGER NOT NULL PRIMARY KEY,
    title TEXT,
    seller TEXT,   -- Primary key of sellers table
    start_time INTEGER,
    end_time INTEGER,
    n_bids INTEGER,
    price INTEGER,
    currency_code TEXT,
    buy_now_price INTEGER,
    starting_price INTEGER,
    winner TEXT,
    location_id TEXT,  -- Primary key of locations table
    image_paths TEXT NOT NULL, -- colon-separated paths relative to some base path
    description TEXT
);

CREATE TABLE ebay_profiles (
    profile_id TEXT NOT NULL PRIMARY KEY,
    description TEXT,
    contacted INTEGER NOT NULL,
    email TEXT,
    location TEXT,
    name TEXT,
    registered INTEGER,
    permission_given INTEGER NOT NULL,
    member_since TEXT,
    member_since_unix INTEGER,
    n_followers INTEGER,
    n_reviews INTEGER,
    percent_positive_feedback INTEGER
);
```

## Additional feature ideas
* Scraping all auctions listed by a given seller
* Add a _when_scraped_ field
* Timestamped log outputs

## Authors
Edd Salkield <edd@salkield.uk>
