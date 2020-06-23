#!/usr/bin/python3
import typer
import xmltodict
import sqlite3
from typing import List
from collections import OrderedDict
from termcolor import colored
import traceback
from numbers import Number

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



ebay_listings_entries = ['auction_id', 'title', 'seller', 'start_time', \
        'end_time', 'n_bids', 'price', 'currency_code', 'buy_now_price', \
        'starting_price', 'winner', 'location_id', 'image_paths', 'description']

def main(db_path: str, paths: List[str]):
    for path in paths:
        try:
            print(f'Processing file: {path}')
            jbw_import(db_path, path)
        except Exception:
            print(colored(f'Error processing file: {path}. Skipping...', 'red'))
            print(colored(traceback.format_exc(), 'red'))

            

def jbw_import(db_path, path):
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

    with open(path, errors='ignore') as fd:
        print(path)
        jbw = xmltodict.parse(fd.read())

    auctions = jbw['jbidwatcher']['auctions']['server']['auction']

    for a in auctions:
        try:
            process_auction(a, db_path)
        except Exception:
            print(colored('Error processing auction. Skipping...'))
            print(colored(traceback.format_exc(), 'red'))

def process_auction(a, db_path):
    auction = a['info']
    auction_id = a['@id']

    existing_auction_dict = {}
    auction_dict = {}
    for e in ebay_listings_entries:
        existing_auction_dict[e] = None
        auction_dict[e] = None

    # Determine if an auction of the given id currently exists
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
        for name, e in zip(ebay_listings_entries, existing_entry):
            if e is not None:
                existing_auction_dict[name] = e

    try:
        auction_dict['title'] = auction['title']
    except KeyError as e:
        pass
    try:
        seller = auction['seller']
    except KeyError:
        pass
    if isinstance(seller, str):
        auction_dict['seller'] = seller
    elif isinstance(seller, OrderedDict):
        auction_dict['seller'] = seller['name']
    elif auction_dict['seller'] is None:
        seller = None
    else:
        raise ValueError('Auction: {}\nSeller {} of invalid type: {}'\
                .format(auction_id, str(seller), str(type(seller))))


    # jbidwatcher timestamps are UNIX time in ms
    try:
        auction_dict['start_time'] = int(auction['start'])/1000 \
                if int(auction['start']) > 0 else None
    except KeyError:
        pass

    try:
        auction_dict['end_time'] = \
                int(auction['end'])/1000 if int(auction['end']) > 0 else None
    except KeyError:
        pass

    try:
        auction_dict['n_bids'] = \
                int(auction['bidcount']) if int(auction['bidcount']) > 0 else 0
    except KeyError:
        pass
    try:
        auction_dict['winner'] = auction['highbidder']
    except KeyError:
        pass

    currency_code = None
    try:
        if auction['currently']['@currency'] != 'UNK':
            auction_dict['price'] = float(auction['currently']['@price'])
            auction_dict['currency_code'] = auction['currently']['@currency']
    except KeyError:
        pass

    try:
        if auction['buynow']['@currency'] != 'UNK':
            auction_dict['buy_now_price'] = float(auction['buynow']['@price'])
            auction_dict['currency_code'] = auction['buynow']['@currency']
    except KeyError:
        pass

    try:
        if auction['minimum']['@currency'] != 'UNK':
            auction_dict['starting_price'] = float(auction['minimum']['@price'])
            auction_dict['currency_code'] = auction['minimum']['@currency']
    except KeyError:
        pass

    # Merge the auctions into one
    current_newer = False
    if existing_entry is not None:
        # Determine which entry is newer
        try:
            current_newer = auction_dict['n_bids'] > existing_auction_dict['n_bids'] \
                    or auction_dict['end_time'] > existing_auction_dict['end_time'] \
                    or auction_dict['price'] > existing_auction_dict['price']
        except TypeError:
            # Short-circuiting of previous expressions will fail if evaluates
            # in place of None
            pass

    if current_newer:
        a = _merge_dicts(existing_auction_dict, auction_dict)
    else:
        a = _merge_dicts(auction_dict, existing_auction_dict)

    # Write out to the database
    @_db_transaction_factory(db_path)
    def _(c):
        # Delete the row
        if existing_entry is not None:
            c.execute('DELETE FROM ebay_auctions WHERE auction_id=?', \
                    (auction_id,))

        # Update the row to its new values
        c.execute('''INSERT INTO ebay_auctions (
            auction_id, title, seller, start_time, end_time, n_bids,
            price, currency_code, starting_price, image_paths) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ""
            )''',
            (auction_id, a['title'], a['seller'], a['start_time'], \
                a['end_time'], a['n_bids'], a['price'], a['currency_code'], \
                a['starting_price']))

    # Update the sellers table
    @_db_transaction_factory(db_path)
    def _(c):
        c.execute('''INSERT OR IGNORE INTO ebay_profiles (
                profile_id, contacted, permission_given) VALUES(?, ?, ?)''', \
                (a['seller'], 0, 0,))


if __name__ == "__main__":
    typer.run(main)
