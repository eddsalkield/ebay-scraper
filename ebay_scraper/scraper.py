import requests
from bs4 import BeautifulSoup
from slimit.parser import Parser
from slimit.visitors import nodevisitor
from slimit import ast
from urllib.parse import urljoin, urlparse
from termcolor import colored
import re

import sys
from pprint import pprint



def scrape_auction_page(url):
    r = requests.get(url)
    if not r.ok:
        raise ValueError('The requested page could not be found')
    return parse_auction_page(r.text)

def _parse_auction_page(page_text):
    soup = BeautifulSoup(page_text, 'html.parser')

    # Locate the JSDF div
    div = soup.find('div', id='JSDF')
    scripts = div.find_all('script', src=None)

    # Look for $rwidgets
    script_texts = []
    for script in scripts:
        for s in script.contents:
            if '$rwidgets' in s:
                script_texts.append(s)

    # Strip c from s
    def strip(s, c):
        if isinstance(s, str):
            return s.strip(c)
        return s


    # Parsing js
    values = {}
    for script_text in script_texts:
        parser = Parser()
        tree = parser.parse(script_text)
        for node in nodevisitor.visit(tree):
            if isinstance(node, ast.FunctionCall):
                if isinstance(node.identifier, ast.Identifier):
                    if node.identifier.value == '$rwidgets':
                        fields = {getattr(n.left, 'value', '').strip('"'): \
                                    strip(getattr(n.right, 'value', ''), '"') \
                                for n in nodevisitor.visit(node) \
                                if isinstance(n, ast.Assign)}
                        values = {**values, **fields}
    return values

# Generates a search URL
def _generate_search_url(query_string: str, page_num: int, n_results: int, \
        base_url: str):
    if not isinstance(n_results, int) or page_num < 1:
        raise ValueError('n_results must be an int, greater than 0')

    search_suffix = '/sch/i.html?_nkw={}&_pgn={}&_skc={}'
    n_results = n_results*(page_num-1)

    suffix = search_suffix.format(query_string, page_num, n_results)
    return urljoin(base_url, suffix)

# Returns a list of dict of products
# TODO: price, thumbnail etc.
def _parse_search_page(page_text):
    soup = BeautifulSoup(page_text, 'html.parser')
    auctions_list = soup.find('ul', id='ListViewInner')
    results = auctions_list.find_all('li', recursive=False)

    auctions = []

    for result in results:
        # Filter out sponsored results
        if result.find('div', attrs={'class': 'promoted-lv'}) or \
                result.find('div', attrs={'class': 's-item__title--tagblock'}) or \
                result.find('a', href=re.compile('.*pulsar.*')):
            continue
            #print(colored('Found sponsored', 'red'))
            #print(result.prettify())

        try:
            listing_id = result.attrs['listingid']
        except KeyError:
            print(colored("Found a non-item. Skipping...", 'red'))
            print(result.prettify())
            continue

        name = ' '.join(result.find('h3').find('a').find( \
                text=True, recursive=False).split())
        # Strip tracking query parameters from the url
        tracking_url = result.find('h3').find('a').attrs['href']
        url = urljoin(tracking_url, urlparse(tracking_url).path)

        auctions.append({'name': name, 'url': url, 'listing_id': listing_id})

    return auctions


# TODO: specify just n_results
def scrape_search_page(query_string: str, page_num: int = 1, \
        n_results: int = 50, base: str = 'https://www.ebay.com'):
    url = _generate_search_url(query_string, page_num, n_results, base)
    r = requests.get(url)
    if not r.ok:
        raise ValueError('The requested page could not be found')
    with open('page.html', 'w') as f:
        soup = BeautifulSoup(r.text, 'html.parser')
        f.write(soup.prettify())
    return _parse_search_page(r.text)


#r = requests.get('https://www.ebay.co.uk/itm/African-Tribal-Art-Figurine-Mambila-Cameroon/183885054092?hash=item2ad067408c:g:LOwAAOSwiHFdLFL7&autorefresh=true')
