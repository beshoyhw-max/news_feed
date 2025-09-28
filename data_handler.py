import pandas as pd
import re
from datetime import datetime, timedelta, date
from typing import List
from collections import defaultdict

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
                
                # Duration is parsed from the 'Total Time' column (source of truth)
                duration = parse_duration(row['Total Time'])
                
                # Arrival datetime is now correctly calculated from the departure time and true duration
                arrival_datetime = departure_datetime + duration
                arrival_time = arrival_datetime.time()
                
                transfer_info = str(row['Transfer Info'])
                if "转" in transfer_info:
                    match = re.search(r'(\d+)', transfer_info)
                    transfers = int(match.group(1)) if match else 0
                else:
                    transfers = 0
                
                flight_number = ''.join(re.findall(r'[A-Z0-9]', str(row['Plane'])))

                # Handle flight class; get the value from the correct 'Flight Class' column.
                flight_class = str(row.get('Flight Class', 'Economy')).strip()

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

def expand_flights_for_date_range(
    base_flights: List[Flight], 
    start_date: date, 
    end_date: date
) -> List[Flight]:
    """
    Expands a list of base flights to cover a given date range.
    It assumes the base flights represent a typical week's schedule.
    """
    flights_by_weekday = defaultdict(list)
    for flight in base_flights:
        flights_by_weekday[flight.date.weekday()].append(flight)

    expanded_flights = []
    current_date = start_date
    while current_date <= end_date:
        weekday = current_date.weekday()
        if weekday in flights_by_weekday:
            for base_flight in flights_by_weekday[weekday]:
                # Calculate the difference in days from the base flight's date
                # This is important for multi-day flights
                arrival_date_offset = (base_flight.arrival_datetime.date() - base_flight.departure_datetime.date()).days
                
                new_departure_datetime = datetime.combine(current_date, base_flight.departure_time)
                new_arrival_datetime = datetime.combine(current_date + timedelta(days=arrival_date_offset), base_flight.arrival_time)

                new_flight = Flight(
                    date=current_date,
                    airline=base_flight.airline,
                    flight_number=base_flight.flight_number,
                    flight_class=base_flight.flight_class,
                    departure_city_code=base_flight.departure_city_code,
                    arrival_city_code=base_flight.arrival_city_code,
                    departure_time=base_flight.departure_time,
                    arrival_time=base_flight.arrival_time,
                    departure_datetime=new_departure_datetime,
                    arrival_datetime=new_arrival_datetime,
                    duration=base_flight.duration,
                    transfers=base_flight.transfers,
                    transfer_info=base_flight.transfer_info,
                    direct_flight=base_flight.direct_flight
                )
                expanded_flights.append(new_flight)
        current_date += timedelta(days=1)
    
    print(f"Expanded {len(base_flights)} base flights to {len(expanded_flights)} flights from {start_date} to {end_date}.")
    return expanded_flights


if __name__ == '__main__':
    # Example usage
    flights_data = load_flights("merged_flight_data.xlsx")
    if flights_data:
        print(f"\nSuccessfully loaded {len(flights_data)} flights.")
        print("First 2 flights:")
        for f in flights_data[:2]:
            print(f"  {f.departure_city_code} -> {f.arrival_city_code} on {f.airline} ({f.flight_number}) class: {f.flight_class}")
        
        print("\n--- Testing Flight Expansion ---")
        test_start_date = date(2025, 10, 6) # A Monday
        test_end_date = date(2025, 10, 12) # A Sunday
        expanded = expand_flights_for_date_range(flights_data, test_start_date, test_end_date)
        if expanded:
            print(f"First 2 expanded flights:")
            for f in expanded[:2]:
                 print(f"  {f.departure_city_code} -> {f.arrival_city_code} on {f.airline} ({f.flight_number}) date: {f.date}")
