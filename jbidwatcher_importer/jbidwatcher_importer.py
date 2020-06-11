#!/usr/bin/python3
import typer
import xmltodict
import sqlite3
from typing import List
from collections import OrderedDict
from termcolor import colored
import traceback

import sys

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


ebay_listings_entries = ['listing_id', 'title', 'seller', 'start_time', \
        'end_time', 'n_bids', 'price', 'price_currency', 'buy_now_price', \
        'buy_now_price_currency', 'starting_price', 'starting_price_currency', \
        'winner', 'location_id', 'image_paths']

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
            CREATE TABLE IF NOT EXISTS ebay_listings (
                listing_id INTEGER NOT NULL PRIMARY KEY,
                title TEXT,
                seller TEXT,   -- Primary key of sellers table
                start_time INTEGER,
                end_time INTEGER,
                n_bids INTEGER,
                price INTEGER,
                price_currency TEXT,
                buy_now_price INTEGER,
                buy_now_price_currency TEXT,
                starting_price INTEGER,
                starting_price_currency TEXT,
                winner TEXT,
                location_id TEXT,  -- Primary key of locations table
                image_paths BLOB NOT NULL -- paths relative to some base path,
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
    listing_id = a['@id']

    auction_dict = {}
    for e in ebay_listings_entries:
        auction_dict[e] = None

    # Determine if an auction of the given id currently exists
    @_db_transaction_factory(db_path)
    def existing_entry(c):
        c.execute('SELECT * FROM ebay_listings WHERE listing_id=?',\
                (listing_id,))
        r = c.fetchall()
        if not r:
            return None
        else:
            return r[0]

    if existing_entry is not None:
        # Merge existing entries
        for name, e in zip(ebay_listings_entries, existing_entry):
            if e is not None:
                auction_dict[name] = e


    try:
        title = auction['title']
    except KeyError as e:
        title = None    # Some strange jbidwatcher entries don't have titles
    try:
        seller = auction['seller']
    except KeyError:
        seller = None
    if isinstance(seller, str):
        seller_name = seller
    elif isinstance(seller, OrderedDict):
        seller_name = seller['name']
    elif seller is None:
        seller_name = None
    else:
        raise ValueError('Auction: {}\nSeller {} of invalid type: {}'\
                .format(listing_id, str(seller), str(type(seller))))


    # jbidwatcher timestamps are UNIX time in ms
    try:
        start_time = int(auction['start'])/1000 \
                if int(auction['start']) > 0 else None
    except KeyError:
        start_time = None

    try:
        end_time = int(auction['end'])/1000 if int(auction['end']) > 0 else None
    except KeyError:
        end_time = None

    try:
        n_bids = int(auction['bidcount']) if int(auction['bidcount']) > 0 else 0
    except KeyError:
        n_bids = None
    try:
        winner = auction['highbidder']
    except KeyError:
        winner = None

    try:
        if auction['currently']['@currency'] != 'UNK':
            price = float(auction['currently']['@price'])
            price_currency = auction['currently']['@currency']
        else:
            price = None
            price_currency = None
    except KeyError:
        price = None
        price_currency = None

    try:
        if auction['buynow']['@currency'] != 'UNK':
            buy_now_price = float(auction['buynow']['@price'])
            buy_now_price_currency = auction['buynow']['@currency']
        else:
            buy_now_price = None
            buy_now_price_currency = None
    except KeyError:
        buy_now_price = None
        buy_now_price_currency = None

    try:
        if auction['minimum']['@currency'] != 'UNK':
            starting_price = float(auction['minimum']['@price'])
            starting_price_currency = auction['minimum']['@currency']
        else:
            starting_price = None
            starting_price_currency = None
    except KeyError:
        starting_price = None
        starting_price_currency = None

    # Merge the auctions into one
    current_newer = False
    if existing_entry is not None:
        # Determine which entry is newer
        try:
            current_newer = n_bids > auction_dict['n_bids'] \
                    or end_time > auction_dict['end_time'] \
                    or (price_currency == auction_dict['price_currency'] \
                    and price > auction_dict['price'])
        except TypeError:
            # Short-circuiting of previous expressions will fail if evaluates
            # in place of None
            pass
    
        #if current_newer:
        #    print("Collision found.  Resolving by updating existing older record with newer information")
        #else:
        #    print("Collision found.  Resolving by updating exising newer information with missing gaps")
        #print(auction)

    # Merge the auctions
    if current_newer:
        if title is not None:
            auction_dict['title'] = title
        if seller_name is not None:
            auction_dict['seller'] = seller_name
        if start_time is not None:
            auction_dict['start_time'] = start_time 
        if end_time is not None:
            auction_dict['end_time'] = end_time
        if winner is not None:
            auction_dict['winner'] = winner
    elif existing_entry is None:
        auction_dict['title'] = title
        auction_dict['seller'] = seller_name
        auction_dict['start_time'] = start_time
        auction_dict['end_time'] = end_time
        auction_dict['winner'] = winner
                
    if existing_entry is not None:
        if auction_dict['n_bids'] is None or \
                (n_bids is not None and n_bids > auction_dict['n_bids']):
            auction_dict['n_bids'] = n_bids

        if auction_dict['price_currency'] is None \
                or (price_currency is not None \
                and auction_dict['price'] is not None \
                and price_currency == auction_dict['price_currency'] \
                and price > auction_dict['price']):
            auction_dict['price'] = price
            auction_dict['price_currency'] = price_currency
            
        if auction_dict['buy_now_price_currency'] is None \
                or (buy_now_price_currency is not None \
                and auction_dict['buy_now_price'] is not None \
                and buy_now_price_currency == auction_dict['buy_now_price_currency'] \
                and buy_now_price > auction_dict['buy_now_price']):
            auction_dict['buy_now_price'] = buy_now_price
            auction_dict['buy_now_price_currency'] = buy_now_price_currency
            
        if auction_dict['starting_price_currency'] is None \
                or (starting_price_currency is not None \
                and auction_dict['starting_price'] is not None \
                and starting_price_currency == auction_dict['starting_price_currency'] \
                and starting_price > auction_dict['starting_price']):
            auction_dict['starting_price'] = starting_price
            auction_dict['starting_price_currency'] = starting_price_currency
            
            
    else:
        auction_dict['n_bids'] = n_bids
        auction_dict['price'] = price
        auction_dict['price_currency'] = price_currency
        auction_dict['buy_now_price'] = buy_now_price
        auction_dict['buy_now_price'] = buy_now_price_currency
        auction_dict['starting_price_currency'] = starting_price
        auction_dict['starting_price_currency'] = starting_price_currency

    # Write out to the database
    @_db_transaction_factory(db_path)
    def _(c):
        # Delete the row
        if existing_entry is not None:
            c.execute('DELETE FROM ebay_listings WHERE listing_id=?', \
                    (listing_id,))

        # Update the row to its new values
        c.execute('''INSERT INTO ebay_listings (
            listing_id, title, seller, start_time, end_time, n_bids,
            price, price_currency, starting_price,
            starting_price_currency, image_paths) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ""
            )''',
            (listing_id, auction_dict['title'], auction_dict['seller'], \
                auction_dict['start_time'], auction_dict['end_time'], \
                auction_dict['n_bids'], auction_dict['price'], \
                auction_dict['price_currency'], auction_dict['starting_price'], \
                auction_dict['starting_price_currency']))

    # Update the sellers table
    @_db_transaction_factory(db_path)
    def _(c):
        c.execute('''INSERT OR IGNORE INTO ebay_sellers (
                nickname, contacted, permission_given) VALUES(?, ?, ?)''', \
                (seller_name, 0, 0,))


if __name__ == "__main__":
    typer.run(main)
