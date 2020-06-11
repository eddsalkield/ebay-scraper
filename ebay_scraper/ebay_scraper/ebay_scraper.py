import requests
from bs4 import BeautifulSoup
from slimit.parser import Parser
from slimit.visitors import nodevisitor
from slimit import ast
from urllib.parse import urljoin, urlparse
from termcolor import colored
import json
import re
import unicodedata
from datetime import datetime
import dateutil.parser

import sys
import os
from pprint import pprint
from typing import List

def _get_dict_value(d, k):
    try:
        d[k]
    except KeyError:
        return None

    if d[k] == 'true':
        return True
    elif d[k] == 'false':
        return False
    elif d[k] == 'null':
        return None

    try:
        return int(d[k])
    except Exception:
        pass

    try:
        return float(d[k])
    except Exception:
        pass

    return d[k]

# auction can be a URL or a page ID
def scrape_auction_page(auction, base: str = 'https://www.ebay.com', \
        raw: bool = False):
    try:
        auction_id = int(auction)
    except ValueError:
        # Ensure auction is a valid url
        if urlparse(auction).netloc == '':
            raise ValueError('auction must be a valid auction ID or URL')
        url = auction
    else:
        url = _generate_auction_url(auction_id, base)

    r = requests.get(url)
    if not r.ok:
        raise ValueError('The requested page could not be found')

    # Return raw data if requested
    raw_data = _parse_auction_page(r.text, ['maxImageUrl'])
    if raw:
        return raw_data
    else:
        # Validate API assumptions
        try:
            raw_data['it']
        except KeyError:
            raise ValueError(f'No it (title) field available for domain {url}.  Consider using a different prefix.')
        if raw_data['kw'] != raw_data['it']:
            print(colored(f'notify author: kw==it assumption incorrect for domain {url}.', 'red'))
        try:
            if raw_data['entityId'] != raw_data['entityName']:
                print(colored(f'notify author: entityid==entityname assumption incorrect for domain {url}', 'red'))
        except KeyError:
            print(colored('notify author: entityid or entityname does not exist for auction {}, for domain {}.'.format(raw_data['itemId'], url), 'red'))

        def f(url):
            return json.loads('"{}"'.format(url))
        image_urls = list(map(f, _get_dict_value(raw_data, 'maxImageUrl')))

        # TODO: get description
        # Maybe using 'itemDescSnippet' field?

        # Assemble important data
        return {
            'listing_id': _get_dict_value(raw_data, 'itemId'),
            'title': unicodedata.normalize("NFKD", _get_dict_value(raw_data, 'it')),
            'seller': _get_dict_value(raw_data, 'entityName'),
            'start_time': int(_get_dict_value(raw_data, 'startTime')/1000),
            'end_time': int(_get_dict_value(raw_data, 'endTime')/1000),
            'n_bids': _get_dict_value(raw_data, 'bids'),
            'currency_code': _get_dict_value(raw_data, 'ccode'),
            'price': _get_dict_value(raw_data, 'bidPriceDouble'),
            'buy_now_price': _get_dict_value(raw_data, 'binPriceDouble'),
            'starting_price': None,
            'winner': None,
            'location': None,
            'won': _get_dict_value(raw_data, 'won'),
            'image_urls': image_urls,
            'locale': _get_dict_value(raw_data, 'locale'),
            'quantity': _get_dict_value(raw_data, 'totalQty'),
            'video_url': _get_dict_value(raw_data, 'videoUrl'),
            'vat_included': _get_dict_value(raw_data, 'vatIncluded'),
            'domain': _get_dict_value(raw_data, 'currentDomain')
        }

def _generate_auction_url(auction_id: int, base_url: str):
    page_suffix = '/itm/{}'
    suffix = page_suffix.format(auction_id)
    return urljoin(base_url, suffix)

# duplicates - a list of keys with permitted duplicates
def _parse_auction_page(page_text: str, duplicates: List[str]):
    # Strip c from s, without exception
    def strip(s, c):
        if isinstance(s, str):
            return s.strip(c)
        return s

    soup = BeautifulSoup(page_text, 'html.parser')

    with open('page.html', 'w') as f:
        f.write(page_text)

    # Locate the JSDF div
    div = soup.find('div', id='JSDF')
    scripts = div.find_all('script', src=None)

    # Look for $rwidgets
    script_texts = []
    for script in scripts:
        for s in script.contents:
            if '$rwidgets' in s:
                script_texts.append(s)

    # Bodge: until we move from slimit to calmjs
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

    # Parsing js
    raw_values = {}
    for script_text in script_texts:
        parser = Parser()
        tree = parser.parse(script_text)
        for node in nodevisitor.visit(tree):
            if isinstance(node, ast.FunctionCall):
                if isinstance(node.identifier, ast.Identifier):
                    if node.identifier.value == '$rwidgets':
                        # Deal with here
                        fields = {}
                        for n in nodevisitor.visit(node):
                            if isinstance(n, ast.Assign):
                                k = getattr(n.left, 'value', '').strip('"')
                                v = strip(getattr(n.right, 'value', ''), '"')
                                if k in duplicates:
                                    try:
                                        fields[k].append(v)
                                    except KeyError:
                                        fields[k] = [v]
                                else:
                                    fields[k] = v

                        # Merge fields and raw_values, resolving duplicates
                        for (k, v) in fields.items():
                            if k in duplicates:
                                try:
                                    raw_values[k] += v
                                except KeyError:
                                    raw_values[k] = v
                            else:
                                raw_values[k] = v
                        #raw_values = {**raw_values, **fields}
    # Bodge: until we move from slimit to calmjs
    sys.stdout = open(os.devnull, "w")
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

    return raw_values

# Generates a search URL
def _generate_search_url(query_string: str, page_num: int, \
        base_url: str, n_results: int = 50):
    if not isinstance(n_results, int) or page_num < 1:
        raise ValueError('n_results must be an int, greater than 0')

    search_suffix = '/sch/i.html?_nkw={}&_pgn={}&_skc={}'
    n_results = n_results*(page_num-1)

    suffix = search_suffix.format(query_string, page_num, n_results)
    return urljoin(base_url, suffix)

# Returns a list of dict of products
def _parse_search_page(page_text):
    soup = BeautifulSoup(page_text, 'html.parser')
    auctions_list = soup.find('ul', id='ListViewInner')
    results = auctions_list.find_all('li', recursive=False)

    auctions = {}

    for result in results:
        # Filter out sponsored results
        if result.find('div', attrs={'class': 'promoted-lv'}) or \
                result.find('div', attrs={'class': 's-item__title--tagblock'}) or \
                result.find('a', href=re.compile('.*pulsar.*')):
            continue

        try:
            listing_id = int(result.attrs['listingid'])
        except KeyError:
            print(colored("Found a non-item. Skipping...", 'red'))
            print(result.prettify())
            continue
        except ValueError:
            print(colored("Could not convert auction ID {listing_id} to int", \
                    'red'))

        name = ' '.join(result.find('h3').find('a').find( \
                text=True, recursive=False).split())
        # Strip tracking query parameters from the url
        tracking_url = result.find('h3').find('a').attrs['href']
        url = urljoin(tracking_url, urlparse(tracking_url).path)

        auctions[listing_id] = {'name': name, 'url': url}

    return auctions


# Returns up to n_results
def scrape_search_page(query_string: str, n_results: int = 50, \
        base: str = 'https://www.ebay.com'):
    results = {}
    n_page = 1
    while len(results) < n_results:
        url = _generate_search_url(query_string, n_page, base)
        r = requests.get(url)
        if not r.ok:
            raise ValueError('The requested page could not be found')
        res = _parse_search_page(r.text)
        n_res = len(results)
        results = {**results, **_parse_search_page(r.text)}
        if len(results) == n_res:
            break
        n_page += 1

    while len(results) > n_results:
        results.popitem()
    return results

# profile can be a URL or a profile ID
def scrape_profile_page(profile: str, base: str = 'https://www.ebay.com'):
    if urlparse(profile).netloc == '':
        url = _generate_profile_url(profile, base)
        seller_id = profile
    else:
        url = profile
        seller_id = urlparse(url).path.split('/')[-1]

    r = requests.get(url)
    if not r.ok:
        raise ValueError('The requested page could not be found')

    d = _parse_profile_page(r.text)
    d['url'] = url
    d['seller_id'] = seller_id
    return d

def _generate_profile_url(profile_id: int, base_url: str):
    page_suffix = '/usr/{}'
    suffix = page_suffix.format(profile_id)
    return urljoin(base_url, suffix)

def _parse_profile_page(page_text):
    soup = BeautifulSoup(page_text, 'html.parser')

    description = soup.find('h2', attrs={'class': 'bio inline_value'}).get_text(strip=True)

    member_info = soup.find('div', id='member_info')
    #n_followers = member_info.find('span', text='Followers').find('span',
    #        attrs={'class': 'info'}).text
    n_followers = None  # Appears obfuscated
    n_reviews = None    # Appears obfuscated
    member_since = member_info.find('span', text=re.compile('.*Member since:.*')) \
            .parent.find('span', attrs={'class': 'info'}).get_text(strip=True)
    try:
        member_since_unix = int(datetime.timestamp(dateutil.parser.parse( \
                member_since)))
    except ValueError:
        member_since_unix = None
    location = member_info.find('span', attrs={'class': 'mem_loc'}).get_text(strip=True)
    percent_positive_feedback = soup.find('div', attrs={'class': 'perctg'}) \
            .get_text(strip=True).split('%')[0]

    return {
        'description': description,
        'n_followers': n_followers,
        'n_reviews': n_reviews,
        'member_since': member_since,
        'member_since_unix': member_since_unix,
        'location': location,
        'percent_positive_feedback': percent_positive_feedback
    }

#r = requests.get('https://www.ebay.co.uk/itm/African-Tribal-Art-Figurine-Mambila-Cameroon/183885054092?hash=item2ad067408c:g:LOwAAOSwiHFdLFL7&autorefresh=true')
