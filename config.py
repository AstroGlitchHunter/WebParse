from pathlib import Path
import re

APP_DIR = Path(__file__).resolve().parent

ICON_DIR = APP_DIR / 'icons'
THEMES_DIR = APP_DIR / 'themes'
DB_PATH = str(APP_DIR / 'shops_data.sqlite')

WB_ICON = str(ICON_DIR / 'wb.svg')
OZON_ICON = str(ICON_DIR / 'ozon.svg')
YANDEX_ICON = str(ICON_DIR / 'yandex.svg')
MEGA_ICON = str(ICON_DIR / 'mega.svg')
JOOM_ICON = str(ICON_DIR / 'joom.svg')

SHOPS = {
    'wildberries': {
        'name': 'Wildberries',
        'icon': WB_ICON,
        'hosts': ('wildberries.ru', 'wb.ru'),
        'theme': 'wildberries.qss',
        'accent': '#CB11AB',
        'bg': '#1C0B18',
        'text': '#FFE8F8',
    },
    'ozon': {
        'name': 'Ozon',
        'icon': OZON_ICON,
        'hosts': ('ozon.ru',),
        'theme': 'ozon.qss',
        'accent': '#005BFF',
        'bg': '#071428',
        'text': '#E8F0FF',
    },
    'yandex': {
        'name': 'Yandex Market',
        'icon': YANDEX_ICON,
        'hosts': ('market.yandex.ru', 'yandex.ru'),
        'theme': 'yandex.qss',
        'accent': '#FFCC00',
        'bg': '#1F1804',
        'text': '#FFF6C8',
    },
    'mega': {
        'name': 'Mega market',
        'icon': MEGA_ICON,
        'hosts': ('megamarket.ru',),
        'theme': 'mega.qss',
        'accent': '#8654CC',
        'bg': '#140C22',
        'text': '#F0E7FF',
    },
    'joom': {
        'name': 'Joom',
        'icon': JOOM_ICON,
        'hosts': ('joom.ru', 'joom.com'),
        'theme': 'joom.qss',
        'accent': '#F54242',
        'bg': '#1F0B0B',
        'text': '#FFE8E8',
    },
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    'Accept': 'application/json,text/html;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9',
}

CAMOUFOX_PREFS = {
    'network.dns.disableIPv6': True,
    'network.trr.mode': 3,
    'network.trr.uri': 'https://cloudflare-dns.com/dns-query',
    'network.trr.bootstrapAddr': '1.1.1.1',
    'network.proxy.type': 0,
}

PRICE_RE = re.compile(r'(\d[\d\s\u2009\u00a0\u202f]*)\s*₽')
WB_NM_RE = re.compile(r'(?:/catalog/|/detail\.aspx\?.*?nm=|[?&]nm=)(\d+)')

SHOP_CARDS = {
    'wildberries': {
        'product': re.compile(r'/catalog/\d+/detail\.aspx'),
        'card': 'article.product-card',
        'link': 'a[data-testid="product-card-link"]',
        'name': 'a[data-testid="product-card-link"]',
        'name_attr': 'aria-label',
        'price': '[data-testid="product-card-price"] ins',
    },
    'ozon': {
        'product': re.compile(r'/product/'),
        'card': '.tile-root',
        'link': 'a[href*="/product/"]',
        'name': '.tsBody500Medium',
        'price': '.tsHeadline500Medium',
    },
    'yandex': {
        'product': re.compile(r'/card/'),
        'card': '[data-zone-name="productSnippet"]',
        'link': 'a[href*="/card/"]',
        'name': '[data-auto="snippet-title"]',
        'price': '[data-auto="snippet-price-current"]',
    },
    'mega': {
        'product': re.compile(r'/catalog/details/'),
        'card': 'article.product-card',
        'link': 'a.product-card__title',
        'name': 'a.product-card__title',
        'price': 'p.product-card__price',
    },
    'joom': {
        'product': re.compile(r'/products/'),
        'card': 'div[class*="product___"]',
        'link': 'a[href*="/products/"]',
        'name': 'h2[class*="productName"]',
        'price': '[class*="pricesRegularValue___"]',
    },
}

def load_stylesheet(shop_key=None):
    filename = SHOPS.get(shop_key, {}).get('theme', 'default.qss')
    path = THEMES_DIR / filename
    if not path.exists():
        path = THEMES_DIR / 'default.qss'
    return path.read_text(encoding='utf-8') if path.exists() else ''
