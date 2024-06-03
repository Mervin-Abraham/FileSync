# FileSync

FileSync is a Python script designed to synchronize files between two directories. It compares the files in the source directory with those in the destination directory and copies any missing files from the source to the destination. The primary purpose of this script is to preserve the original creation and modification timestamps of files during the synchronization process. This ensures that the chronological order of files is maintained, which is personally preferred for backup purposes.

## Features

- Automatic synchronization of files between two directories.
- Logging of all operations performed, including copying files and errors encountered.
- Ability to resume from the last checkpoint in case of interruption.
- User-friendly interface using Tkinter for selecting source and destination directories.
- Progress tracking using tqdm for copying files.

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

Tasks

[x] I have two file dictionary paths and I have around 7000 files in one directory  and the other directory has about 4000 files. 
[x] Both the directories contains the same file and file name. 
[x] I am trying to find out from directory path 1, which are the files missing in directory path 2.
[x] All files have unique names. 
[x] Copy the missing files from directory 1 and put into directory 2 but by copying it, it should not modify the original file's created time. 
    This is mandatory that the created time does not get changed. 
[x] Shows the current file being copied, progress bar, ETA, number of files left to copy
