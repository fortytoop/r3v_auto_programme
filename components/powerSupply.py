import serial
import time

# from constants.ports import PSU_PORT, BAUDRATE, TIMEOUT

class PowerSupply:
    def __init__(self, port, baudrate, timeout):
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout
            )
        except serial.SerialException as e:
            raise RuntimeError(f'Failed to connect to power supply: {e}')

    def send_command(self, command):
        self.ser.write((command + '\n').encode())
        time.sleep(0.1)
        if '?' in command:
            return self.ser.readline().decode().strip()
        return None

    def set_voltage(self, voltage, channel=1):
        self.send_command(f'INST:NSEL {channel}')
        self.send_command(f'VOLT {voltage}')

    def get_voltage(self, channel=1):
        self.send_command(f'INST:NSEL {channel}')
        return float(self.send_command('MEAS:VOLT?'))

    def set_current(self, current, channel=1):
        self.send_command(f'INST:NSEL {channel}')
        self.send_command(f'CURR {current}')

    def get_current(self, channel=1):
        self.send_command(f'INST:NSEL {channel}')
        return float(self.send_command('MEAS:CURR?'))

    def start(self):
        self.send_command('OUTP ON')

    def stop(self):
        self.send_command('OUTP OFF')

    def get_status(self):
        status = self.send_command('OUTP?')
        return status.strip() == '1'

    def identify(self):
        return self.send_command('*IDN?')

    def close(self):
        self.ser.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def test_power_supply():
    print('Testing Power Supply...')
    with PowerSupply(port='/dev/tty.usbserial-FT6W3K240', baudrate=9600, timeout=1) as psu:
        idn = psu.identify()
        print(f'Device ID: {idn}')

        # psu.set_voltage(5)
        psu.set_current(1)
        print('Setting voltage to 5 V and current limit to 1 A...')

        psu.start()
        print(f'PSU Status: {psu.get_status()}')
        time.sleep(2)

        voltage = psu.get_voltage()
        current = psu.get_current()
        print(f'Measured Voltage: {voltage:.3f} V')
        print(f'Measured Current: {current:.3f} A')

        psu.stop()
        print(f'PSU Status: {psu.get_status()}')


if __name__ == '__main__':
    test_power_supply()