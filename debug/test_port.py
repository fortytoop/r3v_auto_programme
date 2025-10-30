import serial.tools.list_ports

def list_serial_ports():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        print(f'Device: {port.device}')
        print(f'Description: {port.description}')
        print(f'HWID: {port.hwid}')
        print('-' * 40)

if __name__ == '__main__':
    list_serial_ports()