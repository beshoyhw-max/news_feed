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
    flight_class_filter: str = "ALL",
    max_transfers: Optional[int] = None,
    min_layover_hours: int = 10,
    max_layover_hours: int = 48,
    max_flight_duration_hours: Optional[int] = None,
    no_fly_start_hour: Optional[int] = None,
    no_fly_end_hour: Optional[int] = None,
    forced_cities: Optional[List[str]] = None,
    stop_event: Optional[object] = None,
    top_n: int = 5
) -> List[TravelPlan]:
    """
    Balanced search: faster with forced cities but still finds diverse results.
    
    Country counting logic:
    - If start_city is specified: visit num_countries ADDITIONAL countries (start country doesn't count)
    - If start_city is None (Any): visit exactly num_countries total
    - End city always counts unless it's the same as start country
    """
    if not base_flights or not cities_choice or num_countries <= 0:
        return []

    # 1. Expand and Pre-filter flights
    search_flights = expand_flights_for_date_range(base_flights, start_date, end_date)
    
    pre_filtered_flights = []
    for flight in search_flights:
        if (flight_class_filter != "ALL" and flight_class_filter not in flight.flight_class) or \
           (max_transfers is not None and flight.transfers > max_transfers) or \
           (flight.departure_city_code not in cities_choice or flight.arrival_city_code not in cities_choice) or \
           (max_flight_duration_hours is not None and flight.duration > timedelta(hours=max_flight_duration_hours)):
            continue
        if no_fly_start_hour is not None and no_fly_end_hour is not None:
            dep_hour = flight.departure_time.hour
            is_overnight = no_fly_start_hour > no_fly_end_hour
            if (is_overnight and (dep_hour >= no_fly_start_hour or dep_hour < no_fly_end_hour)) or \
               (not is_overnight and (no_fly_start_hour <= dep_hour < no_fly_end_hour)):
                continue
        pre_filtered_flights.append(flight)
    print(f"Total flights after filtering: {len(pre_filtered_flights)}")

    if not pre_filtered_flights: return []

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
        pre_filtered_flights = filtered_with_forced + other_flights
    
    flights_by_departure = defaultdict(list)
    for flight in pre_filtered_flights:
        flights_by_departure[flight.departure_city_code].append(flight)

    # Get start country if specified
    start_country = None
    if start_city:
        start_country_obj = get_city_by_code(start_city)
        start_country = start_country_obj.country if start_country_obj else None
    
    # Target is the number of NEW countries to visit (excluding start)
    target_country_count = num_countries
    
    priority_queue: List[Tuple[timedelta, int, List[Flight], frozenset, set]] = []
    found_plans: Dict[Tuple[str, ...], TravelPlan] = {}
    counter = 0

    # 2. Seed the Priority Queue
    initial_cities = [start_city] if start_city else cities_choice
    for city_code in initial_cities:
        start_country_obj = get_city_by_code(city_code)
        if not start_country_obj: continue
        current_start_country = start_country_obj.country
        
        for flight in flights_by_departure.get(city_code, []):
            arrival_city_obj = get_city_by_code(flight.arrival_city_code)
            if not arrival_city_obj or arrival_city_obj.country == current_start_country:
                continue
            
            initial_path = [flight]
            initial_duration = flight.duration
            initial_countries = frozenset([current_start_country, arrival_city_obj.country])
            initial_cities_visited = {city_code, flight.arrival_city_code}
            heapq.heappush(priority_queue, (initial_duration, counter, initial_path, initial_countries, initial_cities_visited))
            counter += 1

    # 3. Search Loop
    paths_explored = 0
    paths_pruned_forced = 0
    paths_pruned_impossible = 0
    pruning_threshold = None

    while priority_queue:
        if stop_event and stop_event.is_set():
            print("Search stopped by user.")
            break
        paths_explored += 1
        if paths_explored % 10000 == 0:
            print(f"Paths: {paths_explored}, Pruned(forced): {paths_pruned_forced}, Pruned(impossible): {paths_pruned_impossible}, Plans: {len(found_plans)}, Queue: {len(priority_queue)}")

        current_duration, _, current_path, visited_countries, visited_cities = heapq.heappop(priority_queue)

        # Calculate how many NEW countries we've visited (excluding start if specified)
        if start_city and start_country and start_country in visited_countries:
            new_countries_count = len(visited_countries) - 1
        else:
            new_countries_count = len(visited_countries)

        # CRITICAL OPTIMIZATION: Early exit if we can't possibly beat existing plans
        if pruning_threshold and current_duration >= pruning_threshold:
            continue

        # Prune if we've already visited more countries than target
        if new_countries_count > target_country_count:
            continue
        
        last_flight = current_path[-1]
        
        # --- SMART PRUNING for forced cities ---
        if forced_cities_set:
            forced_visited = forced_cities_set.intersection(visited_cities)
            forced_remaining = len(forced_cities_set) - len(forced_visited)
            
            if new_countries_count >= target_country_count and forced_remaining > 0:
                paths_pruned_forced += 1
                continue
            
            countries_left = target_country_count - new_countries_count
            if forced_remaining > 0 and countries_left < forced_remaining:
                paths_pruned_forced += 1
                continue
            
            # NEW: Check if forced cities are even reachable from current location
            # If we still need to visit forced cities but have no flights to them
            if forced_remaining > 0 and countries_left > 0:
                current_location = last_flight.arrival_city_code
                # Check if any forced city is reachable with remaining countries budget
                can_reach_forced = False
                for forced_city in forced_cities_set:
                    if forced_city in visited_cities:
                        continue
                    # Check if there's any path from current location to this forced city
                    # Check direct flights from current location to forced city
                    for flight in flights_by_departure.get(current_location, []):
                        if flight.arrival_city_code == forced_city:
                            can_reach_forced = True
                            break
                    if can_reach_forced:
                        break
                    
                    # Check 1-hop connections (current → intermediate → forced)
                    for next_flight in flights_by_departure.get(current_location, []):
                        intermediate = next_flight.arrival_city_code
                        for connecting_flight in flights_by_departure.get(intermediate, []):
                            if connecting_flight.arrival_city_code == forced_city:
                                can_reach_forced = True
                                break
                        if can_reach_forced:
                            break
                    if can_reach_forced:
                        break
                
                if not can_reach_forced:
                    paths_pruned_impossible += 1
                    continue
        
        # --- GOAL CHECK ---
        reached_target = new_countries_count >= target_country_count
        
        if reached_target and ((not end_city) or (last_flight.arrival_city_code == end_city)):
            
            # Check forced cities requirement
            if forced_cities_set and not forced_cities_set.issubset(visited_cities):
                paths_pruned_forced += 1
                continue
            new_plan = TravelPlan(flights=list(current_path))
            path_valid = True
            if start_city:
                if new_plan.flights[0].departure_city_code != start_city:
                    print(f"ERROR: Path doesn't start from {start_city}! Starts from {new_plan.flights[0].departure_city_code}")
                    path_valid = False
            
            for i in range(len(new_plan.flights) - 1):
                if new_plan.flights[i].arrival_city_code != new_plan.flights[i+1].departure_city_code:
                    print(f"ERROR: Discontinuity between flight {i} and {i+1}!")
                    print(f"  Flight {i} arrives at: {new_plan.flights[i].arrival_city_code}")
                    print(f"  Flight {i+1} departs from: {new_plan.flights[i+1].departure_city_code}")
                    path_valid = False
                    break
            
            if not path_valid:
                continue
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
            if next_flight.departure_city_code != departure_city_code:
                print(f"ERROR: Discontinuous route! Last arrival: {departure_city_code}, Next departure: {next_flight.departure_city_code}")
                continue
                    # NEW FIX: Don't visit end_city unless it's the final destination
            if end_city and next_flight.arrival_city_code == end_city:
                arrival_city_obj = get_city_by_code(next_flight.arrival_city_code)
                if arrival_city_obj:
                    end_city_is_new_country = arrival_city_obj.country not in visited_countries
                    # Check if visiting end_city now would complete our requirements
                    if end_city_is_new_country:
                        # If end_city is a new country, we need exactly target-1 countries visited
                        if new_countries_count != target_country_count - 1:
                            continue  # Can't visit end city yet, not enough countries visited
                    else:
                        # If end_city is not a new country, we need exactly target countries visited
                        if new_countries_count != target_country_count:
                            continue  # Can't visit end city yet, not enough countries visited
            
                
            if next_flight.departure_datetime < last_flight.arrival_datetime: continue
            layover = next_flight.departure_datetime - last_flight.arrival_datetime
            if not (timedelta(hours=min_layover_hours) <= layover <= timedelta(hours=max_layover_hours)):
                continue

            arrival_city_obj = get_city_by_code(next_flight.arrival_city_code)
            if not arrival_city_obj:
                continue

            is_new_country = arrival_city_obj.country not in visited_countries
            
            # CRITICAL: Only allow exploring to a new country if we haven't exceeded the limit
            # OR if it's the final leg to the end city
            
            if not is_new_country:

                is_final_leg_home = (
                    end_city is not None and
                    next_flight.arrival_city_code == end_city and
                    new_countries_count >= target_country_count
                )

            # If it's going to an already-visited country
                # Only allow if it's the valid final leg to end_city
                if not is_final_leg_home:
                    continue
            else:
                # It's a new country - only allow if we haven't reached the limit yet
                # UNLESS it's also the end city (which would make it the final leg)
                if new_countries_count >= target_country_count:
                    # We've reached the target, only allow if this IS the end city
                    if not (end_city and next_flight.arrival_city_code == end_city):
                        continue

            new_path = current_path + [next_flight]
            new_duration = current_duration + next_flight.duration
                        # OPTIMIZATION: Don't even add to queue if already too long
            if pruning_threshold and new_duration >= pruning_threshold:
                continue
            
            new_countries = visited_countries.union({arrival_city_obj.country})
            new_cities_visited = visited_cities.copy()
            new_cities_visited.add(next_flight.arrival_city_code)
            # CRITICAL: Check if this new path would exceed country limit
            # Calculate the new country count (excluding start if specified)
            if start_city and start_country and start_country in new_countries:
                new_path_countries_count = len(new_countries) - 1
            else:
                new_path_countries_count = len(new_countries)
            
            # Don't add paths that already exceed the target (unless it's the final destination)
            # Don't add paths that already exceed the target (unless it's the final destination)
            if new_path_countries_count > target_country_count:
                if not (end_city and next_flight.arrival_city_code == end_city):
                    continue

            # NEW: PRE-PRUNING FOR FORCED CITIES
            if forced_cities_set:
                forced_visited = forced_cities_set.intersection(new_cities_visited)
                forced_remaining = len(forced_cities_set) - len(forced_visited)
                
                # Calculate countries we can still visit
                countries_left_to_visit = target_country_count - new_path_countries_count
                
                # If we need to visit more forced cities than we have new countries left in our budget,
                # this path is impossible. Prune it now.
                if forced_remaining > 0 and countries_left_to_visit < forced_remaining:
                    continue # PRUNE! This path can never satisfy the forced cities constraint.

            # PUSH TO QUEUE
            heapq.heappush(priority_queue, (new_duration, counter, new_path, new_countries, new_cities_visited))
            counter += 1

    print(f"Search complete: {paths_explored} paths explored, {paths_pruned_forced} pruned (forced cities), {paths_pruned_impossible} pruned (unreachable)")
    
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