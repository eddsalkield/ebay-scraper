import sqlite3
import pathlib

class ebay_scraper():
    def __init__(self, db_path, images_base_dir):
        print('###')
        print(db_path)
        #self.db_path = db_path
        

        # Create db_path if not exists


        @self._db_transaction
        def _(c):
            c.execute('''
                CREATE TABLE IF NOT EXISTS ebay_listings (
                    ebay_id INTEGER NOT NULL PRIMARY KEY,
                    end_time INTEGER,
                    auction_length INTEGER,
                    bid_list TEXT NOT NULL,
                    loc_id TEXT,  -- Primary key of locations table
                    n_bids INTEGER NOT NULL,
                    --previous_listing_id ???,
                    seller TEXT NOT NULL,   -- Primary key of sellers table
                    title TEXT NOT NULL,
                    winner TEXT,
                    winning_price INTEGER,
                    images // should these be serialised, or paths?,
                )
            ''')

            c.execute('''
            CREATE TABLE ebay_sellers (
                    nickname TEXT NOT NULL PRIMARY KEY,
                    contacted INTEGER NOT NULL,
                    email TEXT,
                    loc_id TEXT,
                    name TEXT,
                    registered INTEGER NOT NULL,
                    permission_given INTEGER NOT NULL,
                    selling_since INTEGER NOT NULL
                )
            ''')

            c.execute('''
                CREATE TABLE ebay_locations (
                    loc_id TEXT NOT NULL PRIMARY KEY,
                    place_name TEXT NOT NULL,
                    country_name TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    notes TEXT
                )
            ''')

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

