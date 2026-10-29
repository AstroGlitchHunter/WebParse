import asyncio
import sys

import config
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtSql import QSqlRelationalDelegate
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from services.goods import DatabaseManager
from services.parse import detect_shop, parse_shop


class ParseWorker(QThread):
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, shop_key: str, url: str):
        super().__init__()
        self.shop_key = shop_key
        self.url = url

    def run(self):
        try:
            items = asyncio.run(parse_shop(self.shop_key, self.url))
            self.finished_ok.emit(items)
        except Exception as error:
            self.failed.emit(str(error))


class ChartCanvas(FigureCanvasQTAgg):
    def __init__(self):
        self.figure = Figure(figsize=(4.2, 2.4), dpi=100)
        super().__init__(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(190)
        self.setObjectName('chartCanvas')

    def apply_colors(self, bg, text, accent):
        self.figure.set_facecolor(bg)
        self.ax.set_facecolor(bg)
        self.ax.tick_params(colors=text, labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_color(accent)
        self.ax.yaxis.label.set_color(text)
        self.ax.xaxis.label.set_color(text)
        self.ax.title.set_color(text)

    def draw_bars(self, names, prices, bg, text, accent):
        self.ax.clear()
        self.apply_colors(bg, text, accent)
        if not prices:
            self.ax.text(0.5, 0.5, 'Нет данных', ha='center', va='center', color=text, fontsize=11)
            self.ax.set_xticks([])
            self.ax.set_yticks([])
        else:
            labels = [name if len(name) <= 18 else name[:18] + '…' for name in names[-12:]]
            values = prices[-12:]
            bars = self.ax.barh(labels, values, color=accent, height=0.62)
            for bar in bars:
                bar.set_alpha(0.92)
            self.ax.set_title('Цены товаров')
            self.figure.tight_layout()
        self.draw()

    def draw_hist(self, prices, bg, text, accent):
        self.ax.clear()
        self.apply_colors(bg, text, accent)
        if not prices:
            self.ax.text(0.5, 0.5, 'Нет данных', ha='center', va='center', color=text, fontsize=11)
            self.ax.set_xticks([])
            self.ax.set_yticks([])
        else:
            buckets = ['< 1 000', '1–5 тыс.', '5–15 тыс.', '> 15 тыс.']
            counts = [
                sum(1 for price in prices if price < 1000),
                sum(1 for price in prices if 1000 <= price < 5000),
                sum(1 for price in prices if 5000 <= price < 15000),
                sum(1 for price in prices if price >= 15000),
            ]
            self.ax.bar(buckets, counts, color=accent, width=0.64)
            self.ax.set_title('Распределение цен')
            self.figure.tight_layout()
        self.draw()


def make_card(name):
    frame = QFrame()
    frame.setObjectName(name)
    frame.setFrameShape(QFrame.Shape.NoFrame)
    return frame


class ParsePanel(QWidget):
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.setObjectName('ParsePanel')
        self.setMinimumSize(1080, 780)
        self.db_manager = db_manager
        self.current_shop = None
        self.worker = None
        self.shop_buttons = {}
        self.initPanel()
        self.apply_theme(None)

    def initPanel(self):
        self.main = QVBoxLayout(self)
        self.main.setContentsMargins(22, 18, 22, 18)
        self.main.setSpacing(14)

        title = QLabel('Парсер магазинов')
        title.setObjectName('sectionTitle')
        hint = QLabel('Выберите площадку — интерфейс переключится на её оформление')
        hint.setObjectName('hintLabel')
        self.main.addWidget(title)
        self.main.addWidget(hint)

        shop_bar = make_card('shopBar')
        icons = QHBoxLayout(shop_bar)
        icons.setContentsMargins(18, 12, 18, 12)
        icons.setSpacing(14)
        icons.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for key, shop in config.SHOPS.items():
            button = QPushButton()
            button.setObjectName('shopButton')
            button.setToolTip(shop['name'])
            button.setIcon(QIcon(shop['icon']))
            button.setIconSize(QSize(96, 96))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setCheckable(True)
            button.setFlat(True)
            button.clicked.connect(lambda checked, shop_key=key: self.select_shop(shop_key))
            self.shop_buttons[key] = button
            icons.addWidget(button)

        self.main.addWidget(shop_bar)

        search_card = make_card('searchCard')
        search_row = QHBoxLayout(search_card)
        search_row.setContentsMargins(14, 12, 14, 12)
        search_row.setSpacing(10)

        self.query_line = QLineEdit()
        self.query_line.setObjectName('queryLine')
        self.query_line.setPlaceholderText('Выберите магазин и вставьте ссылку на товар')
        self.query_line.returnPressed.connect(self.start_parse)

        self.button = QPushButton('Поиск')
        self.button.setObjectName('searchButton')
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setMinimumWidth(140)
        self.button.clicked.connect(self.start_parse)

        search_row.addWidget(self.query_line, 1)
        search_row.addWidget(self.button)
        self.main.addWidget(search_card)

        data = QGridLayout()
        data.setSpacing(12)
        data.setColumnStretch(0, 3)
        data.setColumnStretch(1, 2)

        table_card = make_card('tableCard')
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(10, 10, 10, 10)
        self.view = QTableView()
        self.view.setModel(self.db_manager.get_model())
        self.view.setItemDelegate(QSqlRelationalDelegate(self.view))
        self.view.setAlternatingRowColors(True)
        self.view.setShowGrid(False)
        self.view.verticalHeader().setVisible(False)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        table_layout.addWidget(self.view)
        data.addWidget(table_card, 0, 0, 4, 1)

        chart_card_1 = make_card('chartCard')
        chart_box_1 = QVBoxLayout(chart_card_1)
        chart_box_1.setContentsMargins(10, 10, 10, 10)
        chart_box_1.setSpacing(8)
        self.chart_price = ChartCanvas()
        self.download1 = QPushButton('Скачать диаграмму №1')
        self.download1.setObjectName('downloadButton')
        self.download1.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download1.clicked.connect(lambda: self.save_chart(self.chart_price, 'prices.png'))
        chart_box_1.addWidget(self.chart_price)
        chart_box_1.addWidget(self.download1)
        data.addWidget(chart_card_1, 0, 1, 2, 1)

        chart_card_2 = make_card('chartCard')
        chart_box_2 = QVBoxLayout(chart_card_2)
        chart_box_2.setContentsMargins(10, 10, 10, 10)
        chart_box_2.setSpacing(8)
        self.chart_dist = ChartCanvas()
        self.download2 = QPushButton('Скачать диаграмму №2')
        self.download2.setObjectName('downloadButton')
        self.download2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download2.clicked.connect(lambda: self.save_chart(self.chart_dist, 'distribution.png'))
        chart_box_2.addWidget(self.chart_dist)
        chart_box_2.addWidget(self.download2)
        data.addWidget(chart_card_2, 2, 1, 2, 1)

        self.main.addLayout(data, 1)
        self.refresh_charts()

    def select_shop(self, shop_key):
        self.current_shop = shop_key
        for key, button in self.shop_buttons.items():
            button.setChecked(key == shop_key)
        shop = config.SHOPS[shop_key]
        self.query_line.setPlaceholderText(f'Ссылка товара {shop["name"]}')
        self.db_manager.filter_by_shop_name(shop['name'])
        self.apply_theme(shop_key)
        self.refresh_charts()

    def apply_theme(self, shop_key):
        stylesheet = config.load_stylesheet(shop_key)
        self.setStyleSheet(stylesheet)
        window = self.window()
        if window is not None and window is not self:
            window.setStyleSheet(stylesheet)
        self.refresh_charts()

    def start_parse(self):
        url = self.query_line.text().strip()
        if not url:
            QMessageBox.warning(self, 'Поиск', 'Введите ссылку товара')
            return
        shop_key = self.current_shop or detect_shop(url)
        if shop_key is None:
            QMessageBox.warning(self, 'Поиск', 'Выберите магазин')
            return
        if shop_key != self.current_shop:
            self.select_shop(shop_key)
        self.button.setEnabled(False)
        self.button.setText('Идёт поиск...')
        self.worker = ParseWorker(shop_key, url)
        self.worker.finished_ok.connect(self.on_parse_ok)
        self.worker.failed.connect(self.on_parse_fail)
        self.worker.finished.connect(self.on_parse_done)
        self.worker.start()

    def on_parse_ok(self, items):
        shop = config.SHOPS[self.current_shop]
        shop_id = self.db_manager.get_shop_id(shop['name'])
        payload = []
        for item in items:
            payload.append({
                'name': item['name'],
                'link': item['link'],
                'price': item['price'],
                'shop_id': shop_id,
            })
        if not payload:
            QMessageBox.warning(self, 'Поиск', 'Товары не найдены')
            return
        if not self.db_manager.add_goods(payload):
            QMessageBox.critical(self, 'База данных', 'Не удалось сохранить товары')
            return
        self.refresh_charts()

    def on_parse_fail(self, message):
        QMessageBox.critical(self, 'Ошибка парсера', message or 'Не удалось разобрать страницу')

    def on_parse_done(self):
        self.button.setEnabled(True)
        self.button.setText('Поиск')

    def refresh_charts(self):
        names, prices = self.db_manager.chart_data()
        theme = config.SHOPS.get(self.current_shop) or {
            'bg': '#16181D',
            'text': '#F3F5F8',
            'accent': '#5A6273',
        }
        self.chart_price.draw_bars(names, prices, theme['bg'], theme['text'], theme['accent'])
        self.chart_dist.draw_hist(prices, theme['bg'], theme['text'], theme['accent'])

    def save_chart(self, canvas: ChartCanvas, default_name: str):
        path, _ = QFileDialog.getSaveFileName(self, 'Сохранить диаграмму', default_name, 'PNG (*.png)')
        if path:
            canvas.figure.savefig(path, dpi=150, bbox_inches='tight')


def except_hook(cls, value, traceback):
    sys.__excepthook__(cls, value, traceback)


if __name__ == '__main__':
    sys.excepthook = except_hook
    db_manager = DatabaseManager(config.DB_PATH)
    db_manager.connect()
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = ParsePanel(db_manager)
    window.show()
    sys.exit(app.exec())
