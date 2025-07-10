import argparse
import logging
import os
import pathlib
import re
import shutil
import sys

import yaml

# --- Constants ---
CONFIG_DEFAULTS = {
    'rom_source_dir': './roms',
    'rom_destination_dir': './sorted',
    'archive_dir': './archive',
    'log_file': 'rom_sorter.log',
    'log_level': 'INFO',
    'ranking_criteria': ['[!]'],
    'excluded_dirs': ['images'],
    'excluded_extensions': ['.png', '.jpg']
}


def setup_logging(log_level, log_file):
    """Configures the logging for the application."""
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')

    # Create logger
    logger = logging.getLogger('RomSorter')
    logger.setLevel(numeric_level)

    # The file handler can be explicitly set to use UTF-8 encoding.
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    
    # For the console, we reconfigure stdout to use UTF-8.
    # This is a robust way to handle console encoding issues on Windows.
    sys.stdout.reconfigure(encoding='utf-8')
    console_handler = logging.StreamHandler(sys.stdout)

    # Create formatters and add it to handlers
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # Add handlers to the logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

def normalize_name(name):
    """Normalizes a game name by removing special characters and standardizing spacing."""
    # Remove anything in brackets or parentheses (like region, version, etc.)
    name = re.sub(r'\(.*?\)|\{.*?}|\[.*?]', '', name).strip()
    # Remove leading numerical prefixes (e.g., '001 - ')
    name = re.sub(r'^[0-9\s\-]+', '', name).strip()
    # Replace common separators with a space
    name = re.sub(r'[\s_\-:]+', ' ', name)
    # Remove all non-alphanumeric characters except spaces
    name = re.sub(r"[^a-zA-Z0-9\s']", '', name)
    return name.lower().strip()

def get_rom_rank_vector(filename, ranking_criteria):
    """Creates a ranking vector for a ROM based on all criteria."""
    return [1 if criterion in filename else 0 for criterion in ranking_criteria]


def cleanup_unzipped_duplicates(source_dir, dry_run, excluded_extensions):
    """Scans for and removes unzipped ROMs that have a corresponding .zip file."""
    logger = logging.getLogger('RomSorter')
    logger.info("--- Starting Cleanup of Unzipped Duplicates ---")

    for dirpath, _, filenames in os.walk(source_dir):
        zip_basenames = {pathlib.Path(f).stem for f in filenames if f.lower().endswith('.zip')}
        
        if not zip_basenames:
            continue

        files_to_remove = []
        for f in filenames:
            basename = pathlib.Path(f).stem
            ext = pathlib.Path(f).suffix.lower()
            if basename in zip_basenames and ext != '.zip' and ext not in excluded_extensions:
                files_to_remove.append(pathlib.Path(dirpath) / f)

        for file_path in files_to_remove:
            if dry_run:
                logger.info(f"DRY RUN: DELETE '{file_path}' (duplicate of .zip)")
            else:
                try:
                    logger.info(f"DELETE: '{file_path}' (duplicate of .zip)")
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Failed to delete file: {e}")
    
    logger.info("--- Finished Cleanup ---")


def handle_file_move(source_path, dest_path, dry_run, is_archive=False):
    """Moves or archives a file, or logs the action if in dry-run mode."""
    logger = logging.getLogger('RomSorter')
    action = "ARCHIVE" if is_archive else "MOVE"
    
    if dest_path.exists():
        logger.warning(f"SKIPPING {action}: Destination file already exists: {dest_path}")
        return

    if dry_run:
        logger.info(f"DRY RUN: {action} '{source_path}' -> '{dest_path}'")
    else:
        try:
            logger.info(f"{action}: '{source_path}' -> '{dest_path}'")
            shutil.move(source_path, dest_path)
        except Exception as e:
            logger.error(f"Failed to {action.lower()} file: {e}")


def process_roms(config, dry_run):
    """Main function to scan, group, rank, and move ROMs."""
    logger = logging.getLogger('RomSorter')
    logger.info("--- RomSorter Start ---")
    logger.info(f"Dry Run Mode: {'Enabled' if dry_run else 'Disabled'}")

    source_dir = pathlib.Path(config['rom_source_dir'])
    dest_dir = pathlib.Path(config['rom_destination_dir'])
    archive_dir = pathlib.Path(config['archive_dir'])

    if not source_dir.is_dir():
        logger.error(f"Source directory not found: {source_dir}")
        return

    # Create destination and archive directories if they don't exist
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Scanning for ROMs in: {source_dir}")

    roms_by_game = {}

    # Get exclusion lists from config, defaulting to empty lists if not present
    excluded_dirs = [d.lower() for d in config.get('excluded_dirs', [])]
    excluded_extensions = [e.lower() for e in config.get('excluded_extensions', [])]
    logger.info(f"Excluding directories: {excluded_dirs}")
    logger.info(f"Excluding extensions: {excluded_extensions}")

    # --- Pre-processing Step: Clean up duplicates ---
    cleanup_unzipped_duplicates(source_dir, dry_run, excluded_extensions)

    # 1. Scan for all files recursively and group them
    logger.info(f"Scanning for ROMs in {source_dir}...")
    for filepath in source_dir.rglob('*'):
        if filepath.is_file():
            # Check for excluded extensions
            if filepath.suffix.lower() in excluded_extensions:
                logger.debug(f"Skipping excluded file type: {filepath}")
                continue

            # Check for excluded directories in the path
            # We check if any part of the file's path is in our exclusion list
            if any(part.lower() in excluded_dirs for part in filepath.parent.parts):
                logger.debug(f"Skipping file in excluded directory: {filepath}")
                continue

            base_name = filepath.stem
            extension = filepath.suffix
            normalized = normalize_name(base_name)

            # Group by normalized name and extension to keep systems separate
            game_key = (normalized, extension)
            if game_key not in roms_by_game:
                roms_by_game[game_key] = []
            roms_by_game[game_key].append(filepath)
    
    logger.info(f"Found {len(roms_by_game)} unique games.")

    # 2. Rank and process each game group
    for (game_name, ext), rom_paths in roms_by_game.items():
        if len(rom_paths) == 1:
            # Only one version, move it directly
            rom_path = rom_paths[0]
            target_path = dest_dir / rom_path.name
            logger.info(f"Found single version for '{game_name}{ext}'. Moving to destination.")
            handle_file_move(rom_path, target_path, dry_run)
            continue

        logger.debug(f"Processing group '{game_name}{ext}' with {len(rom_paths)} versions.")
        
        # Rank the ROMs in the current group using vectors for tie-breaking
        best_rom = None
        best_rank_vector = None

        for rom_path in rom_paths:
            rank_vector = get_rom_rank_vector(rom_path.name, config['ranking_criteria'])
            logger.debug(f"  - Found ROM: {rom_path.name} (Rank Vector: {rank_vector})")
            if best_rom is None or rank_vector > best_rank_vector:
                best_rank_vector = rank_vector
                best_rom = rom_path

        if best_rom:
            logger.info(f"Best version for '{game_name}{ext}' is '{best_rom.name}' (Rank: {best_rank_vector})")
            # Move the best ROM to the destination
            target_path = dest_dir / best_rom.name
            handle_file_move(best_rom, target_path, dry_run)

            # Archive the rest
            for rom_path in rom_paths:
                if rom_path != best_rom:
                    archive_path = archive_dir / rom_path.name
                    handle_file_move(rom_path, archive_path, dry_run, is_archive=True)
        else:
            logger.warning(f"Could not determine a best version for '{game_name}{ext}'. Skipping group.")

    logger.info("--- RomSorter Finished ---")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Sorts and organizes emulator ROMs.")
    parser.add_argument('--config', type=str, default='config.yaml', help='Path to the configuration file.')
    parser.add_argument('--dry-run', action='store_true', help='Perform a dry run without moving any files.')

    args = parser.parse_args()

    # Load configuration
    try:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at '{args.config}'. Creating a default one.")
        with open(args.config, 'w') as f:
            yaml.dump(CONFIG_DEFAULTS, f, default_flow_style=False)
        config = CONFIG_DEFAULTS
    except Exception as e:
        print(f"Error loading config file: {e}")
        return

    # Setup logging
    try:
        logger = setup_logging(config.get('log_level', 'INFO'), config.get('log_file', 'rom_sorter.log'))
    except ValueError as e:
        print(f"Error setting up logger: {e}")
        return

    process_roms(config, args.dry_run)


if __name__ == '__main__':
    main()
