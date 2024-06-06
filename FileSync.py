from datetime import datetime
import os
import shutil
import platform
import time
from tqdm import tqdm
import logging
from tkinter import filedialog, Tk
import subprocess
import win32file
import pywintypes

LOG_DIR = 'logs'
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

CHECKPOINT_FILE = os.path.join(LOG_DIR, 'checkpoint.txt')

RUN_ID = datetime.now().strftime('%d %B %Y - %H:%M:%S')

main_logger = logging.getLogger('main')
main_logger.setLevel(logging.INFO)
main_handler = logging.FileHandler(os.path.join(LOG_DIR, 'main_logger.log'))
main_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
main_logger.addHandler(main_handler)

# Paste the path to adb.exe here
adb_path = r"C:\Users\platform-tools-latest-windows\platform-tools\adb.exe"

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
        
        if len(missing_files_from_checkpoint) > 2:
            user_input = input(f"There are {len(missing_files_from_checkpoint)} files missing. Do you want to copy all of them? (y/n): ")
            copy_all = user_input.lower() in ['yes', 'y']
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

# If permission needed you can force permit the entry point.
def grant_permissions_via_adb(directory_path, selected_device_id):
    try:
        subprocess.run([adb_path, '-s', selected_device_id,  'root'], check=True)  # Ensure the device is in root mode or ADB debugging as True
        subprocess.run([adb_path, '-s', selected_device_id,  'shell', 'chmod', '-R', '777', directory_path], check=True)
        print("Permissions granted successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while granting permissions: {e}")

def find_missing_files_and_all_files(dir1, dir2, selected_device_id, dir1_is_mtp=False, dir2_is_mtp=False):
    """
    This function returns a tuple containing:
    1. A list of files and folders that are in dir1 but not in dir2.
    2. A list of all files and folders in dir2.
    3. Find missing files and folders in dir2 compared to dir1
    """
    def list_files_mtp(directory):
        try:
            output = subprocess.check_output([adb_path, '-s', selected_device_id,  'shell', 'ls', '-R', directory]).decode()
            
            file_paths = []
            current_dir = directory
            for line in output.splitlines():
                if line.endswith(':'):
                    current_dir = line[:-1]
                elif line:
                    file_paths.append(os.path.join(current_dir, line))
            return file_paths
        except subprocess.CalledProcessError as e:
            main_logger.error(f"Error listing MTP files: {e}")
            return []

    def list_files_local(directory):
        file_paths = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_paths.append(os.path.relpath(os.path.join(root, file), directory))
        return file_paths

    files_in_dir1 = list_files_mtp(dir1) if dir1_is_mtp else list_files_local(dir1)
    files_in_dir2 = list_files_mtp(dir2) if dir2_is_mtp else list_files_local(dir2)

    missing_files = set(files_in_dir1) - set(files_in_dir2)

    return list(missing_files), files_in_dir2

def copy_file_with_timestamp(src, dst):
    """
    This function copies a file or directory from src to dst without modifying its created time.
    """
    try:
        if os.path.exists(src):
            # Check if source is a directory
            if os.path.isdir(src):
                # Create the destination directory if it doesn't exist
                if not os.path.exists(dst):
                    os.makedirs(dst)
                # Recursively copy the directory and its contents
                for item in os.listdir(src):
                    copy_file_with_timestamp(os.path.join(src, item), os.path.join(dst, item))
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
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

def file_exists_on_phone(phone_file_path, selected_device_id):
    try:
        result = subprocess.run([adb_path, '-s', selected_device_id,  'shell', 'ls', phone_file_path], capture_output=True, text=True)
        return 'No such file or directory' not in result.stderr
    except subprocess.CalledProcessError as e:
        main_logger.error(f"Error checking file existence on phone: {e}")
        return False

def copy_files_to_phone(local_folder, phone_directory, selected_device_id):
    for root, dirs, files in os.walk(local_folder):
        relative_path = os.path.relpath(root, local_folder)
        phone_path = os.path.join(phone_directory, relative_path).replace('\\', '/')

        for file in files:
            local_file = os.path.join(root, file)
            phone_file = os.path.join(phone_path, file).replace('\\', '/')
            if not file_exists_on_phone(phone_file, selected_device_id):
                try:
                    subprocess.run([adb_path, '-s', selected_device_id,  'push', '-p', local_file, phone_file], check=True)
                    main_logger.info(f"Copied {local_file} to {phone_file}")
                except subprocess.CalledProcessError as e:
                    main_logger.error(f"Error copying {local_file} to {phone_file}: {e}")
            else:
                main_logger.info(f"File {phone_file} already exists on the phone. Skipping copy.")

# Might break as this is configured for my own purpose``
def get_file_times(phone_file, selected_device_id):
    try:
        result = subprocess.check_output([adb_path, '-s', selected_device_id,  'shell', 'ls', '-l', phone_file]).decode().strip()
        parts = result.split()
        if len(parts) < 8:
            raise ValueError("Unexpected output from ls command")
        modify_time_str = parts[5] + " " + parts[6]
        modify_time = int(time.mktime(datetime.strptime(modify_time_str, "%Y-%m-%d %H:%M").timetuple()))
        return modify_time
    except (subprocess.CalledProcessError, ValueError) as e:
        main_logger.error(f"Error getting file times for {phone_file}: {e}")
        return None

def copy_files_to_local(phone_directory, local_folder, selected_device_id):
    try:
        phone_files = subprocess.check_output([adb_path, '-s', selected_device_id,  'shell', 'find', phone_directory, '-type', 'f']).decode().splitlines()
        for phone_file in phone_files:
            relative_path = os.path.relpath(phone_file, phone_directory)
            local_file = os.path.join(local_folder, relative_path).replace('/', os.sep)
            local_file_dir = os.path.dirname(local_file)
            if not os.path.exists(local_file_dir):
                os.makedirs(local_file_dir)
            
            if not os.path.exists(local_file):
                try:
                    subprocess.run([adb_path, '-s', selected_device_id,  'pull', phone_file, local_file], check=True)
                    modify_time = get_file_times(phone_file, selected_device_id)
                    if modify_time:
                        current_time = pywintypes.Time(modify_time)  # Convert to pywintypes.Time
                        file_handle = win32file.CreateFile(local_file, win32file.GENERIC_WRITE, 0, None, win32file.OPEN_EXISTING, 0, 0)
                        win32file.SetFileTime(file_handle, CreationTime=current_time, LastAccessTime=current_time, LastWriteTime=current_time)
                        win32file.CloseHandle(file_handle)
                    main_logger.info(f"Copied {phone_file} to {local_file}")
                except subprocess.CalledProcessError as e:
                    main_logger.error(f"Error copying {phone_file} to {local_file}: {e}")
            else:
                main_logger.info(f"File {local_file} already exists locally. Skipping copy.")
    except subprocess.CalledProcessError as e:
        main_logger.error(f"Error retrieving files from phone: {e}")

def select_directory(title):
    """
    Opens a file dialog to select a directory and returns the path.
    """
    root = Tk()
    root.withdraw()
    directory_path = filedialog.askdirectory(title=title)

    if os.path.isabs(directory_path):
        return directory_path

    return os.path.abspath(directory_path)

def list_phone_directories(selected_device_id, current_path="/sdcard/"):
    try:
        root_contents = subprocess.check_output([adb_path, '-s', selected_device_id,  '-s', selected_device_id, 'shell', 'ls', current_path]).decode().splitlines()
        print(f"Available directories in {current_path}:")
        for directory in root_contents:
            print(directory)
        return root_contents
    except subprocess.CalledProcessError as e:
        main_logger.error(f"Error listing phone directories: {e}")
        return None

def traverse_mtp_directories(selected_device_id, current_path="/sdcard/"):
    while True:
        directories = list_phone_directories(selected_device_id, current_path)
        if directories is None:
            break
        
        user_input = input("Enter directory to traverse, '..' to go back, or 'select' to choose this directory: ")
        if user_input == 'select':
            return current_path
        elif user_input == '..':
            if current_path == "/sdcard/":
                print("Already at root directory. Can't go back further.")
            else:
                current_path = os.path.dirname(current_path.rstrip('/')) + '/'
        elif user_input in directories:
            current_path = os.path.join(current_path, user_input).replace('\\', '/') + '/'
        else:
            print("Invalid input. Please try again.")

def check_adb_devices():
    try:
        result = subprocess.check_output([adb_path, 'devices', '-l']).decode().strip().splitlines()[1:]
        devices = {}
        print("Available devices:")
        for index, line in enumerate(result, 1):
            parts = line.split()
            device_id = parts[0]
            model_name = next((part.split(':')[-1] for part in parts if part.startswith('model')), None)
            if model_name:
                print(f"{index}. {device_id} - {model_name}")
                devices[index] = device_id
            else:
                print(f"{index}. {device_id}")
        return devices
    except subprocess.CalledProcessError as e:
        main_logger.error(f"Error listing connected devices: {e}")
        return {}

def select_device(devices):
    while True:
        choice = input("Select a device by entering its number: ")
        if choice.isdigit():
            choice = int(choice)
            if choice in devices:
                return devices[choice]
            else:
                print("Invalid device number. Please try again.")
        else:
            print("Invalid input. Please enter a number.")

def main():
    global directory_path1, directory_path2

    main_logger.info("\n" + "\n" + "-"*40 + f" New Run: {RUN_ID} " + "-"*40 + "\n" + "\n")
    
    while True:
        print("Select the source directory:")
        source_choice = input("Type 'mtp' to select an MTP device or 'local' to select a local directory: ").strip().lower()
        if source_choice == 'mtp':
            devices = check_adb_devices()
            selected_device_id = select_device(devices)
            print(f"Selected device: {selected_device_id}")
            if not devices:
                print("No devices found. Please connect a device and try again.")
                continue
            directory_path1 = traverse_mtp_directories(selected_device_id)
            # grant_permissions_via_adb(directory_path1)
            src_is_mtp = True
        else:
            directory_path1 = select_directory("Select Source Directory")
            src_is_mtp = False
            
        print("Selected source directory: ", directory_path1)

        print("\nSelect the destination directory:")
        dest_choice = input("Type 'mtp' to select an MTP device or 'local' to select a local directory: ").strip().lower()
        if dest_choice == 'mtp':
            directory_path2 = traverse_mtp_directories(selected_device_id)
            # grant_permissions_via_adb(directory_path2)
            dst_is_mtp = True
        else:
            directory_path2 = select_directory("Select Destination Directory")
            dst_is_mtp = False
        
        print("Selected destination directory: ", directory_path2)

        main_logger.info(f"Selected source paths: {directory_path1}")
        main_logger.info(f"Selected destination paths: {directory_path2}")

        if not directory_path1 or not directory_path2 or directory_path1 == directory_path2:
            print("\nInvalid directories selected, please try again")
            main_logger.info("Invalid directories selected")
            continue

        user_input = input(f"\nWrite 'Confirm' or 'c': ")
        print("\n")

        if user_input.lower() in ['confirm', 'c']:
            checkpoint_files = load_checkpoint()
            files_processed = list(checkpoint_files)
            missing_files, all_files_in_dir2 = find_missing_files_and_all_files(directory_path1, directory_path2, selected_device_id, src_is_mtp, dst_is_mtp)
            missing_files = [file for file in missing_files if file not in files_processed]

            main_logger.info(f"{len(missing_files)} file(s) missing from directory 2")

            try:
                if missing_files:
                    main_logger.info("Copying missing files to directory 2:")
                    if not src_is_mtp and dst_is_mtp:
                        copy_files_to_phone(directory_path1, directory_path2, selected_device_id)
                    elif src_is_mtp and not dst_is_mtp:
                        copy_files_to_local(directory_path1, directory_path2, selected_device_id)
                    elif not src_is_mtp and not dst_is_mtp:
                        with tqdm(total=len(missing_files)) as pbar:
                            for file in missing_files:
                                main_logger.info(f"Current File: {file}")
                                pbar.set_description(f"Copying {file}")
                                src_file = os.path.join(directory_path1, file)
                                dst_file = os.path.join(directory_path2, file)
                                copy_file_with_timestamp(src_file, dst_file)
                                files_processed.append(file)
                                save_checkpoint(files_processed)
                                pbar.update(1)

                        # Log all the files in directory2 to a separate log file
                        log_all_files_in_dir2(all_files_in_dir2)
                        
                        # Log missing files from the checkpoint log
                        log_missing_files_from_checkpoint(checkpoint_files, all_files_in_dir2)
                    main_logger.info("All files copied successfully!")

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
                    main_logger.error(f"Permission denied to remove file: {dst_file}")
                except FileNotFoundError:
                    main_logger.error(f"File not found: {dst_file}")
        else:
            print("\nInvalid input. Please confirm to start copying files.")

        restart = input("Do you want to start again? (yes/no): ").strip().lower()
        if restart != 'yes':
            break

if __name__ == "__main__":
    main()
