import os
import subprocess
import time
import win32file
import pywintypes
from datetime import datetime

adb_path = r"C:\Users\platform-tools-latest-windows\platform-tools\adb.exe"

def list_phone_directories(current_path="/sdcard/"):
    try:
        root_contents = subprocess.check_output([adb_path, 'shell', 'ls', current_path]).decode().splitlines()
        print(f"Available directories in {current_path}:")
        for directory in root_contents:
            print(directory)
        return root_contents
    except subprocess.CalledProcessError as e:
        print(f"Error listing phone directories: {e}")
        return None

def traverse_phone_directories(current_path="/sdcard/"):
    while True:
        directories = list_phone_directories(current_path)
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

def select_local_folder():
    folder_path = input("Enter the path of the local folder you want to copy files to: ")
    if os.path.exists(folder_path):
        return folder_path
    else:
        print("Invalid folder path. Please enter a valid path.")
        return None

def file_exists_locally(local_file_path):
    return os.path.exists(local_file_path)

def get_file_times(phone_file):
    try:
        result = subprocess.check_output([adb_path, 'shell', 'ls', '-l', phone_file]).decode().strip()
        parts = result.split()
        print("parts: ", parts)
        if len(parts) < 8:
            raise ValueError("Unexpected output from ls command")
        # Extract the modify time
        modify_time_str = parts[5] + " " + parts[6]
        print("modify_time_str: ", modify_time_str)
        modify_time = int(time.mktime(datetime.strptime(modify_time_str, "%Y-%m-%d %H:%M").timetuple()))
        print("modify_time: ", modify_time)
        return modify_time, modify_time  # Using the modify time for both access and modify times
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error getting file times for {phone_file}: {e}")
        return None, None


def copy_files_to_local(phone_directory, local_folder):
    try:
        phone_files = subprocess.check_output([adb_path, 'shell', 'find', phone_directory, '-type', 'f']).decode().splitlines()
        for phone_file in phone_files:
            relative_path = os.path.relpath(phone_file, phone_directory)
            local_file = os.path.join(local_folder, relative_path).replace('/', os.sep)
            local_file_dir = os.path.dirname(local_file)
            if not os.path.exists(local_file_dir):
                os.makedirs(local_file_dir)
            
            if not file_exists_locally(local_file):
                try:
                    subprocess.run([adb_path, 'pull', phone_file, local_file], check=True)
                    access_time, modify_time = get_file_times(phone_file)
                    if access_time and modify_time:
                        # os.utime(local_file, (access_time, modify_time))
                        current_time = pywintypes.Time(modify_time)  # Convert to pywintypes.Time
                        file_handle = win32file.CreateFile(local_file, win32file.GENERIC_WRITE, 0, None, win32file.OPEN_EXISTING, 0, 0)
                        win32file.SetFileTime(file_handle, CreationTime=current_time, LastAccessTime=current_time, LastWriteTime=current_time)
                        win32file.CloseHandle(file_handle)
                    print(f"Copied {phone_file} to {local_file}")
                except subprocess.CalledProcessError as e:
                    print(f"Error copying {phone_file} to {local_file}: {e}")
            else:
                print(f"File {local_file} already exists locally. Skipping copy.")
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving files from phone: {e}")

def main():
    print("Listing available directories on phone...")
    selected_directory = traverse_phone_directories()
    if selected_directory:
        local_folder = select_local_folder()
        if local_folder:
            copy_files_to_local(selected_directory, local_folder)

if __name__ == "__main__":
    main()
