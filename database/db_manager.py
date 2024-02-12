"""Database manager for MySQL operations"""
import time
from mysql.connector   import Error
import mysql.connector as mysql_connector
import pandas          as pd
import streamlit as st

from utils.utils import COUNTRY_DICTIONARY_PATH, get_country_name


def get_country_b_counts_for_country_a(country_id, country_name, countries_df):   
    # Step 1: Execute query to get country_b_id_fk where country_a_id_fk equals given value
    # Step 2: Extract and rank patterns for country_id
    # Define weights for calculating the Power score
    WEIGHT_PATTERN_LENGTH = 0.2
    WEIGHT_INDEXES        = 0.3
    WEIGHT_AVERAGE_CORR   = 0.5

    # Extract patterns for country_id
    patterns_df = pd.read_csv(r"data/countries/" + country_id + "_" + country_name + "_patterns.csv")

    # Convert columns to numericals
    patterns_df["pattern_length_fk"] = pd.to_numeric(patterns_df["pattern_length_fk"], errors="coerce")
    patterns_df["correlation"] = pd.to_numeric(patterns_df["avg_corr"], errors="coerce")

    # Calculate Power score
    patterns_df["Power"] = (
        patterns_df["pattern_length_fk"] * WEIGHT_PATTERN_LENGTH +
        patterns_df["indexes"] * WEIGHT_INDEXES +
        patterns_df["avg_corr"] * WEIGHT_AVERAGE_CORR
    )

    # Sort by Power score
    patterns_grouped_sorted = patterns_df.sort_values(by="Power", ascending=False)
    
    patterns_grouped_sorted = patterns_grouped_sorted[patterns_grouped_sorted["indexes"] > 1]

    # Step 3: Convert the data to a list
    country_b_ids = patterns_grouped_sorted["country_b_id_fk"].tolist()

    # Step 4: Group and count the country IDs
    counts_df = pd.DataFrame(country_b_ids, columns=["country_b_id_fk"]).value_counts().reset_index(name="count")

    # Step 5: Sort by count in descending order
    counts_df = counts_df.sort_values(by="count", ascending=False)

    # Step 6: Replace country IDs with names
    # counts_df["country_b_id_fk"] = counts_df["country_b_id_fk"].apply(lambda x: get_value_by_id("country", x, "name_1"))
    counts_df["country_b_id_fk"] = counts_df["country_b_id_fk"].apply(lambda x: get_country_name(countries_df, x))

    # Step 7: Rename columns to "Country" and "Patterns"
    counts_df.rename(columns={"country_b_id_fk": "Country", "count": "Patterns"}, inplace=True)

    # Step 8: Drop the index column
    counts_df.reset_index(drop = True, inplace = True)

    return counts_df


def get_alpha2_by_name(country_name: str) -> str:
    """
    Retrieves the ISO 3166-1 alpha-2 country code for a given country name.

    Parameters:
    - country_name (str): The name of the country.

    Returns:
    - str: The ISO 3166-1 alpha-2 country code.
    """
    countries_df = pd.read_csv(COUNTRY_DICTIONARY_PATH)
    match = countries_df[countries_df["name_1"] == country_name]
    if not match.empty:
        return match["alpha_2"].iloc[0]
    else:
        return None



# # TODO have common DB_CREDENTIALS
# DB_CREDENTIALS = {
#     "user":     "root", 
#     "password": "5465", 
#     "host":     "127.0.0.1", 
#     "database": "qgi_db"
# }
# DB_COUNTRY_B_STR      = "country_b"
# DB_PATTERN_LENGTH_STR = "pattern_length"
# DB_START_YEAR_A_STR   = "start_year_a"
# DB_START_YEAR_B_STR   = "start_year_b"


# class DatabaseManager:
#     def __init__(self):
#         self.conn = self._connect_to_database()
# 
#     def _connect_to_database(self, max_retries = 99999, retry_delay = 1):
#         attempt = 0
#         remarkable_attempts = [100, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]
#         while attempt < max_retries:
#             try:
#                 connection = mysql_connector.connect(
#                     user     = DB_CREDENTIALS["user"],
#                     password = DB_CREDENTIALS["password"],
#                     host     = DB_CREDENTIALS["host"],
#                     database = DB_CREDENTIALS["database"]
#                 )
#                 return connection
#             except Error as err:
#                 attempt += 1
#                 if attempt in remarkable_attempts:
#                     print(f"Attempt {attempt}: {err}")
#                 time.sleep(retry_delay)
#                 if attempt >= max_retries:
#                     raise Exception("Could not connect to MySQL.")
# 
#     def execute_this_query(self, query: str = ""):
#         cursor = self.conn.cursor()
#         cursor.execute(query)
#         data         = cursor.fetchall()
#         column_names = [desc[0] for desc in cursor.description]
#         df           = pd.DataFrame(data, columns = column_names)
#         cursor.close()
#         return df
# 
#     def list_tables(self):
#         cursor = self.conn.cursor()
#         cursor.execute("SHOW TABLES")
#         tables = cursor.fetchall()
#         cursor.close()
#         return [table[0] for table in tables]
# 
#     def delete_table(self, table_name):
#         cursor = self.conn.cursor()
#         query = f"DROP TABLE IF EXISTS {table_name}"
#         cursor.execute(query)
#         self.conn.commit()
#         cursor.close()
# 
#     def delete_all_contents_of(self, table_name):
#         cursor = self.conn.cursor()
#         query  = f"DELETE FROM {table_name}"
#         cursor.execute(query)
#         self.conn.commit()
#         cursor.close()
# 
#     def get_value_by_id(self, table, id, column):
#         cursor = self.conn.cursor()
#         query  = f"SELECT `{column}` FROM `{table}` WHERE id = %s"
#         cursor.execute(query, (id,))
#         result = cursor.fetchone()
#         cursor.close()
#         return result[0] if result else None
# 
#     def get_id_by_value(self, table, value, column=None):
#         cursor = self.conn.cursor()
#         if column:
#             query = f"SELECT id FROM `{table}` WHERE `{column}` = %s"
#             cursor.execute(query, (value,))
#         else:
#             cursor.execute(f"SHOW COLUMNS FROM `{table}`")
#             columns = [col[0] for col in cursor.fetchall()]
#             for col in columns:
#                 query = f"SELECT id FROM `{table}` WHERE `{col}` = %s"
#                 cursor.execute(query, (value,))
#         result = cursor.fetchone()
#         cursor.close()
#         return result[0] if result else None
# 
#     def close_connection(self):
#         if self.conn.is_connected():
#             self.conn.close()

###################################################################################
# def return_mysql_connection(max_retries: int = 99999, retry_delay: int = 1,):
#     attempt             = 0
#     remarkable_attempts = [100, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 45000, 5000]

#     while attempt < max_retries:
#         try:
#             mysql_conn = mysql_connector.connect(
#                 user     = DB_CREDENTIALS["user"],
#                 password = DB_CREDENTIALS["password"],
#                 host     = DB_CREDENTIALS["host"],
#                 database = DB_CREDENTIALS["database"]
#             )
#             # Connection successful, break out of the loop
#             break
#         except (Exception, mysql_connector.Error) as err:
#             attempt += 1
#             if attempt in remarkable_attempts:
#                 print(f"!!! {err} !!!")
#                 print(f"Retrying in {retry_delay} seconds... (Attempt: {attempt})")
#             if attempt >= max_retries:
#                 raise Exception("Maximum retries reached. Could not connect to MySQL. ")
#             time.sleep(retry_delay)
    
#     return mysql_conn


# def delete_table(table_name, close_connections: bool = False):
#     try:
#         conn = return_mysql_connection()

#         if conn.is_connected():
#             cursor = conn.cursor()
#             # Formulate the SQL query to delete the table
#             delete_table_query = f"DROP TABLE IF EXISTS {table_name};"
#             cursor.execute(delete_table_query)
#             conn.commit()
#             print(f"- Table {table_name} deleted successfully.")

#     except Error as e:
#         print(f"Error while connecting to MySQL: {e}")

#     finally:
#         # Close the database connection
#         if conn.is_connected():
#             if close_connections:
#                 cursor.close()
#                 conn.close()
#             print("- MySQL connection is closed")


# def fetch_table_data(
#     table_name: str, 
#     close_connections: bool = False, 
#     country_b: str = "",
#     patt_len: int = "",
#     start_year_a: int = "",
#     start_year_b: int = "",
#     field_name: str = ""
#     ) -> pd.DataFrame:
#     """
#     Fetches all records from a specified table in the MySQL database and returns the count and DataFrame of records.

#     Parameters:
#     table_name (str): The name of the table to fetch data from.

#     Returns:
#     tuple: A tuple containing the count of records and a DataFrame of the records.
#     """

#     # Establish a connection to the MySQL database
#     conn = return_mysql_connection()

#     # Create a cursor object using the cursor() method
#     cursor = conn.cursor()
    
#     # Execute the SQL query using the execute() method
#     if field_name == "":
#         cursor.execute("SELECT * FROM " + table_name.lower().replace(" ", "_"))
#     else:
#         try:
#             cursor.execute(f"SELECT {field_name} FROM " + table_name.lower().replace(" ", "_"))
#         except Exception as e:
#             print(e)

#     # Fetch all rows using the fetchall() method
#     data = cursor.fetchall()

#     # Get column names
#     column_names = [desc[0] for desc in cursor.description]

#     # Convert to DataFrame
#     df = pd.DataFrame(data, columns=column_names)

#     if country_b != "":
#         df = df[df[DB_COUNTRY_B_STR] == country_b]
#         if patt_len != "":
#             df = df[df[DB_PATTERN_LENGTH_STR] == patt_len]
#             if start_year_a != "":
#                 df = df[df[DB_START_YEAR_A_STR] == start_year_a]
#                 if start_year_b != "":
#                     df = df[df[DB_START_YEAR_B_STR] == start_year_b]

#     # Close the cursor and connection
#     if close_connections:
#         cursor.close()
#         conn.close()

#     return df


# def list_tables(print: bool = True, close_connections: bool = False) -> list:
#     try:
#         conn = return_mysql_connection()

#         if conn.is_connected():
#             cursor = conn.cursor()
#             # SQL query to list all tables in the database
#             cursor.execute("SHOW TABLES")
#             tables = cursor.fetchall()
#             print("- List of tables in the database:")
#             if print:
#                 for table in tables:
#                     print(table[0])

#     except Error as e:
#         print(f"Error while connecting to MySQL: {e}")

#     finally:
#         # Close the database connection
#         if conn.is_connected():
#             if close_connections:
#                 cursor.close()
#                 conn.close()
#                 print("- MySQL connection is closed")
#         return tables


# def delete_all_contents_of(table_name, close_connections: bool = False):
#     """ Deletes all contents of a specified table in a MySQL database. """

#     try:
#         # Establishing the connection to the database
#         conn = return_mysql_connection()

#         if conn.is_connected():
#             cursor = conn.cursor()

#             # SQL query to delete all contents of the table
#             delete_query = f"DELETE FROM {table_name};"
#             cursor.execute(delete_query)
#             conn.commit()

#             print(f"- All contents of the table '{table_name}' have been deleted.")

#     except Error as e:
#         print(f"Error while connecting to MySQL: {e}")
#     finally:
#         # Closing the connection
#         if conn.is_connected():
#             if close_connections:
#                 cursor.close()
#                 conn.close()
#             print("- MySQL connection is closed.")


# def get_databases_size(close_connections: bool = False):
#     try:
#         # Establishing a connection to the MySQL server
#         conn   = return_mysql_connection()
#         cursor = conn.cursor()

#         # SQL query to get the size of each database
#         query = """
#         SELECT table_schema AS 'Database',
#         SUM(data_length + index_length) / 1024 / 1024 AS 'Size in MB'
#         FROM information_schema.TABLES
#         GROUP BY table_schema;
#         """

#         # Executing the query
#         cursor.execute(query)

#         # Fetching and printing the results
#         databases_size = cursor.fetchall()
#         for db in databases_size:
#             print(f"Database: {db[0]}, Size: {db[1]:.2f} MB")

#         # Closing the connection
#         if close_connections:
#             cursor.close()
#             conn.close()

#     except mysql_connector.Error as e:
#         print(f"Error: {e}")


# def extract_and_rank_patterns(table_name, close_connections: bool = False):
#     try:
#         # Connect to the MySQL database
#         conn   = return_mysql_connection()
#         cursor = conn.cursor()

#         # Query to select all data from the table
#         query = f"SELECT * FROM {table_name}"
#         cursor.execute(query)

#         # Fetch all records and convert to a DataFrame
#         records = cursor.fetchall()
#         df = pd.DataFrame(records, columns=[desc[0] for desc in cursor.description])

#         # Group by 'country_a', 'country_b', and 'pattern_length'
#         # Count unique 'unique_id' for each group
#         pattern_strength = df.groupby(["country_a", "country_b", "pattern_length"])["unique_id"].nunique()

#         # Sort the patterns by their strength in descending order
#         sorted_patterns = pattern_strength.sort_values(ascending = False)

#         # Close the connection
#         if close_connections:
#             cursor.close()
#             conn.close()

#         return sorted_patterns

#     except mysql_connector.Error as e:
#         print(f"Error: {e}")
#         return None


# def get_value_by_id(table, id, column):
#     """
#     Retrieves a specific value from a specified column in a table based on the provided ID.

#     Parameters:
#     - table (str): The name of the table in the database.
#     - id (int or str): The ID used to search for the value.
#     - column (str): The column from which the value is to be retrieved.

#     Returns:
#     - The value corresponding to the given ID in the specified column, if found. Otherwise, None.

#     Raises:
#     - Error: If any MySQL operation fails or if the specified column does not exist in the table.
#     """
#     try:
#         # Establish a connection to the MySQL database
#         conn = return_mysql_connection()
#         cursor = conn.cursor()

#         # Formulate the SQL query to retrieve the value
#         query = f"SELECT `{column}` FROM `{table}` WHERE id = %s"
#         cursor.execute(query, (id,))

#         # Fetch the result
#         result = cursor.fetchone()

#         # Close the cursor and the connection
#         cursor.close()
#         conn.close()

#         # Return the value if found
#         if result:
#             return result[0]
#         else:
#             print(f"No record found with ID {id} in column '{column}' of table '{table}'.")
#             return None

#     except Error as e:
#         print(f"Error occurred while fetching value by ID: {e}")
#         return None


# def get_id_by_value(table, value, column=None):
#     """
#     Retrieves the ID of a record from a specified table by searching a specific column or all columns for the given value.

#     Parameters:
#     - table (str): The name of the table.
#     - value (str or int): The value to search for in the table.
#     - column (str, optional): The specific column to search. If None, searches all columns.

#     Returns:
#     - int: The ID of the record if found, otherwise None.

#     Raises:
#     - Error: If any MySQL operation fails or if the table does not exist.
#     """
#     try:
#         # Establish a connection to the MySQL database
#         conn = return_mysql_connection()
#         cursor = conn.cursor()

#         # If a specific column is provided, search only that column
#         if column:
#             query = f"SELECT id FROM `{table}` WHERE `{column}` = %s"
#             cursor.execute(query, (value,))
#         else:
#             # No specific column provided, search all columns
#             cursor.execute(f"SHOW COLUMNS FROM `{table}`")
#             columns = [col[0] for col in cursor.fetchall()]

#             for col in columns:
#                 query = f"SELECT id FROM `{table}` WHERE `{col}` = %s"
#                 cursor.execute(query, (value,))

#         # Fetch the result
#         result = cursor.fetchone()

#         # Close the cursor and the connection
#         cursor.close()
#         conn.close()

#         # Return the ID if found
#         return result[0] if result else None

#     except Error as e:
#         print(f"Error searching for value in {table}: {e}")
#         return None
