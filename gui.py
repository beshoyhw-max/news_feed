import flet as ft
import threading
from datetime import timedelta, datetime
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
    page.title = "旅行计划查找器"
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

    # Travel Dates
    start_date_tf = ft.TextField(label="出发日期", value="2025-09-29", width=120, disabled=True)
    end_date_tf = ft.TextField(label="到达日期", value="2025-10-05", width=120, disabled=True)
    start_date_button = ft.IconButton(icon=ft.Icons.CALENDAR_MONTH, on_click=lambda _: page.open(start_date_picker), disabled=True)
    end_date_button = ft.IconButton(icon=ft.Icons.CALENDAR_MONTH, on_click=lambda _: page.open(end_date_picker), disabled=True)

    def on_start_date_change(e):
        start_date_tf.value = e.control.value.strftime("%Y-%m-%d")
        page.update()

    def on_end_date_change(e):
        end_date_tf.value = e.control.value.strftime("%Y-%m-%d")
        page.update()

    start_date_picker = ft.DatePicker(
        on_change=on_start_date_change,
        first_date=datetime(2024, 1, 1),
        last_date=datetime(2026, 12, 31),
        current_date=datetime(2025, 9, 29),
    )
    end_date_picker = ft.DatePicker(
        on_change=on_end_date_change,
        first_date=datetime(2024, 1, 1),
        last_date=datetime(2026, 12, 31),
        current_date=datetime(2025, 10, 3),
    )
    page.overlay.extend([start_date_picker, end_date_picker])


    # Flight Preferences
    min_layover_tf = ft.TextField(label="最短停留 (小时)", value="10", width=150, disabled=True)
    max_layover_tf = ft.TextField(label="最长停留 (小时)", value="48", width=150, disabled=True)
    flight_class_rg = ft.RadioGroup(content=ft.Row([
        ft.Radio(value="ALL", label="任何"),
        ft.Radio(value="Economy", label="经济舱"),
        ft.Radio(value="Business", label="公务舱"),
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
    no_fly_cb = ft.Checkbox(label="排除飞行时间段（红眼航班）", on_change=toggle_time_filter, value=False, disabled=True)
    
    # --- NEW: Forced Cities Checklist ---
    forced_cities_checklist = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True)
    forced_city_checkboxes = []
    for city in sorted_cities:
        cb = ft.Checkbox(label=f"{city.country_cn} - {city.name_cn} ({city.code})", disabled=True)
        forced_city_checkboxes.append((cb, city.code))
        forced_cities_checklist.controls.append(cb)

    def toggle_all_forced_cities(e):
        for cb, _ in forced_city_checkboxes:
            cb.value = e.control.value
        page.update()
    select_all_forced_cities_cb = ft.Checkbox(label="全选 / 取消全选", on_change=toggle_all_forced_cities, disabled=True)


    # Search Scope Cities Checklist
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
    select_all_cities_cb = ft.Checkbox(label="全选 / 取消全选", on_change=toggle_all_cities)

    # Action Button
    find_button = ft.ElevatedButton(text="寻找最佳方案", icon=ft.Icons.TRAVEL_EXPLORE, height=50, disabled=True)
    
    # Results Display
    results_view = ft.Column(
        alignment=ft.MainAxisAlignment.START,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        scroll=ft.ScrollMode.ADAPTIVE,
        expand=True
    )
    
    # --- Dialog for Errors/Warnings using Cupertino style ---
    def show_alert(title, message, icon, icon_color):
        def close_dialog(e):
            page.close(cupertino_alert_dialog)
            page.update()

        cupertino_alert_dialog = ft.CupertinoAlertDialog(
            title=ft.Row([ft.Icon(icon, color=icon_color), ft.Text(title)]),
            content=ft.Text(message),
            actions=[
                ft.CupertinoDialogAction("OK", on_click=close_dialog),
            ],
        )
        page.open(cupertino_alert_dialog)

    # --- Event Handlers ---
    def find_plan_click(e):
        # --- 1. Input Validation First ---
        try:
            start_date = datetime.strptime(start_date_tf.value, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_tf.value, "%Y-%m-%d").date()
            num_countries = int(num_countries_tf.value)
            min_layover = int(min_layover_tf.value)
            max_layover = int(max_layover_tf.value)
            no_fly_start = int(no_fly_start_tf.value) if no_fly_cb.value else None
            no_fly_end = int(no_fly_end_tf.value) if no_fly_cb.value else None
            cities_choice = [code for cb, code in city_checkboxes if cb.value]
            forced_city_codes = [code for cb, code in forced_city_checkboxes if cb.value]

        except ValueError:
            show_alert("输入错误", "请为所有数字字段输入有效的数字。", ft.Icons.ERROR_OUTLINE, ft.Colors.RED)
            return

        if start_date > end_date:
            show_alert("无效的日期范围", "开始日期不能晚于结束日期。", ft.Icons.ERROR_OUTLINE, ft.Colors.RED)
            return
        
        if not cities_choice:
            show_alert("无效信息", "请在旅行范围内至少选择一个城市。", ft.Icons.WARNING_AMBER_ROUNDED, ft.Colors.AMBER)
            return

        if start_city_dd.value == "Any" and end_city_dd.value == "Any" and num_countries == 1:
            show_alert(
                "无效条件",
                "一段没有明确起点和终点的旅行必定会跨越多个国家。",
                ft.Icons.ERROR_OUTLINE,
                ft.Colors.RED
            )
            return

        # --- 2. If Validation Passes, Update UI to Loading State ---
        find_button.disabled = True
        results_view.controls.clear()
        results_view.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.ProgressRing(),
                        ft.Text("寻找最佳方案...", size=16)
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=20
                ),
                alignment=ft.alignment.center,
                expand=True
            )
        )
        page.update()

        # --- 3. Run Search in Background ---
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "start_city": city_name_to_code_map.get(start_city_dd.value) if start_city_dd.value != "Any" else None,
            "end_city": city_name_to_code_map.get(end_city_dd.value) if end_city_dd.value != "Any" else None,
            "num_countries": num_countries,
            "min_layover_hours": min_layover,
            "max_layover_hours": max_layover,
            "no_fly_start_hour": no_fly_start,
            "no_fly_end_hour": no_fly_end,
            "cities_choice": cities_choice,
            "flight_class_filter": flight_class_rg.value,
            "direct_flights_only": direct_only_cb.value,
            "forced_cities": forced_city_codes
        }

        thread = threading.Thread(target=run_search, args=(params,), daemon=True)
        thread.start()
        
    def run_search(params):
        nonlocal search_results
        search_results = find_best_travel_plan(base_flights=all_flights, **params)
        display_results()

    def display_results():
        results_view.alignment = ft.MainAxisAlignment.START
        results_view.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        results_view.controls.clear()

        if not search_results:
            centered_message = ft.Container(
                ft.Text("未找到符合指定条件的旅行计划。", size=18, italic=True),
                alignment=ft.alignment.center,
                expand=True
            )
            results_view.controls.append(centered_message)
        else:
            summary = ft.Text(f"找到了{len(search_results)}个最优的旅行方案", size=18, weight=ft.FontWeight.BOLD)
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
                                                                # ft.Text(f"{dep_city.country_cn} ({dep_city.name_cn} {dep_city.code}) 🡺 {arr_city.country_cn} ({arr_city.name_cn} {arr_city.code})", weight=ft.FontWeight.BOLD),

                                ft.Text(f"{dep_city.country_cn} ({dep_city.name_cn}) 🡺 {arr_city.country_cn} ({arr_city.name_cn})", weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    (
                                        f"{flight.airline} {flight.flight_number} • {flight.flight_class} "

                                    ),
                                    color=ft.Colors.GREY_600,
                                    size=12
                                ) ,
                                                                ft.Text(
                                    (

                                        f"{'直飞' if 'N/A:' in flight.transfer_info else flight.transfer_info}"
                                        f"{f' • 签证信息: {flight.visa_info}' if flight.visa_info != 'N/A' else ''}"
                                        f" • 飞行时间：{format_delta(flight.duration)}"
                                    ),
                                    color=ft.Colors.GREY_600,
                                    size=12
                                )                             ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Column(
                            [
                                ft.Text(f"出发: {flight.departure_datetime.strftime('%Y-%m-%d %H:%M')}"),
                                ft.Text(f"到达: {flight.arrival_datetime.strftime('%Y-%m-%d %H:%M')}")
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
                            ft.Text(f"方案 {plan_num}", size=20, weight=ft.FontWeight.BOLD),
                            ft.Text(f"总飞行时间: {format_delta(plan.total_duration)}", size=16),
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
                ft.Text(" ", size=5, weight=ft.FontWeight.BOLD),
                start_city_dd, end_city_dd, num_countries_tf,
                ft.Divider(height=20),
                ft.Row([start_date_tf, start_date_button , end_date_tf, end_date_button]),
                ft.Divider(height=20),
                ft.Text("航班筛选", size=16, weight=ft.FontWeight.BOLD),
                ft.Row([min_layover_tf, max_layover_tf]),
                ft.Text("舱位等级:"), flight_class_rg, direct_only_cb,
                no_fly_cb, ft.Row([no_fly_start_tf, no_fly_end_tf]),
                ft.Divider(height=20),               
                ft.Text("旅行范围", size=16, weight=ft.FontWeight.BOLD),
                select_all_cities_cb,
                ft.Container(content=cities_checklist, border=ft.border.all(1, ft.Colors.GREY_400), border_radius=5, padding=5, height=250),
                ft.Divider(height=20),
                ft.Text("包含国家（可选)", size=16, weight=ft.FontWeight.BOLD),
                ft.Container(content=forced_cities_checklist, border=ft.border.all(1, ft.Colors.GREY_400), border_radius=5, padding=5, height=150),
                ft.Divider(height=20),
                find_button,
                ft.Text(" ", size=5),
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
            ft.Text("行程建议", size=28, weight=ft.FontWeight.BOLD),
            ft.Divider(height=20),
            results_view,
        ]),
        padding=30,
        expand=True
    )

    main_layout = ft.Row(
        [
            ft.Column([controls_panel], width=500),
            ft.Column([results_panel], expand=True),
        ],
        expand=True
    )

    # --- Initial Data Loading in Background ---
    def load_initial_data():
        nonlocal all_flights
        print("Loading flight data...")
        all_flights = load_flights("merged_flight_data.xlsx")
        print(f"Loaded {len(all_flights)} flights.")
        
        def enable_controls():
            # Clear the loading indicator and add the main layout
            page.controls.clear()
            page.add(main_layout)
            
            # Enable all the interactive controls
            for ctrl in [
                start_city_dd, end_city_dd, num_countries_tf,
                min_layover_tf, max_layover_tf, flight_class_rg,
                direct_only_cb, no_fly_cb, find_button,
                start_date_tf, end_date_tf, start_date_button, end_date_button,
                select_all_forced_cities_cb, select_all_cities_cb
            ]:
                ctrl.disabled = False
            
            for cb, _ in forced_city_checkboxes:
                cb.disabled = False

            page.update()
        
        enable_controls()

    loading_indicator = ft.Container(
        content=ft.Column(
            [
                ft.ProgressRing(),
                ft.Text("加载航班数据中...", size=18)
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20
        ),
        alignment=ft.alignment.center,
        expand=True
    )
    
    page.add(loading_indicator)
    page.update()

    load_thread = threading.Thread(target=load_initial_data, daemon=True)
    load_thread.start()

if __name__ == "__main__":
    ft.app(target=main)

