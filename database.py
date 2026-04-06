"""
Database initialization and migrations
"""
from flask_sqlalchemy import SQLAlchemy #type:ignore
from sqlalchemy import text #type:ignore

db = SQLAlchemy()

def init_db(app):
    """Initialize database with app context"""
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        run_migrations()
        with db.engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL;"))
            conn.execute(text("PRAGMA busy_timeout=30000;"))
            conn.commit()

def run_migrations():
    """Run all database migrations"""
    # Migration: Add started_at column
    try:
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE scrape ADD COLUMN started_at DATETIME'))
            conn.commit()
        print("Added started_at column")
    except Exception as e:
        if 'duplicate column' not in str(e).lower() and 'already exists' not in str(e).lower():
            print(f"Migration warning: {e}")
    
    # Migration: Add platforms column
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE scrape ADD COLUMN platforms VARCHAR(100) DEFAULT 'all'"))
            conn.commit()
        print("Added platforms column")
    except Exception as e:
        if 'duplicate column' not in str(e).lower() and 'already exists' not in str(e).lower():
            print(f"Migration warning: {e}")
    
    # Migration: Add filename to Like table
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE 'like' ADD COLUMN filename VARCHAR(200)"))
            conn.commit()
        print("Added filename column to Like table")
    except Exception as e:
        if 'duplicate column' not in str(e).lower() and 'already exists' not in str(e).lower():
            print(f"Migration warning: {e}")
    
    # Migration: Add filename to Comment table
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE comment ADD COLUMN filename VARCHAR(200)"))
            conn.commit()
        print("Added filename column to Comment table")
    except Exception as e:
        if 'duplicate column' not in str(e).lower() and 'already exists' not in str(e).lower():
            print(f"Migration warning: {e}")
    
    # Migrate existing data
    try:
        with db.engine.connect() as conn:
            conn.execute(text("""
                UPDATE 'like' 
                SET filename = (SELECT filename FROM video WHERE video.id = 'like'.video_id)
                WHERE video_id IS NOT NULL AND filename IS NULL
            """))
            conn.execute(text("""
                UPDATE comment 
                SET filename = (SELECT filename FROM video WHERE video.id = comment.video_id)
                WHERE video_id IS NOT NULL AND filename IS NULL
            """))
            conn.commit()
    except Exception as e:
        pass
    
    # Create indexes
    try:
        with db.engine.connect() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_like_filename ON 'like'(filename)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_comment_filename ON comment(filename)"))
            conn.commit()
    except Exception as e:
        pass
