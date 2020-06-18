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

def _normalise_description(desc):
    # Strips multiple groups of c from s
    def strip_multiple(s, c):
        return c.join(filter(None, s.split(c)))

    norm = unicodedata.normalize("NFKD", desc)
    norm = '\n'.join(filter(None, filter(lambda e: not e.isspace(), norm.split('\n'))))
    norm = strip_multiple(norm, ' ')
    return norm

def _get_page_resolve_iframes(url):
    r = requests.get(url)
    if not r.ok:
        raise ValueError('The requested page could not be found')
    soup = BeautifulSoup(r.text, 'html.parser')
    for iframe in soup.find_all('iframe'):
        try:
            src = iframe['src']
        except KeyError:
            continue

        ir = requests.get(src)
        if not ir.ok:
            continue
        iframe_soup = BeautifulSoup(ir.text, 'html.parser')
        iframe.append(iframe_soup)
    return soup

# auction can be a URL or a page ID
def scrape_auction_page(auction, base: str = 'https://www.ebay.com', \
        raw: bool = False, page_save_path=None):
    is_file = False
    try:
        auction_id = int(auction)
    except ValueError:
        # Ensure auction is a valid url
        p = urlparse(auction)
        if p.netloc == '':
            if p.scheme == 'file':
                is_file = True
                url = p.path
            else:
                raise ValueError('auction must be a valid auction ID or URL')
        else:
            url = auction
    else:
        url = _generate_auction_url(auction_id, base)

    if is_file:
        with open(url, errors='ignore') as f:
            page = f.read()
            soup = BeautifulSoup(page, 'html.parser')
    else:
        # Open page, resolving iframes
        soup = _get_page_resolve_iframes(url)

    a = _parse_auction_page(soup, ['maxImageUrl', 'displayImgUrl'])

    # Write out page, if required
    if page_save_path is not None:
        name = '{}.html'.format(a['auction_id'])
        with open(page_save_path.joinpath(name), 'w') as f:
            f.write(soup.prettify())

    return a

def _generate_auction_url(auction_id: int, base_url: str):
    page_suffix = '/itm/{}'
    suffix = page_suffix.format(auction_id)
    return urljoin(base_url, suffix)

def _parse_2010_auction_soup(soup, duplicates, raw):
    # Example file: mambila_art_database/jbidwatcher/jbidwatch\ data\ 2010\ perhaps/auctionsave/400130806558.html
    # Find listing id
    auction_id = soup.find('td', text=re.compile('.*Item number:.*')) \
            .next_sibling.text

    # Find description
    desc = soup.find('div', attrs={'class': 'item_description'}).text

    return {
        'auction_id': int(auction_id),
        'description': _normalise_description(desc)
    }

    # TODO: add any or all of the following:
#            'auction_id': _get_dict_value(raw_data, 'itemId'),
#            'title': unicodedata.normalize("NFKD", _get_dict_value(raw_data, 'it')),
#            'seller': _get_dict_value(raw_data, 'entityName'),
#            'start_time': int(_get_dict_value(raw_data, 'startTime')/1000),
#            'end_time': int(_get_dict_value(raw_data, 'endTime')/1000),
#            'n_bids': _get_dict_value(raw_data, 'bids'),
#            'currency_code': _get_dict_value(raw_data, 'ccode'),
#            'price': _get_dict_value(raw_data, 'bidPriceDouble'),
#            'buy_now_price': _get_dict_value(raw_data, 'binPriceDouble'),
#            'starting_price': None,
#            'winner': None,
#            'location': None,
#            'won': _get_dict_value(raw_data, 'won'),
#            'image_urls': image_urls,
#            'locale': _get_dict_value(raw_data, 'locale'),
#            'quantity': _get_dict_value(raw_data, 'totalQty'),
#            'video_url': _get_dict_value(raw_data, 'videoUrl'),
#            'vat_included': _get_dict_value(raw_data, 'vatIncluded'),
#            'domain': _get_dict_value(raw_data, 'currentDomain')
    return results

def _parse_2020_auction_soup(soup, duplicates, raw=False):
    # Strip c from s, without exception
    def strip(s, c):
        if isinstance(s, str):
            return s.strip(c)
        return s

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

    if raw:
        return raw_values

    # Validate API assumptions
    try:
        raw_values['it']
    except KeyError:
        try:
            raw_values['kw']
        except KeyError:
            raise ValueError(f'No it (title) field available.  Consider using a different prefix.')
        else:
            title_key = 'kw'
    else:
        title_key = 'it'

    if raw_values['kw'] != raw_values['it']:
        print(colored(f'notify author: kw==it assumption incorrect for domain {url}.', 'red'))
    try:
        if raw_values['entityId'] != raw_values['entityName']:
            print(colored(f'notify author: entityid==entityname assumption incorrect for domain {url}', 'red'))
    except KeyError:
        print(colored('notify author: entityid or entityname does not exist for auction {}, for domain {}.'.format(raw_values['itemId'], url), 'red'))

    def f(url):
        return json.loads('"{}"'.format(url))

    # Get image URLS
    # TODO: sometimes only displayImgUrl is given, when the s-l600 image exists
    # Example: https://www.ebay.com/itm/Chubby-Blob-Seal-Plush-Toy-Animal-Cute-Ocean-Pillow-Pet-Stuffed-Doll-Kids-Gift/362995774962
    # Example: https://i.ebayimg.com/images/g/6NkAAOSwkEFd50Kb/s-l600.jpg
    raw_image_urls = []
    if 'maxImageUrl' in raw_values.keys():
        if 'displayImgUrl' in raw_values.keys():
            for max_image, disp_image in zip( \
                    _get_dict_value(raw_values, 'maxImageUrl'), \
                    _get_dict_value(raw_values, 'displayImgUrl')):
                if max_image == 'null':
                    if disp_image != 'null':
                        raw_image_urls.append(disp_image)
                else:
                    raw_image_urls.append(max_image)
        else:
            raw_image_urls = _get_dict_value(raw_values, 'maxImageUrl')
    else:
        if 'displayImgUrl' in raw_values.keys():
            raw_image_urls = _get_dict_value(raw_values, 'displayImgUrl')

    image_urls = list(map(f, raw_image_urls))

    # Get description
    # Since the description is stored in a separate iframe, an additional
    # request is required
    # Determine if iframe already loaded
    
    # If not loaded
    iframe = soup.find('div', attrs={'id': 'desc_div'}).find('iframe')
    # Else get the desc_soup some other way
    desc = _normalise_description(iframe.text)

    print(f'Image urls: {image_urls}')

    # Assemble important data
    return {
        'auction_id': _get_dict_value(raw_values, 'itemId'),
        'title': unicodedata.normalize("NFKD", _get_dict_value(raw_values, \
                title_key)),
        'seller': _get_dict_value(raw_values, 'entityName'),
        'start_time': int(_get_dict_value(raw_values, 'startTime')/1000),
        'end_time': int(_get_dict_value(raw_values, 'endTime')/1000),
        'n_bids': _get_dict_value(raw_values, 'bids'),
        'currency_code': _get_dict_value(raw_values, 'ccode'),
        'price': _get_dict_value(raw_values, 'bidPriceDouble'),
        'buy_now_price': _get_dict_value(raw_values, 'binPriceDouble'),
        'starting_price': None,
        'winner': None,
        'location': None,
        'won': _get_dict_value(raw_values, 'won'),
        'image_urls': image_urls,
        'locale': _get_dict_value(raw_values, 'locale'),
        'quantity': _get_dict_value(raw_values, 'totalQty'),
        'video_url': _get_dict_value(raw_values, 'videoUrl'),
        'vat_included': _get_dict_value(raw_values, 'vatIncluded'),
        'domain': _get_dict_value(raw_values, 'currentDomain'),
        'description': desc
    }

# duplicates - a list of keys with permitted duplicates
def _parse_auction_page(soup, duplicates: List[str], raw: bool = False):
    # Try various parsing methods until one works
    try:
        return _parse_2020_auction_soup(soup, duplicates, raw)
    except Exception:
        try:
            return _parse_2010_auction_soup(soup, duplicates, raw)
        except Exception as e:
            raise ValueError('Could not parse web page')

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
            auction_id = int(result.attrs['listingid'])
        except KeyError:
            print(colored("Found a non-item. Skipping...", 'red'))
            print(result.prettify())
            continue
        except ValueError:
            print(colored("Could not convert auction ID {auction_id} to int", \
                    'red'))

        name = ' '.join(result.find('h3').find('a').find( \
                text=True, recursive=False).split())
        # Strip tracking query parameters from the url
        tracking_url = result.find('h3').find('a').attrs['href']
        url = urljoin(tracking_url, urlparse(tracking_url).path)

        auctions[auction_id] = {'name': name, 'url': url}

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
def scrape_profile_page(profile: str, base: str = 'https://www.ebay.com', \
        page_save_path=None):
    if urlparse(profile).netloc == '':
        url = _generate_profile_url(profile, base)
        profile_id = profile
    else:
        url = profile
        profile_id = urlparse(url).path.split('/')[-1]

    r = requests.get(url)
    if not r.ok:
        raise ValueError('The requested page could not be found')

    text = r.text
    if page_save_path is not None:
        profile_path = page_save_path.joinpath(f'{profile_id}.html')
        with open(profile_path, 'w') as f:
            soup = BeautifulSoup(text, 'html.parser')
            f.write(soup.prettify())

    d = _parse_profile_page(text)
    d['url'] = url
    d['profile_id'] = profile_id
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
