#!/usr/bin/python3
import typer
import sqlite3
import csv
from numbers import Number

from pprint import pprint

app = typer.Typer()

def _appl(f, d, k):
    try:
        v = d[k]
    except KeyError:
        return None

    if isinstance(v, str) and v == "":
        return None

    try:
        return f(v)
    except Exception: return None

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


def _db_transaction_factory(db_path):
    def _db_transaction(f):
        for _ in range(5):
            try:
                conn = sqlite3.connect(db_path)
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
        c = sqlite3.connect(db_path)
        try:
            c.execute('''BEGIN EXCLUSIVE TRANSACTION''')
            result = f(c)
            c.commit()
        finally:
            c.close()
    return _db_transaction

def _csv_import_profile(db_path, ebay_profiles_entries, new_profile_dict):
    # Process new_profile_dict into the correct types
    new_profile_dict['profile_id'] = _appl(int, new_profile_dict, 'profile_id')
    new_profile_dict['description'] = _appl(str, new_profile_dict, 'description')
    new_profile_dict['contacted'] = _appl(str, new_profile_dict, 'contacted')
    new_profile_dict['email'] = _appl(int, new_profile_dict, 'email')
    new_profile_dict['location'] = _appl(int, new_profile_dict, 'location')
    new_profile_dict['name'] = _appl(int, new_profile_dict, 'name')
    new_profile_dict['registered'] = _appl(int, new_profile_dict, 'registered')
    new_profile_dict['permission_given'] = _appl(str, new_profile_dict, 'permission_given')
    new_profile_dict['member_since'] = _appl(int, new_profile_dict, 'member_since')
    new_profile_dict['member_since_unix'] = _appl(int, new_profile_dict, 'member_since_unix')
    new_profile_dict['n_followers'] = _appl(str, new_profile_dict, 'n_followers')
    new_profile_dict['n_reviews'] = _appl(str, new_profile_dict, 'n_reviews')
    new_profile_dict['percent_positive_feedback'] = _appl(str, new_profile_dict, 'percent_positive_feedback')

    existing_profile_dict = {}
    for e in ebay_profiles_entries:
        existing_profile_dict[e] = None

    # Get existing profile
    try:
        profile_id = new_profile_dict['profile_id']
    except KeyError:
        pass
    else:
        # Get the existing profile
        @_db_transaction_factory(db_path)
        def existing_entry(c):
            c.execute('SELECT * FROM ebay_profiles WHERE profile_id=?',\
                    (profile_id,))
            r = c.fetchall()
            if not r:
                return None
            else:
                return r[0]

        if existing_entry is not None:
            # Merge existing entries
            for name, e in zip(ebay_profiles_entries, existing_entry):
                if e is not None:
                    existing_profile_dict[name] = e

    # Merge the profiles
    a = _merge_dicts(existing_profile_dict, new_profile_dict)
    pprint(a)

    # Write out
    @_db_transaction_factory(db_path)
    def _(c):
        # Delete the row
        if existing_entry is not None:
            c.execute('DELETE FROM ebay_profiles WHERE profile_id=?', \
                    (profile_id,))

        # Update the row to its new values
        c.execute('''INSERT INTO ebay_profiles (
            profile_id, description, contacted, email, location, name,
            registered, permission_given, member_since, member_since_unix,
            n_followers, n_reviews, percent_positive_feedback) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )''',
            (profile_id, a['description'], a['contacted'], a['email'], \
                a['location'], a['name'], a['registered'], a['permission_given'], \
                a['member_since'], a['member_since_unix'], a['n_followers'],
                a['n_reviews'], a['percent_positive_feedback']))

@app.command()
def profile(db_path, path):
    # Initialise dbs
    @_db_transaction_factory(db_path)
    def _(c):
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

    @_db_transaction_factory(db_path)
    def ebay_profiles_entries(c):
        return [row[1] for row in \
            c.execute("pragma table_info('ebay_profiles')").fetchall()]

    # Read CSV into new_auction_dict
    with open(path) as fd:
        reader = csv.DictReader(fd)
        for d in reader:
            pprint(d)
            _csv_import_profile(db_path, ebay_profiles_entries, d)

def _csv_import_auction(db_path, ebay_auctions_entries, new_auction_dict):
    # Process new_auction_dict into the correct types
    new_auction_dict['auction_id'] = _appl(int, new_auction_dict, 'auction_id')
    new_auction_dict['title'] = _appl(str, new_auction_dict, 'title')
    new_auction_dict['seller'] = _appl(str, new_auction_dict, 'seller')
    new_auction_dict['start_time'] = _appl(int, new_auction_dict, 'start_time')
    new_auction_dict['end_time'] = _appl(int, new_auction_dict, 'end_time')
    new_auction_dict['n_bids'] = _appl(int, new_auction_dict, 'n_bids')
    new_auction_dict['price'] = _appl(int, new_auction_dict, 'price')
    new_auction_dict['currency_code'] = _appl(str, new_auction_dict, 'currency_code')
    new_auction_dict['buy_now_price'] = _appl(int, new_auction_dict, 'buy_now_price')
    new_auction_dict['starting_price'] = _appl(int, new_auction_dict, 'starting_price')
    new_auction_dict['winner'] = _appl(str, new_auction_dict, 'winner')
    new_auction_dict['location_id'] = _appl(str, new_auction_dict, 'location_id')
    new_auction_dict['image_paths'] = _appl(str, new_auction_dict, 'image_paths')
    new_auction_dict['description'] = _appl(str, new_auction_dict, 'description')

    existing_auction_dict = {}
    for e in ebay_auctions_entries:
        existing_auction_dict[e] = None

    # Get existing auction
    try:
        auction_id = new_auction_dict['auction_id']
    except KeyError:
        pass
    else:
        # Get the existing auction
        @_db_transaction_factory(db_path)
        def existing_entry(c):
            c.execute('SELECT * FROM ebay_auctions WHERE auction_id=?',\
                    (auction_id,))
            r = c.fetchall()
            if not r:
                return None
            else:
                return r[0]

        if existing_entry is not None:
            # Merge existing entries
            for name, e in zip(ebay_auctions_entries, existing_entry):
                if e is not None:
                    existing_auction_dict[name] = e

    # Merge the auctions
    a = _merge_dicts(existing_auction_dict, new_auction_dict)
    pprint(a)

    # Write out
    @_db_transaction_factory(db_path)
    def _(c):
        # Delete the row
        if existing_entry is not None:
            c.execute('DELETE FROM ebay_auctions WHERE auction_id=?', \
                    (auction_id,))

        # Update the row to its new values
        c.execute('''INSERT INTO ebay_auctions (
            auction_id, title, seller, start_time, end_time, n_bids,
            price, currency_code, starting_price, buy_now_price,
            winner, location_id, image_paths, description) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )''',
            (auction_id, a['title'], a['seller'], a['start_time'], \
                a['end_time'], a['n_bids'], a['price'], a['currency_code'], \
                a['starting_price'], a['buy_now_price'], a['winner'], \
                a['location_id'], a['image_paths'], a['description']))

@app.command()
def auction(db_path, path):
    # Initialise dbs
    @_db_transaction_factory(db_path)
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

    @_db_transaction_factory(db_path)
    def ebay_auctions_entries(c):
        return [row[1] for row in \
            c.execute("pragma table_info('ebay_auctions')").fetchall()]

    # Read CSV into new_auction_dict
    with open(path) as fd:
        reader = csv.DictReader(fd)
        for d in reader:
            pprint(d)
            _csv_import_auction(db_path, ebay_auctions_entries, d)

if __name__ == "__main__":
    app()
