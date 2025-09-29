import heapq
from typing import List, Optional, Dict, Tuple, Set
from collections import defaultdict
from datetime import timedelta, date

from data_handler import expand_flights_for_date_range, load_flights
from models import TravelPlan, Flight, get_city_by_code, CITIES

def find_best_travel_plan(
    base_flights: List[Flight],
    start_date: date,
    end_date: date,
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
    forced_cities: Optional[List[str]] = None,
    top_n: int = 5
) -> List[TravelPlan]:
    """
    Balanced search: faster with forced cities but still finds diverse results.
    """
    if not base_flights or not cities_choice or num_countries <= 0:
        return []

    # 1. Expand and Pre-filter flights
    search_flights = expand_flights_for_date_range(base_flights, start_date, end_date)
    pre_filtered_flights = []
    for flight in search_flights:
        if (flight_class_filter != "ALL" and flight_class_filter != flight.flight_class) or \
           (direct_flights_only and flight.transfers > 0) or \
           (flight.departure_city_code not in cities_choice or flight.arrival_city_code not in cities_choice):
            continue
        if no_fly_start_hour is not None and no_fly_end_hour is not None:
            dep_hour = flight.departure_time.hour
            is_overnight = no_fly_start_hour > no_fly_end_hour
            if (is_overnight and (dep_hour >= no_fly_start_hour or dep_hour < no_fly_end_hour)) or \
               (not is_overnight and (no_fly_start_hour <= dep_hour < no_fly_end_hour)):
                continue
        pre_filtered_flights.append(flight)
    
    if not pre_filtered_flights: return []

    # **OPTIMIZATION**: If forced cities exist, pre-filter to only flights touching forced cities
    forced_cities_set = set(forced_cities) if forced_cities else set()
    if forced_cities_set:
        filtered_with_forced = [
            f for f in pre_filtered_flights 
            if f.departure_city_code in forced_cities_set or f.arrival_city_code in forced_cities_set
        ]
        other_flights = [
            f for f in pre_filtered_flights 
            if f.departure_city_code not in forced_cities_set and f.arrival_city_code not in forced_cities_set
        ]
        print(f"Flights touching forced cities: {len(filtered_with_forced)}, Other flights: {len(other_flights)}")
        # Use forced city flights + a sample of others for connections
        pre_filtered_flights = filtered_with_forced + other_flights
    
    flights_by_departure = defaultdict(list)
    for flight in pre_filtered_flights:
        flights_by_departure[flight.departure_city_code].append(flight)

    # --- Search Initialization ---
    target_country_count = num_countries + 1 if start_city else num_countries
    # State: (duration, counter, path, countries, cities_visited_set)
    priority_queue: List[Tuple[timedelta, int, List[Flight], frozenset, set]] = []
    found_plans: Dict[Tuple[str, ...], TravelPlan] = {}
    counter = 0

    # 2. Seed the Priority Queue
    initial_cities = [start_city] if start_city else cities_choice
    for city_code in initial_cities:
        start_country_obj = get_city_by_code(city_code)
        if not start_country_obj: continue
        start_country = start_country_obj.country
        
        for flight in flights_by_departure.get(city_code, []):
            arrival_city_obj = get_city_by_code(flight.arrival_city_code)
            if not arrival_city_obj or arrival_city_obj.country == start_country:
                continue
            
            initial_path = [flight]
            initial_duration = flight.duration
            initial_countries = frozenset([start_country, arrival_city_obj.country])
            initial_cities_visited = {city_code, flight.arrival_city_code}
            heapq.heappush(priority_queue, (initial_duration, counter, initial_path, initial_countries, initial_cities_visited))
            counter += 1

    # 3. Search Loop
    paths_explored = 0
    paths_pruned_forced = 0
    pruning_threshold = None

    while priority_queue:
        paths_explored += 1
        if paths_explored % 10000 == 0:
            print(f"Paths: {paths_explored}, Pruned(forced): {paths_pruned_forced}, Plans: {len(found_plans)}, Queue: {len(priority_queue)}")

        current_duration, _, current_path, visited_countries, visited_cities = heapq.heappop(priority_queue)

        if pruning_threshold and current_duration >= pruning_threshold:
            continue
        
        last_flight = current_path[-1]
        
        # --- SMART PRUNING for forced cities ---
        if forced_cities_set:
            forced_visited = forced_cities_set.intersection(visited_cities)
            forced_remaining = len(forced_cities_set) - len(forced_visited)
            
            # Only prune if we've reached target countries AND missing forced cities
            if len(visited_countries) >= target_country_count and forced_remaining > 0:
                paths_pruned_forced += 1
                continue
            
            # Prune if mathematically impossible to visit remaining forced cities
            countries_left = target_country_count - len(visited_countries)
            if forced_remaining > 0 and countries_left < forced_remaining:
                paths_pruned_forced += 1
                continue
        
        # --- GOAL CHECK ---
        if len(visited_countries) >= target_country_count and ((not end_city) or (last_flight.arrival_city_code == end_city)):
            
            # Check forced cities requirement
            if forced_cities_set and not forced_cities_set.issubset(visited_cities):
                paths_pruned_forced += 1
                continue

            new_plan = TravelPlan(flights=list(current_path))
            first_city = start_city if start_city else current_path[0].departure_city_code
            path_signature = tuple([first_city] + [f.arrival_city_code for f in new_plan.flights])
            
            if path_signature not in found_plans or new_plan.total_duration < found_plans[path_signature].total_duration:
                found_plans[path_signature] = new_plan

                if len(found_plans) > top_n:
                    sorted_plans = sorted(found_plans.values(), key=lambda p: p.total_duration, reverse=True)
                    worst_plan_to_remove = sorted_plans[0]
                    
                    sig_to_remove = next(sig for sig, plan in found_plans.items() if plan is worst_plan_to_remove)
                    del found_plans[sig_to_remove]

            if len(found_plans) == top_n:
                pruning_threshold = max(p.total_duration for p in found_plans.values())

            continue

        # --- Explore Next Flights ---
        departure_city_code = last_flight.arrival_city_code
        for next_flight in flights_by_departure.get(departure_city_code, []):
            if next_flight.departure_datetime < last_flight.arrival_datetime: continue
            layover = next_flight.departure_datetime - last_flight.arrival_datetime
            if not (timedelta(hours=min_layover_hours) <= layover <= timedelta(hours=max_layover_hours)):
                continue

            arrival_city_obj = get_city_by_code(next_flight.arrival_city_code)
            if not arrival_city_obj or arrival_city_obj.country in visited_countries:
                continue

            new_path = current_path + [next_flight]
            new_duration = current_duration + next_flight.duration
            new_countries = visited_countries.union({arrival_city_obj.country})
            new_cities_visited = visited_cities.copy()
            new_cities_visited.add(next_flight.arrival_city_code)

            heapq.heappush(priority_queue, (new_duration, counter, new_path, new_countries, new_cities_visited))
            counter += 1

    print(f"Search complete: {paths_explored} paths explored, {paths_pruned_forced} pruned due to forced cities")
    
    # 4. Final Processing
    unique_best_plans = list(found_plans.values())
    unique_best_plans.sort(key=lambda p: p.total_duration)
    return unique_best_plans[:top_n]


if __name__ == '__main__':
    print("--- Running Test Search (Balanced) ---")
    base_flights = load_flights("merged_flight_data.xlsx")
    if not base_flights:
        print("Could not load flight data. Exiting.")
        exit()
    
    params = {
        "base_flights": base_flights,
        "start_date": date(2025, 9, 29),
        "end_date": date(2025, 10, 5),
        "start_city": "CAI",
        "end_city": None,
        "cities_choice": [c['code'] for c in CITIES],
        "num_countries": 3,
        "min_layover_hours": 12,
        "max_layover_hours": 72,
        "flight_class_filter": "ALL",
        "forced_cities": ["ALG", "CMN"],
        "top_n": 5
    }

    print(f"\nSearching for {params['top_n']} plans visiting {params['num_countries']} countries from {params['start_city']}, forcing {params['forced_cities']}...")
    
    top_plans = find_best_travel_plan(**params)
    
    if top_plans:
        print(f"\n--- Found {len(top_plans)} Travel Plan(s) ---")
        for i, plan in enumerate(top_plans):
            print(f"\n--- Plan {i+1} | Total Flight Duration: {plan.total_duration} ---")
            
            first_city = params['start_city'] if params['start_city'] else (plan.flights[0].departure_city_code if plan.flights else "N/A")
            route_sig = [first_city] + [f.arrival_city_code for f in plan.flights]
            print(f"  Route: {' -> '.join(route_sig)}")
            
            cities_in_path = {params['start_city']} if params['start_city'] else set()
            for f in plan.flights:
                cities_in_path.add(f.departure_city_code)
                cities_in_path.add(f.arrival_city_code)
            print(f"  Cities visited: {cities_in_path}")
    else:
        print("\nNo travel plan found matching the criteria.")