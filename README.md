# RomSorter

A Python script to organize your emulator ROM collection by identifying the best version of each game based on your preferences and moving the rest to an archive.

## Features

- Scans a directory recursively for ROM files.
- Groups ROMs by game, ignoring minor name variations.
- Ranks different versions of the same game based on user-defined criteria (e.g., region, language, verified good dumps).
- Moves the best version to a clean directory.
- Moves all other versions to an archive directory.
- Dry-run mode to see what changes will be made without moving any files.
- Detailed logging.

## How to Use

1.  **Configure:** Edit `config.yaml` to set your source, destination, and archive directories, and to define your ranking criteria.
2.  **Run:** Execute the script from your terminal:

    ```bash
    python rom_sorter.py
    ```

3.  **Dry Run:** It is highly recommended to perform a dry run first to ensure the script will do what you expect:

    ```bash
    python rom_sorter.py --dry-run
    ```
