import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, make_transient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import Flask app and DB components
from app import app
from database import db
from models import User, Scrape, Video, Comment, Like, SavedVideo, WatchHistory

def run_migration():
    # 1. Connect to SQLite Source
    sqlite_path = 'instance/app.db'
    if not os.path.exists(sqlite_path):
        print(f"Error: SQLite database file not found at {sqlite_path}")
        return
        
    sqlite_url = f'sqlite:///{sqlite_path}'
    src_engine = create_engine(sqlite_url)
    SQLiteSession = sessionmaker(bind=src_engine)
    src_session = SQLiteSession()
    
    # 2. Connect to PostgreSQL Destination using Flask App Context
    with app.app_context():
        print("Dropping old database tables in PostgreSQL to reset schema...")
        db.drop_all()
        print("Creating fresh database tables in PostgreSQL...")
        db.create_all()  # Ensure all tables exist in PostgreSQL
        
        dest_session = db.session
        
        # Order models to satisfy Foreign Key dependencies
        models = [User, Scrape, Video, Comment, Like, SavedVideo, WatchHistory]
        
        print("\nStarting migration...")
        for model in models:
            table_name = model.__table__.name
            print(f"\n--- Migrating {model.__name__} ---")
            
            # Fetch SQLite records
            records = src_session.query(model).all()
            print(f"Found {len(records)} records in SQLite.")
            
            if not records:
                print(f"No records to migrate for {model.__name__}.")
                continue
                
            # Clear target table for a clean fresh dump
            print(f"Clearing existing records in PostgreSQL table \"{table_name}\"...")
            try:
                dest_session.execute(text(f'TRUNCATE TABLE "{table_name}" CASCADE'))
                dest_session.commit()
            except Exception as e:
                dest_session.rollback()
                # If TRUNCATE CASCADE fails, fallback to simple delete
                try:
                    dest_session.query(model).delete()
                    dest_session.commit()
                except Exception as del_err:
                    dest_session.rollback()
                    print(f"Warning: Could not clear target table: {del_err}")
            
            # Transfer records
            print(f"Writing {len(records)} records to PostgreSQL...")
            for record in records:
                src_session.expunge(record)
                make_transient(record)
                dest_session.add(record)
                
            try:
                dest_session.commit()
                print(f"Successfully migrated {model.__name__}!")
            except Exception as e:
                dest_session.rollback()
                print(f"Error migrating {model.__name__}: {e}")
                
        # 3. Reset PostgreSQL Primary Key Sequences
        print("\nResetting PostgreSQL primary key sequences...")
        tables = {
            'user': 'user_id_seq',
            'scrape': 'scrape_id_seq',
            'video': 'video_id_seq',
            'comment': 'comment_id_seq',
            'like': 'like_id_seq',
            'saved_video': 'saved_video_id_seq',
            'watch_history': 'watch_history_id_seq'
        }
        
        for table_name, seq_name in tables.items():
            try:
                query = f"SELECT setval('{seq_name}', COALESCE((SELECT MAX(id)+1 FROM \"{table_name}\"), 1), false)"
                db.session.execute(text(query))
                db.session.commit()
                print(f"Successfully reset sequence for table: {table_name}")
            except Exception as e:
                db.session.rollback()
                print(f"Could not reset sequence for {table_name}: {e}")
                
    print("\nData migration completed successfully! All data has been dumped to PostgreSQL.")

if __name__ == '__main__':
    run_migration()
