#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix errors and signal time tears in lcheapo files:
  1: Isolated one second time tag offsets.
  2: Isolated bad time tags
  3: Bad n_blocks in directory entry (says 16384 but is 14336)
"""
import sys
import argparse
import queue
import os
import textwrap
import logging      # for logging information
from datetime import timedelta
from pathlib import Path

from lcheapo_utils import (LCDataBlock, LCDiskHeader, LCDirEntry)
from sdpchain import ProcessStep
from version import __version__

# ------------------------------------
# Global Variable Declarations
# ------------------------------------
warnings = 0  # count # of warnings


class BugCounters():
    """
    lcfix bug counters:
        BUG1: 1-second errors in time tag_regexp
        BUG2: Other isoluated errors in time tag_reg
        BUG3: Incorrect directory entry length
        bad_hdr: unexpected header value
        Time Tear: Bug1 or Bug2 for more than two consecutive samples, must
                   be manually repaired
    """
    def __init__(self):
        self.bug1 = 0
        self.bug2 = 0
        self.bug3 = 0
        self.time_tear = 0
        self.bad_hdr = 0

    def __str__(self):
        s = f"{self.bug1:d} BUG1s, "
        s += f"{self.bug2:d} BUG2s, "
        s += f"{self.bug3:d} BUG3s, "
        s += f"{self.time_tear:d} Time Tears, "
        s += f"{self.bad_hdr:d} unexpected header values"
        return s

    def __add__(self, other):
        assert isinstance(other, BugCounters)
        out = BugCounters()
        out.bug1 = self.bug1 + other.bug1
        out.bug2 = self.bug2 + other.bug2
        out.bug3 = self.bug3 + other.bug3
        out.time_tear = self.time_tear + other.time_tear
        out.bad_hdr = self.bad_hdr + other.bad_hdr
        return out

    def __iadd__(self, other):
        assert isinstance(other, BugCounters)
        self.bug1 += other.bug1
        self.bug2 += other.bug2
        self.bug3 += other.bug3
        self.time_tear += other.time_tear
        self.bad_hdr += other.bad_hdr
        return self

    def bug_info_str(self):
        lines = []
        if self.bug1 > 0:
            lines.append("BUG1= 1-second errors in time tag")
        if self.bug2 > 0:
            lines.append("BUG2= Other isolated errors in time tag")
        if self.bug3 > 0:
            lines.append("BUG3= Incorrect entry length in directory")
        if self.time_tear > 0:
            lines.append("Time Tear=Bad time tag (BUG1 or BUG2) for more than "
                         "two consecutive samples. Could be a long")
            lines.append("            stretch of bad records or an offset in "
                         "records. MUST BE REPAIRED")
        return "\n".join(lines)


def main():
    global warnings
    # Prepare variables
    counters = BugCounters()
    n_files = 0
    msgs = []
    outFiles = []
    # lcData = LCDataBlock()

    # GET ARGUMENTS
    args = _get_options()
    commandQ = queue.Queue(0)
    responseQ = queue.Queue(0)

    out_filename_root = args.input_files[0].split('.')[0]
    _make_logger(os.path.join(args.out_dir, out_filename_root + '.fix.txt'))
    if args.dryrun:
        logging.info("DRY RUN: will not output a new file")
        if args.forceTime:
            logging.info("-F (forceTimes) IGNORED during dry run")
            args.forceTime = False

    # IF THERE IS A FILE WITH '.header.', PUT IT AT THE BEGINNING OF THE LIST
    for f in args.input_files:
        if '.header.' in f:
            args.input_files.remove(f)
            args.input_files.insert(0, f)
            break

    # LOOP THROUGH INPUT FILES
    numInFiles = len(args.input_files)
    firstFile = True
    for fname in args.input_files:
        ifp1 = open(os.path.join(args.in_dir, fname), 'rb')

        # Find and copy the disk header
        if firstFile:    # First file, extract header
            lcHeader, firstInpBlock = __readLCHeader(ifp1)
            if args.verbosity:
                lcHeader.printHeader()
            # DO NOT TRY TO READ DATA IF FILE IS JUST A HEADER
            if '.header.' in fname:
                firstFile = False
                continue
        else:
            firstInpBlock = 0      # dataBlocks will start at the beginning
            lcHeader.dirCount = 0  # No header, so no directory entries

        logging.info('='*14 + " PROCESSING FILE {} ".format(fname) + "="*13)

        # Determine last file block
        ifp1.seek(0, 2)                # Seek end of file
        lastInpBlock = int(ifp1.tell() / 512) - 1

        if lastInpBlock <= firstInpBlock + 4:
            print("No data, skipping file")
            firstFile = False
            continue

        if __stopProcess(commandQ):
            return

        # Adjust first block to correspond to first block with channel 0
        firstInpBlock = __findFirstMux0Block(firstInpBlock, ifp1)

        outFileRoot = __makeOutFileRoot(args.out_dir, fname, numInFiles,
                                        ifp1, firstInpBlock)

        # Process file
        (loopcounters, msg, ofname) = _process_input_file(
            ifp1, fname, outFileRoot, lcHeader, firstInpBlock,
            lastInpBlock, firstFile, args, commandQ, responseQ)
        ifp1.close()

        # Update counters
        counters += loopcounters
        n_files += 1
        msgs.append(msg)
        outFiles.append(ofname)

        firstFile = False
        # END OF INPUT FILES LOOP
    _print_final_message(args.forceTime, counters, n_files)

    exit_status = 0
    if not args.dryrun:
        if counters.time_tear:
            exit_status = -1
        elif not warnings == 0:
            exit_status = 2

        global process_step
        process_step.messages = msgs
        process_step.exit_status = exit_status
        process_step.output_files = [Path(x).name for x in outFiles]
        process_step.write(args.in_dir, args.out_dir)

    sys.exit(exit_status)


def _get_options():
    """
    Parse user passed options and parameters.
    """
    epi_text = textwrap.dedent("""\
    Outputs (for input filename root.*):
      - root.fix.lch: fixed data
      - root.fix.txt: text on bugs found and fixes applied
      - (root.fix.timetears.txt): list of time tears
    Notes:
      - TIME TEARS MUST BE ELIMINATED BEFORE FURTHER PROCESSING!!!
    Recommendations:
      - Name your inputfile STA.raw.lch, where STA is the station name
      - Run "%(prog)s -v --dryrun" on the fixed file to verify that no errors
        remain.
    Example:
      - for an LCHEAPO file named RR38.lch:
        > %(prog)s RR38.raw.lch
        > %(prog)s -v --dryrun RR38.fix.lch
    """)
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=epi_text,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_files", metavar="inFileName", nargs='+',
                        help="Input filename(s).  If there are captured "
                             "wildcards (put in '' so that they aren't "
                             "interpreted by the shell), will expand them "
                             "in the input directory")
    parser.add_argument("--version", action='version',
                        version='%(prog)s {:s}'.format(__version__))
    parser.add_argument("-v", "--verbose", dest="verbosity", default=0,
                        action="count",
                        help="be verbose (-v = kind of, -vv = very)")
    parser.add_argument("--dryrun", dest="dryrun", default=False,
                        action="store_true",
                        help="do not output fixed LCHEAPO file")
    parser.add_argument("-d", dest="base_dir", metavar="BASE_DIR",
                        default='.', help="base directory for files")
    parser.add_argument("-i", dest="in_dir", metavar="IN_DIR", default='.',
                        help="input file directory (absolute, " +
                             "or relative to base_dir)")
    parser.add_argument("-o", dest="out_dir", metavar="OUT_DIR", default='.',
                        help="output file directory (absolute, " +
                             "or relative to base_dir)")
    parser.add_argument("-F", "--forceTimes", dest="forceTime", default=False,
                        action="store_true",
                        help="Force timetags to be consecutive")
    args = parser.parse_args()
    global process_step
    process_step = ProcessStep(
        'lcfix',
        " ".join(sys.argv),
        app_description='Fix common bugs in LCHEAPO data files',
        app_version=__version__,
        parameters=args)
    args.in_dir, args.out_dir, args.input_files = ProcessStep.setup_paths(args)
    return args


def getTimeDelta(seconds=0.):
    """
    Convert seconds to a timedelta() object

    :param seconds: the number of seconds
    :type  seconds: float
    :return: timedelta
    :rtype:  class datetime.timedelta
    """
    days = int(seconds / 86400)
    seconds -= days * 86400
    hours = int(seconds / 3600)
    seconds -= hours * 3600
    minutes = int(seconds/60)
    seconds -= minutes * 60
    int_secs = int(seconds)
    seconds -= int_secs
    msec = int(seconds * 1000)
    return timedelta(days=days, hours=hours, minutes=minutes,
                     seconds=seconds, milliseconds=msec)


def _to_msec(tm):
    """
    Return the number of milliseconds corresponding to a timedelta object

    :param tm: timedelta
    :type  tm: class datetime.timedelta
    :return: milliseconds
    :rtype: int
    """
    return 1000 * ((tm.days * 86400) + tm.seconds) + \
        int(tm.microseconds / 1000.)


def __stopProcess(commandQ):
    global warnings
    if not commandQ:
        return False
    try:
        if commandQ.get(0) == "Stop":
            logging.warning("RECEIVED 'STOP' MESSAGE")
            warnings += 1
            return True
    except queue.Empty:
        pass
    return False


def __endBUG1A(startBlock, endBlock):
    global startBUG1A
    if startBUG1A >= 0:
        logging.info("{:8d}:  End LCHEAPO BUG #3 (started at {:d})".format(
                     endBlock, startBlock))
        global printHeader
        startBUG1A = -1
        printHeader = ''


def _print_final_message(forceTime, counters, n_files):
    logging.info(97*"=")
    if not forceTime:  # Standard case
        logging.info(f"Overall: {n_files:d} files, " + str(counters))
        logging.info("  " + counters.bug_info_str())

    # Make error message (and return code) if there are time tears
        if counters.time_tear > 0:
            logging.warning(82*"!")
            txt = "YOU HAVE {:d} TIME TEARS: YOU MUST ELIMINATE THEM " +\
                  "BEFORE CONTINUING!!!"
            logging.warning(txt.format(counters.time_tear))
            txt = 'Use "lcdump.py OBSfile.*.lch STARTBLOCK NUMBLOCKS" ' +\
                  'to look at suspect sections'
            logging.warning(txt)
            logging.warning(82*"!")
    else:  # Forced time corrections
        logging.warning("FORCED TIME CORRECTIONS, NO EVALUATION OF BUG1/2s")
        txt = "  Overall totals: {:d} files, {:d} forced corrections," +\
            " {:d} unexpected header values"
        logging.warning(txt.format(n_files, counters.time_tear,
                                   counters.bad_hdr))


def __findFirstMux0Block(firstBlock, ifp1):
    """
    Find the first 0-channel block
    """
    lcData = LCDataBlock()
    lcData.seekBlock(ifp1, firstBlock)
    lcData.readBlock(ifp1)
    i = 0
    while lcData.muxChannel != 0:
        i += 1
        lcData.readBlock(ifp1)
    return firstBlock + i


def __readLCHeader(ifp1):
    lcHeader = LCDiskHeader()
    lcHeader.seekHeaderPosition(ifp1)
    lcHeader.readHeader(ifp1)
    # firstInpBlock = lcHeader.dataStart
    return (lcHeader, lcHeader.dataStart)


def __makeOutFileRoot(outfile_path, infname, numInFiles, ifp1, firstBlock):
    """
    Create the root of the output filename

    If the user specified one, use it
    If not, use the part of the input filename before the first '.'
    If there are multiple input files, append the data start time to the root
    """
    outFileRoot = os.path.join(outfile_path, infname.split('.')[0])
    if numInFiles > 1:
        # Add first time to outfile name
        lcData = LCDataBlock()
        # Step back one so that next read will be here
        lcData.seekBlock(ifp1, firstBlock)
        lcData.readBlock(ifp1)    # Read next block
        t = lcData.getDateTime()
        timestring = t.strftime("%Y%m%dT%H%M%S")
        outFileRoot += '_' + timestring
    return outFileRoot


def _make_logger(fname):
    """
    Create a logger instance

    Allows one to send outputs to a file and to stdout, plus handle debugging
    """
    # First create the file logger
    logging.basicConfig(filename=fname, filemode='w',
                        level=logging.INFO,
                        format='%(levelname)s %(message)s')
    # now the stdout logger
    sth = logging.StreamHandler(sys.stdout)
    sth.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    sth.setLevel(logging.DEBUG)
    # now add the stdout handler to the original
    logging.getLogger().addHandler(sth)


def verify_non_time_header_values(lcData, n_bad_hdr, printHeader,
                                  currBlock):
    if ((lcData.blockFlag != 73) | (lcData.numberOfSamples != 166) |
            (lcData.U1 != 3) | (lcData.U2 != 166)):
        if (n_bad_hdr < 100):
            logging.info("{}{:8d}: Unexpected non-time header values:".format(
                printHeader, currBlock))
            lcData.prettyPrintHeader(True)
        elif (n_bad_hdr == 100):
            logging.info("{}{:8d}: >100 Unexpected non-time headers:".format(
                printHeader, currBlock))
            logging.info("    WON'T PRINT ANY MORE!")
        n_bad_hdr += 1
    return n_bad_hdr


def verify_channel_number(mux_channel, num_channels, prev_mux_chan,
                          warnings, printHeaer, currBlock):
    if prev_mux_chan != -1:
        predictedChannel = prev_mux_chan + 1
        if predictedChannel >= num_channels:
            predictedChannel = 0
        if mux_channel != predictedChannel:
            if ((mux_channel >= num_channels) | (mux_channel < 0)):
                txt = "{}{:8d}: WARNING: Channel = {:d} IS IMPOSSIBLE, " +\
                    "setting to predicted {:d}"
                logging.warning(txt.format(printHeader, currBlock,
                                           mux_channel, predictedChannel))
                mux_channel = predictedChannel
            else:
                txt = "{}{:8d}: WARNING: Channel = {:d}, predicted was {:d}"
                logging.warning(txt.format(printHeader, currBlock,
                                           mux_channel, predictedChannel))
            warnings += 1
    return mux_channel, warnings


def _process_input_file(ifp1, fname, outFileRoot, lcHeader,
                        firstInpBlock, lastInpBlock, hasHeader, args,
                        commandQ=None, responseQ=None, debug=False):
    """
    Process one LCHEAPO file

    :param ifp1: input file pointer
    :type  ifp1: file object
    :param fname: input file name (without path)
    :type  fname: string
    :param outFileRoot: base output file name (with path)
    :type  outFileRoot: string
    :param lcHeader: header taken from the first input file
    :type  lcHeader: :class: `lcheapo:lcHeader`
    :param firstInpBlock: First block with channel 0 data
    :type  firstInpBlock: integer
    :param lastInpBlock: Last block number in the input file
    :type  lastInpBlock: integer
    :param hasHeader: Does the input file have a header?
    :type  hasHeader: boolean
    :param args: command line arguments
    :type  args: :class: `argparse.Namespace`
    :param commandQ: something to do with elegant quitting?
    :type  commandQ: :class: Queue.Queue
    :param responseQ: something to do with elegant quitting?
    :type  responseQ: :class: Queue.Queue
    :param debug: Print out debugging information?
    :type  debug: boolean
    :return: counters, message, fname_timetears
    :rtype: `tuple`
    """
    # Declare variables
    global startBUG1A, printHeader, lcDir, warnings
    i = 0
    counters = BugCounters()
    lastBUG1s = [0, 0, 0, 0]
    printHeader = ''
    startBUG1A = -1
    prev_mux_chan = -1
    # prev_block_flag = 73
    # prev_num_samps = 166
    # prev_U1 = 3
    # prev_U2 = 166
    verbosity = args.verbosity
    consecIdentTimeErrors, oldDiff = 0, 0
    lcData = LCDataBlock()

    if not args.dryrun:
        outfilename = outFileRoot + ".fix.lch"
        if os.path.exists(outfilename):
            print(f"output file {outfilename} exists already! Quitting")
            sys.exit(2)
        ofp1 = open(outfilename, 'wb')
    fname_timetears = outFileRoot + '.fix.timetears.txt'
    oftt = open(fname_timetears, 'w')

    # -----------------------------
    # Copy the disk header to the output file
    # -----------------------------
    if not args.dryrun:
        lcHeader.seekHeaderPosition(ofp1)
        lcHeader.writeHeader(ofp1)
    if __stopProcess(commandQ):
        return

    blockTime = int((166 * (1.0 / lcHeader.realSampleRate)) * 1000)
    blockTimeDelta = t = timedelta(0, 0, 0, blockTime, 0, 0)

    # -----------------------------
    # Grab the first time entries (one for each channel) and adjust them
    # so that they point an entire blockTimeDelta in the past.  This is done to
    # "prime the pump" so that we can add in the blockTimeDelta the first time
    # we use it.
    # -----------------------------
    lcData.seekBlock(ifp1, firstInpBlock)
    lastTime = []
    for i in range(0, lcHeader.numberOfChannels):
        lcData.readBlock(ifp1)
        lastTime.append(lcData.getDateTime() - blockTimeDelta)

    ifp1.seek(0, 2)  # Go to the end
    # lastAddress = ifp1.tell()
    # Back up to data start block
    lcData.seekBlock(ifp1, firstInpBlock)
    if not args.dryrun:
        if hasHeader:
            lcData.seekBlock(ofp1, firstInpBlock)
        else:
            lcData.seekBlock(ofp1, lcHeader.dataStart)

    logging.info("  data Blocks: first={:d}, last={:d}".format(
                 firstInpBlock, lastInpBlock))
    logging.info("  PROCESSING FILE")
    if debug:
        logging.info("  DEBUGGING")

    # Loop over blocks, comparing expected and actual times.
    for i in range(firstInpBlock, lastInpBlock+1):
        if debug and (i > lastInpBlock-10):
            logging.info("  BLOCK {:d}".format(i))
        lcData.readBlock(ifp1)
        if debug and (i > lastInpBlock - 10):
            logging.info("  READ")
        currBlock = int(ifp1.tell() / 512) - 1
        if startBUG1A >= 0 and currBlock > (lastBUG1s[0] + 500):
            __endBUG1A(startBUG1A, currBlock)
        if i != currBlock:
            raise ValueError(
                f"Current Block ({currBlock:d}) != expected ({i:d})")
        if verbosity > 1:  # Very verbose, print each block header
            logging.info("{:8d}({:d}): ".format(i, ifp1.tell()))
            lcData.prettyPrintHeader()
        # VERIFY NON-TIME HEADER VALUES ############
        counters.bad_hdr = verify_non_time_header_values(
            lcData, counters.bad_hdr, printHeader, currBlock)
        # VERIFY CHANNEL NUMBER ############
        lcData.muxChannel, warnings = verify_channel_number(
            lcData.muxChannel, lcHeader.numberOfChannels,
            prev_mux_chan, warnings, printHeader, currBlock)
        # Handle bad chan numbers without crashing
        # iCh = lcData.muxChannel % lcHeader.numberOfChannels
        expect_time = lastTime[lcData.muxChannel] + blockTimeDelta
        t = lcData.getDateTime()
        diff = abs(_to_msec(t - expect_time))
        if diff:
            if args.forceTime or (i > lastInpBlock
                                  - (3*lcHeader.numberOfChannels)):
                # FORCE TIME TO BE WHAT WE EXPECT
                if (consecIdentTimeErrors > 0) & (diff != oldDiff):
                    # Starting a new time offset
                    logging.info("{:d} blocks".format(
                        consecIdentTimeErrors))
                    consecIdentTimeErrors = 0

                if consecIdentTimeErrors == 0:
                    # New time error or error offset
                    txt = "{}{:8d}:  CH{:d}: {:g}s offset" +\
                          " FORCED to conform..."
                    forceTimeErrorStr = txt.format(printHeader, currBlock,
                                                   lcData.muxChannel,
                                                   diff/1000.)
                    if not args.forceTime:
                        forceTimeErrorStr += " BECAUSE NEAR END OF FILE"
                t = expect_time
                lcData.changeTime(t)
                if args.forceTime:
                    counters.time_tear += 1
                consecIdentTimeErrors += 1  # Only used for forceTime
                oldDiff = diff
            else:
                if diff > 1100:
                    # Difference greater than 1 second, could be a time
                    # tear or an isolated bad entry (bug #2)
                    # See if following blocks have the expected time
                    pos = ifp1.tell()
                    channel = lcData.muxChannel
                    nextTime = _get_next_time(ifp1, channel, pos)
                    tempDiff = abs(_to_msec(nextTime - expect_time))
                    if (tempDiff - 2*_to_msec(blockTimeDelta) < 2):
                        _log_error_2("2", printHeader, currBlock,
                                     lcData.muxChannel, expect_time,
                                     t)
                        counters.bug2 += 1
                        t = expect_time
                        lcData.changeTime(t)
                    else:
                        # Check TWO blocks ahead with the same channel
                        nextTime = _get_next_time(ifp1, channel, pos)
                        tempDiff = abs(_to_msec(nextTime -
                                                expect_time))
                        if (tempDiff - 3*_to_msec(blockTimeDelta) < 2):
                            _log_error_2("2b", printHeader, currBlock,
                                         lcData.muxChannel,
                                         expect_time, t)
                            counters.bug2 += 1
                            t = expect_time
                            lcData.changeTime(t)
                        else:
                            # Check THREE blocks ahead, same channel
                            nextTime = _get_next_time(ifp1, channel,
                                                      pos)
                            tempDiff = abs(_to_msec(nextTime -
                                                    expect_time))
                            if (tempDiff - 4*_to_msec(blockTimeDelta)
                                    < 2):
                                # LCHEAPO BUG 2C
                                _log_error_2("2c",
                                             printHeader,
                                             currBlock,
                                             lcData.muxChannel,
                                             expect_time,
                                             t)
                                counters.bug2 += 1
                                t = expect_time
                                lcData.changeTime(t)
                            else:
                                # Time tear (do not fix it!)
                                fmt = "{:8d}: Time Tear in Data.   " +\
                                      "CH{:d} Expected Time: {}, " +\
                                      "Got: {}"
                                txt = fmt.format(currBlock,
                                                 lcData.muxChannel,
                                                 expect_time, t)
                                logging.warning(printHeader + txt)
                                warnings += 1
                                print(printHeader + txt, file=oftt)
                                counters.time_tear += 1
                    # Go back to original position
                    ifp1.seek(pos)
                    # End if diff > 1100:
                else:
                    # LCHEAPO BUG - A second is dropped (then recovered)
                    if lastBUG1s[0] == currBlock - 500:
                        if startBUG1A < 0:
                            txt = "{}{:8d}: LCHEAPO BUG #1a. BUG #1s " +\
                                  "repeating at 500-block intervals"
                            logging.info(txt.format(printHeader,
                                                    currBlock))
                            startBUG1A = currBlock
                            printHeader = '      '
                    else:
                        txt = "{}{:8d}: LCHEAPO BUG #1. CH{:d} " +\
                              "Expected Time: {}, Got: {} "
                        logging.info(
                            txt.format(printHeader, currBlock,
                                       lcData.muxChannel, expect_time, t))
                    counters.bug1 += 1
                    t = expect_time
                    lcData.changeTime(t)
                    # FIFO: remove 1st elem & add new last
                    lastBUG1s.pop(0)
                    lastBUG1s.append(currBlock)
        else:
            if args.forceTime and (consecIdentTimeErrors > 0):
                logging.info(forceTimeErrorStr +
                             "{:d} blocks".format(consecIdentTimeErrors))
                consecIdentTimeErrors = 0
        # Write out the block of data and report status (if necessary)
        if not args.dryrun:
            lcData.writeBlock(ofp1)
        if (i % 5000 == 0):
            if __stopProcess(commandQ):
                return
            if responseQ:
                responseQ.put((i, lastInpBlock, counters.bug1,
                               counters.time_tear))

        # Handle bad muxChannel numbers without crashing
        # iCh = lcData.muxChannel % lcHeader.numberOfChannels
        lastTime[lcData.muxChannel] = t
        prev_mux_chan = lcData.muxChannel
        # prev_block_flag = lcData.blockFlag
        # prev_num_samps = lcData.numberOfSamples
        # prev_U1 = lcData.U1
        # prev_U2 = lcData.U2
    # END LOOP THROUGH EVERY BLOCK
    if responseQ:
        responseQ.put((i, lastInpBlock, counters.bug1, counters.time_tear))

    # ----------------------------------------------------------------------
    # Copy over the directory entries and modify the block time to correspond
    # to the actual time in the data block.
    # ----------------------------------------------------------------------

    # Open the output datafile for reading
    if not args.dryrun:
        ofp_data = open(outfilename, 'rb')  # generally the output file
    else:
        # if no output file, read block data from input file
        ofp_data = open(fname, 'rb')
    lcData2 = LCDataBlock()

    # Point input and output file ptrs to the directory
    # (reads one, updates the other?)
    if hasHeader:  # In input file
        lcDir = LCDirEntry()
        lcDir.seekBlock(ifp1, lcHeader.dirStart)
    if not args.dryrun:  # In output file
        lcDir.seekBlock(ofp1, lcHeader.dirStart)

    # Copy directory but change  time to correspond to that in the data block.
    # ifp1 points to the start of the input file's directory
    # ofp1 points to the start of the output file's directory
    # ofp_data points to the output file's data block.
    if verbosity:
        if hasHeader:
            logging.info("  COPYING/CORRECTING DIRECTORY")
        else:
            logging.info("  CREATING DIRECTORY")
        logging.info("   {:4s} | {:9s} | {:26s} | {:28s} | {}".format(
            "DIR#", "BLOCK#", "ORIG DIRTIME", "NEW DIRTIME (BLOCKTIME)",
            "DIFF (SECS)"))
        logging.info("   {:-<5s}|{:-<11s}|{:-<28s}|{:-<30s}|{:-<10s}".format(
                     "", "", "", "", ""))
    iDir = 0
    if hasHeader:
        lastOutBlock = lastInpBlock
    else:
        lastOutBlock = lastInpBlock + lcHeader.dataStart
    # LCHEAPO DIRECTORY ENTRIES ARE EVERY 14336 blocks BY DEFAULT
    DIRBLOCKS = 14336
    BAD_DIRBLOCKS = 16384
    # Loop through the directory
    while True:
        # If the input file had a directory, read in the next entry
        # (or add one if we're beyond original end)
        if hasHeader:
            if iDir < lcHeader.dirCount:
                lcDir.readDirEntry(ifp1)
                origDirTime = lcDir.getDateTime()
                if not lcDir.numBlocks == DIRBLOCKS:
                    if lcDir.numBlocks == BAD_DIRBLOCKS:
                        lcDir.numBlocks = DIRBLOCKS
                        counters.bug3 += 1
                    else:
                        fmt = "DIR{:10d}: Expected {:d} blocks, found {:d}"
                        logging.info(fmt.format(iDir, DIRBLOCKS,
                                                lcDir.numBlocks))
            else:
                nextDirBlock = lcDir.blockNumber + lcDir.numBlocks
                if iDir <= lcHeader.dirSize and nextDirBlock <= lastOutBlock:
                    # ADD DIRECTORY ENTRIES
                    lcDir.blockNumber += lcDir.numBlocks
                    origDirTime = 'None'
                else:
                    break
        # If it did not have a directory, make up the next entry
        else:
            lcDir.numBlocks = DIRBLOCKS
            nextDirBlock = lcHeader.dataStart + iDir * lcDir.numBlocks
            if iDir < lcHeader.dirSize and nextDirBlock <= lastOutBlock:
                lcDir.blockNumber = nextDirBlock
                origDirTime = 'None'
            else:
                break
        verboselogtext = "   {:4d} | {:9d} | {:26s} |".format(
            iDir + 1, lcDir.blockNumber, origDirTime)
        # Jump out if directory start block number is beyond end of file
        if lcDir.blockNumber > lastOutBlock:
            if verbosity:
                logging.info(verboselogtext)
            break

        # Put start time of block pointed to by the directory entry into the
        # directory entry
        # ofp_data has a header unless dryrun on a headerless file
        if hasHeader or not args.dryrun:
            lcData2.seekBlock(ofp_data, lcDir.blockNumber)
        else:  # ofp_data is headerless
            lcData2.seekBlock(ofp_data, lcDir.blockNumber - lcHeader.dataStart)
        lcData2.readBlock(ofp_data)
        blockTime = lcData2.getDateTime()
        if verbosity:
            if hasHeader:  # Compare directory times to block times
                diff = abs(_to_msec(blockTime - lcDir.getDateTime()))
                logging.info(verboselogtext + "   {:26s} | {:14.1f}".format(
                             str(blockTime), diff/1000))
            else:
                logging.info(verboselogtext + "   {:26s} | {:<14s}".format(
                             str(blockTime), "N/A"))
        lcDir.changeTime(blockTime)
        # If directory entry goes beyond end of data, write and break out
        if lcDir.blockNumber + lcDir.numBlocks >= lastOutBlock:
            lcDir.numBlocks = lastOutBlock - lcDir.blockNumber + 1
            if not args.dryrun:
                lcDir.writeDirEntry(ofp1)
            iDir += 1
            break
        if not args.dryrun:
            lcDir.writeDirEntry(ofp1)
        iDir += 1

    message = _print_blockloop_message(fname, outfilename, args.forceTime, i,
                                       counters)
    if iDir != lcHeader.dirCount:
        if hasHeader:
            if iDir < lcHeader.dirCount:
                txt = "\n  DIR{:d}, LAST BLOCK ({:d}) IS BEYOND THE " +\
                      "END OF FILE!"
                logging.info(txt.format(iDir + 1,
                                        lcDir.blockNumber + lcDir.numBlocks))
                txt = "  REDUCING NUMBER OF DIRECTORY ENTRIES IN HEADER " +\
                      "FROM {:d} TO {:d}"
                logging.info(txt.format(lcHeader.dirCount, iDir))
            else:
                txt = "\n  ADDED {:d} DIRECTORY ENTRIES TO COVER END OF DATA!"
                logging.info(txt.format(iDir - lcHeader.dirCount))
        else:
            logging.info("  {:d} DIRECTORY ENTRIES CREATED".format(iDir))
        if not args.dryrun:
            lcHeader.dirCount = iDir
            lcHeader.dirBlock = lcHeader.dirStart + int(iDir/16)
            lcHeader.seekHeaderPosition(ofp1)
            lcHeader.writeHeader(ofp1)
    if __stopProcess(commandQ):
        return

    # -----------------------
    # Close all the files
    # -----------------------
    if not args.dryrun:
        ofp1.close()
        ofp_data.close()
    oftt.close()

    # If there is no tear, remove the timetears file
    if counters.time_tear == 0:
        os.remove(fname_timetears)
    # Otherwise, if not forced time corrections, remove the output data file
    elif not args.forceTime:
        os.remove(outfilename)
        return counters, message, fname_timetears
    return counters, message, outfilename


def _log_error_2(type, printHeader, currBlock, chan, expect_time, t):
    # LCHEAPO BUG 2 - Isolated time tag error
    logging.info(
        "{}{:8d}: LCHEAPO BUG #{}.  CH{:d}  Expected Time: {}, Got: {}".
        format(printHeader, currBlock, type, chan, expect_time, t))


def _print_blockloop_message(fname, outfilename, forceTime, i,
                             counters):
    # Print out end-of-loop message for one file
    msg = "  {}=>{}: Finished at block {:d} ".format(
        fname, os.path.split(outfilename)[1], i)
    if forceTime:
        msg += f"({counters.time_tear:d} time errors FORCEABLY corrected)"
    else:
        msg += "(" + str(counters) + ")"
    logging.info(msg)
    return msg


def _get_next_time(ifp1, channel, pos):
    # Get the time at the next occurence of same channel
    tempData = LCDataBlock()
    tempData.readBlock(ifp1)
    while channel != tempData.muxChannel:
        tempData.readBlock(ifp1)
    tempTime = tempData.getDateTime()
    return tempTime


# ---------------------------------------------------------------------------
# Run 'main' if the script is not imported as a module
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    main()
