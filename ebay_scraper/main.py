import pathlib
import requests
from termcolor import colored
from urllib.parse import urlparse
import sqlite3
import pickle

from pprint import pprint

import ebay_scraper as es

# From https://stackoverflow.com/questions/18092354/python-split-string-without-splitting-escaped-character#21107911
def _escape_split(s, delim):
    i, res, buf = 0, [], ''
    while True:
        j, e = s.find(delim, i), 0
        if j < 0:  # end reached
            return res + [buf + s[i:]]  # add remainder
        while j - e and s[j - e - 1] == '\\':
            e += 1  # number of escapes
        d = e // 2  # number of double escapes
        if e != d * 2:  # odd number of escapes
            buf += s[i:j - d - 1] + s[j]  # add the escaped char
            i = j + 1  # and skip it
            continue  # add more to buf
        res.append(buf + s[i:j - d])
        i, buf = j + len(delim), ''  # start after delim

class EbayScraper():
    def __init__(self, db_path, image_location=None):
        self.db_path = db_path

        @self._db_transaction
        def _(c):
            c.execute('''
                CREATE TABLE IF NOT EXISTS ebay_listings (
                    listing_id INTEGER NOT NULL PRIMARY KEY,
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
                    image_paths TEXT NOT NULL -- colon-separated paths relative to some base path,
                )
            ''')

            c.execute('''
            CREATE TABLE IF NOT EXISTS ebay_sellers (
                    nickname TEXT NOT NULL PRIMARY KEY,
                    contacted INTEGER NOT NULL,
                    email TEXT,
                    loc_id TEXT,
                    name TEXT,
                    registered INTEGER,
                    permission_given INTEGER NOT NULL,
                    selling_since INTEGER
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS ebay_locations (
                    location_id TEXT NOT NULL PRIMARY KEY,
                    place_name TEXT NOT NULL,
                    country_name TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    notes TEXT
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    prefix TEXT NOT NULL PRIMARY KEY,
                    image_location TEXT NOT NULL
                )
            ''')

        @self._db_transaction
        def ebay_listings_entries(c):
            return [row[1] for row in \
                c.execute("pragma table_info('sqlite_master')").fetchall()]
        self.ebay_listings_entries = ebay_listings_entries

        if image_location is None:
            # Determine the image location
            @self._db_transaction
            def im_loc(c):
                c.execute('''
                    SELECT * FROM settings WHERE prefix="ebay"
                    ''')
                return c.fetchall()
            if not im_loc:
                raise ValueError('image_location must be specified on first run')
            print(im_loc)
            image_location = im_loc[0][1]
            print(image_location)
        else:
            print(f'Setting image_location to {image_location}')
            @self._db_transaction
            def _(c):
                c.execute('''
                    DELETE FROM settings WHERE prefix="ebay"
                ''')
                c.execute('''
                    INSERT INTO settings (prefix, image_location) VALUES (
                        "ebay", ?)
                ''', (image_location,))

        pathlib.Path(image_location).mkdir(parents=True, exist_ok=True)
        self.image_location = image_location

    def _db_transaction(self, f):
        for _ in range(5):
            try:
                conn = sqlite3.connect(self.db_path)
                c = conn.execute('''BEGIN TRANSACTION''')
                try:
                    result = f(c)
                    conn.commit()
                except:
                    conn.rollback()
                    raise
                finally:
                    try:
                        conn.close()
                    except:
                        os.abort()
            except sqlite3.OperationalError as e:
                pass
            else:
                return result
        c = sqlite3.connect(self.db_path)
        try:
            c.execute('''BEGIN EXCLUSIVE TRANSACTION''')
            result = f(c)
            c.commit()
        finally:
            c.close()

    def download_images(self, image_urls, name_prefix: str = 'ebay'):
        self.image_location = pathlib.Path(self.image_location)
        image_paths = []
        for url in image_urls:
            name = name_prefix + '_' + '_'.join(urlparse(url).path.split('/')[-2:])
            path = self.image_location.joinpath(name).resolve()
            image_paths.append(path)

            if not pathlib.Path(path).is_file():
                r = requests.get(url)
                if not r.ok:
                    print(colored('Could not find page: {}'.format(url), 'red'))
                with open(path, 'wb') as f:
                    f.write(r.content)
        return image_paths

    # merges d2 into d1
    def _merge_dicts(self, d1: dict, d2: dict):
        for k,v2 in d2.items():
            try:
                v1 = d1[k]
            except KeyError:
                d1[k] = v2
                continue
            
            if v1 is None:
                d1[k] = v2
                continue

            if type(v1) != type(v2):
                raise ValueError(f'{v1} and {v2} not of same type!')

            if int(v1) and v2 > v1:
                d1[k] = v2
                continue

            if str(v1):
                d1[k] = v2
                continue
            
            raise ValueError('Unknown failure')
        return d1


    def _merge_and_write_auction(self, auction: dict):
        # Determine if an auction of the given id currently exists
        @self._db_transaction
        def existing_entry(c):
            c.execute('SELECT * FROM ebay_listings WHERE listing_id=?',\
                    (auction['listing_id'],))
            r = c.fetchall()
            if not r:
                return None
            else:
                return r[0]

        existing_auction = {}
        if existing_entry is not None:
            # Merge existing entries
            print('###')
            print(self.ebay_listings_entries)
            for name, e in zip(self.ebay_listings_entries, existing_entry):
                existing_auction[name] = e

        # Determine whether auction or existing_auction is newer
        current_newer = False
        if existing_entry is not None:
            # Determine which entry is newer
            pprint(auction)
            pprint(existing_auction)
            try:
                current_newer = auction['n_bids'] > existing_auction['n_bids'] \
                        or auction['end_time'] > existing_auction['end_time'] \
                        or (auction['currency_code'] == \
                            existing_auction['currency_code'] \
                        and auction['price'] > existing_auction['price'])
            except TypeError:
                # Short-circuiting of previous expressions will fail if evaluates
                # in place of None
                pass
            except KeyError:
                # existing auction must have failed, so the current is newer
                current_newer = True
        
        if current_newer:
            a = self._merge_dicts(existing_auction, auction)
        else:
            a = self._merge_dicts(auction, existing_auction)

        # Write out to self.db_path
        @self._db_transaction
        def _(c):
            # Delete the row
            if existing_entry is not None:
                c.execute('DELETE FROM ebay_listings WHERE listing_id=?', \
                        (a['listing_id'],))

            # Update the row to its new values
            c.execute('''INSERT INTO ebay_listings (
                listing_id, title, seller, start_time, end_time, n_bids,
                price, currency_code, starting_price,
                image_paths) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ""
                )''',
                (a['listing_id'], a['title'], a['seller'], \
                    a['start_time'], a['end_time'], \
                    a['n_bids'], a['price'], \
                    a['currency_code'], a['starting_price']))

    # Some method to write out to the database
    def scrape_auction_to_db(self, auction, base: str = 'https://www.ebay.com'):
        auction_dict = es.scrape_auction_page(auction, base)
        self._merge_and_write_auction(auction_dict)

        # Grab images and save them
        new_image_paths = list(map(str, self.download_images( \
                auction_dict['image_urls'])))
        try:
            existing_image_paths = _escape_split(auction_dict['image_paths'])
        except KeyError:
            existing_image_paths = []
        image_paths = ':'.join(list(set(new_image_paths).union(existing_image_paths)))

        @self._db_transaction
        def _(c):
            c.execute('''
                UPDATE ebay_listings SET image_paths=?
                WHERE listing_id=?
            ''', (image_paths, auction_dict['listing_id'],))


    # Some ebay download profile method

    # Some ebay search and download method

    # Some scheduling method
