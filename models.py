from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict

CITIES: List[Dict[str, str]] = [
    {'name': 'Bamako', 'name_cn': '巴马科', 'code': 'BKO', 'country': 'Mali', 'country_cn': '马里'},
    {'name': 'Algiers', 'name_cn': '阿尔及尔', 'code': 'ALG', 'country': 'Algeria', 'country_cn': '阿尔及利亚'},
    {'name': 'Malabo', 'name_cn': '马拉博', 'code': 'SSG', 'country': 'Equatorial Guinea', 'country_cn': '赤道几内亚'},
    {'name': 'Cotonou', 'name_cn': '科托努', 'code': 'COO', 'country': 'Benin', 'country_cn': '贝宁'},
    {'name': 'Tunis', 'name_cn': '突尼斯', 'code': 'TUN', 'country': 'Tunisia', 'country_cn': '突尼斯'},
    {'name': 'Abidjan', 'name_cn': '阿比让', 'code': 'ABJ', 'country': 'Cote dIvoire', 'country_cn': '科特迪瓦'},
    {'name': 'Nouakchott', 'name_cn': '努瓦克肖特', 'code': 'NKC', 'country': 'Mauritania', 'country_cn': '毛里塔尼亚'},
    {'name': 'Casablanca', 'name_cn': '卡萨布兰卡', 'code': 'CMN', 'country': 'Morocco', 'country_cn': '摩洛哥'},
    {'name': 'Ouagadougou', 'name_cn': '瓦加杜古', 'code': 'OUA', 'country': 'Burkina Faso', 'country_cn': '布基纳法索'},
    {'name': 'Niamey', 'name_cn': '尼亚美', 'code': 'NIM', 'country': 'Niger', 'country_cn': '尼日尔'},
    {'name': 'Lome', 'name_cn': '洛美', 'code': 'LFW', 'country': 'Togo', 'country_cn': '多哥'},
    {'name': 'Dakar', 'name_cn': '达喀尔', 'code': 'DSS', 'country': 'Senegal', 'country_cn': '塞内加尔'},
    {'name': 'Addis Ababa', 'name_cn': '亚的斯亚贝巴', 'code': 'ADD', 'country': 'Ethiopia', 'country_cn': '埃塞俄比亚'},
    {'name': 'Cairo', 'name_cn': '开罗', 'code': 'CAI', 'country': 'Egypt', 'country_cn': '埃及'},
    {'name': 'Douala', 'name_cn': '杜阿拉', 'code': 'DLA', 'country': 'Cameroon', 'country_cn': '喀麦隆'},
    {'name': 'Yaounde', 'name_cn': '雅温得', 'code': 'NSI', 'country': 'Cameroon', 'country_cn': '喀麦隆'},
    {'name': 'Djibouti', 'name_cn': '吉布提', 'code': 'JIB', 'country': 'Djibouti', 'country_cn': '吉布提'},
    {'name': 'Juba', 'name_cn': '朱巴', 'code': 'JUB', 'country': 'South Sudan', 'country_cn': '南苏丹'},
    {'name': 'Libreville', 'name_cn': '利伯维尔', 'code': 'LBV', 'country': 'Gabon', 'country_cn': '加蓬'},
    {'name': 'Benghazi', 'name_cn': '班加西', 'code': 'BEN', 'country': 'Libya', 'country_cn': '利比亚'},
    {'name': 'Tripoli', 'name_cn': '的黎波里', 'code': 'TIP', 'country': 'Libya', 'country_cn': '利比亚'},
    {'name': 'Monrovia', 'name_cn': '蒙罗维亚', 'code': 'ROB', 'country': 'Liberia', 'country_cn': '利比里亚'},
    {'name': 'Kinshasa', 'name_cn': '金沙萨', 'code': 'FIH', 'country': 'DR Congo', 'country_cn': '刚果（金）'},
    {'name': 'Brazzaville', 'name_cn': '布拉柴维尔', 'code': 'BZV', 'country': 'Congo-Brazzaville', 'country_cn': '刚果（布）'},
    {'name': 'Conakry', 'name_cn': '科纳克里', 'code': 'CKY', 'country': 'Guinea', 'country_cn': '几内亚'},
    {'name': 'Banjul', 'name_cn': '班珠尔', 'code': 'BJL', 'country': 'Gambia', 'country_cn': '冈比亚'},
    {'name': 'Praia', 'name_cn': '普拉亚', 'code': 'RAI', 'country': 'Cape Verde', 'country_cn': '佛得角'},
    {'name': 'NDjamena', 'name_cn': '恩贾梅纳', 'code': 'NDJ', 'country': 'Chad', 'country_cn': '乍得'},
    {'name': 'Bangui', 'name_cn': '班吉', 'code': 'BGF', 'country': 'Central African Republic', 'country_cn': '中非共和国'}
]

@dataclass
class City:
    name: str
    name_cn: str
    code: str
    country: str
    country_cn: str

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
    transfer_info: str
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
