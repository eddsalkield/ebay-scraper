import requests
from bs4 import BeautifulSoup
from slimit.parser import Parser
from slimit.visitors import nodevisitor
from slimit import ast

import sys
from pprint import pprint

def scrape_ebay_url(url):
    r = requests.get(url)
    return ebay_parser(r.text)

def ebay_parser(page_text):
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

#r = requests.get('https://www.ebay.co.uk/itm/African-Tribal-Art-Figurine-Mambila-Cameroon/183885054092?hash=item2ad067408c:g:LOwAAOSwiHFdLFL7&autorefresh=true')
