import serial
import time

class Stirrer:
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
            raise RuntimeError(f'Failed to connect to stirrer: {e}')

    def send_command(self, command):
        self.ser.write((command + '\r').encode())
        time.sleep(0.1)
        response = self.ser.readline().decode('utf-8', errors='ignore').strip()
        return response

    def set_speed(self, rpm):
        # Assuming valid range: 0–1500 depending on device.
        if not (0 <= rpm <= 1500):
            raise ValueError('Speed must be between 0 and 1500 rpm.')
        cmd = f'OUT_SP_4 {rpm}'
        return self.send_command(cmd)

    def get_speed(self):
        return self.send_command('IN_PV_4')

    def get_set_speed(self):
        return self.send_command('IN_SP_4')

    def start(self):
        return self.send_command('START_4')

    def stop(self):
        return self.send_command('STOP_4')

    def close(self):
        self.ser.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def test_stirrer():
    print('Testing IKA Stirring Plate...')
    with Stirrer(port='/dev/tty.usbserial-FT6W3K242', baudrate=9600, timeout=1) as stirrer:
        print('Setting speed to 800 rpm...')
        stirrer.set_speed(800)

        print('Starting stirrer...')
        stirrer.start()
        time.sleep(2)

        actual_speed = stirrer.get_speed()
        print(f'Actual speed: {actual_speed}')

        print('Stopping stirrer...')
        stirrer.stop()

        set_speed = stirrer.get_set_speed()
        print(f'Set speed: {set_speed}')


if __name__ == '__main__':
    test_stirrer()
