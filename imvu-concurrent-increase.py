import os
import zipfile
import shutil
appdata_path = os.path.expandvars(os.getenv('APPDATA'))
imvu_client_path = f"{appdata_path}\\IMVUClient\\"
custom_client = False
def run(imvu_path=imvu_client_path):

    if custom_client is True:
        print("Please provide your custom IMVU client path")
        alternative_client_folder = input("[custom IMVU Client path]: ")
        imvu_path = alternative_client_folder

    print("################################################################################")
    print("#                        Select one of the options                             #")
    print("# 1.  8 concurrent http connections (Recommended for older laptops)            #")
    print("# 2. 16 concurrent http connections (Sweet spot between old and new hardware)  #")
    print("# 3. 32 concurrent http connections (Recommended for high end hardware)        #")
    print("# 4. 64 concurrent http connections (Diminishing returns)                      #")
    print("################################################################################")

    
    
    library_zip_path = f"{appdata_path}\\IMVUClient\\library.zip"
    library_zip_temp_path = f"{appdata_path}\\IMVUClient\\library-temp.zip"
    checksum_path = f"{appdata_path}\\IMVUClient\\checksum.txt"
    relative_path_in_zip = "imvu/http/"

    user_input = input("[1, 2, 3 or 4]: ")
    if not user_input.isdigit():
        print("Please enter a valid number (1-4).")
        exit(1)

    source_file = None
    if int(user_input) == 1:
        source_file = "DownloadManager-8.pyo"
    elif int(user_input) == 2:
        source_file = "DownloadManager-16.pyo"
    elif int(user_input) == 3:
        source_file = "DownloadManager-32.pyo"
    elif int(user_input) == 4:
        source_file = "DownloadManager-64.pyo"
    else:
        print("Invalid input. Please choose between 1 and 4.")
        exit(1)


    shutil.copy(source_file, "DownloadManager.pyo")
    source_file = "DownloadManager.pyo"
    shutil.copy(library_zip_path, library_zip_temp_path)
    with zipfile.ZipFile(library_zip_temp_path, "r") as zread:
        with zipfile.ZipFile(library_zip_path, 'w', zipfile.ZIP_STORED) as zipf:
            # Delete old file first
            for item in zread.infolist():
                buffer = zread.read(item.filename)
                if "DownloadManager.pyo" not in item.filename:
                    zipf.writestr(item, buffer)
            # Write the source file into the zip at the specified relative path
            zipf.write(source_file, arcname=relative_path_in_zip + source_file)

    print("File written successfully.")

    # Process the checksum file
    try:
        # Read the checksum file and remove lines related to library.zip
        with open(checksum_path, 'r', encoding='utf-8') as f:
            lines = [line.rstrip('\n') for line in f]
        
        # Filter out lines containing 'library.zip'
        cleaned_lines = [
            line for line in lines
            if not any(libzip in line.lower() for libzip in ['library.zip'])
        ]
        
        # Write the cleaned lines back to the checksum file
        with open(checksum_path, 'w', encoding='utf-8') as f:
            print('\n'.join(cleaned_lines), file=f)
    except Exception as e:
        print(f"Error processing checksum file: {e}")
        exit(1)

    os.remove(source_file)
    os.remove(library_zip_temp_path)
    print(f"{source_file} has been added to library.zip.")

if __name__ == "__main__":
    run()