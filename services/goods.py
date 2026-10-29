from PyQt6.QtCore import Qt
from PyQt6.QtSql import QSqlDatabase, QSqlQuery, QSqlRelationalTableModel, QSqlRelation

from config import SHOPS


class DatabaseManager:
    def __init__(self, db_name=':memory:'):
        self.db = QSqlDatabase.addDatabase('QSQLITE')
        self.db.setDatabaseName(db_name)
        self.model = None

    def connect(self):
        if not self.db.open():
            return False
        query = QSqlQuery(self.db)
        query.exec('PRAGMA foreign_keys = ON;')
        self.create_table()
        self.init_model()
        return True

    def create_table(self):
        query = QSqlQuery(self.db)
        query.exec('CREATE TABLE IF NOT EXISTS shops (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)')
        query.exec(
            'CREATE TABLE IF NOT EXISTS goods ('
            'id INTEGER PRIMARY KEY AUTOINCREMENT,'
            'name TEXT NOT NULL,'
            'link TEXT NOT NULL,'
            'price REAL NOT NULL,'
            'shop_id INTEGER,'
            'FOREIGN KEY (shop_id) REFERENCES shops(id)'
            ')'
        )
        query.exec('PRAGMA table_info(goods)')
        columns = set()
        while query.next():
            columns.add(str(query.value(1)))
        if 'description' in columns and 'link' not in columns:
            query.exec('ALTER TABLE goods RENAME COLUMN description TO link')
        for shop in SHOPS.values():
            query.prepare('SELECT id FROM shops WHERE name = ?')
            query.addBindValue(shop['name'])
            query.exec()
            if not query.next():
                insert = QSqlQuery(self.db)
                insert.prepare('INSERT INTO shops (name) VALUES (?)')
                insert.addBindValue(shop['name'])
                insert.exec()

    def init_model(self):
        self.model = QSqlRelationalTableModel(db=self.db)
        self.model.setTable('goods')
        self.model.setRelation(4, QSqlRelation('shops', 'id', 'name'))
        self.model.setEditStrategy(QSqlRelationalTableModel.EditStrategy.OnManualSubmit)
        self.model.setHeaderData(0, Qt.Orientation.Horizontal, 'ID')
        self.model.setHeaderData(1, Qt.Orientation.Horizontal, 'Название')
        self.model.setHeaderData(2, Qt.Orientation.Horizontal, 'Ссылка')
        self.model.setHeaderData(3, Qt.Orientation.Horizontal, 'Цена')
        self.model.setHeaderData(4, Qt.Orientation.Horizontal, 'Магазин')
        self.model.select()

    def get_model(self):
        return self.model

    def get_shop_id(self, shop_name):
        query = QSqlQuery(self.db)
        query.prepare('SELECT id FROM shops WHERE name = ?')
        query.addBindValue(shop_name)
        if query.exec() and query.next():
            return query.value(0)
        return None

    def add_good(self, name, link, price, shop_id):
        query = QSqlQuery(self.db)
        query.prepare('INSERT INTO goods (name, link, price, shop_id) VALUES (?, ?, ?, ?)')
        query.addBindValue(name)
        query.addBindValue(link)
        query.addBindValue(price)
        query.addBindValue(shop_id)
        return query.exec()

    def add_goods(self, goods_list):
        ok = True
        for goods in goods_list:
            if not self.add_good(
                name=goods.get('name'),
                link=goods.get('link'),
                price=goods.get('price'),
                shop_id=goods.get('shop_id'),
            ):
                ok = False
        self.model.select()
        return ok

    def save_changes(self):
        if self.model.submitAll():
            self.model.select()
            return True
        self.model.revertAll()
        return False

    def delete_good(self, row_idx):
        if row_idx >= 0:
            self.model.removeRow(row_idx)

    def filter_by_shop_name(self, shop_name):
        if shop_name:
            shop_id = self.get_shop_id(shop_name)
            if shop_id is None:
                self.model.setFilter("shop_id = -1")
            else:
                self.model.setFilter(f'shop_id = {int(shop_id)}')
        else:
            self.model.setFilter('')
        self.model.select()

    def chart_data(self):
        names = []
        prices = []
        for row in range(self.model.rowCount()):
            name = self.model.data(self.model.index(row, 1))
            price = self.model.data(self.model.index(row, 3))
            if name is None or price is None:
                continue
            try:
                prices.append(float(price))
            except (TypeError, ValueError):
                continue
            names.append(str(name))
        return names, prices

    def close(self):
        if self.db.isOpen():
            self.db.close()
