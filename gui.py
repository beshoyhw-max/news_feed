import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import threading

from main import find_best_travel_plan
from data_handler import load_flights
from models import CITIES_BY_CODE, get_city_by_code, CITIES, City


class ScrolledCheckboxList(tk.Frame):
    def __init__(self, parent, choices, **kwargs):
        super().__init__(parent, **kwargs)
        self.vars = {}
        
        # --- Select All Checkbox ---
        self.select_all_var = tk.BooleanVar()
        self.select_all_button = ttk.Checkbutton(self, text="Select All", variable=self.select_all_var, command=self.toggle_all)
        self.select_all_button.pack(anchor='w', padx=5, pady=2)
        
        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        for city_obj in choices:
            self.vars[city_obj.code] = tk.BooleanVar()
            # New format: Country (CN) - City (CN) (Code)
            display_text = f"{city_obj.country_cn} - {city_obj.name_cn} ({city_obj.code})"
            ttk.Checkbutton(self.scrollable_frame, text=display_text, variable=self.vars[city_obj.code]).pack(anchor='w', padx=5, pady=2)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def get_checked(self):
        return [code for code, var in self.vars.items() if var.get()]
        
    def toggle_all(self):
        # Set all checkboxes to the state of the 'Select All' button
        is_checked = self.select_all_var.get()
        for var in self.vars.values():
            var.set(is_checked)


class TravelApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Travel Plan Finder")
        self.root.geometry("1200x800")

        # --- Styling ---
        style = ttk.Style()
        style.configure("TLabel", font=("Helvetica", 12))
        style.configure("Bold.TLabel", font=("Helvetica", 12, "bold"))
        style.configure("TButton", font=("Helvetica", 12, "bold"))
        style.configure("TCombobox", font=("Helvetica", 12))
        style.configure("TSpinbox", font=("Helvetica", 12))
        style.configure("TRadiobutton", font=("Helvetica", 12))
        style.configure("TCheckbutton", font=("Helvetica", 12))
        style.configure("TLabelframe.Label", font=("Helvetica", 12, "bold"))
        style.configure("Treeview.Heading", font=("Helvetica", 12, "bold"))

        self.flights = load_flights("merged_flight_data.xlsx")
        if not self.flights:
            messagebox.showerror("Error", "Could not load flight data. Exiting.")
            self.root.destroy()
            return
            
        self.search_thread = None
        self.search_result = None

        self.city_name_to_code_map = {f"{city.country_cn} - {city.name_cn}": city.code for city in CITIES_BY_CODE.values()}
        sorted_cities = sorted(CITIES_BY_CODE.values(), key=lambda c: (c.country_cn, c.name_cn))
        city_display_names = [f"{city.country_cn} - {city.name_cn}" for city in sorted_cities]

        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        controls_column = ttk.Frame(main_frame)
        controls_column.pack(side="left", fill="y", padx=(0, 20), pady=5)

        results_frame = ttk.LabelFrame(main_frame, text="Best Travel Plan", padding="10")
        results_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        
        route_options_frame = ttk.LabelFrame(controls_column, text="行程选项", padding="15")
        route_options_frame.pack(fill='x', pady=10, anchor='n')

        ttk.Label(route_options_frame, text="出发城市:", style="Bold.TLabel").pack(anchor='w')
        self.start_city_combo = ttk.Combobox(route_options_frame, values=["Any"] + city_display_names)
        self.start_city_combo.pack(fill='x', pady=5)
        self.start_city_combo.set("Any")

        ttk.Label(route_options_frame, text="目的城市:", style="Bold.TLabel").pack(anchor='w')
        self.end_city_combo = ttk.Combobox(route_options_frame, values=["Any"] + city_display_names)
        self.end_city_combo.pack(fill='x', pady=5)
        self.end_city_combo.set("Any")
        
        ttk.Label(route_options_frame, text="访问国家数量:", style="Bold.TLabel").pack(anchor='w')
        self.num_countries_spinbox = ttk.Spinbox(route_options_frame, from_=1, to=10)
        self.num_countries_spinbox.pack(fill='x', pady=5)
        self.num_countries_spinbox.set("3")

        flight_prefs_frame = ttk.LabelFrame(controls_column, text="航班偏好", padding="15")
        flight_prefs_frame.pack(fill='x', pady=10, anchor='n')

        ttk.Label(flight_prefs_frame, text="最短停留 (小时):", style="Bold.TLabel").pack(anchor='w')
        self.min_layover_spinbox = ttk.Spinbox(flight_prefs_frame, from_=1, to=100)
        self.min_layover_spinbox.pack(fill='x', pady=5)
        self.min_layover_spinbox.set("10")

        ttk.Label(flight_prefs_frame, text="最长停留 (小时):", style="Bold.TLabel").pack(anchor='w')
        self.max_layover_spinbox = ttk.Spinbox(flight_prefs_frame, from_=1, to=100)
        self.max_layover_spinbox.pack(fill='x', pady=5)
        self.max_layover_spinbox.set("48")
        
        class_frame = ttk.Frame(flight_prefs_frame)
        class_frame.pack(fill='x', pady=(10, 5))
        ttk.Label(class_frame, text="舱位等级:", style="Bold.TLabel").pack(anchor='w')
        self.flight_class = tk.StringVar(value="ALL")
        ttk.Radiobutton(class_frame, text="任何", variable=self.flight_class, value="ALL").pack(anchor='w')
        ttk.Radiobutton(class_frame, text="经济舱", variable=self.flight_class, value="Economy").pack(anchor='w')
        ttk.Radiobutton(class_frame, text="商务舱", variable=self.flight_class, value="Business").pack(anchor='w')
        
        self.direct_only_var = tk.BooleanVar()
        ttk.Checkbutton(flight_prefs_frame, text="仅限直飞航班", variable=self.direct_only_var).pack(anchor='w', pady=10)
        
        time_filter_frame = ttk.LabelFrame(controls_column, text="禁飞时段", padding="15")
        time_filter_frame.pack(fill='x', pady=10, anchor='n')
        
        self.no_fly_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(time_filter_frame, text="启用禁飞时段", variable=self.no_fly_enabled).pack(anchor='w')
        
        time_frame = ttk.Frame(time_filter_frame)
        time_frame.pack(fill='x', pady=5)
        ttk.Label(time_frame, text="从:").pack(side='left', padx=(0, 5))
        self.no_fly_start_spinbox = ttk.Spinbox(time_frame, from_=0, to=23, width=4)
        self.no_fly_start_spinbox.pack(side='left')
        self.no_fly_start_spinbox.set("23")
        ttk.Label(time_frame, text="至:").pack(side='left', padx=5)
        self.no_fly_end_spinbox = ttk.Spinbox(time_frame, from_=0, to=23, width=4)
        self.no_fly_end_spinbox.pack(side='left')
        self.no_fly_end_spinbox.set("6")

        self.find_button = ttk.Button(controls_column, text="查找最佳旅行计划", command=self.find_plan, style="TButton")
        self.find_button.pack(fill='x', pady=20, anchor='s')
        
        cities_frame = ttk.LabelFrame(controls_column, text="搜索城市范围", padding="10")
        cities_frame.pack(fill="both", expand=True, pady=10, anchor='n')
        self.cities_list = ScrolledCheckboxList(cities_frame, sorted_cities)
        self.cities_list.pack(fill="both", expand=True)

        # --- Results Treeview ---
        columns = ("#", "route", "departs", "arrives", "airline", "class", "transfers")
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show="headings", style="Treeview")
        
        self.results_tree.heading("#", text="#")
        self.results_tree.heading("route", text="路线")
        self.results_tree.heading("departs", text="出发时间")
        self.results_tree.heading("arrives", text="到达时间")
        self.results_tree.heading("airline", text="航空公司")
        self.results_tree.heading("class", text="舱位")
        self.results_tree.heading("transfers", text="中转信息")

        self.results_tree.column("#", width=40, anchor='center', stretch=False)
        self.results_tree.column("route", width=250)
        self.results_tree.column("departs", width=150, anchor='center')
        self.results_tree.column("arrives", width=150, anchor='center')
        self.results_tree.column("airline", width=150)
        self.results_tree.column("class", width=80, anchor='center')
        self.results_tree.column("transfers", width=200)

        tree_scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=tree_scrollbar.set)
        
        self.results_tree.pack(side="left", fill="both", expand=True)
        tree_scrollbar.pack(side="right", fill="y")

    def find_plan(self):
        start_city_display = self.start_city_combo.get()
        start_city_val = self.city_name_to_code_map.get(start_city_display) if start_city_display != "Any" else None
            
        end_city_display = self.end_city_combo.get()
        end_city_val = self.city_name_to_code_map.get(end_city_display) if end_city_display != "Any" else None

        try:
            num_countries_val = int(self.num_countries_spinbox.get())
            min_layover_val = int(self.min_layover_spinbox.get())
            max_layover_val = int(self.max_layover_spinbox.get())
            
            no_fly_start = int(self.no_fly_start_spinbox.get()) if self.no_fly_enabled.get() else None
            no_fly_end = int(self.no_fly_end_spinbox.get()) if self.no_fly_enabled.get() else None

        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers for countries and layover hours.")
            return

        cities_choice_val = self.cities_list.get_checked()
        if not cities_choice_val:
            messagebox.showwarning("Warning", "Please select at least one city to include in the search.")
            return

        self.find_button.config(state="disabled")
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.results_tree.insert("", "end", values=("", "正在搜索最佳旅行计划，请稍候...", "", "", "", "", ""))


        self.search_thread = threading.Thread(
            target=self.run_search,
            args=(cities_choice_val, num_countries_val, start_city_val, end_city_val, min_layover_val, max_layover_val, no_fly_start, no_fly_end)
        )
        self.search_thread.start()
        self.check_for_result()

    def run_search(self, cities_choice, num_countries, start_city, end_city, min_layover, max_layover, no_fly_start, no_fly_end):
        plan = find_best_travel_plan(
            flights=self.flights,
            cities_choice=cities_choice,
            num_countries=num_countries,
            start_city=start_city,
            end_city=end_city,
            flight_class_filter=self.flight_class.get(),
            direct_flights_only=self.direct_only_var.get(),
            min_layover_hours=min_layover,
            max_layover_hours=max_layover,
            no_fly_start_hour=no_fly_start,
            no_fly_end_hour=no_fly_end
        )
        self.search_result = plan

    def check_for_result(self):
        if self.search_thread.is_alive():
            self.root.after(100, self.check_for_result)
        else:
            self.display_result()

    def display_result(self):
        self.find_button.config(state="normal")
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
            
        plan = self.search_result
        if plan:
            for i, flight in enumerate(plan.flights):
                dep_city = get_city_by_code(flight.departure_city_code)
                arr_city = get_city_by_code(flight.arrival_city_code)
                
                route_str = f"{dep_city.name_cn} ({dep_city.code}) → {arr_city.name_cn} ({arr_city.code})"
                airline_str = f"{flight.airline} ({flight.flight_number})"
                
                self.results_tree.insert("", "end", values=(
                    i + 1,
                    route_str,
                    flight.departure_datetime.strftime('%Y-%m-%d %H:%M'),
                    flight.arrival_datetime.strftime('%Y-%m-%d %H:%M'),
                    airline_str,
                    flight.flight_class,
                    flight.transfer_info
                ))
        else:
            self.results_tree.insert("", "end", values=("", "未找到符合条件的旅行计划。", "", "", "", "", ""))
        
        self.search_result = None

if __name__ == '__main__':
    root = tk.Tk()
    app = TravelApp(root)
    root.mainloop()