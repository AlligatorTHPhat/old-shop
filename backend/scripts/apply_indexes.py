"""Apply reviewed additive indexes; PostgreSQL uses the existing migration runner."""

from scripts.indexes import main

if __name__ == "__main__":
    main("apply")
