#!/usr/bin/env python3
"""Simulate 10k file creation events to trigger Pyrefly's didChangeWatchedFiles."""

import os
import time

NUM_FILES = 10000
PREFIX = "_pyrefly_trigger_"


def main():
    print(f"Creating {NUM_FILES} .py files...")
    start = time.time()

    # Create files
    for i in range(NUM_FILES):
        filename = f"{PREFIX}{i}.py"
        with open(filename, "w") as f:
            f.write(f"# trigger file {i}\n")
        if (i + 1) % 500 == 0:
            time.sleep(1)
        if (i + 1) % 1000 == 0:
            print(f"  Created {i + 1} files...")

    create_time = time.time() - start
    print(f"Created {NUM_FILES} files in {create_time:.2f}s")

    input("\nPress Enter to delete all files...")

    # Delete files
    print(f"Deleting {NUM_FILES} .py files...")
    start = time.time()

    for i in range(NUM_FILES):
        filename = f"{PREFIX}{i}.py"
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass
        if (i + 1) % 500 == 0:
            time.sleep(1)
        if (i + 1) % 1000 == 0:
            print(f"  Deleted {i + 1} files...")

    delete_time = time.time() - start
    print(f"Deleted {NUM_FILES} files in {delete_time:.2f}s")


if __name__ == "__main__":
    main()
