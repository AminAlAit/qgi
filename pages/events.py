import streamlit as st
import pandas as pd
import os
from collections import Counter
from constant.constant import COUNTRY_EVENTS_PATH, MATCHING_EVENTS_CSV_PATH
from utils.utils import read_events_as_df


def show_event_frequency_page():
    st.title("Event Frequency Analysis")

    all_events = []

    # Iterate over all files in the specified directory
    for filename in os.listdir(COUNTRY_EVENTS_PATH):
        if filename.endswith(".txt"):  # Check if the file is a txt file
            country_name = filename.replace(".txt", "")
            df = read_events_as_df(filename)
            if df is not None:
                all_events.extend(df["Raw Event"].tolist())

    # Count the frequency of each event
    event_counts = Counter(all_events)
    event_df = pd.DataFrame(event_counts.items(), columns=["Raw Event", "Frequency"])
    event_df = event_df.sort_values(by="Frequency", ascending=False)

    # Display the DataFrame in Streamlit
    st.dataframe(event_df)

    # Load and display the matching events frequency from matching_events.csv
    st.title("Matching Event Frequency Analysis")

    if os.path.exists(MATCHING_EVENTS_CSV_PATH):
        matching_df = pd.read_csv(MATCHING_EVENTS_CSV_PATH)

        # Count the frequency of each matching event
        matching_event_counts = Counter(matching_df["Matching Event"].tolist())
        matching_event_df = pd.DataFrame(matching_event_counts.items(), columns=["Matching Event", "Frequency"])
        matching_event_df = matching_event_df.sort_values(by="Frequency", ascending=False)

        # Display the DataFrame in Streamlit
        st.dataframe(matching_event_df)
    else:
        st.write("No matching events found.")

