"""Build/send a command for the AD9106 demo UART controller (Python 3.8+)."""
import argparse
import math
import struct
from functools import reduce
from operator import xor

STATUS = {0: "OK", 1: "bad terminator", 2: "checksum error", 3: "unknown command",
          4: "invalid parameter", 5: "frame timeout", 6: "UART framing error",
          7: "DAC initialization incomplete", 8: "scene session conflict / legacy preset disabled until reset"}


def code12(value, name):
    if not -2048 <= value <= 2047:
        raise ValueError(name + " must be in -2048..2047")
    return value & 0xfff


def build_command(seq, wave, enable=True, gain=1.0, offset=0, rate=1,
                  phase=0, duty=743, high=1024, low=-1024):
    """rate: sine DDS word / triangle step / square cycles per 1485 samples.

    phase is a 16-bit phase word; square duty is in rate..(1485-rate).
    offset/high/low are signed DAC codes, gain is a signed multiplier.
    """
    if wave not in (1, 2, 3) or not 0 <= seq <= 255:
        raise ValueError("wave must be 1..3 and sequence must be 0..255")
    if not math.isfinite(gain) or not -2 <= gain <= 2047 / 1024:
        raise ValueError("gain must be in -2..1.9990234375")
    limits = {1: 0x7fffff, 2: 63, 3: 742}
    if not 1 <= rate <= limits[wave] or not 0 <= phase <= 65535:
        raise ValueError("rate or phase out of range")
    if wave == 3 and not rate <= duty <= 1485-rate:
        raise ValueError("square duty threshold must be in cycles..(1485-cycles)")
    packet = bytearray([0xaa, 0x55, seq, wave, int(bool(enable))])
    packet += struct.pack(">HH", code12(round(gain * 1024), "gain"), code12(offset, "offset"))
    packet += rate.to_bytes(3, "big")
    packet += struct.pack(">HHHH", phase if wave == 1 else 0,
                          duty if wave == 3 else 0,
                          code12(high, "high") if wave == 3 else 0,
                          code12(low, "low") if wave == 3 else 0)
    packet += b"\x00\x00"
    packet += bytes([reduce(xor, packet[2:], 0), 0x0d])
    return bytes(packet)


def decode_reply(data, seq, wave):
    if len(data) != 8 or data[:2] != b"\x55\xaa" or data[6:] != b"\r\n":
        raise ValueError("incomplete or malformed reply: " + data.hex(" "))
    if data[2:4] != bytes([seq, wave]) or data[5] != reduce(xor, data[2:5], 0):
        raise ValueError("reply sequence/command/checksum mismatch")
    return data[4]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wave", choices=["sine", "triangle", "square"])
    parser.add_argument("--port", help="e.g. COM3; omit to only print command hex")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--seq", type=int, default=1)
    parser.add_argument("--off", action="store_true")
    parser.add_argument("--gain", type=float, default=1.0)
    parser.add_argument("--offset", type=int, default=0, help="signed DAC offset code")
    parser.add_argument("--dac-clock", type=float, default=148500000)
    parser.add_argument("--frequency", type=float, help="Hz; quantized to supported rate")
    parser.add_argument("--phase", type=float, default=0, help="sine phase in degrees")
    parser.add_argument("--step", type=int, default=4, help="triangle SAW_STEP, 1..63")
    parser.add_argument("--cycles", type=int, default=50, help="square cycles per 1485 samples (1..742); each cycle adds 100 kHz")
    parser.add_argument("--duty", type=float, default=50, help="square high duty, percent")
    parser.add_argument("--high", type=int, default=1024)
    parser.add_argument("--low", type=int, default=-1024)
    args = parser.parse_args()
    wave = {"sine": 1, "triangle": 2, "square": 3}[args.wave]
    try:
        if not math.isfinite(args.dac_clock) or args.dac_clock <= 0:
            raise ValueError("DAC clock must be positive")
        if args.frequency is not None and (not math.isfinite(args.frequency) or args.frequency <= 0):
            raise ValueError("frequency must be positive")
        if not math.isfinite(args.phase) or not 0 <= args.phase < 360:
            raise ValueError("phase must be in [0, 360)")
        if not math.isfinite(args.duty) or not 0 < args.duty < 100:
            raise ValueError("duty must be between 0 and 100 percent")
        if wave == 1:
            freq = args.frequency if args.frequency is not None else 10000000
            rate = round(freq / args.dac_clock * (1 << 24))
            actual = rate * args.dac_clock / (1 << 24)
        elif wave == 2:
            rate = round(args.dac_clock / (32768 * args.frequency)) if args.frequency else args.step
            actual = args.dac_clock / (32768 * rate) if rate else 0
        else:
            rate = round(args.frequency * 1485 / args.dac_clock) if args.frequency else args.cycles
            actual = rate * args.dac_clock / 1485
        packet = build_command(args.seq, wave, not args.off, args.gain, args.offset,
                               rate, round(args.phase / 360 * 65536) & 65535,
                               math.floor(args.duty * 1485 / 100 + 0.5), args.high, args.low)
    except ValueError as error:
        parser.error(str(error))
    print("Actual nominal frequency: {:.6f} Hz; rate={}".format(actual, rate))
    print("TX: " + packet.hex(" ").upper())
    if args.port:
        try:
            import serial
        except ImportError:
            parser.error("sending requires pyserial: python -m pip install pyserial")
        with serial.Serial(args.port, args.baud, timeout=1, bytesize=8, parity="N", stopbits=1) as port:
            port.reset_input_buffer()
            port.write(packet)
            port.flush()
            reply = port.read(8)
        print("RX: " + reply.hex(" ").upper())
        status = decode_reply(reply, args.seq, wave)
        print(STATUS.get(status, "unknown status {}".format(status)))
        if status:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
