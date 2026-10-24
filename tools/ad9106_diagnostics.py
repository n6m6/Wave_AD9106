"""Read AD9106 shadow registers through UART 0x45 and the chip's SDO pin."""
import argparse
import json
from functools import reduce
from operator import xor
from ad9106_firing import frame, HARDWARE_PATTERN_REPEATS

REGISTERS = (0x00, 0x1e, 0x1f, 0x2a, 0x2b, 0x28, 0x29, 0x26, 0x27,
             0x50, 0x51, 0x52, 0x54, 0x55, 0x56, 0x58, 0x59, 0x5a,
             0x5c, 0x5d, 0x5e, 0x44, 0x45, 0x60)

def decode_read_reply(data, seq):
    if len(data) != 10 or data[:4] != bytes([0x55,0xaa,seq,0x45]) or data[-2:] != b'\r\n':
        raise ValueError('Invalid register-read reply: '+data.hex(' '))
    if data[7] != reduce(xor,data[2:7],0):
        raise ValueError('Register-read checksum mismatch')
    if data[4]:
        raise ValueError('Register-read error status {}'.format(data[4]))
    return int.from_bytes(data[5:7],'big')

def read_registers(port_name, baud=115200):
    import serial
    values={}
    with serial.Serial(port_name,baud,timeout=2) as port:
        port.reset_input_buffer()
        for seq,address in enumerate(REGISTERS):
            port.write(frame(seq,0x45,address.to_bytes(2,'big'))); port.flush()
            prefix=port.read(8)
            if len(prefix)==8 and prefix[:4]==bytes([0x55,0xaa,seq,0x45]) and prefix[-2:]==b'\r\n' and prefix[4]==3 and prefix[5]==(seq^0x45^3):
                raise ValueError('FPGA firmware does not support register readback; program the new bitstream')
            values['0x{:02X}'.format(address)]=decode_read_reply(prefix+port.read(2),seq)
    expected=(HARDWARE_PATTERN_REPEATS-1)*0x0101
    return dict(registers=values, finite_once=(values['0x1F']==1 and values['0x2A']==0 and values['0x2B']==0),
                finite_expected=(values['0x1F']==1 and values['0x2A']==expected and values['0x2B']==expected),
                expected_pattern_repeats=HARDWARE_PATTERN_REPEATS,
                note='SDO shadow-register readback; this does not prove analog output or active-register contents.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    args=parser.parse_args()
    print(json.dumps(read_registers(args.port),indent=2))
