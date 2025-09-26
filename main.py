from typing import List, Optional
from collections import defaultdict
from datetime import timedelta

from data_handler import load_flights
from models import TravelPlan, Flight, get_city_by_code, CITIES_BY_CODE


def find_best_travel_plan(
    flights: List[Flight],
    cities_choice: List[str],
    num_countries: int,
    start_city: Optional[str] = None,
    end_city: Optional[str] = None,
    direct_flights_only: bool = False,
    flight_class_filter: str = "ALL",
    min_layover_hours: int = 10,
    max_layover_hours: int = 48,
    no_fly_start_hour: Optional[int] = None,
    no_fly_end_hour: Optional[int] = None,
) -> Optional[TravelPlan]:
    """
    Finds the best travel plan based on the user's criteria using a recursive search.
    """
    if not flights or not cities_choice or num_countries <= 0:
        return None

    # --- NEW PRE-FILTERING STAGE ---
    # Apply simple, non-recursive filters first to reduce the dataset.
    print("Pre-filtering flights based on initial criteria...")
    pre_filtered_flights = []
    for flight in flights:
        # Filter by flight class
        if flight_class_filter != "ALL" and flight.flight_class != flight_class_filter:
            continue
        # Filter by direct flights
        if direct_flights_only and flight.transfers > 0:
            continue
        # Filter by cities to include in the search
        if (flight.departure_city_code not in cities_choice) or \
           (flight.arrival_city_code not in cities_choice):
            continue
        
        # --- NEW Time-based flight filter ---
        if no_fly_start_hour is not None and no_fly_end_hour is not None:
            dep_hour = flight.departure_time.hour
            arr_hour = flight.arrival_time.hour
            
            # Check if start and end times are on the same day or span across midnight
            if no_fly_start_hour <= no_fly_end_hour:  # Same day range (e.g., 0 to 6)
                if (no_fly_start_hour <= dep_hour < no_fly_end_hour) or \
                   (no_fly_start_hour <= arr_hour < no_fly_end_hour):
                    continue
            else:  # Overnight range (e.g., 23 to 6)
                if (dep_hour >= no_fly_start_hour or dep_hour < no_fly_end_hour) or \
                   (arr_hour >= no_fly_start_hour or arr_hour < no_fly_end_hour):
                    continue
        
        pre_filtered_flights.append(flight)
    
    print(f"Reduced flight list from {len(flights)} to {len(pre_filtered_flights)} flights.")
    
    if not pre_filtered_flights:
        return None

    # 1. Prepare the NOW-SMALLER flight data for efficient lookup
    flights_by_departure_city = defaultdict(list)
    for flight in pre_filtered_flights: # Use the filtered list
        flights_by_departure_city[flight.departure_city_code].append(flight)

    for city_flights in flights_by_departure_city.values():
        city_flights.sort(key=lambda f: f.departure_datetime)

    all_found_plans: List[TravelPlan] = []
    target_country_count = num_countries + 1 if start_city else num_countries
    paths_explored_counter = 0

    # 3. The recursive search function now operates on a smaller dataset
    def find_routes_recursive(current_path: List[Flight], visited_countries: set, last_departure_city):
        nonlocal paths_explored_counter
        paths_explored_counter += 1
        if paths_explored_counter % 10000 == 0:
            print(f"  ... still searching, {paths_explored_counter} paths explored ...")

        if all_found_plans and current_path:
            current_duration = current_path[-1].arrival_datetime - current_path[0].departure_datetime
            if current_duration > all_found_plans[0].total_duration:
                return

        if len(visited_countries) == target_country_count:
            if not end_city or (current_path and current_path[-1].arrival_city_code == end_city):
                new_plan = TravelPlan(flights=list(current_path))
                all_found_plans.append(new_plan)
                all_found_plans.sort(key=lambda p: p.total_duration)
                print(f"  > Found a potential plan with duration {new_plan.total_duration}. Still searching for a better one...")
            return

        potential_next_flights = flights_by_departure_city.get(last_departure_city, [])
        
        for flight in potential_next_flights:
            arrival_city = get_city_by_code(flight.arrival_city_code)
            
            # Simplified checks, as some were already done in pre-filtering
            if not arrival_city:
                continue

            # The complex, state-dependent checks remain here
            if current_path:
                last_flight = current_path[-1]
                if flight.arrival_city_code == last_flight.departure_city_code:
                    continue
                
                layover_duration = flight.departure_datetime - last_flight.arrival_datetime
                if not (timedelta(hours=min_layover_hours) <= layover_duration <= timedelta(hours=max_layover_hours)):
                    continue
            
            if arrival_city.country not in visited_countries:
                new_visited_countries = visited_countries.union({arrival_city.country})
                find_routes_recursive(
                    current_path + [flight],
                    new_visited_countries,
                    flight.arrival_city_code
                )

    # 4. Start the search
    initial_cities = [start_city] if start_city else cities_choice
    for city_code in initial_cities:
        start_country = get_city_by_code(city_code).country
        find_routes_recursive(
            current_path=[],
            visited_countries={start_country},
            last_departure_city=city_code
        )
    
    return all_found_plans[0] if all_found_plans else None


if __name__ == '__main__':
    print("Loading flight data...")
    all_flights = load_flights("merged_flight_data.xlsx")
    if not all_flights:
        print("Could not load flight data. Exiting.")
        exit()
    print(f"Loaded {len(all_flights)} flights.")

    user_start_city = "ABJ"
    user_num_countries = 5
    
    print(f"\nSearching for a {user_num_countries}-country travel plan...")
    
    best_plan = find_best_travel_plan(
        flights=all_flights,
        start_city=user_start_city,
        cities_choice=[c.code for c in CITIES_BY_CODE.values()],
        num_countries=user_num_countries,
        min_layover_hours=10,
        max_layover_hours=48
    )
    
    if best_plan:
        print("\n--- Best Travel Plan Found! ---")
        for i, flight in enumerate(best_plan.flights):
            dep_city = get_city_by_code(flight.departure_city_code)
            arr_city = get_city_by_code(flight.arrival_city_code)
            print(
                f"  {i+1}. {dep_city.name} ({dep_city.code}) -> {arr_city.name} ({arr_city.code})"
                f" | Departs: {flight.departure_datetime}, Arrives: {flight.arrival_datetime}"
            )
        print(f"\nTotal flight duration: {best_plan.total_duration}")
    else:
        print("\nNo travel plan found matching the criteria.")