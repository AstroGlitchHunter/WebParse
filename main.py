import sys
import config
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox
from interface import ParsePanel
from services.goods import DatabaseManager


class MainWindow(QMainWindow):
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Парсер магазинов')
        self.panel = ParsePanel(self.db_manager)
        self.setCentralWidget(self.panel)
        self.resize(1180, 820)
        self.setStyleSheet(config.load_stylesheet())

    def closeEvent(self, event):
        self.db_manager.close()
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QFont('Segoe UI', 10))
    db_manager = DatabaseManager(config.DB_PATH)
    if not db_manager.connect():
        QMessageBox.critical(None, 'База данных', 'Не удалось открыть базу данных')
        sys.exit(1)
    window = MainWindow(db_manager)
    window.show()
    sys.exit(app.exec())
