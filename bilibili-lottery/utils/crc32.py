"""
Refactor crc32 crack app to OOP
https://github.com/Aruelius/crc32-crack
"""



class Cracker(object):

    CRCPOLYNOMIAL = 0xEDB88320

    def __init__(self):
        self.crc_table = self._create_crc_table()

    def _create_crc_table(self):
        crc_table = [0 for x in range(256)]
        for i in range(256):
            crc_reg = i
            for _ in range(8):
                if (crc_reg & 1) != 0:
                    crc_reg = self.CRCPOLYNOMIAL ^ (crc_reg >> 1)
                else:
                    crc_reg = crc_reg >> 1
            crc_table[i] = crc_reg
        return crc_table

    def _crc32(self, text):
        crc_start = 0xFFFFFFFF
        for i in range(len(str(text))):
            index = (crc_start ^ ord(str(text)[i])) & 255
            crc_start = (crc_start >> 8) ^ self.crc_table[index]
        return crc_start

    def _crc32_last_index(self, text):
        crcstart = 0xFFFFFFFF
        for i in range(len(str(text))):
            index = (crcstart ^ ord(str(text)[i])) & 255
            crcstart = (crcstart >> 8) ^ self.crc_table[index]
        return index

    def _get_crc_index(self, t):
        for i in range(256):
            if self.crc_table[i] >> 24 == t:
                return i
        return -1

    def _deep_check(self, i, index):
        string = ""
        tc = 0x00
        hashcode = self._crc32(i)
        tc = hashcode & 0xff ^ index[2]
        if not (tc <= 57 and tc >= 48):
            return [0]
        string += str(tc - 48)
        hashcode = self.crc_table[index[2]] ^ (hashcode >>8)
        tc = hashcode & 0xff ^ index[1]
        if not (tc <= 57 and tc >= 48):
            return [0]
        string += str(tc - 48)
        hashcode = self.crc_table[index[1]] ^ (hashcode >> 8)
        tc = hashcode & 0xff ^ index[0]
        if not (tc <= 57 and tc >= 48):
            return [0]
        string += str(tc - 48)
        hashcode = self.crc_table[index[0]] ^ (hashcode >> 8)
        return [1, string]

    def crack(self, text):
        index = [0 for x in range(4)]
        i = 0
        ht = int(f'0x{text}', 16) ^ 0xffffffff

        for i in range(3, -1, -1):
            index[3-i] = self._get_crc_index(ht >> (i*8))
            snum = self.crc_table[index[3-i]]
            ht ^= snum >> ((3-i)*8)

        for i in range(100000000):
            last_index = self._crc32_last_index(i)
            if last_index == index[3]:
                deep_check_data = self._deep_check(i, index)
                if deep_check_data[0]:
                    break

        if i == 100000000:
            return -1

        return f'{i}{deep_check_data[1]}'
