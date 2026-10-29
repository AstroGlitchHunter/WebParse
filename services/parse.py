import asyncio
import json
import re
from urllib.parse import urlparse

import httpx
from camoufox.async_api import AsyncCamoufox
from selectolax.lexbor import LexborHTMLParser

from config import SHOPS, PRICE_RE, SHOP_CARDS, HEADERS, CAMOUFOX_PREFS, WB_NM_RE


def detect_shop(url: str):
    host = urlparse(url).netloc.lower().removeprefix('www.')
    for key, shop in SHOPS.items():
        if any(host.endswith(item) for item in shop['hosts']):
            return key
    return None


def _to_price(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace('\u00a0', ' ').replace('\u2009', ' ').replace('\u202f', ' ')
    text = text.replace(' ', '').replace(',', '.')
    text = re.sub(r'[^\d.]', '', text)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clean_text(value, limit=400):
    if not value:
        return ''
    text = re.sub(r'\s+', ' ', str(value)).strip()
    if not text:
        return ''
    return text[:limit]


def _item(name, link, price):
    if not name or not link or price is None:
        return None
    return {'name': _clean_text(name, 180), 'link': _clean_text(link, 2000), 'price': round(float(price), 2)}


def _walk_jsonld(node, acc):
    if isinstance(node, list):
        for item in node:
            _walk_jsonld(item, acc)
        return
    if not isinstance(node, dict):
        return
    types = node.get('@type')
    types = types if isinstance(types, list) else [types]
    types = [str(item).lower() for item in types if item]
    if any('product' in item for item in types):
        acc.append(node)
    if '@graph' in node:
        _walk_jsonld(node['@graph'], acc)


def _offer_price(offers):
    if isinstance(offers, list) and offers:
        return _offer_price(offers[0])
    if isinstance(offers, dict):
        return _to_price(offers.get('price') or offers.get('lowPrice'))
    return None


def _from_jsonld(html, url):
    items = []
    for script in LexborHTMLParser(html).css('script[type="application/ld+json"]'):
        raw = script.text()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found = []
        _walk_jsonld(payload, found)
        for product in found:
            item = _item(product.get('name'), product.get('url') or url, _offer_price(product.get('offers')))
            if item:
                items.append(item)
    return items


def _from_meta(html, url):
    tree = LexborHTMLParser(html)
    title = ''
    for selector, attr in (('meta[property="og:title"]', 'content'), ('meta[name="twitter:title"]', 'content')):
        node = tree.css_first(selector)
        if node and node.attributes.get(attr):
            title = node.attributes[attr]
            break
    h1 = tree.css_first('h1')
    if h1 and h1.text(strip=True):
        title = h1.text(strip=True)
    text = tree.text()
    match = PRICE_RE.search(text or '')
    price = _to_price(match.group(1)) if match else None
    item = _item(title, url, price)
    return [item] if item else []


def _from_listing(html, base):
    price_re = re.compile(r'^\d[\d\s\u2009\u00a0\u202f]*₽$')
    items = []
    seen = set()
    for link_el in LexborHTMLParser(html).css('a[href*="/product/"], a[href*="/catalog/"], a[href*="/card/"]'):
        href = (link_el.attributes.get('href') or '').split('?')[0]
        name = link_el.text(strip=True)
        if not href or href in seen or not name or '₽' in name:
            continue
        seen.add(href)
        price = None
        parent = link_el.parent
        for _ in range(6):
            if parent is None:
                break
            prices = [t for el in parent.css('span, div') if price_re.match(t := el.text(strip=True))]
            if prices:
                price = _to_price(prices[0])
                break
            parent = parent.parent
        item = _item(name, href if href.startswith('http') else base + href, price)
        if item:
            items.append(item)
        if len(items) >= 20:
            break
    return items


def _clean_link(href, base):
    href = (href or '').split('#')[0].split('?')[0]
    if not href:
        return ''
    return href if href.startswith('http') else base + href


def _from_cards(html, base, spec):
    items = []
    seen = set()
    for card in LexborHTMLParser(html).css(spec['card']):
        name_node = card.css_first(spec['name'])
        link_node = card.css_first(spec['link'])
        price_node = card.css_first(spec['price'])
        if not (name_node and link_node and price_node):
            continue
        name = name_node.attributes.get(spec['name_attr']) if spec.get('name_attr') else name_node.text(strip=True)
        link = _clean_link(link_node.attributes.get('href'), base)
        match = PRICE_RE.search(price_node.text(strip=True) or '')
        price = _to_price(match.group(1)) if match else None
        if not link or link in seen:
            continue
        seen.add(link)
        item = _item(name, link, price)
        if item:
            items.append(item)
        if len(items) >= 20:
            break
    return items


def extract_goods(html, url):
    parsed = urlparse(url)
    base = f'{parsed.scheme}://{parsed.netloc}'
    spec = SHOP_CARDS.get(detect_shop(url))
    cards = (lambda data: _from_cards(data, base, spec)) if spec else (lambda data: [])
    generic = lambda data: _from_listing(data, base)
    jsonld = lambda data: _from_jsonld(data, url)
    meta = lambda data: _from_meta(data, url)
    if spec and spec['product'].search(url):
        # страница одного товара: сначала данные самого товара, потом карточки
        collectors = (jsonld, meta, cards, generic)
    else:
        # лента/выдача: сначала карточки своего магазина
        collectors = (cards, jsonld, generic)
    for collector in collectors:
        items = collector(html)
        if items:
            return items
    return []


def _wb_price(product):
    for size in product.get('sizes') or []:
        price = (size.get('price') or {}).get('product')
        if price:
            return float(price) / 100
    for key in ('salePriceU', 'priceU'):
        if product.get(key):
            return float(product[key]) / 100
    return None


async def _parse_wb_api(url: str):
    match = WB_NM_RE.search(url) or re.search(r'(\d{6,})', url)
    if not match:
        raise ValueError('Не удалось определить артикул Wildberries')
    nm = match.group(1)
    params = {'appType': 1, 'curr': 'rub', 'dest': -1257786, 'nm': nm}
    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        response = await client.get('https://card.wb.ru/cards/v2/detail', params=params)
        response.raise_for_status()
        payload = response.json()
        products = ((payload.get('data') or {}).get('products')) or []
        if not products:
            raise ValueError('Wildberries не вернул карточку товара')
        product = products[0]
        item = _item(product.get('name'), url, _wb_price(product))
        if not item:
            raise ValueError('Не удалось разобрать карточку Wildberries')
        return [item]


async def parse_wildberries(url: str):
    if WB_NM_RE.search(url):
        try:
            return await _parse_wb_api(url)
        except Exception:
            pass
    return await _parse_browser(url, 'h1, article.product-card')


async def _parse_browser(url: str, wait_selector: str):
    async with AsyncCamoufox(headless=False, firefox_user_prefs=CAMOUFOX_PREFS) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=40000)
        except Exception:
            pass
        try:
            await page.wait_for_selector(wait_selector, timeout=180000)
        except Exception:
            await asyncio.sleep(3)
        for _ in range(4):
            await page.mouse.wheel(0, 1400)
            await asyncio.sleep(0.8)
        html = await page.content()
        await context.close()
    items = extract_goods(html, url)
    if not items:
        raise ValueError('Не удалось найти товар на странице')
    return items


async def parse_ozon(url: str):
    return await _parse_browser(url, 'h1, .tile-root')


async def parse_yandex(url: str):
    return await _parse_browser(url, 'h1, [data-zone-name="productSnippet"]')


async def parse_mega(url: str):
    return await _parse_browser(url, 'h1, article.product-card')


async def parse_joom(url: str):
    return await _parse_browser(url, 'h1, a[href*="/products/"]')


PARSERS = {
    'wildberries': parse_wildberries,
    'ozon': parse_ozon,
    'yandex': parse_yandex,
    'mega': parse_mega,
    'joom': parse_joom,
}


async def parse_shop(shop_key: str, url: str):
    parser = PARSERS.get(shop_key)
    if parser is None:
        raise ValueError('Неизвестный магазин')
    return await parser(url)