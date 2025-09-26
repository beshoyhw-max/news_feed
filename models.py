from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict

CITIES: List[Dict[str, str]] = [
    {'name': 'Bamako', 'code': 'BKO', 'country': 'Mali'},
    {'name': 'Algiers', 'code': 'ALG', 'country': 'Algeria'},
    {'name': 'Malabo', 'code': 'SSG', 'country': 'Equatorial Guinea'},
    {'name': 'Cotonou', 'code': 'COO', 'country': 'Benin'},
    {'name': 'Tunis', 'code': 'TUN', 'country': 'Tunisia'},
    {'name': 'Abidjan', 'code': 'ABJ', 'country': 'Cote dIvoire'},
    {'name': 'Nouakchott', 'code': 'NKC', 'country': 'Mauritania'},
    {'name': 'Casablanca', 'code': 'CMN', 'country': 'Morocco'},
    {'name': 'Ouagadougou', 'code': 'OUA', 'country': 'Burkina Faso'},
    {'name': 'Niamey', 'code': 'NIM', 'country': 'Niger'},
    {'name': 'Lome', 'code': 'LFW', 'country': 'Togo'},
    {'name': 'Dakar', 'code': 'DSS', 'country': 'Senegal'},
    {'name': 'Addis Ababa', 'code': 'ADD', 'country': 'Ethiopia'},
    {'name': 'Cairo', 'code': 'CAI', 'country': 'Egypt'},
    {'name': 'Douala', 'code': 'DLA', 'country': 'Cameroon'},
    {'name': 'Yaounde', 'code': 'NSI', 'country': 'Cameroon'},
    {'name': 'Djibouti', 'code': 'JIB', 'country': 'Djibouti'},
    {'name': 'Juba', 'code': 'JUB', 'country': 'South Sudan'},
    {'name': 'Libreville', 'code': 'LBV', 'country': 'Gabon'},
    {'name': 'Benghazi', 'code': 'BEN', 'country': 'Libya'},
    {'name': 'Tripoli', 'code': 'TIP', 'country': 'Libya'},
    {'name': 'Monrovia', 'code': 'ROB', 'country': 'Liberia'},
    {'name': 'Kinshasa', 'code': 'FIH', 'country': 'DR Congo'},
    {'name': 'Brazzaville', 'code': 'BZV', 'country': 'Congo-Brazzaville'},
    {'name': 'Conakry', 'code': 'CKY', 'country': 'Guinea'},
    {'name': 'Banjul', 'code': 'BJL', 'country': 'Gambia'},
    {'name': 'Praia', 'code': 'RAI', 'country': 'Cape Verde'},
    {'name': 'NDjamena', 'code': 'NDJ', 'country': 'Chad'},
    {'name': 'Bangui', 'code': 'BGF', 'country': 'Central African Republic'}
]

@dataclass
class City:
    name: str
    code: str
    country: str

@dataclass
class Flight:
    date: datetime.date
    airline: str
    flight_number: str
    flight_class: str
    departure_city_code: str
    arrival_city_code: str
    departure_time: datetime.time
    arrival_time: datetime.time
    departure_datetime: datetime
    arrival_datetime: datetime
    duration: timedelta
    transfers: int
    direct_flight: bool

@dataclass
class TravelPlan:
    flights: List[Flight] = field(default_factory=list)
    total_duration: timedelta = field(init=False)
    
    def __post_init__(self):
        self.total_duration = sum((f.duration for f in self.flights), timedelta())


# Helper for city lookups
CITIES_BY_CODE: Dict[str, City] = {
    city_data['code']: City(**city_data) for city_data in CITIES
}

def get_city_by_code(code: str) -> City | None:
    """Returns a City object for a given IATA code."""
    return CITIES_BY_CODE.get(code)
