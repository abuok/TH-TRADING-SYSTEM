import os
import sys

# Add root to path
sys.path.append(os.getcwd())

from shared.database.session import engine, Base
from shared.database.models import Base as ModelsBase

def repair():
    print("Initializing missing tables in trading.db...")
    # This will only create tables that don't exist
    ModelsBase.metadata.create_all(bind=engine)
    print("Done.")

if __name__ == "__main__":
    repair()
