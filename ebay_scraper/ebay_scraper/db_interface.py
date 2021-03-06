import pathlib
import requests
from termcolor import colored
from urllib.parse import urlparse
import sqlite3
import pickle
import traceback
from numbers import Number

from pprint import pprint

from . import scraper

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

# merges d2 into d1
def _merge_dicts(d1: dict, d2: dict):
    for k,v2 in d2.items():
        try:
            v1 = d1[k]
        except KeyError:
            d1[k] = v2
            continue
        
        if v1 is None:
            d1[k] = v2
            continue
        elif v2 is None:
            d1[k] = v1
            continue

        if isinstance(v1, Number) and isinstance(v2, Number):
            if v2 > v1:
                d1[k] = v2
            continue

        if type(v1) != type(v2):
            raise ValueError('{} and {} not of same types: {}, {}'.format(\
                    v1, v2, type(v1), type(v2)))

        if isinstance(v1, str):
            d1[k] = v2
            continue
        
        raise ValueError('Unknown failure between {}:{} and {}:{}'\
                .format(v1, type(v1), v2, type(v2)))
    return d1

class EbayScraper():
    def __init__(self, db_path, save_location=None):
        self.db_path = db_path

        @self._db_transaction
        def _(c):
            c.execute('''
                CREATE TABLE IF NOT EXISTS ebay_auctions (
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
                )
            ''')

            c.execute('''
            CREATE TABLE IF NOT EXISTS ebay_profiles (
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

                )
            ''')


        @self._db_transaction
        def ebay_auctions_entries(c):
            return [row[1] for row in \
                c.execute("pragma table_info('ebay_auctions')").fetchall()]
        self.ebay_auctions_entries = ebay_auctions_entries

        @self._db_transaction
        def ebay_profiles_entries(c):
            return [row[1] for row in \
                c.execute("pragma table_info('ebay_profiles')").fetchall()]
        self.ebay_profiles_entries = ebay_profiles_entries

        save_path = pathlib.Path(save_location).joinpath('ebay')
        self.image_location = save_path.joinpath('images')
        pathlib.Path(self.image_location).mkdir(parents=True, exist_ok=True)
        self.auction_page_location = save_path.joinpath('auctions')
        pathlib.Path(self.auction_page_location).mkdir(parents=True, exist_ok=True)
        self.profile_page_location = save_path.joinpath('profiles')
        pathlib.Path(self.profile_page_location).mkdir(parents=True, exist_ok=True)

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

    def _download_images(self, image_urls, auction_id,  name_prefix: str = 'ebay'):
        self.image_location = pathlib.Path(self.image_location)
        image_paths = []
        for url in image_urls:
            name = name_prefix + '_' + str(auction_id) + \
                    '_' + '_'.join(urlparse(url).path.split('/')[-2:])
            path = self.image_location.joinpath(name).resolve()
            image_paths.append(path)

            if not pathlib.Path(path).is_file():
                r = requests.get(url)
                if not r.ok:
                    print(colored('Could not find page: {}'.format(url), 'red'))
                with open(path, 'wb') as f:
                    f.write(r.content)
        return image_paths


    def _merge_and_write_auction(self, auction: dict):
        # Determine if an auction of the given id currently exists
        @self._db_transaction
        def existing_entry(c):
            c.execute('SELECT * FROM ebay_auctions WHERE auction_id=?',\
                    (auction['auction_id'],))
            r = c.fetchall()
            if not r:
                return None
            else:
                return r[0]

        existing_auction = {}
        if existing_entry is not None:
            # Merge existing entries
            for name, e in zip(self.ebay_auctions_entries, existing_entry):
                existing_auction[name] = e

        # Determine whether auction or existing_auction is newer
        current_newer = False
        if existing_entry is not None:
            # Determine which entry is newer
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
            a = _merge_dicts(existing_auction, auction)
        else:
            a = _merge_dicts(auction, existing_auction)

        # Write out to self.db_path
        @self._db_transaction
        def _(c):
            # Delete the row
            if existing_entry is not None:
                c.execute('DELETE FROM ebay_auctions WHERE auction_id=?', \
                        (a['auction_id'],))

            # Construct and execute the new query
            keys = ', '.join(a.keys())
            filler = ('?, ' * (len(a)-1)) + '?'
            vals = tuple(a.values())
            query = f'INSERT INTO ebay_auctions ({keys}) VALUES ({filler})'
            c.execute(query, vals)

    # Some method to write out to the database
    def scrape_auction_to_db(self, auction, base: str = 'https://www.ebay.com'):
        auction_dict = scraper.scrape_auction_page(auction, base, \
                page_save_path=self.auction_page_location)
        try:
            image_urls = auction_dict['image_urls']
        except KeyError:
            image_urls = None
        
        # Normalise auction_dict entries
        # Filter keys to known-good values
        auction_dict = {k:v for k,v in auction_dict.items() if \
                k in self.ebay_auctions_entries}

        # Set NOT NULL constraint keys to their defaults
        if 'image_paths' not in auction_dict.keys():
            auction_dict['image_paths'] = ''

        self._merge_and_write_auction(auction_dict)

        # Grab images and save them
        if image_urls is not None:
            new_image_paths = list(map(str, self._download_images(image_urls, \
                    auction_dict['auction_id'])))
            try:
                existing_image_paths = _escape_split(auction_dict['image_paths'], ':')
            except KeyError:
                existing_image_paths = []
            image_paths = ':'.join(list(set(new_image_paths).union(existing_image_paths)))

            @self._db_transaction
            def _(c):
                c.execute('''
                    UPDATE ebay_auctions SET image_paths=?
                    WHERE auction_id=?
                ''', (image_paths, auction_dict['auction_id'],))

        return auction_dict


    def _merge_and_write_profile(self, profile):
        # Determine if a seller of the given id currently exists
        @self._db_transaction
        def existing_entry(c):
            c.execute('SELECT * FROM ebay_profiles WHERE profile_id=?',\
                    (profile['profile_id'],))
            r = c.fetchall()
            if not r:
                return None
            else:
                return r[0]

        existing_profile = {}
        if existing_entry is not None:
            # Merge existing entries
            for name, e in zip(self.ebay_profiles_entries, existing_entry):
                existing_profile[name] = e

        # Assume the existing profile is older
        p = {**existing_profile, **profile}

        # Write out to self.db_path
        @self._db_transaction
        def _(c):
            # Delete the row
            if existing_entry is not None:
                c.execute('DELETE FROM ebay_profiles WHERE profile_id=?', \
                        (p['profile_id'],))

            # Update the row to its new values
            c.execute('''
                INSERT INTO ebay_profiles (
                    profile_id, description, contacted, location, registered,
                    permission_given, member_since, member_since_unix,
                    n_followers, n_reviews, percent_positive_feedback)
                VALUES (?, ?, 0, ?, 0, 0, ?, ?, ?, ?, ?)''',
                (p['profile_id'], p['description'], p['location'], \
                    p['member_since'], p['member_since_unix'], \
                    p['n_followers'], p['n_reviews'], \
                    p['percent_positive_feedback'])
                )

    def scrape_profile_to_db(self, profile: str, base: str = 'https://www.ebay.com'):
        profile_dict = scraper.scrape_profile_page(profile, base, \
                page_save_path=self.profile_page_location)
        self._merge_and_write_profile(profile_dict)

    # Some ebay search and download method
    def scrape_search_to_db(self, query_strings, n_results, base: str = 'https://www.ebay.com'):
        results = {}
        for query_string in query_strings:
            results = {**results, \
                    **scraper.scrape_search_page(query_string, n_results, base)}
        scraped_profiles = set()
        for auction_id, d in results.items():
            try:
                print('Scraping auction url {}'.format(d['url']))
                a = self.scrape_auction_to_db(d['url'])
                profile = a['seller']
                if profile not in scraped_profiles:
                    print('Scraping profile {}'.format(a['seller']))
                    self.scrape_profile_to_db(a['seller'])
                    scraped_profiles.add(profile)
                else:
                    print('Already scraped profile {}'.format(a['seller']))
            except Exception:
                print(colored('Error processing auction {}'.format(d['url']), 'red'))
                print(colored(traceback.format_exc(), 'red'))
