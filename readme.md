# FileSync

FileSync is a Python script designed to synchronize files between two directories. It compares the files in the source directory with those in the destination directory and copies any missing files from the source to the destination. The primary purpose of this script is to preserve the original creation and modification timestamps of files during the synchronization process. This ensures that the chronological order of files is maintained, which is personally preferred for backup purposes.

## Features

- Automatic synchronization of files between two directories.
- Logging of all operations performed, including copying files and errors encountered.
- Ability to resume from the last checkpoint in case of interruption.
- User-friendly interface using Tkinter for selecting source and destination directories.
- Progress tracking using tqdm for copying files.
- **Support for handling files and directories on MTP (Media Transfer Protocol) devices**:
  - Enables users to select MTP devices as both source and destination directories.
  - Implements directory traversal and file operations on MTP devices using the subprocess module.
  - Integrates permission management for accessing and modifying files on MTP devices.
  - Facilitates copying files between local directories and MTP devices, as well as between MTP devices.
  - Ensures accurate handling of file timestamps during copying operations.

## Usage

1. Run the script:

2. Select the source directory when prompted.

3. Select the destination directory when prompted.

4. Confirm the synchronization process by typing 'Confirm' or 'c' and pressing Enter.

5. Sit back and relax while FileSync synchronizes your files!

## Configuration

- The script uses the `logs` directory to store log files. Make sure this directory exists in the same directory as the script.
- You can customize the log file names and formats by modifying the `main_logger` and other logger configurations in the script.
- Adjust the paths of the source and destination directories according to your requirements by modifying the `directory_path1` and `directory_path2` variables in the script.

## Implementation Details for MTP Support

- Utilizes ADB (Android Debug Bridge) commands to interact with connected Android devices in MTP mode.
- Implements directory listing, file copying, and permission management functionalities for MTP devices.
- Incorporates error handling mechanisms to gracefully manage exceptions during MTP operations.

## Logging

- The script logs all operations to separate log files in the `logs` directory.
- Three main log files are generated:
  - `main_logger.log`: Logs general information and errors encountered during the synchronization process.
  - `all_files_in_directory2.log`: Logs all files found in the destination directory during each run.
  - `missing_files_from_checkpoint.log`: Logs files present in the checkpoint but not found in the destination directory.
- Log files are appended with a timestamp to distinguish between different runs.

## Contributing

Contributions are welcome! Feel free to fork the repository and submit pull requests for any improvements or fixes.

## Credits

FileSync is developed by Mervin Abraham (https://github.com/Mervin-Abraham).
