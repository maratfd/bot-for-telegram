import sqlite3

class Database:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._create_tables()
    
    def _create_tables(self):
        """Создаем таблицы пользователей и товаров"""
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            username TEXT
        )""")
        self.conn.commit()
    
    def add_user(self, user_id, username):
        """Добавляем пользователя в БД"""
        self.cursor.execute(
            "INSERT OR IGNORE INTO users VALUES (?, ?)",
            (user_id, username)
        )
        self.conn.commit()
