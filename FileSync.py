from datetime import datetime
import os
import shutil
import platform
import sys
from tqdm import tqdm
import logging
from tkinter import filedialog
from tkinter import Tk

# Define paths
LOG_DIR = 'logs'
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Define the checkpoint file path
CHECKPOINT_FILE = os.path.join(LOG_DIR, 'checkpoint.txt')

# Generate a unique run identifier using the current timestamp
RUN_ID = datetime.now().strftime('%d %B %Y - %H:%M:%S')

# Configure the main logger
main_logger = logging.getLogger('main')
main_logger.setLevel(logging.INFO)
main_handler = logging.FileHandler(os.path.join(LOG_DIR, 'main_logger.log'))
main_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
main_logger.addHandler(main_handler)



def log_all_files_in_dir2(all_files_in_dir2):
    """
    Log all the files in directory2 to a separate log file.
    """
    if all_files_in_dir2:
        logger2 = logging.getLogger('AllFilesInDirectory2')
        logger2.setLevel(logging.INFO)
        file_handler2 = logging.FileHandler(os.path.join(LOG_DIR, 'all_files_in_directory2.log'))
        file_handler2.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger2.addHandler(file_handler2)
        
        logger2.info("\n" + "\n" + "-"*40 + f" New Run: {RUN_ID} " + "-"*40 + "\n" + "\n")
    
        logger2.info(f"Number of files found in directory 2: {len(all_files_in_dir2)}")
        for file_path in all_files_in_dir2:
            logger2.info(file_path)

def log_missing_files_from_checkpoint(checkpoint_files, all_files_in_dir2):
    """
    Log files that are in the checkpoint log but not found in directory 2.
    """
    missing_files_from_checkpoint = [file for file in checkpoint_files if file not in all_files_in_dir2]
    if missing_files_from_checkpoint:
        logger3 = logging.getLogger('MissingFilesFromCheckpoint')
        logger3.setLevel(logging.INFO)
        file_handler3 = logging.FileHandler(os.path.join(LOG_DIR, 'missing_files_from_checkpoint.log'))
        file_handler3.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger3.addHandler(file_handler3)
        
        logger3.info("\n" + "\n" + "-"*40 + f" New Run: {RUN_ID} " + "-"*40 + "\n" + "\n")
        
        logger3.info(f"{len(missing_files_from_checkpoint)} file(s) present in the checkpoint")
        for file_path in missing_files_from_checkpoint:
            logger3.info(file_path)
        
       # Ask user whether to create the missing files
        if len(missing_files_from_checkpoint) > 2:
            user_input = input(f"There are {len(missing_files_from_checkpoint)} files missing. Do you want to copy all of them? (y/n): ")
            if user_input.lower() in ['yes', 'y']:
                copy_all = True
            else:
                copy_all = False
        else:
            copy_all = False

        for file_path in missing_files_from_checkpoint:
            if not copy_all:
                user_input = input(f"Do you want to copy the missing file {file_path}? (y/n): ")
                if user_input.lower() not in ['yes', 'y']:
                    main_logger.info(f"File copy skipped for {file_path}")
                    continue
            src_file = os.path.join(directory_path1, file_path)
            dst_file = os.path.join(directory_path2, file_path)
            copy_file_with_timestamp(src_file, dst_file)
            main_logger.info(f"Copied file: {file_path}")

def save_checkpoint(files_processed):
    """
    Save the current progress (list of processed files) to the checkpoint file.
    """
    with open(CHECKPOINT_FILE, 'w') as f:
        for file in files_processed:
            f.write(file + '\n')

def load_checkpoint():
    """
    Load the list of processed files from the checkpoint file.
    """
    files_processed = []
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            files_processed = [line.strip() for line in f.readlines()]
    return files_processed

def find_missing_files_and_all_files(dir1, dir2):
    """
    This function returns a tuple containing:
    1. A list of files and folders that are in dir1 but not in dir2.
    2. A list of all files and folders in dir2.
    3. Find missing files and folders in dir2 compared to dir1
    """
    # Get the list of files and folders in dir1
    files_in_dir1 = []
    for root, dirs, files in os.walk(dir1):
        for file in files:
            files_in_dir1.append(os.path.relpath(os.path.join(root, file), dir1))

    # Get the list of files and folders in dir2
    files_in_dir2 = []
    for root, dirs, files in os.walk(dir2):
        for file in files:
            files_in_dir2.append(os.path.relpath(os.path.join(root, file), dir2))

    # Find missing files and folders in dir2 compared to dir1
    missing_files = set(files_in_dir1) - set(files_in_dir2)

    return list(missing_files), files_in_dir2

def copy_file_with_timestamp(src, dst):
    """
    This function copies a file or directory from src to dst without modifying its created time.
    """
    try:
        # Check if source exists
        if os.path.exists(src):
            # Check if source is a directory
            if os.path.isdir(src):
                # Create the destination directory if it doesn't exist
                if not os.path.exists(dst):
                    os.makedirs(dst)
                # Recursively copy the directory and its contents
                for item in os.listdir(src):
                    src_item = os.path.join(src, item)
                    dst_item = os.path.join(dst, item)
                    copy_file_with_timestamp(src_item, dst_item)
            else:
                # Create the parent directory if it doesn't exist
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                # Copy the file with timestamp preservation
                shutil.copy2(src, dst)
                # Preserve timestamps
                if platform.system() == 'Windows':
                    os.utime(dst, (os.path.getatime(dst), os.path.getmtime(dst)))
                else:
                    shutil.copystat(src, dst)
        else:
            main_logger.error(f"Source '{src}' not found.")
    except Exception as e:
        main_logger.error(f"Error occurred while copying {src}: {e}")
        # Remove the partially copied file if an error occurs during copying
        if os.path.exists(dst):
            os.remove(dst)

def select_directory(title):
    """
    Opens a file dialog to select a directory and returns the path.
    """
    root = Tk()
    root.withdraw()  # Hide the main window
    directory_path = filedialog.askdirectory(title=title)

    # If the selected directory is an absolute path, return it as is
    if os.path.isabs(directory_path):
        return directory_path

    # Otherwise, construct the absolute path based on the current working directory
    print(os.path.abspath(directory_path))
    return os.path.abspath(directory_path)


def main():
    global directory_path1, directory_path2  # Declare global variables to modify them inside the function

    main_logger.info("\n" + "\n" + "-"*40 + f" New Run: {RUN_ID} " + "-"*40 + "\n" + "\n")
    
    # Get source and destination paths from the user
    print("Select the source directory:")
    directory_path1 = select_directory("Select Source Directory")
    print("\nSelect the destination directory:")
    directory_path2 = select_directory("Select Destination Directory")
    
    main_logger.info(f"Selected source paths: {directory_path1}")
    main_logger.info(f"Selected destination paths: {directory_path2}")
    
    if directory_path1 == '' or directory_path2 == '':
        print("\nSource and destination cannot be pointed to the root of the program")
        main_logger.info("Source and destination cannot be pointed to the root of the program")
        sys.exit(0)
    elif directory_path1 == directory_path2:
        print("\nSource and destination cannot be the same")
        main_logger.info("Source and destination cannot be the same")
        sys.exit(0)
    
    user_input = input(f"\nWrite 'Confirm' or 'c': ")
    print("\n\n")
    if user_input.lower() in ['confirm', 'c']:        
        # Load the checkpoint to determine the progress
        checkpoint_files = load_checkpoint()
        files_processed = list(checkpoint_files)
        missing_files, all_files_in_dir2 = find_missing_files_and_all_files(directory_path1, directory_path2)
        missing_files = [file for file in missing_files if file not in files_processed]

        main_logger.info(f"{len(missing_files)} file(s) missing from directory 2")

        try:
            if missing_files:
                main_logger.info("Copying missing files to directory 2:")
                with tqdm(total=len(missing_files)) as pbar:
                    for file in missing_files:
                        main_logger.info(f"Current File: {file}")
                        pbar.update(1)
                        pbar.set_description(f"Copying {file}")
                        src_file = os.path.join(directory_path1, file)
                        dst_file = os.path.join(directory_path2, file)
                        copy_file_with_timestamp(src_file, dst_file)
                        files_processed.append(file)
                        save_checkpoint(files_processed)
                main_logger.info("All files copied successfully!")
            
            # Log all the files in directory2 to a separate log file
            log_all_files_in_dir2(all_files_in_dir2)
            
            # Log missing files from the checkpoint log
            log_missing_files_from_checkpoint(checkpoint_files, all_files_in_dir2)
        except Exception as e:
            main_logger.error(f"An error occurred: {e}")
            try:
                main_logger.info("\nOperation interrupted by the user.")
                main_logger.info(f"Removing {dst_file} as it was being processed.")
                if os.path.exists(dst_file):
                    os.remove(dst_file)
                # Remove the interrupted file from the progress list and save the updated checkpoint
                files_processed.remove(file)
                save_checkpoint(files_processed)
                main_logger.info(f"{dst_file} File removed.")
                main_logger.info("Operation aborted.")
            except PermissionError:
                # Handle permission errors gracefully
                main_logger.error(f"Permission denied to remove file: {dst_file}")
            except FileNotFoundError:
                # Handle file not found errors gracefully
                main_logger.error(f"File not found: {dst_file}")

if __name__ == "__main__":
    main()

