import threading
import time
import logging
from components.powerSupply import PowerSupply
from components.pump import Pump
from components.mfc import MassFlowController
from components.stirrer import Stirrer

from constants.ports import PSU_PORT, PUMP_PORT, MFC_PORT, STIRRER_PORT, BAUDRATE,  TIMEOUT

class Controller():
    def __init__(self, parent):
        super().__init__()
        # self.daemon = True  # Exits when app closes

        # Store reference to the main App (GUI)
        self.parent = parent 

        self.should_run = False
        self.should_stop = False
        self.should_reset = False

        self.psu = None
        self.pump = None
        self.mfc = None
        # self.stirrer = None
        

        try:
            self.connect_devices()
        except Exception as e:
            logging.error(f'Controller could not connect to devices. Error: {e}')
            return

    def connect_devices(self):
        '''Test connection to devices'''
        print(BAUDRATE, TIMEOUT)

        self.psu = PowerSupply(port=PSU_PORT, baudrate=BAUDRATE, timeout=TIMEOUT)
        self.pump = Pump(port=PUMP_PORT, baudrate=BAUDRATE, timeout=TIMEOUT)
        self.mfc = MassFlowController(port=MFC_PORT, baudrate=BAUDRATE, timeout=TIMEOUT)
        # self.stirrer = Stirrer(port=STIRRER_PORT, baudrate=BAUDRATE, timeout=TIMEOUT)

        logging.info(f'Connected to components!')

    def run(self, psu_config, pump_config, mfc_config, stirrer_config, duration_config):
        try:
            self.setup_devices(psu_config, pump_config, mfc_config, stirrer_config)
        except Exception as e:
            logging.error(f'Controller could not setup devices. Error: {e}')
            return

        logging.info('Controller ready!')
        self.should_reset = False


        cut_off_time = duration_config['time'] * 60 if duration_config['unit'] != 'minutes' else duration_config['time']
        print(cut_off_time)

        # Run so long as not reset
        while not self.should_reset:
            # Disable devices remotely if stopped
            if self.should_stop:
                self.shutdown_devices()

            # Log parameters if started
            if self.should_run:
                self.startup_devices()
                self.log_devices()

            time.sleep(10)

        logging.info('Controller has been reset. Ready for new experiment!')
        self.parent.reset_complete()

    def setup_devices(self, psu_config, pump_config, mfc_config, stirrer_config):
        # PSU
        mode = psu_config['mode']
        value = psu_config['value']

        if mode == 'V':
            try:
                if self.psu:
                    self.psu.set_voltage(voltage=value)
            except:
                pass
        else:
            current = value / 1000 if mode == 'mA' else value

            try:
                if self.psu:
                    self.psu.set_current(current=current)
            except:
                pass

        # Pump
        try:
            if self.pump:
                self.pump.set_direction(clockwise=pump_config['direction'] == 'Clockwise')
                self.pump.set_speed(rpm=pump_config['speed'])
        except:
            pass

        # MFC
        try:
            if self.mfc:
                self.mfc.set_flow_rate(flow_rate=mfc_config['flow'])
        except:
            pass

        # # Stirrer
        # try:
        #     if self.stirrer:
        #         self.stirrer.set_speed(rpm=stirrer_config['speed'])


    def shutdown_devices(self):
        print('Shutdown devices')
        try:
            if self.psu:
                self.psu.stop()
        except:
            pass

        try:
            if self.pump:
                self.pump.stop()
        except:
            pass

        try:
            if self.mfc:
                self.mfc.stop()
        except:
            pass

        # try:
        #     if self.stirrer:
        #         self.stirrer.stop()
        # except:
        #     pass

    def startup_devices(self):
        try:
            if self.psu:
                self.psu.start()
        except:
            pass

        try:
            if self.pump:
                self.pump.start()
        except:
            pass

        try:
            if self.mfc:
                self.mfc.start()
        except:
            pass

        # try:
        #     if self.stirrer:
        #         self.stirrer.start()
        # except:
        #     pass

    def log_devices(self):
        # Get current readings
        try:
            if self.psu:
                print(f'Current: {self.psu.get_current()}')
                print(f'Voltage: {self.psu.get_voltage()}')
        except:
            pass

        try:
            if self.pump:
                print(f'Pump Speed: {self.pump.pump_get_info()}')
        except:
            pass

        try:
            if self.mfc:
                print(f'Flow Rate: {self.mfc.get_flow_rate()}')
        except:
            pass

        # try:
        #     if self.stirrer:
        #         print(f'Stirrer Speed: {self.stirrer.get_speed()}')
        # except:
        #     pass

        logging.debug('Logging data!')
        self.parent.log_experiment_data(
            {'current': self.psu.get_current(), 'voltage': self.psu.get_voltage()}, 
            {'pump_speed': self.pump.pump_get_info()}, 
            {'flow_rate': self.mfc.get_flow_rate()}
        )
        

    def start(self):
        self.should_run = True
        self.should_stop = False

        logging.debug('Controller started!')

    def stop(self):
        self.should_run = False
        self.should_stop = True

        logging.debug('Controller stopped!')

    def reset(self):
        self.should_run = False
        self.should_stop = False
        self.should_reset = True

        logging.debug('Resetting controller!')
