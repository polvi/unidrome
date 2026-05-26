from datetime import timedelta, date
import requests
import os
import zipfile
import shutil
import tempfile

class FAA:
    DATA_PATH = os.path.join("data", "us/faa/nasr")
    CYCLE_LENGTH = timedelta(days=28)
    START_CYCLE_DATE = date(2024, 1, 25)

    def get_latest_path(self):
        return os.path.join(self.DATA_PATH, "APT_BASE-latest.csv")

    def current_data_cycle(self):
        next_cycle = self.START_CYCLE_DATE
        while date.today() >= next_cycle:
            next_cycle += self.CYCLE_LENGTH
        return next_cycle - self.CYCLE_LENGTH

    def download_airport_data_archive(self, destination_directory):
        cycle_date = self.current_data_cycle().strftime('%d_%b_%Y')
        url = f"https://nfdc.faa.gov/webContent/28DaySub/extra/{cycle_date}_CSV.zip"
        try:
            response = requests.get(url)
            response.raise_for_status()  # Will raise an exception for 4XX/5XX errors
            archive_path = os.path.join(destination_directory, 'archive.zip')
            with open(archive_path, 'wb') as file:
                file.write(response.content)
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(destination_directory)
            print("Download and extraction successful.")
        except requests.RequestException as e:
            print(f"Failed to download or handle the file: {e}")

    def manage_data_files(self, temp_directory):
        files = ["APT_BASE.csv", "APT_RWY.csv", "ATC_SVC.csv"]
        # Copy required CSV files to the cycle directory
        for filename in files:
            src = os.path.join(temp_directory, filename)
            dst = os.path.join(self.DATA_PATH, filename)
            if os.path.exists(src):
                shutil.copy(src, dst)
                print(f"Copied {filename} to {self.DATA_PATH}")
            else:
                print(f"Warning: {filename} not found at {src}")

if __name__ == "__main__":
    faa = FAA()
    with tempfile.TemporaryDirectory() as temp_dir:
        faa.download_airport_data_archive(temp_dir)
        faa.manage_data_files(temp_dir)

