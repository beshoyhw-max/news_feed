import heapq
from typing import List, Optional, Dict, Tuple, Set
from collections import defaultdict
from datetime import timedelta, datetime
import itertools

# Assuming these are defined in your project structure
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
    top_n: int = 3,  # Parameter to control how many best plans to find
) -> List[TravelPlan]:
    """
    Finds the top_n best travel plans with distinctly different country paths.
    """
    verbose_logging = False

    if not flights or not cities_choice:
        return []

    # --- Pre-filtering Stage ---
    print("Pre-filtering flights based on user criteria...")
    pre_filtered_flights = []
    for flight in flights:
        if flight_class_filter != "ALL" and flight_class_filter not in flight.flight_class: continue
        if direct_flights_only and flight.transfers > 0: continue
        if (flight.departure_city_code not in cities_choice) or (flight.arrival_city_code not in cities_choice): continue
        
        if no_fly_start_hour is not None and no_fly_end_hour is not None:
            s, e = no_fly_start_hour, no_fly_end_hour
            allowed_hours = set()
            if s > e:
                for h in range(e, s): allowed_hours.add(h)
            else:
                for h in range(0, 24):
                    if not (s <= h < e): allowed_hours.add(h)
            dep_h, arr_h = flight.departure_time.hour, flight.arrival_time.hour
            if dep_h not in allowed_hours or arr_h not in allowed_hours: continue

        pre_filtered_flights.append(flight)
    
    print(f"Reduced flight list to {len(pre_filtered_flights)} flights.")
    if not pre_filtered_flights: return []

    min_flight_duration = min((f.duration for f in pre_filtered_flights if f.duration > timedelta(0)), default=timedelta(0))
    print(f"Calculated minimum flight duration for heuristic: {min_flight_duration}")

    flights_by_departure_city = defaultdict(list)
    for flight in pre_filtered_flights:
        flights_by_departure_city[flight.departure_city_code].append(flight)

    pq = [] 
    visited: Dict[Tuple[str, frozenset], datetime] = {}
    tie_breaker = itertools.count()

    initial_cities = [start_city] if start_city else cities_choice
    target_country_count = num_countries + 1 if start_city else num_countries
    
    for city_code in initial_cities:
        # Always initialize the visited_countries with the starting country.
        # This is crucial for the revisit logic to work correctly from the first flight.
        start_country = get_city_by_code(city_code).country
        visited_countries = {start_country}
        
        countries_needed = target_country_count - len(visited_countries)
        heuristic_cost = max(0, countries_needed) * min_flight_duration
        initial_state = (heuristic_cost, timedelta(0), next(tie_breaker), [], visited_countries, city_code)
        heapq.heappush(pq, initial_state)

    print(f"Starting A* search. Initial queue size: {len(pq)}")
    paths_explored = 0
    found_plans = []

    while pq:
        paths_explored += 1
        if paths_explored % 100000 == 0:
            print(f"  ... explored {paths_explored} paths ...")
            
        priority, duration, _, path, visited_countries, current_city_code = heapq.heappop(pq)
        
        current_arrival_time = path[-1].arrival_datetime if path else datetime.min
        visited_key = (current_city_code, frozenset(visited_countries))

        if visited_key in visited and visited[visited_key] <= current_arrival_time:
            continue
        visited[visited_key] = current_arrival_time
        
        if found_plans and duration > found_plans[-1].total_duration and len(found_plans) == top_n:
            continue

        if len(visited_countries) == target_country_count:
            if not end_city or (end_city and current_city_code == end_city):
                new_plan = TravelPlan(flights=path)

                # --- Final Filter for Unwanted Round Trips ---
                # A plan is an unwanted round trip if it starts and ends in the same country,
                # UNLESS the user explicitly requested it by setting start and end cities to the same value.
                is_explicit_round_trip = start_city is not None and start_city == end_city
                if not is_explicit_round_trip:
                    origin_country = get_city_by_code(new_plan.flights[0].departure_city_code).country
                    destination_country = get_city_by_code(new_plan.flights[-1].arrival_city_code).country
                    if origin_country == destination_country:
                        continue # Discard the plan
                
                # --- NEW DIVERSITY LOGIC ---
                # Create a signature for the path based on the sequence of countries
                countries_in_order = [get_city_by_code(path[0].departure_city_code).country]
                for flight in path:
                    arrival_country = get_city_by_code(flight.arrival_city_code).country
                    if arrival_country != countries_in_order[-1]:
                        countries_in_order.append(arrival_country)
                path_signature = tuple(countries_in_order)

                # Check if a plan with the same path signature already exists
                existing_plan_index = -1
                for i, plan in enumerate(found_plans):
                    existing_countries = [get_city_by_code(plan.flights[0].departure_city_code).country]
                    for f in plan.flights:
                        ac = get_city_by_code(f.arrival_city_code).country
                        if ac != existing_countries[-1]:
                            existing_countries.append(ac)
                    if tuple(existing_countries) == path_signature:
                        existing_plan_index = i
                        break

                if existing_plan_index != -1:
                    # A plan with this path exists. Replace it if the new one is better.
                    if new_plan.total_duration < found_plans[existing_plan_index].total_duration:
                        found_plans[existing_plan_index] = new_plan
                        found_plans.sort(key=lambda p: p.total_duration)
                else:
                    # This is a new, unique path. Add it if there's space or it's better than the worst.
                    if len(found_plans) < top_n:
                        found_plans.append(new_plan)
                        found_plans.sort(key=lambda p: p.total_duration)
                    elif new_plan.total_duration < found_plans[-1].total_duration:
                        found_plans.pop()
                        found_plans.append(new_plan)
                        found_plans.sort(key=lambda p: p.total_duration)
                continue
                # --- END DIVERSITY LOGIC ---

        for flight in flights_by_departure_city.get(current_city_code, []):
            if path:
                layover = flight.departure_datetime - path[-1].arrival_datetime
                if not (timedelta(hours=min_layover_hours) <= layover <= timedelta(hours=max_layover_hours)):
                    continue

            arrival_city = get_city_by_code(flight.arrival_city_code)
            if not arrival_city: continue

            is_revisit = arrival_city.country in visited_countries
            is_valid_return_flight = (is_revisit and end_city == start_city and arrival_city.code == end_city and len(visited_countries) == target_country_count)
            
            if is_revisit and not is_valid_return_flight:
                continue
            
            new_visited_countries = visited_countries.union({arrival_city.country})
            
            if len(new_visited_countries) > target_country_count:
                continue

            new_path = path + [flight]
            new_duration = sum((f.duration for f in new_path), timedelta())
            countries_needed = target_country_count - len(new_visited_countries)
            heuristic_cost = max(0, countries_needed) * min_flight_duration
            new_priority = new_duration + heuristic_cost
            new_state = (new_priority, new_duration, next(tie_breaker), new_path, new_visited_countries, flight.arrival_city_code)
            heapq.heappush(pq, new_state)

    if found_plans:
        print(f"--- Search complete. Found {len(found_plans)} best plans. ---")
    else:
        print("--- Search complete. No valid plan found. ---")
        
    return found_plans

if __name__ == '__main__':
    print("--- Running Test Search from main.py ---")
    all_flights = load_flights("merged_flight_data.xlsx")
    if not all_flights:
        print("Could not load flight data. Exiting."); exit()
    print(f"Loaded {len(all_flights)} flights.")

    best_plans = find_best_travel_plan(
        flights=all_flights,
        start_city="CAI",
        cities_choice=[c.code for c in CITIES_BY_CODE.values()],
        num_countries=4,
        min_layover_hours=10,
        max_layover_hours=72
    )
    
    if best_plans:
        for i, plan in enumerate(best_plans):
            print(f"\n--- Plan {i+1} ---")
            print(f"Total flight duration: {plan.total_duration}")
            for flight in plan.flights:
                dep_city = get_city_by_code(flight.departure_city_code)
                arr_city = get_city_by_code(flight.arrival_city_code)
                print(f"  {dep_city.code} -> {arr_city.code} | {flight.departure_datetime} -> {flight.arrival_datetime}")
    else:
        print("\nNo travel plan found matching the criteria for the test case.")

