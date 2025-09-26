import pandas as pd
import re
from datetime import datetime, timedelta
from typing import List

from models import Flight

def parse_duration(duration_str: str) -> timedelta:
    """Parses a duration string (e.g., '19小时20分', '1天20分') into a timedelta object."""
    days = 0
    hours = 0
    minutes = 0

    if isinstance(duration_str, str):
        if '天' in duration_str:
            parts = duration_str.split('天')
            try:
                days = int(parts[0])
            except ValueError:
                days = 0 
            if len(parts) > 1 and parts[1]:
                duration_str = parts[1]
            else:
                duration_str = ''

        if '小时' in duration_str:
            parts = duration_str.split('小时')
            if parts[0]:
                try:
                    hours = int(parts[0])
                except ValueError:
                    hours = 0
            if len(parts) > 1 and parts[1]:
                duration_str = parts[1]
            else:
                duration_str = ''
        
        if '分' in duration_str:
            try:
                minutes = int(duration_str.replace('分', ''))
            except ValueError:
                minutes = 0
    
    return timedelta(days=days, hours=hours, minutes=minutes)


import os

def load_flights(
    filepath: str = "merged_flight_data.xlsx"
) -> List[Flight]:
    """
    Loads flight data from a fast-loading Feather cache if it exists.
    If not, it reads the original Excel file, creates the cache, and then loads the data.
    """
    feather_path = filepath.replace(".xlsx", ".feather")
    flights = []

    try:
        if os.path.exists(feather_path):
            print(f"Loading flights from fast cache: {feather_path}")
            df = pd.read_feather(feather_path)
        else:
            print(f"Cache not found. Loading from original file: {filepath}")
            df = pd.read_excel(filepath)
            # Save the dataframe to a feather file for future fast loading
            df.to_feather(feather_path)
            print(f"Cache created at: {feather_path}")

        # Convert 'Date' column to datetime, coercing errors to NaT
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        # Drop rows where 'Date' could not be parsed
        df.dropna(subset=['Date'], inplace=True)

        for _, row in df.iterrows():
            try:
                # Date and Time parsing - now 'Date' is a datetime object
                flight_date = row['Date'].date()
                
                # Make sure times are read as strings before parsing
                departure_time_str = str(row['Departure Time'])
                arrival_time_str = str(row['Arrival Time'])

                # Handle cases where time might be just 'HH:MM' without seconds
                try:
                    departure_time = datetime.strptime(departure_time_str, '%H:%M').time()
                except ValueError:
                    departure_time = datetime.strptime(departure_time_str, '%H:%M:%S').time()

                departure_datetime = datetime.combine(flight_date, departure_time)
                
                arrival_time_parts = arrival_time_str.split(' ')
                
                try:
                    arrival_time = datetime.strptime(arrival_time_parts[0], '%H:%M').time()
                except ValueError:
                    arrival_time = datetime.strptime(arrival_time_parts[0], '%H:%M:%S').time()

                days_offset = 0
                if len(arrival_time_parts) > 1:
                    if '+1' in arrival_time_parts[1]:
                        days_offset = 1
                    elif '+2' in arrival_time_parts[1]:
                        days_offset = 2
                    elif '+3' in arrival_time_parts[1]:
                        days_offset = 3
                    
                arrival_datetime = datetime.combine(flight_date + timedelta(days=days_offset), arrival_time)

                # Duration and Transfer parsing
                duration = parse_duration(row['Total Time'])
                
                transfer_info = str(row['Transfer Info'])
                if "转" in transfer_info:
                    match = re.search(r'(\d+)', transfer_info)
                    transfers = int(match.group(1)) if match else 0
                else:
                    transfers = 0
                
                flight_number = ''.join(re.findall(r'[A-Z0-9]', str(row['Plane'])))

                # Handle flight class, making it case-insensitive and matching 'Business'/'Economy'
                flight_class = str(row.get('flight_class', 'Economy')).strip().capitalize()

                # Create Flight object
                flight = Flight(
                    date=flight_date,
                    airline=row['Company (Airline)'],
                    flight_number=flight_number if flight_number else "N/A",
                    flight_class=flight_class,
                    departure_city_code=row['From'],
                    arrival_city_code=row['To'],
                    departure_time=departure_datetime.time(),
                    arrival_time=arrival_datetime.time(),
                    departure_datetime=departure_datetime,
                    arrival_datetime=arrival_datetime,
                    duration=duration,
                    transfers=transfers,
                    transfer_info=transfer_info,
                    direct_flight=(transfers == 0)
                )
                flights.append(flight)
            except (ValueError, KeyError, IndexError, AttributeError) as e:
                print(f"Warning: Could not parse row: {row}. Error: {e}. Skipping.")
                continue
    except FileNotFoundError:
        print(f"Error: Data file not found at {filepath}.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    return flights

if __name__ == '__main__':
    # Example usage
    flights_data = load_flights("merged_flight_data.xlsx")
    if flights_data:
        print(f"\nSuccessfully loaded {len(flights_data)} flights.")
        print("First 2 flights:")
        for f in flights_data[:2]:
            print(f"  {f.departure_city_code} -> {f.arrival_city_code} on {f.airline} ({f.flight_number}) class: {f.flight_class}")