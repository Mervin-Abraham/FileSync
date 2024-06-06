import os
import subprocess

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
    folder_path = input("Enter the path of the local folder you want to copy files from: ")
    if os.path.exists(folder_path):
        return folder_path
    else:
        print("Invalid folder path. Please enter a valid path.")
        return None

def file_exists_on_phone(phone_file_path):
    try:
        result = subprocess.run([adb_path, 'shell', 'ls', phone_file_path], capture_output=True, text=True)
        return 'No such file or directory' not in result.stderr
    except subprocess.CalledProcessError as e:
        print(f"Error checking file existence on phone: {e}")
        return False

def copy_files_to_phone(local_folder, phone_directory):
    for root, dirs, files in os.walk(local_folder):
        relative_path = os.path.relpath(root, local_folder)
        phone_path = os.path.join(phone_directory, relative_path).replace('\\', '/')

        for file in files:
            local_file = os.path.join(root, file)
            phone_file = os.path.join(phone_path, file).replace('\\', '/')
            if not file_exists_on_phone(phone_file):
                try:
                    subprocess.run([adb_path, 'push', '-p', local_file, phone_file], check=True)
                    print(f"Copied {local_file} to {phone_file}")
                except subprocess.CalledProcessError as e:
                    print(f"Error copying {local_file} to {phone_file}: {e}")
            else:
                print(f"File {phone_file} already exists on the phone. Skipping copy.")

def main():
    print("Listing available directories on phone...")
    selected_directory = traverse_phone_directories()
    if selected_directory:
        local_folder = select_local_folder()
        if local_folder:
            copy_files_to_phone(local_folder, selected_directory)

if __name__ == "__main__":
    main()