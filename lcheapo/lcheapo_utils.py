#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data access for lcheapo files
"""
import sys
import datetime
import struct
# import string
import os

# ------------------------------------
# Global Variable Declarations
# ------------------------------------
PROGRAM_NAME = "lcheapo.py"
VERSION = "0.3.0"
HEADER_START = 2
BLOCK_SIZE = 512


class LCCommon:
    """
    LCHEAPO Parent Class
    """
    def __init__(self):
        (self.msec, self.second, self.minute, self.hour,
         self.day, self.month, self.year) = (0, 0, 0, 0, 1, 1, 2000)

    def fixYear(self, year):
        """
        Change year from 2 to 4 digits
        """
        if (0 <= year < 50):
            year += 2000
        elif (50 < year < 100):
            year += 1900
        return year

    def getDateTime(self):
        """
        Convert year:day:month:hour:minute:second.msec value to datetime
        """
        try:
            return datetime.datetime(self.fixYear(self.year),
                                     self.month, self.day,
                                     self.hour, self.minute,
                                     self.second, self.msec*1000)
        except ValueError:
            # return bogus date
            return datetime.datetime(1900, 1, 1, 0, 0, 0, 0)

    def changeTime(self, tm):
        """
        Change local values to correspond to datetime object
        """
        if (tm.year < 2000):
            self.year = tm.year - 1900
        else:
            self.year = tm.year - 2000

        self.month = tm.month
        self.day = tm.day
        self.hour = tm.hour
        self.minute = tm.minute
        self.second = tm.second
        self.msec = int(tm.microsecond / 1000)

    def getRealSampleRate(self, sampleRate):
        """
        Return floating point sample rate
        """
        if (sampleRate < 61):
            return 31.25
        elif (sampleRate < 125):
            return 62.50
        return float(sampleRate)

    def determineLastBlock(self, fp):
        """
        Determine the last full block in the file
        """
        currentPos = fp.tell()
        fp.seek(-1, 2)
        lastBlock = int(fp.tell() / BLOCK_SIZE)
        if currentPos % BLOCK_SIZE != 0:
            lastBlock -= 1
        fp.seek(currentPos, 0)
        return lastBlock

    def seekBlock(self, fp, block):
        """
        Go to a particular block in the file
        """
        fp.seek(block * BLOCK_SIZE, os.SEEK_SET)


class LCUserData (LCCommon):
    """
    LCheapo user data section class
    """
    def __init__(self):
        self.userData = ""

    def seekUserDataPosition(self, fp):
        """
        Move the file pointer to the user data position
        """
        fp.seek(0, os.SEEK_SET)

    def isValidData(self):
        if self.userData.find("LCHEAPO") != 0:
            return False
        else:
            return True

    def readData(self, fp):
        self.userData = fp.read(2048)

    def writeData(self, fp):
        # ------ NOT FINISHED ------
        fp.write(self.userData)


class LCDiskHeader (LCCommon):
    """
    LCheapo disk header class
    """
    def __init__(self):
        pass

    def fixDiskSizeBug(self):
        "Fix an old bug which doubled the disk size."
        self.diskSize /= 2

    def seekHeaderPosition(self, fp):
        "Move the file pointer to the standard header position."
        fp.seek(HEADER_START*BLOCK_SIZE, os.SEEK_SET)

    def readHeader(self, fp):
        """
        :returns: 1 if good read, 0 otherwise
        """
        self.seekHeaderPosition(fp)
        "Read an LCheapo disk header (packed big endian format)."
        (self.writeBlock, self.writeByte, self.readBlock, self.readByte) =\
            struct.unpack('>LHLH', fp.read(12))
        (self.dirStart, self.dirSize, self.dirBlock, self.dirCount) =\
            struct.unpack('>4L', fp.read(16))
        (self.slowStart, self.slowSize, self.slowBlock, self.slowByte) =\
            struct.unpack('>4L', fp.read(16))
        (self.logStart, self.logSize, self.logBlock, self.logByte) =\
            struct.unpack('>4L', fp.read(16))
        (self.dataStart, self.diskNumber) =\
            struct.unpack('>LH', fp.read(6))
        (self.softwareVersion, self.description) =\
            struct.unpack('>10s80s', fp.read(90))
        # Python strings do not terminate on '\0', therefore, do this manually.
        self.softwareVersion = _str_from_cstr(self.softwareVersion)
        if self.softwareVersion is None:
            print('Could not read softwareVersion, file may not have a header')
            return 0
        self.description = _str_from_cstr(self.description)

        (self.sampleRate, self.startChannel, self.numberOfChannels) =\
            struct.unpack('>3H', fp.read(6))
        (self.slowDataRate, self.slowStartChannel,
         self.slowNumberOfChannels) = struct.unpack('>3H', fp.read(6))
        (self.dataType, self.diskSize, self.ramSize, self.numberOfWindows) =\
            struct.unpack('>4H', fp.read(8))

        # Additions which cannot be written back out
        self.realSampleRate = self.getRealSampleRate(self.sampleRate)
        self.dataTypeString = "Unknown Compression"
        if self.dataType >= 0 and self.dataType <= 3:
            self.dataTypeString = ("Uncompressed (16-Bit)",
                                   "Compressed (16-Bit)",
                                   "Uncompressed (24-Bit)",
                                   "Compressed (24-Bit)")[self.dataType]
        return 1

    def writeHeader(self, fp):
        "Write an LCheapo disk header (packed big endian format)."
        fp.write(struct.pack('>LHLH', self.writeBlock, self.writeByte,
                             self.readBlock, self.readByte))
        fp.write(struct.pack('>4L', self.dirStart, self.dirSize, self.dirBlock,
                             self.dirCount))
        fp.write(struct.pack('>4L', self.slowStart, self.slowSize,
                             self.slowBlock, self.slowByte))
        fp.write(struct.pack('>4L', self.logStart, self.logSize,
                             self.logBlock, self.logByte))
        fp.write(struct.pack('>LH', self.dataStart, self.diskNumber))
        fp.write(struct.pack('>10s80s',
                             _cstr_from_str(self.softwareVersion),
                             _cstr_from_str(self.description)))
        fp.write(struct.pack('>3H', self.sampleRate, self.startChannel,
                             self.numberOfChannels))
        fp.write(struct.pack('>3H', self.slowDataRate, self.slowStartChannel,
                             self.slowNumberOfChannels))
        fp.write(struct.pack('>4H', self.dataType, self.diskSize,
                             self.ramSize, self.numberOfWindows))

    def printHeader(self):
        "Print the disk header information."
        print("\n\n")
        print("===========================")
        print("Disk Header")
        print("===========================\n")
        print("Field Name                 Contents")
        print("----------                 --------")
        f_int = "{:22s} {:12d} ({})"
        f_str = "{:35s} {}"
        print(f_int.format("Write Block", self.writeBlock,
                           "Next block to write"))
        print(f_int.format("Write Byte", self.writeByte, "Next byte to write"))
        print(f_int.format("Read Block", self.readBlock, "Unused"))
        print(f_int.format("Read Byte ", self.readByte, "Unused"))

        print("\n==== Dir Info ====")
        print(f_int.format("Dir Start", self.dirStart, "Dir start block"))
        print(f_int.format("Dir Size ", self.dirSize, "Max Dir entries"))
        print(f_int.format("Dir Block", self.dirBlock, "Next Dir block"))
        print(f_int.format("Dir Count", self.dirCount, "Total Dir entries"))

        print("\n==== Slow Data Storage ====")
        print(f_int.format("Slow Start", self.slowStart,
                           "Slow data start block)"))
        print(f_int.format("Slow Size ", self.slowSize,
                           "Slow data size in blocks"))
        print(f_int.format("Slow Block", self.slowBlock,
                           "Next block number to write"))
        print(f_int.format("Slow Byte ", self.slowByte,
                           "Next byte number to write"))

        print("\n==== Log Data Info ====")
        print(f_int.format("Log Start", self.logStart, "Log data start block"))
        print(f_int.format("Log Size ", self.logSize,  "Log size in blocks"))
        print(f_int.format("Log Block", self.logBlock,
                           "Next block number to write"))
        print(f_int.format("Log Byte ", self.logByte,
                           "Next byte number to write"))

        print("\n==== General Information ====")
        print(f_int.format("Data Start ", self.dataStart,
                           "Normal data start block"))
        print(f_int.format("Disk Number", self.diskNumber, ""))
        print(f_str.format("Software Version", self.softwareVersion))
        print(f_str.format("Description", self.description))
        print("{:22s} {:12.2f} Hz (written as {:d} Hz)".format(
            "Sample Rate", self.realSampleRate, self.sampleRate))
        print(f_int.format("Start Channel       ", self.startChannel, ""))
        print(f_int.format("Number Of Channels  ", self.numberOfChannels, ""))
        print(f_int.format("Slow Data Rate      ", self.slowDataRate,
                           "Unused"))
        print(f_int.format("Slow Start Channel  ", self.slowStartChannel,
                           "Unused"))
        print(f_int.format("Slow Num Of Channels", self.slowNumberOfChannels,
                           "Unused"))

        # Determine data type
        print(f_int.format("Data Type", self.dataType, self.dataTypeString))
        print(f_int.format("Disk Size", self.diskSize, "GB"))
        print(f_int.format("RAM Size ", self.ramSize, "MB"))
        print(f_int.format("Number Of windows", self.numberOfWindows,
                           "Unused"))


class LCDirEntry (LCCommon):
    """
    LCheapo Directory single-entry class
    """
    def __init__(self):
        pass

    def readDirEntry(self, fp):
        """
        Read an LCheapo directory entry (packed big endian format)
        """
        (self.msec, self.second, self.minute, self.hour, self.day,
         self.month, self.year) = struct.unpack('>HBBBBBB', fp.read(8))
        (self.blockNumber, self.recordLength, self.sampleRate,
         self.numBlocks) = struct.unpack('>2L2H', fp.read(12))
        (self.flag, self.muxChannel) = struct.unpack('>2B', fp.read(2))
        self.U1 = struct.unpack('>10B', fp.read(10))  # Unused

    def writeDirEntry(self, fp):
        """
        Write an LCheapo directory entry (packed big endian format)
        """
        timeData = struct.pack('>HBBBBBB', self.msec, self.second,
                               self.minute, self.hour, self.day,
                               self.month, self.year)
        flagData = struct.pack('>2L2H2B', self.blockNumber,
                               self.recordLength, self.sampleRate,
                               self.numBlocks, self.flag, self.muxChannel)
        # self.U1 doesn't work?
        uData = struct.pack('>10B', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        fp.write(timeData)
        fp.write(flagData)
        fp.write(uData)

    def __str__(self):
        """
        Create directory entry string (short format)
        """
        str_a = "{:26s} Ch:{:02d} {:7.2f}Hz     ".format(
            str(self.getDateTime()),
            self.muxChannel,
            self.getRealSampleRate(self.sampleRate))
        str_b = "{:12d} {:12d} {:12d} Flg:0x{:02x}".format(
            self.blockNumber,
            self.numBlocks,
            self.recordLength,
            self.flag)
        return str_a + str_b


class LCDataBlock (LCCommon):
    "LCheapo data block class"
    def __init__(self):
        pass

    def readBlock(self, fp):
        "Read a block of LCheapo data from the specified pointer."
        (self.msec, self.second, self.minute, self.hour, self.day,
         self.month, self.year) = struct.unpack('>HBBBBBB', fp.read(8))
        (self.blockFlag, self.muxChannel, self.numberOfSamples) =\
            struct.unpack('>BBH', fp.read(4))
        # U1=Flag=3 & U2=SampleCount=166
        (self.U1, self.U2) = struct.unpack('>BB', fp.read(2))
        self.data = fp.read(498)

    def writeBlock(self, fp):
        "Write a block of LCheapo data to the specified pointer."
        timeData = struct.pack('>HBBBBBB', self.msec, self.second,
                               self.minute, self.hour, self.day, self.month,
                               self.year)
        flagData = struct.pack('>BBH', self.blockFlag, self.muxChannel,
                               self.numberOfSamples)
        uData = struct.pack('>BB', self.U1, self.U2)
        fp.write(timeData)
        fp.write(flagData)
        fp.write(uData)
        fp.write(self.data)

    def printHexDumpOfHeader(self, annotated=False):
        "Print out the data header in hexidecimal format."
        if annotated:
            fmt = "ms:{:04x} s:{:02x} mn:{:02x} hr:{:02x} dy:{:02x} " +\
                  "mo:{:02x} yr:{:02x} Flag:{:02x} Chan:{:02x} Samples:{:04x}"
        else:
            fmt = "{:04x}{:02x}{:02x} {:02x}{:02x}{:02x}{:02x} %02x%02x%04x"
        print(fmt.format(self.msec, self.second, self.minute, self.hour,
                         self.day, self.month, self.year, self.blockFlag,
                         self.muxChannel, self.numberOfSamples))

    def printDecimalDumpOfHeader(self, annotated=False):
        "Print out the data header in decimal format."
        if annotated:
            fmt = "ms:{:4d} s:{:02d} mn:{:02d} hr:{:02d} dy:{:02d} " +\
                  "mo:{:02d} yr:{:02d} Flag:{:03d} Chan:{:02d} Samples:{:4d}"
        else:
            fmt = "{:4d} {:02d} {:02d} {:02d} {:02d} {:02d} {:02d} " +\
                  "{:03d} {:02d} {:4d}"
        print(fmt.format(self.msec, self.second, self.minute, self.hour,
                         self.day, self.month, self.year, self.blockFlag,
                         self.muxChannel, self.numberOfSamples))

    def prettyPrintHeader(self, annotated=False):
        "Print out the data header in pretty format."
        if annotated:
            fmt = "DateTime:{:02d}/{:02d}/{:02d}-{:02d}:{:02d}:{:02d}." +\
                  "{:03d} Flag:{:03d} Chan:{:02d} Samples:{:4d} " +\
                  "U1:{:03d} U2:{:03d}"
        else:
            fmt = "{:02d}/{:02d}/{:02d}-{:02d}:{:02d}:{:02d}.{:03d}" +\
                  "  F{:03d} CH{:02d} {:4d} samps U1={:03d} U2={:03d}"
        print(fmt.format(self.year, self.month, self.day, self.hour,
                         self.minute, self.second, self.msec,
                         self.blockFlag, self.muxChannel,
                         self.numberOfSamples, self.U1, self.U2))

    def convertDataTo24BitValues(self):
        "Convert the data block into a list of 24-bit values."
        data = [x * (1 << 16) + y * (1 << 8) + z
                for x, y, z in [struct.unpack(">bBB", self.data[x:x + 3])
                                for x in range(0, 498, 3)]]
        return data

    def printHexDumpOfData(self):
        "Print out the data block in hexidecimal format."
        count = 0
        for i in struct.unpack(">498B", self.data):
            sys.stdout.write("{:02x}".format(i))
            count += 1
            if count % 3 == 0:
                sys.stdout.write("  ")
            if count % 30 == 0:
                sys.stdout.write("\n")
        sys.stdout.write("\n")

    def printDecimalDumpOfData(self):
        "Print out the data block in decimal format."
        count = 0
        data = self.convertDataTo24BitValues()
        for i in data:
            sys.stdout.write("{:8d} ".format(i))
            count += 1
            if count % 8 == 0:
                sys.stdout.write("\n")
        sys.stdout.write("\n")

    def __str__(self):
        ch_str = "CH:{:d}".format(self.muxChannel)
        samp_str = "Samples:%3d".format(self.numberOfSamples)
        date_fmt = "Date:{:02d}-{:02d}-{:02d} {:02d}:{:02d}:{02d}.{:04d}"
        date_str = date_fmt.format(self.year, self.month, self.day, self.hour,
                                   self.minute, self.second, self.msec)
        return "{}  {}  {}".format(ch_str, samp_str, date_str)


def _str_from_cstr(cstr):
    """
    Convert a C string to Python
    """
    try:
        return cstr.decode("utf-8").split('\0')[0]
    except Exception:
        return None


def _cstr_from_str(str):
    """
    Convert a Python str to C string
    """
    # return str.encode("utf-8") + b'\0' Removed for comparison test
    return str.encode("utf-8")


def main():
    "Main Program"
    print("lcheapo.py is not a runnable program.")
    return 0


# Run 'main' if the script is not imported as a module)
if __name__ == '__main__':
    main()
