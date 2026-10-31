# app/core/database.py
from sqlmodel import create_engine, Session, SQLModel
from .config import settings

# PostgreSQL Connection String
# Format: postgresql+psycopg2://<username>:<password>@<host>:<port>/<dbname>
DATABASE_URL = settings.database_url  # We will add this to settings next

# Create the SQLModel engine
engine = create_engine(DATABASE_URL, echo=settings.debug_mode)

# Function to create the database tables (optional, useful for development)
def create_db_and_tables():
    """Creates the database tables based on the SQLModel metadata."""
    # SQLModel.metadata is the container for all tables defined in your project
    SQLModel.metadata.create_all(engine)

# Context manager for creating database sessions
def get_session():
    """Context manager to easily create and close database sessions."""
    with Session(engine) as session:
        yield session
