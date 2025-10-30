import os
import re
import csv
import sys
import glob
import json
import time
import math
import logging
import serial
import threading
import collections
import numpy as np
import pandas as pd
import tkinter as tk
import customtkinter as ctk
from datetime import datetime, timedelta
from PIL import Image

from controller.controller import Controller

logging.basicConfig(
    level=logging.DEBUG, 
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)

ctk.set_appearance_mode('system')
ctk.set_default_color_theme('blue')


class NewExperimentToplevelWindow(ctk.CTkToplevel):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent

        self.setup_default_parameters()
        self.build_ui()

    def setup_default_parameters(self):
        self.voltage_units_var = 'V'
        self.duration_units_var = 'hours'
        self.pump_direction_var = 'Clockwise'
        self.save_state_var = tk.IntVar()

    def validate_numeric_entry(self, entry):
        try:
            return float(entry.get())
        except ValueError:
            entry.delete(0, 'end')
            entry.configure(placeholder_text_color=App.COLOUR_BRIGHT_RED)
            logging.error(f'Invalid numeric entry in: {entry.cget("placeholder_text")}')
            return None

    def reset_entry_fields(self):
        logging.debug('Resetting entry fields to empty.')

        self.voltage_entry.delete(0, 'end')
        self.pump_speed_entry.delete(0, 'end')
        self.mfc_flow_entry.delete(0, 'end')
        self.stirrer_speed_entry.delete(0, 'end')
        self.duration_entry.delete(0, 'end')

        self.voltage_units_options.set('V')
        self.voltage_units_var = 'V'

        self.duration_units_options.set('hours')
        self.duration_units_var = 'hours'

    def set_entry_value(self, entry_widget, value):
        entry_widget.delete(0, 'end')
        if value is not None:
            entry_widget.insert(0, str(value))

    def load_save_into_fields(self, save_data):
        valid_voltage_units = ['V', 'A', 'mA']
        valid_pump_direction = ['Clockwise', 'Counter-clockwise']
        valid_duration_units = ['minutes', 'hours']

        # -- Voltage/Current --
        voltage = save_data.get('voltage', {})
        voltage_value = voltage.get('value')
        voltage_unit = voltage.get('unit', 'V')

        # Validate that its loading a correct unit
        if voltage_unit not in valid_voltage_units:
            logging.warning(f'Invalid voltage unit "{voltage_unit}". Defaulting to "V".')
            voltage_unit = 'V'

        self.set_entry_value(self.voltage_entry, voltage_value)
        self.voltage_units_options.set(voltage_unit)
        self.voltage_units_var = voltage_unit

        # --- Pump ---
        pump = save_data.get('pump', {})
        pump_speed = pump.get('speed')
        tubing_size = pump.get('tubing')
        pump_direction = pump.get('direction', 'Clockwise')

        # Validate that its loading a correct direction
        if pump_direction not in valid_pump_direction:
            logging.warning(f'Invalid pump direction "{pump_direction}". Defaulting to "Clockwise".')
            pump_direction = 'Clockwise'

        self.set_entry_value(self.pump_speed_entry, pump_speed)
        self.set_entry_value(self.tubing_size_entry, tubing_size)
        self.pump_direction_options.set(pump_direction)
        self.pump_direction_var = pump_direction

        # --- Others ---
        self.set_entry_value(self.mfc_flow_entry, save_data.get('mfc_flow_rate'))
        self.set_entry_value(self.stirrer_speed_entry, save_data.get('stirrer_speed'))

        # --- Duration (optional) ---
        duration = save_data.get('duration', {})
        duration_value = duration.get('value')
        duration_unit = duration.get('unit', 'hours')

        # Validate that its loading a correct unit
        if duration_unit not in valid_duration_units:
            logging.warning(f'Invalid duration unit "{duration_unit}". Defaulting to "hours".')
            duration_unit = 'hours'

        self.set_entry_value(self.duration_entry, duration_value)
        self.duration_units_options.set(duration_unit)
        self.duration_units_var = duration_unit

    def save_state_event(self):
        save_state = self.save_state_var.get()
        logging.info(f'Selected save state: {"custom" if save_state == 0 else f"save {save_state}"}')

        # Only enable the overwrite button for the saves not custom entry
        if save_state == 0:
            self.overwrite_button.configure(fg_color=App.COLOUR_GREY, hover_color=App.COLOUR_GREY, state='disabled')
            # Need to clear the entry fields in the event that user clicked save then custom
            self.reset_entry_fields()
        else:
            self.overwrite_button.configure(fg_color=App.COLOUR_BRIGHT_BLUE, hover_color=App.COLOUR_DARK_BLUE, state='normal')

            # Load save data based on the save state
            try:
                with open('save_state_data.json', 'r') as f:
                    saves = json.load(f)
                save_key = f'save_{save_state}'
                if save_key in saves:
                    self.load_save_into_fields(saves[save_key])
                    logging.info(f'Successfully loaded from {save_key}.')
                else:
                    logging.warning(f'No save data found for {save_key}.')
            except Exception as e:
                logging.error(f'Error loading save file: {e}')

    def overwrite_save_data(self):
        save_state = self.save_state_var.get()

        # This should never happen because overwrite save button is disabled, but just for safety
        if save_state == 0:
            logging.warning('Overwrite attempt in custom mode. Ignored.')
            return

        # Validate the entry fields first
        voltage = self.validate_numeric_entry(self.voltage_entry)
        pump_speed = self.validate_numeric_entry(self.pump_speed_entry)
        tubing_size = self.validate_numeric_entry(self.tubing_size_entry)
        mfc_flow_rate = self.validate_numeric_entry(self.mfc_flow_entry)
        stirrer_speed = self.validate_numeric_entry(self.stirrer_speed_entry)
        # Duration is optional so validate value if given
        duration_value = self.validate_numeric_entry(self.duration_entry) if self.duration_entry.get() else None

        if None in [voltage, pump_speed, tubing_size, mfc_flow_rate, stirrer_speed]:
            logging.error('Failed to overwrite save. One or more required fields are invalid.')
            return

        # Collect the units (no need validation because they are from a dropdown)
        voltage_unit = self.voltage_units_var
        duration_unit = self.duration_units_var
        pump_direction = self.pump_direction_var

        # Create save structure, then load and overwrite
        new_save = {
            'voltage': {'value': voltage, 'unit': voltage_unit},
            'pump': {'speed': pump_speed, 'tubing': tubing_size, 'direction': pump_direction},
            'mfc_flow_rate': mfc_flow_rate,
            'stirrer_speed': stirrer_speed,
            'duration': {'value': duration_value, 'unit': duration_unit}
        }

        save_key = f'save_{save_state}'
        try:
            with open('save_state_data.json', 'r') as f:
                data = json.load(f)
            data[save_key] = new_save
            with open('save_state_data.json', 'w') as f:
                json.dump(data, f, indent=4)
            logging.info(f'Successfully overwrote {save_key}.')
        except Exception as e:
            logging.error(f'Error saving data: {e}')


    def build_ui(self):
        self.title('New Experiment')
        self.geometry(f"{App.SECONDARY_WIDTH}x{App.SECONDARY_HEIGHT}")

        # Configure grid layout (5x1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)


        # ===== Select Save =====
        self.select_frame = ctk.CTkFrame(self)
        self.select_frame.grid(row=0, column=0, pady=(0, 20), sticky='ew')
        self.select_frame.grid_rowconfigure(0, weight=1)
        self.select_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        radio_save_0 = ctk.CTkRadioButton(self.select_frame, text='Custom', command=self.save_state_event, variable=self.save_state_var, value=0)
        radio_save_1 = ctk.CTkRadioButton(self.select_frame, text='Save 1', command=self.save_state_event, variable=self.save_state_var, value=1)
        radio_save_2 = ctk.CTkRadioButton(self.select_frame, text='Save 2', command=self.save_state_event, variable=self.save_state_var, value=2)
        radio_save_3 = ctk.CTkRadioButton(self.select_frame, text='Save 3', command=self.save_state_event, variable=self.save_state_var, value=3)
        radio_save_4 = ctk.CTkRadioButton(self.select_frame, text='Save 4', command=self.save_state_event, variable=self.save_state_var, value=4)
        radio_save_5 = ctk.CTkRadioButton(self.select_frame, text='Save 5', command=self.save_state_event, variable=self.save_state_var, value=5)

        radio_save_0.grid(row=0, column=0, padx=10, pady=10, sticky='ew')
        radio_save_1.grid(row=0, column=1, padx=10, pady=10, sticky='ew')
        radio_save_2.grid(row=0, column=2, padx=10, pady=10, sticky='ew')
        radio_save_3.grid(row=0, column=3, padx=10, pady=10, sticky='ew')
        radio_save_4.grid(row=0, column=4, padx=10, pady=10, sticky='ew')
        radio_save_5.grid(row=0, column=5, padx=10, pady=10, sticky='ew')


        # ===== User Details Frame =====
        self.details_frame = ctk.CTkFrame(self)
        self.details_frame.grid(row=1, column=0, pady=(0, 20), sticky='ew')
        self.details_frame.grid_rowconfigure((0, 1, 2), weight=1)
        self.details_frame.grid_columnconfigure((0, 1), weight=1)

        self.details_title = ctk.CTkLabel(self.details_frame, text='User Details', font=('Futura', 20, 'underline'))
        self.details_title.grid(row=0, column=0, columnspan=2, padx=10, pady=(5, 15))


        self.username_label = ctk.CTkLabel(self.details_frame, text='User Name')
        self.username_label.grid(row=1, column=0, padx=5, pady=5, sticky='e')

        self.username_entry = ctk.CTkEntry(self.details_frame, placeholder_text='Adriano')
        self.username_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')

        self.filename_label = ctk.CTkLabel(self.details_frame, text='File Name')
        self.filename_label.grid(row=2, column=0, padx=5, pady=(5, 20), sticky='e')

        self.filename_entry = ctk.CTkEntry(self.details_frame, placeholder_text='test-1')
        self.filename_entry.grid(row=2, column=1, padx=5, pady=(5, 20), sticky='w')


        # ===== Setup Details Frame =====
        self.setup_frame = ctk.CTkFrame(self)
        self.setup_frame.grid(row=2, column=0, pady=(0, 20), sticky='ew')
        self.setup_frame.grid_columnconfigure((0, 1), weight=1)

        # === Power Supply Section ===
        power_label = ctk.CTkLabel(self.setup_frame, text='Power Supply', font=('Futura', 16, 'underline'))
        power_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky='ew')

        self.voltage_entry = ctk.CTkEntry(self.setup_frame, placeholder_text='Voltage', justify='right')
        self.voltage_entry.grid(row=1, column=0, padx=5, pady=5, sticky='e')

        self.voltage_units_options = ctk.CTkOptionMenu(
            self.setup_frame,
            values=['V', 'A', 'mA'],
            width=1,
            command=self.voltage_units_options_callback
        )
        self.voltage_units_options.set('V')
        self.voltage_units_options.grid(row=1, column=1, padx=5, pady=5, sticky='w')


        # === Pump Section ===
        pump_label = ctk.CTkLabel(self.setup_frame, text='Pump', font=('Futura', 16, 'underline'))
        pump_label.grid(row=2, column=0, columnspan=2, padx=10, pady=(15, 5), sticky='ew')

        self.pump_speed_entry = ctk.CTkEntry(self.setup_frame, placeholder_text='Pump Speed', justify='right')
        self.pump_speed_entry.grid(row=3, column=0, padx=5, pady=5, sticky='e')

        self.pump_speed_units = ctk.CTkLabel(self.setup_frame, text='rpm')
        self.pump_speed_units.grid(row=3, column=1, padx=5, pady=5, sticky='w')

        self.tubing_size_entry = ctk.CTkEntry(self.setup_frame, placeholder_text='Tubing Size', justify='right')
        self.tubing_size_entry.grid(row=4, column=0, padx=5, pady=5, sticky='e')

        self.tubing_size_units = ctk.CTkLabel(self.setup_frame, text='mm')
        self.tubing_size_units.grid(row=4, column=1, padx=5, pady=5, sticky='w')


        self.pump_direction_options = ctk.CTkOptionMenu(
            self.setup_frame,
            values=['Clockwise', 'Counter-clockwise'],
            width=1,
            command=self.pump_direction_options_callback
        )
        self.pump_direction_options.set('Clockwise')
        self.pump_direction_options.grid(row=5, column=0, padx=5, pady=5, sticky='e')

        self.pump_direction_label = ctk.CTkLabel(self.setup_frame, text='direction')
        self.pump_direction_label.grid(row=5, column=1, padx=5, sticky='w')


        # === MFC Section ===
        mfc_label = ctk.CTkLabel(self.setup_frame, text='Mass Flow Controller', font=('Futura', 16, 'underline'))
        mfc_label.grid(row=6, column=0, columnspan=2, padx=10, pady=(15, 5), sticky='ew')

        self.mfc_flow_entry = ctk.CTkEntry(self.setup_frame, placeholder_text='Flow rate', justify='right')
        self.mfc_flow_entry.grid(row=7, column=0, padx=5, pady=5, sticky='e')

        self.mfc_flow_units = ctk.CTkLabel(self.setup_frame, text='sccm')
        self.mfc_flow_units.grid(row=7, column=1, padx=5, pady=5, sticky='w')


        # === Stirrer Section ===
        stirrer_label = ctk.CTkLabel(self.setup_frame, text='Stirrer', font=('Futura', 16, 'underline'))
        stirrer_label.grid(row=8, column=0, columnspan=2, padx=10, pady=(15, 5), sticky='ew')

        self.stirrer_speed_entry = ctk.CTkEntry(self.setup_frame, placeholder_text='Stirrer Speed', justify='right')
        self.stirrer_speed_entry.grid(row=9, column=0, padx=5, pady=(5, 20), sticky='e')

        self.stirrer_speed_units = ctk.CTkLabel(self.setup_frame, text='rpm')
        self.stirrer_speed_units.grid(row=9, column=1, padx=5, pady=(5, 20), sticky='w')





        # # ===== Setup Details Frame =====
        # self.setup_frame = ctk.CTkFrame(self)
        # self.setup_frame.grid(row=2, column=0, pady=(0, 20), sticky='ew')
        # self.setup_frame.grid_rowconfigure((0, 1, 2, 3, 4, 5), weight=1)
        # self.setup_frame.grid_columnconfigure((0, 1), weight=1)

        # self.setup_title = ctk.CTkLabel(self.setup_frame, text='Setup Experiment', font=('Futura', 20, 'underline'))
        # self.setup_title.grid(row=0, column=0, columnspan=2, padx=10, pady=(5, 15))

        # self.voltage_entry = ctk.CTkEntry(self.setup_frame, placeholder_text='Voltage', justify='right')
        # self.voltage_entry.grid(row=1, column=0, padx=5, pady=5, sticky='e')

        # self.voltage_units_options = ctk.CTkOptionMenu(self.setup_frame, values=['V', 'A', 'mA'], width=1,
        #     command=self.voltage_units_options_callback)
        # self.voltage_units_options.set('V')
        # self.voltage_units_options.grid(row=1, column=1, padx=5, pady=5, sticky='w')

        # self.pump_speed_entry = ctk.CTkEntry(self.setup_frame, placeholder_text='Pump Speed', justify='right')
        # self.pump_speed_entry.grid(row=2, column=0, padx=5, pady=5, sticky='e')

        # self.pump_speed_units = ctk.CTkLabel(self.setup_frame, text='mL/min')
        # self.pump_speed_units.grid(row=2, column=1, padx=5, pady=5, sticky='w')


        # self.mfc_flow_entry = ctk.CTkEntry(self.setup_frame, placeholder_text='Flow rate', justify='right')
        # self.mfc_flow_entry.grid(row=3, column=0, padx=5, pady=5, sticky='e')

        # self.mfc_flow_units = ctk.CTkLabel(self.setup_frame, text='sccm')
        # self.mfc_flow_units.grid(row=3, column=1, padx=5, pady=5, sticky='w')


        # self.stirrer_speed_entry = ctk.CTkEntry(self.setup_frame, placeholder_text='Stirrer Speed', justify='right')
        # self.stirrer_speed_entry.grid(row=4, column=0, padx=5, pady=(5, 20), sticky='e')

        # self.stirrer_speed_units = ctk.CTkLabel(self.setup_frame, text='rpm')
        # self.stirrer_speed_units.grid(row=4, column=1, padx=5, pady=(5, 20), sticky='w')


        # ===== Cut-off Parameters Frame =====
        self.cutoff_frame = ctk.CTkFrame(self)
        self.cutoff_frame.grid(row=3, column=0, pady=(0, 20), sticky='ew')
        self.cutoff_frame.grid_rowconfigure((0, 1, 2), weight=1) # Increase number in list in tuple to add sensor cut-offs
        self.cutoff_frame.grid_columnconfigure((0, 1), weight=1) 

        self.cutoff_title = ctk.CTkLabel(self.cutoff_frame, text='Cut-off Parameters (Optional)', font=('Futura', 20, 'underline'))
        self.cutoff_title.grid(row=0, column=0, columnspan=3, padx=10, pady=(5, 15))

        self.duration_entry = ctk.CTkEntry(self.cutoff_frame, placeholder_text='Duration', justify='right')
        self.duration_entry.grid(row=1, column=0, padx=5, pady=(5, 20), sticky='e')

        self.duration_units_options = ctk.CTkOptionMenu(self.cutoff_frame, values=['minutes', 'hours'], width=1,
            command=self.duration_units_options_callback)
        self.duration_units_options.set('hours')
        self.duration_units_options.grid(row=1, column=1, padx=5, pady=(5, 20), sticky='w')


        # ===== Confirm Experiment Frame =====
        self.start_frame = ctk.CTkFrame(self)
        self.start_frame.grid(row=4, column=0, pady=0, sticky='nsew')
        self.start_frame.grid_rowconfigure(0, weight=1)
        self.start_frame.grid_columnconfigure((0, 1), weight=1) 

        self.overwrite_button = ctk.CTkButton(
            self.start_frame, 
            text='Overwrite Save', 
            fg_color=App.COLOUR_GREY, hover_color=App.COLOUR_GREY, 
            state='disabled',
            command=self.overwrite_save_data
        )
        self.overwrite_button.grid(row=0, column=0, padx=20, pady=20, sticky='ew')

        self.start_button = ctk.CTkButton(
            self.start_frame, 
            text='Create Experiment', 
            fg_color=App.COLOUR_BRIGHT_GREEN, hover_color=App.COLOUR_DARK_GREEN, 
            command=self.confirm_data_entry
        )
        self.start_button.grid(row=0, column=1, padx=20, pady=20, sticky='ew')


    def voltage_units_options_callback(self, choice):
        self.voltage_units_var = choice
        if choice == 'V':
            self.voltage_entry.configure(placeholder_text='Voltage')
        else:
            self.voltage_entry.configure(placeholder_text='Current')

    def duration_units_options_callback(self, choice):
        self.duration_units_var = choice

    def pump_direction_options_callback(self, choice):
        self.pump_direction_var = choice

    def confirm_data_entry(self):
        logging.info('Confirming data entry...')
        
        # Details entry fields
        detail_fields = [self.username_entry, self.filename_entry]
        detail_values = []

        logging.debug('Validating detail fields...')
        for entry in detail_fields:
            if not entry.get():
                logging.error(f'Missing required field: {entry.cget("placeholder_text")}')
                entry.configure(placeholder_text_color=App.COLOUR_BRIGHT_RED)
                return
            detail_values.append(entry.get())

        # Required numeric fields
        required_fields = [
            self.voltage_entry,
            self.pump_speed_entry,
            self.tubing_size_entry,
            self.mfc_flow_entry,
            self.stirrer_speed_entry
        ]
        required_values = []

        logging.debug('Validating mandatory numeric fields...')
        for entry in required_fields:
            value = self.validate_numeric_entry(entry)
            if value is None:
                return
            required_values.append(value)

        # Optional numeric field
        optional_fields = [self.duration_entry]
        optional_values = []

        logging.debug('Validating optional fields...')
        for entry in optional_fields:
            if entry.get():
                value = self.validate_numeric_entry(entry)
                if value is None:
                    return
                optional_values.append(value)
            else:
                optional_values.append(None)

        # Units (no need validation because they are from a dropdown)
        mode_select_values = [self.voltage_units_var, self.pump_direction_var, self.duration_units_var]

        logging.info('All fields validated. Sending data to parent...')

        # Run in background thread, otherwise it stops the window from automatically closing
        def setup_experiment_for_controller():
            self.parent.set_experiment(
                detail_values,
                required_values,
                optional_values,
                mode_select_values
            )
        threading.Thread(target=setup_experiment_for_controller, daemon=True).start()

        logging.info('Data entry confirmed and closing window now.')
        self.destroy()


# Custom handler to write logs to the GUI textbox
class TextBoxHandler(logging.Handler):
    def __init__(self, textbox):
        super().__init__()
        self.textbox = textbox

    def emit(self, record):
        log_entry = self.format(record)
        self.textbox.configure(state='normal')
        self.textbox.insert('end', f'\n{log_entry}')
        self.textbox.configure(state='disabled')
        self.textbox.see('end')  # Auto-scroll to bottom


class App(ctk.CTk):
    MAIN_WIDTH = 640
    MAIN_HEIGHT = 720

    SECONDARY_WIDTH = 640
    SECONDARY_HEIGHT = 860

    # DEFAULT COLOURS
    COLOUR_BRIGHT_RED = '#ff1a1a'
    COLOUR_DARK_RED = '#cc0000'
    COLOUR_BRIGHT_ORANGE = '#ffa31a'
    COLOUR_DARK_ORANGE = '#cc7a00'
    COLOUR_BRIGHT_GREEN = '#00cc00'
    COLOUR_DARK_GREEN = '#009900'
    COLOUR_BRIGHT_BLUE = '#0066ff'
    COLOUR_DARK_BLUE = '#0052cc'
    COLOUR_GREY = '#595959'

    def __init__(self):
        super().__init__()

        self.set_parameters()
        self.build_ui()

    def set_parameters(self):
        self.new_experiment_topLevel_window = None

        self.detail_entry_values = None
        self.mandatory_entry_values = None
        self.optional_entry_values = None
        self.mode_select_values = None

        self.start_time = None
        self.timer_running = False

        self.current_log_file_name = None
        self.controller = Controller(self)

    def build_ui(self):
        self.title('Data Logger')
        self.geometry(f"{App.MAIN_WIDTH}x{App.MAIN_HEIGHT}")

        # Configure grid layout (5x1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # ===== Start Experiment Frame =====
        self.start_frame = ctk.CTkFrame(self)
        self.start_frame.grid(row=0, column=0, pady=(0, 20), sticky='ew')

        self.start_frame.grid_rowconfigure((0, 1) , weight=1)
        self.start_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.start_title = ctk.CTkLabel(self.start_frame, text='Setup Experiment', font=('Futura', 20))
        self.start_title.grid(row=0, column=1, padx=10, pady=(5, 0), sticky='ew')

        self.new_experiment_button = ctk.CTkButton(
            self.start_frame,
            text='New',
            fg_color=App.COLOUR_BRIGHT_BLUE, hover_color=App.COLOUR_DARK_BLUE,
            command=self.open_new_experiment_topLevel
        )
        self.new_experiment_button.grid(row=1, column=1, padx=5, pady=20, sticky='n')

        # ===== Control Experiment Frame =====
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame.grid(row=1, column=0, pady=(0, 20), sticky='ew')

        self.control_frame.grid_rowconfigure((0, 1), weight=1)
        self.control_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.control_title = ctk.CTkLabel(self.control_frame, text='Controls', font=('Futura', 20))
        self.control_title.grid(row=0, column=0, columnspan=3, padx=10, pady=(5, 0), sticky='ew')

        self.start_button = ctk.CTkButton(
            self.control_frame,
            text='Start',
            fg_color=App.COLOUR_GREY,
            command=self.start_experiment,
            state='disabled'
        )
        self.start_button.grid(row=1, column=0, padx=5, pady=20, sticky='e')

        self.stop_button = ctk.CTkButton(
            self.control_frame,
            text='Stop',
            fg_color=App.COLOUR_GREY,
            command=self.stop_experiment,
            state='disabled'
        )
        self.stop_button.grid(row=1, column=1, padx=5, pady=20)

        self.reset_button = ctk.CTkButton(
            self.control_frame,
            text='Reset',
            fg_color=App.COLOUR_GREY,
            command=self.reset_experiment,
            state='disabled'
        )
        self.reset_button.grid(row=1, column=2, padx=5, pady=20, sticky='w')

        # ===== Timer Frame =====
        self.timer_frame = ctk.CTkFrame(self)
        self.timer_frame.grid(row=2, column=0, pady=(0, 20), sticky='ew')

        self.timer_frame.grid_rowconfigure((0, 1), weight=1)
        self.timer_frame.grid_columnconfigure(0, weight=1)

        self.timer_title = ctk.CTkLabel(self.timer_frame, text='Timer', font=('Futura', 20))
        self.timer_title.grid(row=0, column=0, columnspan=3, padx=10, pady=10, sticky='ew')

        self.timer_textbox = ctk.CTkLabel(self.timer_frame, text='0 hr 0 min')
        self.timer_textbox.grid(row=1, column=0, padx=20, pady=(0, 0), sticky='ew')

        # ===== Log Frame =====
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=3, column=0, pady=(0, 20), sticky='ew')

        self.log_frame.grid_rowconfigure((0, 1), weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)

        self.log_title = ctk.CTkLabel(self.log_frame, text='Log', font=('Futura', 20))
        self.log_title.grid(row=0, column=0, columnspan=3, padx=10, pady=10, sticky='ew')

        self.log_textbox = ctk.CTkTextbox(self.log_frame, height=200, state='disabled')
        self.log_textbox.grid(row=1, column=0, padx=20, pady=(0, 20), sticky='nsew')

        # Add logging to terminal and GUI
        textbox_handler = TextBoxHandler(self.log_textbox)
        textbox_handler.setLevel(logging.INFO) # Set level to INFO instead of DEBUG for logging window
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%y-%m-%d %H:%M:%S')
        textbox_handler.setFormatter(formatter)
        logging.getLogger().addHandler(textbox_handler)

        # ===== Logo Frame =====
        self.logo_frame = ctk.CTkFrame(self, fg_color='transparent')
        self.logo_frame.grid(row=4, column=0, sticky='e', padx=10, pady=(0, 10))  # Align right with padding

        # Load logo with correct aspect ratio
        logo_path = os.path.join(os.path.dirname(__file__), 'images', 'R3VTech_StackLogo_col1.png')
        original_logo = Image.open(logo_path)
        max_width = 120
        aspect_ratio = original_logo.width / original_logo.height
        logo_resized = original_logo.resize((max_width, int(max_width / aspect_ratio)))

        logo_image = ctk.CTkImage(light_image=logo_resized, size=logo_resized.size)
        self.logo_label = ctk.CTkLabel(self.logo_frame, image=logo_image, text='')
        self.logo_label.pack()

        logging.info('Program launched successfully!!')

    def update_timer(self):
        if self.timer_running and self.start_time:
            elapsed = datetime.now() - self.start_time
            hours, remainder = divmod(elapsed.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            self.timer_textbox.configure(text=f"{hours} hr {minutes} min")
            self.after(1000, self.update_timer)

    def open_new_experiment_topLevel(self):
        if self.new_experiment_topLevel_window is None or not self.new_experiment_topLevel_window.winfo_exists():
            logging.info('Setting up new experiment...')
            self.new_experiment_topLevel_window = NewExperimentToplevelWindow(self)
        else:
            self.new_experiment_topLevel_window.focus()

    def set_experiment(self, detail_entry_values, mandatory_entry_values, optional_entry_values, mode_select_values):
        '''Called by NewExperimentToplevelWindow(object) only'''
        self.detail_entry_values = detail_entry_values
        self.mandatory_entry_values = mandatory_entry_values
        self.optional_entry_values = optional_entry_values
        self.mode_select_values = mode_select_values

        current_date = datetime.now().strftime('%Y%m%d')
        self.current_log_file_name = f'output/{current_date}_{self.detail_entry_values[1]}.csv'
        with open(self.current_log_file_name, 'w', newline='') as file:
            wr = csv.writer(file, quoting=csv.QUOTE_ALL)
            wr.writerow(['Author', self.detail_entry_values[0]])
            wr.writerow(['Experiment name', self.detail_entry_values[1]])
            wr.writerow([''])
            wr.writerow(['Parameters'])
            wr.writerow(['Voltage', self.mandatory_entry_values[0], self.mode_select_values[0]])
            wr.writerow(['Pump speed', self.mandatory_entry_values[1]])
            wr.writerow(['Tubing size', self.mandatory_entry_values[2]])
            wr.writerow(['Pump direction', self.mode_select_values[1]])
            wr.writerow(['Flow rate', self.mandatory_entry_values[3]])
            wr.writerow(['Stirrer speed', self.mandatory_entry_values[4]])
            wr.writerow(['Duration', self.optional_entry_values[0], self.mode_select_values[2]])
            wr.writerow([''])
            wr.writerow(['Report'])
            wr.writerow(['Total power', '', 'W'])
            wr.writerow(['Total liquid used', '', 'mL'])
            wr.writerow(['Total gas used', '', 'cm^3'])
            wr.writerow([''])
            wr.writerow(['Time', 'Voltage', 'Current', 'Pump speed', 'Flow rate', 'Stirrer speed'])

        logging.info(f'Creating new experiment file: output/{current_date}_{self.detail_entry_values[1]}.csv')

        # Setup controller and run in thread
        psu_config={
            'value': self.mandatory_entry_values[0],
            'mode': self.mode_select_values[0]
        }
        pump_config={
            'speed': self.mandatory_entry_values[1],
            'direction': self.mode_select_values[1]
        }
        mfc_config={
            'flow': self.mandatory_entry_values[3]
        }
        stirrer_config={
            'speed': self.mandatory_entry_values[4]
        }
        duration_config={
            'time': self.optional_entry_values[0],
            'unit': self.mode_select_values[2]
        }
        threading.Thread(target=self.controller.run, args=(psu_config, pump_config, mfc_config, stirrer_config, duration_config), daemon=True).start()

        self.enable_start_button()
        self.disable_stop_button()
        self.enable_reset_button()
        self.disable_new_experiment_button()

    def log_experiment_data(self, psu_readings, pump_readings, mfc_readings):
        '''Called by the Controller(object) only'''
        current_time = datetime.now().strftime('%H:%M:%S')
        with open(self.current_log_file_name, 'a', newline='') as file:
            wr = csv.writer(file, quoting=csv.QUOTE_ALL)
            wr.writerow([current_time, psu_readings['voltage'], psu_readings['current'], 'S', mfc_readings, 'P'])


    def enable_new_experiment_button(self):
        self.new_experiment_button.configure(fg_color=App.COLOUR_BRIGHT_BLUE, hover_color=App.COLOUR_DARK_BLUE, state='normal')

    def disable_new_experiment_button(self):
        self.new_experiment_button.configure(fg_color=App.COLOUR_GREY, state='disabled')

    def enable_start_button(self):
        self.start_button.configure(fg_color=App.COLOUR_BRIGHT_GREEN, hover_color=App.COLOUR_DARK_GREEN, state='normal')

    def disable_start_button(self):
        self.start_button.configure(fg_color=App.COLOUR_GREY, state='disabled')

    def enable_stop_button(self):
        self.stop_button.configure(fg_color=App.COLOUR_BRIGHT_RED, hover_color=App.COLOUR_DARK_RED, state='normal')

    def disable_stop_button(self):
        self.stop_button.configure(fg_color=App.COLOUR_GREY, state='disabled')

    def enable_reset_button(self):
        self.reset_button.configure(fg_color=App.COLOUR_BRIGHT_ORANGE, hover_color=App.COLOUR_DARK_ORANGE, state='normal')

    def disable_reset_button(self):
        self.reset_button.configure(fg_color=App.COLOUR_GREY, state='disabled')

    def start_experiment(self):
        self.disable_new_experiment_button()
        self.disable_start_button()
        self.enable_stop_button()
        self.disable_reset_button()

        self.start_time = datetime.now()
        self.timer_running = True
        self.update_timer()

        current_time = datetime.now().strftime('%H:%M:%S')
        logging.info(f'Experiment started at: {current_time}')
        self.controller.start()

    def stop_experiment(self):
        self.disable_new_experiment_button()
        self.enable_start_button()
        self.disable_stop_button()
        self.enable_reset_button()

        self.timer_running = False

        current_time = datetime.now().strftime('%H:%M:%S')
        logging.info(f'Experiment stopped at: {current_time}')
        self.controller.stop()

    def reset_complete(self):
        '''
        The delay in the controller.run() loop means that it can take up to 10 seconds to
        exit the while loop. 
        So wait until the it exits, the only enable the user to start a new experiment.
        '''
        self.enable_new_experiment_button()

    def reset_experiment(self):
        self.disable_start_button()
        self.disable_stop_button()
        self.disable_reset_button()

        self.timer_running = False
        self.start_time = None
        self.timer_textbox.configure(text='0 hr 0 min')

        self.current_log_file_name = None

        current_time = datetime.now().strftime('%H:%M:%S')
        logging.info(f'Experiment reset at: {current_time}')
        self.controller.reset()


def main():
    pass

if __name__ == '__main__':
    print('Starting up the GUI... ')

    app = App()
    app.mainloop()