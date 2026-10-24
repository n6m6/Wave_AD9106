import unittest
import sys
import types
from unittest.mock import patch
from ad9106_diagnostics import decode_read_reply, read_registers, REGISTERS

class DiagnosticReplyTests(unittest.TestCase):
    def test_values_and_checksums(self):
        for value in (0,1,0xa55a,0xffff):
            b=bytearray([0x55,0xaa,19,0x45,0,value>>8,value&255,0,13,10])
            for x in b[2:7]: b[7]^=x
            self.assertEqual(decode_read_reply(bytes(b),19),value)
            b[5]^=1
            with self.assertRaises(ValueError): decode_read_reply(bytes(b),19)

    def test_malformed_or_error(self):
        for b in (b'',bytes([0x55,0xaa,19,0x45,4,0,0,19^0x45^4,13,10])):
            with self.assertRaises(ValueError): decode_read_reply(b,19)

    def test_serial_readback_and_old_firmware(self):
        class Port:
            old = False
            repeat_word = 0
            requests = []
            def __init__(self, *args, **kwargs): self.buffer = b''
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def reset_input_buffer(self): pass
            def flush(self): pass
            def write(self, data):
                self.requests.append(data)
                seq, cmd = data[2:4]
                address = int.from_bytes(data[4:6], 'big')
                if self.old:
                    self.buffer = bytes([0x55,0xaa,seq,cmd,3,seq^cmd^3,13,10])
                else:
                    value = 1 if address == 0x1f else self.repeat_word if address in (0x2a,0x2b) else 0
                    hi, lo = value >> 8, value & 255
                    self.buffer = bytes([0x55,0xaa,seq,cmd,0,hi,lo,seq^cmd^hi^lo,13,10])
            def read(self, count):
                result, self.buffer = self.buffer[:count], self.buffer[count:]
                return result
        with patch.dict(sys.modules, {'serial': types.SimpleNamespace(Serial=Port)}):
            result = read_registers('COM_TEST')
            self.assertTrue(result['finite_once'])
            self.assertFalse(result['finite_expected'])
            self.assertEqual(len(Port.requests), len(REGISTERS))
            self.assertTrue(all(len(p)==24 and p[3]==0x45 for p in Port.requests))
            Port.repeat_word = 0x0101
            result = read_registers('COM_TEST')
            self.assertTrue(result['finite_expected'])
            self.assertFalse(result['finite_once'])
            self.assertEqual(result['expected_pattern_repeats'], 2)
            Port.old = True
            with self.assertRaisesRegex(ValueError, 'program the new bitstream'):
                read_registers('COM_TEST')

if __name__=='__main__': unittest.main()
