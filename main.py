import heapq
from typing import List, Optional, Dict, Tuple
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
    Finds the top N best travel plans using a uniform-cost search algorithm (a variation of A*)
    to guarantee the discovery of the optimal path.
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

    flights_by_departure = defaultdict(list)
    for flight in pre_filtered_flights:
        flights_by_departure[flight.departure_city_code].append(flight)

    # --- Search Initialization ---
    target_country_count = num_countries + 1 if start_city else num_countries
    priority_queue: List[Tuple[timedelta, int, List[Flight], frozenset]] = []
    found_plans: Dict[Tuple[str, ...], TravelPlan] = {}
    counter = 0
    forced_cities_set = set(forced_cities) if forced_cities else set()

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
            heapq.heappush(priority_queue, (initial_duration, counter, initial_path, initial_countries))
            counter += 1

    # 3. Search Loop
    paths_explored = 0
    pruning_threshold = None

    while priority_queue:
        paths_explored += 1
        if paths_explored % 10000 == 0:
            print(f"Paths explored (A*): {paths_explored}...")

        current_duration, _, current_path, visited_countries = heapq.heappop(priority_queue)

        if pruning_threshold and current_duration >= pruning_threshold:
            continue
        
        last_flight = current_path[-1]
        
        # --- GOAL CHECK ---
        if len(visited_countries) >= target_country_count and ((not end_city) or (last_flight.arrival_city_code == end_city)):
            
            # Check for forced cities
            if forced_cities_set:
                path_cities = {f.departure_city_code for f in current_path}.union({f.arrival_city_code for f in current_path})
                if not forced_cities_set.issubset(path_cities):
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

            heapq.heappush(priority_queue, (new_duration, counter, new_path, new_countries))
            counter += 1

    # 4. Final Processing
    unique_best_plans = list(found_plans.values())
    unique_best_plans.sort(key=lambda p: p.total_duration)
    return unique_best_plans[:top_n]


if __name__ == '__main__':
    print("--- Running Test Search from main.py (A* Algorithm) ---")
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
        "forced_cities": ["ALG", "CMN"], # Example of forcing Algiers and Casablanca
        "top_n": 5
    }

    print(f"\nSearching for top {params['top_n']} diverse plans visiting {params['num_countries']} countries, starting from {params['start_city']} and forcing {params['forced_cities']}...")
    
    top_plans = find_best_travel_plan(**params)
    
    if top_plans:
        print(f"\n--- Found {len(top_plans)} Optimal and Diverse Travel Plan(s) (A*) ---")
        for i, plan in enumerate(top_plans):
            print(f"\n--- Plan {i+1} | Total Flight Duration: {plan.total_duration} ---")
            
            first_city = params['start_city'] if params['start_city'] else (plan.flights[0].departure_city_code if plan.flights else "N/A")
            route_sig = [first_city] + [f.arrival_city_code for f in plan.flights]
            print(f"  Route Signature: {' -> '.join(route_sig)}")

            for j, flight in enumerate(plan.flights):
                dep_city = get_city_by_code(flight.departure_city_code)
                arr_city = get_city_by_code(flight.arrival_city_code)
                print(f"  {j+1}. {dep_city.name} ({dep_city.code}) -> {arr_city.name} ({arr_city.code}) | {flight.departure_datetime.strftime('%m-%d %H:%M')} to {flight.arrival_datetime.strftime('%m-%d %H:%M')}")
    else:
        print("\nNo travel plan found matching the criteria.")
