import serial
import time

class MassFlowController:
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
            raise RuntimeError(f'Failed to connect to MFC: {e}')

    def send_command(self, command, delay=0.1):
        self.ser.write((command + '\r').encode())
        time.sleep(delay)
        response = self.ser.readline().decode('utf-8', errors='ignore').strip()
        return response

    def set_flow_rate(self, flow_rate):
        return self.send_command(f'As{flow_rate}')

    def get_flow_rate(self):
        # Gives all raw data from MFC
        raw_response = self.send_command('A')

        # Only pick flow rate
        # 0 - MFC name, 1 - PSIA, 2 - Temp, 3 - ccm, 4 - sccm, 5 - setpoint, 6 - gas type, 7 - valve state
        return float(raw_response.split()[4])

    def start(self):
        return self.send_command('AC')

    def stop(self):
        return self.send_command('AHC')

    def tare_flow(self):
        # Zero the flow rate
        return self.send_command('AV')

    def get_info(self):
        manufacturer = self.send_command('A??M*')
        firmware = self.send_command('AVE')
        return {'manufacturer': manufacturer, 'firmware': firmware}

    def close(self):
        self.ser.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def test_mfc():
    print('Testing MFC...')
    with MassFlowController(port='/dev/cu.usbserial-FT6W3K242', baudrate=9600, timeout=1) as mfc:
        print('Getting device info...')
        info = mfc.get_info()
        print(info)

        print('Setting flow to 5.0...')
        mfc.set_flow_rate(5.0)

        print('Starting flow...')
        mfc.start()
        time.sleep(2)

        data = mfc.get_flow_rate()
        print(f'Flow data: {data}')

        print('Stopping flow...')
        mfc.set_flow_rate(0)
        mfc.stop()
        time.sleep(1)

        data = mfc.get_flow_rate()
        print(f'Flow after stop: {data}')

if __name__ == '__main__':
    test_mfc()
