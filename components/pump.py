import serial
import time

class Pump:
    def __init__(self, port, baudrate, timeout):
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_TWO,
                timeout=timeout
            )
        except serial.SerialException as e:
            raise RuntimeError(f'Failed to connect to pump: {e}')

    def send_command(self, command):
        self.ser.write((command + '\r').encode())
        time.sleep(0.1)
        response = self.ser.readline().decode('utf-8', errors='ignore').strip()
        return response

    def set_speed(self, rpm):
        speed = f'{int(rpm):03}'
        self.send_command(f'1SP{speed}')

    def set_direction(self, clockwise=True):
        cmd = '1RR' if clockwise else '1RL'
        self.send_command(cmd)

    def start(self):
        self.send_command('1GO')

    def stop(self):
        self.send_command('1ST')

    def get_info(self):
        return self.send_command('1RS')

    def get_status(self):
        status = self.send_command('1ZY')
        return bool(int(status)) if status else False

    def close(self):
        self.ser.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def test_pump():
    print('Testing Pump...')
    with Pump(port='/dev/tty.usbserial-FT6W3K241', baudrate=9600, timeout=1) as pump:
        status = pump.get_status()
        print(f'Pump status (1=running, 0=stopped): {status}')

        print('Setting speed to 60 rpm...')
        pump.set_speed(60)

        print('Setting direction: Clockwise')
        pump.set_direction(clockwise=True)

        print('Starting pump...')
        pump.start()

        time.sleep(2)

        status = pump.get_status()
        print(f'Pump status (1=running, 0=stopped): {status}')

        info = pump.get_info()
        print(f'Pump info: {info}')

        print('Stopping pump...')
        pump.stop()

        time.sleep(1)
        status = pump.get_status()
        print(f'Status after stop: {status}')


if __name__ == '__main__':
    test_pump()