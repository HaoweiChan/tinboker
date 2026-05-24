"""
Database initialization and connection management for SQLite
"""
import os
import sqlite3
from pathlib import Path
from src.config import settings


def get_db_path() -> str:
    """Get database file path, creating directory if needed"""
    db_path = settings.database_path
    db_dir = os.path.dirname(db_path)
    if db_dir:
        Path(db_dir).mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection() -> sqlite3.Connection:
    """Get SQLite database connection"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    return conn


def init_db():
    """Initialize database by creating all tables if they don't exist"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Create stocks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                ticker TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL,
                change REAL,
                change_percent REAL,
                market_cap INTEGER,
                revenue INTEGER,
                pe REAL,
                dividend_yield REAL,
                about TEXT,
                volume INTEGER,
                beta REAL,
                volatility REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create stock_history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                FOREIGN KEY (ticker) REFERENCES stocks(ticker) ON DELETE CASCADE,
                UNIQUE(ticker, date)
            )
        """)
        
        # Create index on stock_history for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_stock_history_ticker_date 
            ON stock_history(ticker, date DESC)
        """)
        
        # Create graphs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graphs (
                id TEXT PRIMARY KEY,
                concept_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create graph_nodes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                node_type TEXT NOT NULL,
                label TEXT NOT NULL,
                ticker TEXT NOT NULL,
                market_cap_tier TEXT NOT NULL,
                position_x REAL NOT NULL,
                position_y REAL NOT NULL,
                FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE,
                UNIQUE(graph_id, node_id)
            )
        """)
        
        # Create graph_edges table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_id TEXT NOT NULL,
                edge_id TEXT NOT NULL,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                label TEXT NOT NULL,
                category TEXT NOT NULL,
                FOREIGN KEY (graph_id) REFERENCES graphs(id) ON DELETE CASCADE,
                UNIQUE(graph_id, edge_id)
            )
        """)
        
        # Create news table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                date INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create news_tickers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_tickers (
                news_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                PRIMARY KEY (news_id, ticker),
                FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE
            )
        """)
        
        # Create comments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY,
                podcast_name TEXT NOT NULL,
                episode_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                user_avatar TEXT,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                parent_comment_id TEXT REFERENCES comments(id) ON DELETE SET NULL,
                depth INTEGER NOT NULL DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_comments_episode
            ON comments(podcast_name, episode_id, created_at ASC)
        """)

        # Migrate existing DBs: add threading columns if they don't exist.
        # NOTE: SQLite ALTER TABLE ADD COLUMN cannot reliably add a column with a
        # FOREIGN KEY (REFERENCES) clause — we skip it on the migration path. Fresh
        # DBs still get the FK via the CREATE TABLE above.
        existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(comments)").fetchall()}
        if "parent_comment_id" not in existing_cols:
            cursor.execute("ALTER TABLE comments ADD COLUMN parent_comment_id TEXT")
        if "depth" not in existing_cols:
            cursor.execute("ALTER TABLE comments ADD COLUMN depth INTEGER NOT NULL DEFAULT 0")

        conn.commit()
        print(f"Database initialized successfully at {get_db_path()}")
    except Exception as e:
        conn.rollback()
        print(f"Error initializing database: {e}")
        raise
    finally:
        conn.close()


def ensure_db_initialized() -> None:
    """Ensure database is initialized (call on startup)."""
    init_db()

