"""Verify applied snapshots; use --desired to verify a proposed catalog explicitly."""

from scripts.indexes import main

if __name__ == "__main__":
    main("verify")
