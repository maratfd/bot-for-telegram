import sqlite3

class Database:
    def __init__(self, db_file):
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()
        self._init_db()

    def _init_db(self):
        # Таблица пользователей
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY
        )
        """)
        
        # Таблица товаров
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            photo TEXT
        )
        """)
        
        # Таблица корзины
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER,
            product_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
        """)
        self.connection.commit()

    def user_exists(self, user_id):
        self.cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        return bool(self.cursor.fetchone())

    def add_user(self, user_id):
        self.cursor.execute("INSERT INTO users (id) VALUES (?)", (user_id,))
        self.connection.commit()

    def add_product(self, name, description, price, photo):
        self.cursor.execute("""
        INSERT INTO products (name, description, price, photo)
        VALUES (?, ?, ?, ?)
        """, (name, description, price, photo))
        self.connection.commit()

    def get_products(self):
        self.cursor.execute("SELECT * FROM products")
        return self.cursor.fetchall()

    def get_product(self, product_id):
        self.cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        return self.cursor.fetchone()

    def add_to_cart(self, user_id, product_id):
        self.cursor.execute("INSERT INTO cart (user_id, product_id) VALUES (?, ?)", (user_id, product_id))
        self.connection.commit()

    def get_cart(self, user_id):
        self.cursor.execute("""
        SELECT p.id, p.name, p.description, p.price 
        FROM cart c 
        JOIN products p ON c.product_id = p.id 
        WHERE c.user_id = ?
        """, (user_id,))
        return self.cursor.fetchall()

    def clear_cart(self, user_id):
        self.cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        self.connection.commit()
