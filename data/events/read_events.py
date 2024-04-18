import pandas as pd
import os

def read_events_as_df(country_name):
    # Get the directory of the current script
    dir_path = os.path.dirname(os.path.realpath(__file__))
    # Append the subdirectory and file name
    file_path = os.path.join(dir_path, country_name + ".csv")
    return pd.read_csv(file_path)
