import flet as ft
import threading
from datetime import timedelta
from main import find_best_travel_plan
from data_handler import load_flights
from models import CITIES_BY_CODE, get_city_by_code, TravelPlan

# --- Helper Functions ---
def format_delta(td: timedelta) -> str:
    """Formats a timedelta into a readable string like '3d 4h 5m' or '12h 30m'."""
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {int(hours)}h {int(minutes)}m"
    return f"{int(hours)}h {int(minutes)}m"

# --- Main Application ---
def main(page: ft.Page):
    page.title = "Executive Travel Plan Finder"
    page.window_width = 1600
    page.window_height = 950
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE_GREY, font_family="Microsoft YaHei")
    page.bgcolor = ft.Colors.GREY_200

    # --- Application State ---
    all_flights = []
    search_results = []
    city_name_to_code_map = {f"{city.country_cn} - {city.name_cn}": city.code for city in CITIES_BY_CODE.values()}
    sorted_cities = sorted(CITIES_BY_CODE.values(), key=lambda c: (c.country_cn, c.name_cn))
    city_display_names = [ft.dropdown.Option(text) for text in [f"{city.country_cn} - {city.name_cn}" for city in sorted_cities]]

    # --- UI Controls ---
    # Route Options
    start_city_dd = ft.Dropdown(label="出发城市", options=[ft.dropdown.Option("Any")] + city_display_names, value="Any", disabled=True)
    end_city_dd = ft.Dropdown(label="目的城市", options=[ft.dropdown.Option("Any")] + city_display_names, value="Any", disabled=True)
    num_countries_tf = ft.TextField(label="访问国家数量", value="3", width=150, disabled=True)

    # Flight Preferences
    min_layover_tf = ft.TextField(label="最短停留 (小时)", value="10", width=150, disabled=True)
    max_layover_tf = ft.TextField(label="最长停留 (小时)", value="48", width=150, disabled=True)
    flight_class_rg = ft.RadioGroup(content=ft.Row([
        ft.Radio(value="ALL", label="任何"),
        ft.Radio(value="Economy", label="经济舱"),
        ft.Radio(value="Business", label="商务舱"),
    ]), value="ALL", disabled=True)
    direct_only_cb = ft.Checkbox(label="仅限直飞航班", value=False, disabled=True)

    # Time Filter
    no_fly_start_tf = ft.TextField(label="从", value="23", width=70, disabled=True)
    no_fly_end_tf = ft.TextField(label="至", value="6", width=70, disabled=True)
    def toggle_time_filter(e):
        is_enabled = e.control.value
        no_fly_start_tf.disabled = not is_enabled
        no_fly_end_tf.disabled = not is_enabled
        page.update()
    no_fly_cb = ft.Checkbox(label="启用禁飞时段", on_change=toggle_time_filter, value=False, disabled=True)
    
    # Cities Checklist
    cities_checklist = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True)
    city_checkboxes = []
    for city in sorted_cities:
        cb = ft.Checkbox(label=f"{city.country_cn} - {city.name_cn} ({city.code})")
        city_checkboxes.append((cb, city.code))
        cities_checklist.controls.append(cb)
    
    def toggle_all_cities(e):
        for cb, _ in city_checkboxes:
            cb.value = e.control.value
        page.update()
    select_all_cities_cb = ft.Checkbox(label="Select All / Deselect All", on_change=toggle_all_cities)

    # Action Button
    find_button = ft.ElevatedButton(text="Find Optimal Plans", icon=ft.Icons.TRAVEL_EXPLORE, height=50, disabled=True)
    
    # Results Display
    results_view = ft.Column(
        alignment=ft.MainAxisAlignment.START,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        scroll=ft.ScrollMode.ADAPTIVE,
        expand=True
    )
    
    # --- Banner for Errors/Warnings ---
    def close_banner(e):
        page.banner.open = False
        page.update()

    page.banner = ft.Banner(
        bgcolor=ft.Colors.AMBER_100,
        leading=ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.AMBER, size=40),
        content=ft.Text(""), # Content will be set dynamically
        actions=[
            ft.TextButton("OK", on_click=close_banner),
        ]
    )
    
    # --- Event Handlers ---
    def find_plan_click(e):
        find_button.disabled = True
        results_view.controls.clear()
        results_view.alignment = ft.MainAxisAlignment.CENTER
        results_view.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        results_view.controls.append(ft.ProgressRing())
        results_view.controls.append(ft.Text("Calculating optimal routes...", size=16))
        page.update()

        try:
            params = {
                "start_city": city_name_to_code_map.get(start_city_dd.value) if start_city_dd.value != "Any" else None,
                "end_city": city_name_to_code_map.get(end_city_dd.value) if end_city_dd.value != "Any" else None,
                "num_countries": int(num_countries_tf.value),
                "min_layover_hours": int(min_layover_tf.value),
                "max_layover_hours": int(max_layover_tf.value),
                "no_fly_start_hour": int(no_fly_start_tf.value) if no_fly_cb.value else None,
                "no_fly_end_hour": int(no_fly_end_tf.value) if no_fly_cb.value else None,
                "cities_choice": [code for cb, code in city_checkboxes if cb.value],
                "flight_class_filter": flight_class_rg.value,
                "direct_flights_only": direct_only_cb.value
            }
        except ValueError:
            page.banner.content = ft.Text("Error: Please enter valid numbers for all numeric fields.")
            page.banner.bgcolor = ft.Colors.RED_100
            page.banner.leading = ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.RED, size=40)
            page.banner.open = True
            find_button.disabled = False
            results_view.controls.clear()
            page.update()
            return
        
        if not params["cities_choice"]:
            page.banner.content = ft.Text("Warning: Please select at least one city in the search scope.")
            page.banner.bgcolor = ft.Colors.AMBER_100
            page.banner.leading = ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.AMBER, size=40)
            page.banner.open = True
            find_button.disabled = False
            results_view.controls.clear()
            page.update()
            return

        thread = threading.Thread(target=run_search, args=(params,), daemon=True)
        thread.start()
        
    def run_search(params):
        nonlocal search_results
        search_results = find_best_travel_plan(flights=all_flights, **params)
        display_results()

    def display_results():
        results_view.alignment = ft.MainAxisAlignment.START
        results_view.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        results_view.controls.clear()

        if not search_results:
            centered_message = ft.Container(
                ft.Text("No travel plans found matching the specified criteria.", size=18, italic=True),
                alignment=ft.alignment.center,
                expand=True
            )
            results_view.controls.append(centered_message)
        else:
            summary = ft.Text(f"Found {len(search_results)} optimal and diverse travel plans.", size=18, weight=ft.FontWeight.BOLD)
            results_view.controls.append(summary)
            
            for i, plan in enumerate(search_results):
                results_view.controls.append(create_plan_card(plan, i+1))
        
        find_button.disabled = False
        page.update()

    def create_plan_card(plan, plan_num):
        flight_legs = []
        for i, flight in enumerate(plan.flights):
            dep_city = get_city_by_code(flight.departure_city_code)
            arr_city = get_city_by_code(flight.arrival_city_code)
            
            flight_legs.append(
                ft.Row(
                    [
                        ft.Text(f"{i+1}.", weight=ft.FontWeight.BOLD, width=30),
                        ft.Column(
                            [
                                ft.Text(f"{dep_city.name_cn} ({dep_city.code}) to {arr_city.name_cn} ({arr_city.code})", weight=ft.FontWeight.BOLD),
                                ft.Text(f"{flight.airline} {flight.flight_number} • {flight.flight_class} • {flight.transfer_info} • Flight Time: {format_delta(flight.duration)}", color=ft.Colors.GREY_600, size=12)
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Text(f"Depart: {flight.departure_datetime.strftime('%Y-%m-%d %H:%M')}"),
                                ft.Text(f"Arrive:  {flight.arrival_datetime.strftime('%Y-%m-%d %H:%M')}")
                            ],
                            spacing=2,
                            horizontal_alignment=ft.CrossAxisAlignment.END
                        )
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER
                )
            )

        route_summary = " → ".join([get_city_by_code(f.departure_city_code).country_cn for f in plan.flights] + [get_city_by_code(plan.flights[-1].arrival_city_code).country_cn])

        return ft.Card(
            ft.Container(
                ft.Column([
                    ft.Container(
                        ft.Row([
                            ft.Text(f"Option {plan_num}", size=20, weight=ft.FontWeight.BOLD),
                            ft.Text(f"Total Flight Time: {format_delta(plan.total_duration)}", size=16),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        bgcolor=ft.Colors.BLUE_GREY_50,
                        padding=15,
                        border_radius=ft.border_radius.only(top_left=8, top_right=8)
                    ),
                    ft.Container(
                        ft.Column([
                            ft.Text(route_summary, weight=ft.FontWeight.BOLD, size=16),
                            ft.Divider(height=10),
                            *flight_legs
                        ]),
                        padding=15
                    )
                ]),
                border_radius=8,
                border=ft.border.all(1, ft.Colors.GREY_300)
            )
        )

    find_button.on_click = find_plan_click
    
    # --- Layout ---
    controls_panel = ft.Container(
        ft.Column(
            [
                ft.Text("Itinerary Criteria", size=22, weight=ft.FontWeight.BOLD),
                ft.Text("Route Options", size=16, weight=ft.FontWeight.BOLD),
                start_city_dd, end_city_dd, num_countries_tf,
                ft.Divider(height=20),
                ft.Text("Flight Preferences", size=16, weight=ft.FontWeight.BOLD),
                ft.Row([min_layover_tf, max_layover_tf]),
                ft.Text("舱位等级:"), flight_class_rg, direct_only_cb,
                ft.Divider(height=20),
                ft.Text("Time Filter", size=16, weight=ft.FontWeight.BOLD),
                no_fly_cb, ft.Row([no_fly_start_tf, no_fly_end_tf]),
                ft.Divider(height=20),
                find_button,
                ft.Divider(height=20),
                ft.Text("Search Scope", size=16, weight=ft.FontWeight.BOLD),
                select_all_cities_cb,
                cities_checklist
            ],
            scroll=ft.ScrollMode.ADAPTIVE
        ),
        bgcolor=ft.Colors.WHITE,
        padding=20,
        border_radius=8,
        expand=True
    )
    
    results_panel = ft.Container(
        ft.Column([
            ft.Text("Executive Itinerary Proposal", size=28, weight=ft.FontWeight.BOLD),
            ft.Divider(height=20),
            results_view,
        ]),
        padding=30,
        expand=True
    )

    page.add(
        ft.Row(
            [
                ft.Column([controls_panel], width=500),
                ft.Column([results_panel], expand=True),
            ],
            expand=True
        )
    )

    # --- Initial Data Loading in Background ---
    def load_initial_data():
        nonlocal all_flights
        print("Loading flight data...")
        all_flights = load_flights("merged_flight_data.xlsx")
        print(f"Loaded {len(all_flights)} flights.")
        
        def enable_controls():
            for ctrl in [start_city_dd, end_city_dd, num_countries_tf, min_layover_tf, max_layover_tf, flight_class_rg, direct_only_cb, no_fly_cb, find_button]:
                ctrl.disabled = False
            loading_overlay.visible = False
            page.update()
        
        enable_controls()

    loading_overlay = ft.Container(
        ft.Column([ft.ProgressRing(), ft.Text("Loading Flight Data...", size=18)]),
        alignment=ft.alignment.center,
        expand=True,
        bgcolor="rgba(255, 255, 255, 0.8)"
    )
    
    page.overlay.append(loading_overlay)
    page.update()

    load_thread = threading.Thread(target=load_initial_data, daemon=True)
    load_thread.start()

if __name__ == "__main__":
    ft.app(target=main)

