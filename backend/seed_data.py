import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import db_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    print("=== SEEDING DATABASE SCRIPT ===")
    if not db_manager.is_connected:
        print("[WARNING] MongoDB is not connected! Please set MONGODB_URI in .env to seed MongoDB.")
        print("Defaulting to local data files.")
        return

    print("Connected to MongoDB! Starting database seeding...")
    db_manager.seed_scripts_database(force=True)
    print("Seeding completed successfully!")

if __name__ == "__main__":
    main()

