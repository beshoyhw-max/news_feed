import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import threading

from main import find_best_travel_plan
from data_handler import load_flights
from models import CITIES_BY_CODE, get_city_by_code, CITIES


class ScrolledCheckboxList(tk.Frame):
    def __init__(self, parent, choices, **kwargs):
        super().__init__(parent, **kwargs)
        self.vars = {}
        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        for choice in choices:
            self.vars[choice['code']] = tk.BooleanVar()
            ttk.Checkbutton(self.scrollable_frame, text=f"{choice['name']} ({choice['code']})", variable=self.vars[choice['code']]).pack(anchor='w', padx=5, pady=2)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def get_checked(self):
        return [code for code, var in self.vars.items() if var.get()]


class TravelApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Travel Plan Finder")
        self.root.geometry("800x600")

        self.flights = load_flights("merged_flight_data.xlsx")
        if not self.flights:
            messagebox.showerror("Error", "Could not load flight data. Exiting.")
            self.root.destroy()
            return
            
        self.search_thread = None
        self.search_result = None

        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill="both", expand=True)

        controls_frame = ttk.LabelFrame(main_frame, text="Trip Options", padding="10")
        controls_frame.pack(side="left", fill="y", padx=5, pady=5)

        results_frame = ttk.LabelFrame(main_frame, text="Best Travel Plan", padding="10")
        results_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)

        ttk.Label(controls_frame, text="Start City:").pack(anchor='w')
        self.start_city_combo = ttk.Combobox(controls_frame, values=["Any"] + sorted([c['code'] for c in CITIES]))
        self.start_city_combo.pack(fill='x', pady=2)
        self.start_city_combo.set("Any")

        ttk.Label(controls_frame, text="End City:").pack(anchor='w')
        self.end_city_combo = ttk.Combobox(controls_frame, values=["Any"] + sorted([c['code'] for c in CITIES]))
        self.end_city_combo.pack(fill='x', pady=2)
        self.end_city_combo.set("Any")
        
        ttk.Label(controls_frame, text="Number of Countries to Visit:").pack(anchor='w')
        self.num_countries_spinbox = ttk.Spinbox(controls_frame, from_=1, to=10)
        self.num_countries_spinbox.pack(fill='x', pady=2)
        self.num_countries_spinbox.set("3")

        # --- NEW LAYOVER CONTROLS ---
        ttk.Label(controls_frame, text="Min Layover (hours):").pack(anchor='w')
        self.min_layover_spinbox = ttk.Spinbox(controls_frame, from_=1, to=100)
        self.min_layover_spinbox.pack(fill='x', pady=2)
        self.min_layover_spinbox.set("10")

        ttk.Label(controls_frame, text="Max Layover (hours):").pack(anchor='w')
        self.max_layover_spinbox = ttk.Spinbox(controls_frame, from_=1, to=100)
        self.max_layover_spinbox.pack(fill='x', pady=2)
        self.max_layover_spinbox.set("48")

        ttk.Label(controls_frame, text="Flight Class:").pack(anchor='w')
        self.flight_class = tk.StringVar(value="ALL")
        ttk.Radiobutton(controls_frame, text="Any", variable=self.flight_class, value="ALL").pack(anchor='w')
        ttk.Radiobutton(controls_frame, text="Economy", variable=self.flight_class, value="Economy").pack(anchor='w')
        ttk.Radiobutton(controls_frame, text="Business", variable=self.flight_class, value="Business").pack(anchor='w')
        
        self.direct_only_var = tk.BooleanVar()
        ttk.Checkbutton(controls_frame, text="Direct flights only", variable=self.direct_only_var).pack(anchor='w', pady=5)
        
        self.midnight_flights_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls_frame, text="Allow midnight flights", variable=self.midnight_flights_var).pack(anchor='w', pady=5)

        self.find_button = ttk.Button(controls_frame, text="Find Travel Plan", command=self.find_plan)
        self.find_button.pack(fill='x', pady=10)
        
        cities_frame = ttk.LabelFrame(controls_frame, text="Cities to Include in Search", padding="10")
        cities_frame.pack(fill="both", expand=True, pady=5)
        self.cities_list = ScrolledCheckboxList(cities_frame, CITIES)
        self.cities_list.pack(fill="both", expand=True)

        self.result_text = tk.Text(results_frame, wrap="word", state="disabled")
        self.result_text.pack(fill="both", expand=True)

    def find_plan(self):
        start_city_val = self.start_city_combo.get()
        if start_city_val == "Any":
            start_city_val = None
            
        end_city_val = self.end_city_combo.get()
        if end_city_val == "Any":
            end_city_val = None

        try:
            num_countries_val = int(self.num_countries_spinbox.get())
            min_layover_val = int(self.min_layover_spinbox.get())
            max_layover_val = int(self.max_layover_spinbox.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers for countries and layover hours.")
            return

        cities_choice_val = self.cities_list.get_checked()
        if not cities_choice_val:
            messagebox.showwarning("Warning", "Please select at least one city to include in the search.")
            return

        self.find_button.config(state="disabled")
        self.result_text.config(state="normal")
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, "Searching for the best travel plan, this might take a while...")
        self.result_text.config(state="disabled")

        self.search_thread = threading.Thread(
            target=self.run_search,
            args=(cities_choice_val, num_countries_val, start_city_val, end_city_val, min_layover_val, max_layover_val)
        )
        self.search_thread.start()
        self.check_for_result()

    def run_search(self, cities_choice, num_countries, start_city, end_city, min_layover, max_layover):
        plan = find_best_travel_plan(
            flights=self.flights,
            cities_choice=cities_choice,
            num_countries=num_countries,
            start_city=start_city,
            end_city=end_city,
            flight_class_filter=self.flight_class.get(),
            direct_flights_only=self.direct_only_var.get(),
            allow_midnight_flights=self.midnight_flights_var.get(),
            min_layover_hours=min_layover,
            max_layover_hours=max_layover
        )
        self.search_result = plan

    def check_for_result(self):
        if self.search_thread.is_alive():
            self.root.after(100, self.check_for_result)
        else:
            self.display_result()

    def display_result(self):
        self.find_button.config(state="normal")
        self.result_text.config(state="normal")
        self.result_text.delete(1.0, tk.END)
        plan = self.search_result
        if plan:
            result_str = f"Found a plan with total flight duration: {plan.total_duration}\\n\\n"
            for i, flight in enumerate(plan.flights):
                dep_city = get_city_by_code(flight.departure_city_code)
                arr_city = get_city_by_code(flight.arrival_city_code)
                result_str += (
                    f"{i+1}. {dep_city.name} ({dep_city.code}) -> {arr_city.name} ({arr_city.code})\\n"
                    f"   Departs: {flight.departure_datetime}, Arrives: {flight.arrival_datetime}\\n"
                    f"   Airline: {flight.airline} ({flight.flight_number}), Class: {flight.flight_class}\\n\\n"
                )
            self.result_text.insert(tk.END, result_str)
        else:
            self.result_text.insert(tk.END, "No travel plan found matching the criteria.")
        
        self.result_text.config(state="disabled")
        self.search_result = None

if __name__ == '__main__':
    root = tk.Tk()
    app = TravelApp(root)
    root.mainloop()