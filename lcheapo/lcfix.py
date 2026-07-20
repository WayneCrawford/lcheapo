#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix errors and signal time tears in lcheapo files:
  1: Isolated one second time tag offsets.
  2: Isolated bad time tags
  3: Bad n_blocks in directory entry (says 16384 but is 14336)

Optimized version requirements for LCDataBlock:
  - get_time_ms(): return integer milliseconds since 1970-01-01T00:00:00 UTC
  - change_time_ms(value): write that integer timestamp into the block header
"""
import sys
import argparse
import queue
import os
import textwrap
import logging      # for logging information
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from time import perf_counter

from obspy import UTCDateTime   # Added after the timedelta above, replace timedelta?
from sdpchainpy import ProcessStep
from progress.bar import IncrementalBar

from .lcheapo_utils import (LCDataBlock, LCDiskHeader, LCDirEntry)
# from .sdpchain import ProcessStep
from .version import __version__

# ------------------------------------
# Global Variable Declarations
# ------------------------------------
warnings = 0  # count # of warnings

# LCHEAPO records are fixed-size. Large buffered reads/writes reduce the
# number of calls into the operating system, while the progress interval
# avoids doing terminal bookkeeping for every 512-byte record.
BLOCK_SIZE = 512
FILE_BUFFER_SIZE = 1 * 1024 * 1024
PROGRESS_INTERVAL = 50_000
TIME_EPOCH = UTCDateTime(0)  # 1970-01-01T00:00:00 UTC


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
    """Command-line entry point, including optional local-output staging."""
    processing_start = perf_counter()
    args = _parse_arguments()
    final_out_dir = Path(args.out_dir).resolve()

    # A dry run creates only small report files, so local staging offers no
    # meaningful performance benefit.
    if args.local is None or args.dryrun:
        if args.local is not None and args.dryrun:
            print("NOTE: --local is ignored during --dryrun")
        exit_status, _, _, _ = _run_lcfix(args, final_out_dir)
        sys.exit(exit_status)

    local_parent = None
    if args.local:
        local_parent = Path(args.local).expanduser().resolve()
        local_parent.mkdir(parents=True, exist_ok=True)

    work_dir = Path(tempfile.mkdtemp(prefix="lcfix-", dir=local_parent))
    print(f"Using local working directory: {work_dir}")

    try:
        _check_local_space(args, work_dir)
        args.out_dir = str(work_dir)

        exit_status, out_files, messages, output_names = _run_lcfix(
            args,
            final_out_dir,
            write_process_step=False,
        )
        processing_elapsed = perf_counter() - processing_start
        print(f"Local processing completed in "
              f"{processing_elapsed:.1f} seconds"
              )
        # Close the file logger before copying its file.
        logging.shutdown()

        copy_start = perf_counter()
        copied_files = _copy_results_back(work_dir, final_out_dir)
        for copied_file in copied_files:
            print(f"Copied result to {copied_file}")
        copy_elapsed = perf_counter() - copy_start
        print(f"Copy-back completed in {copy_elapsed:.1f} seconds")

        # Restore the user-facing output directory before recording the
        # ProcessStep metadata, so it does not contain the temporary path.
        args.out_dir = str(final_out_dir)

        global process_step
        process_step.messages = messages
        process_step.exit_status = exit_status
        process_step.output_files = output_names
        process_step.write(args.in_dir, str(final_out_dir))

    except Exception:
        print(f"Local working files retained in {work_dir}", file=sys.stderr)
        raise
    else:
        if args.keep_local:
            print(f"Local working files retained in {work_dir}")
        else:
            shutil.rmtree(work_dir)

    sys.exit(exit_status)


def _run_lcfix(args, process_step_out_dir, write_process_step=True):
    """Run lcfix using the input and output directories stored in ``args``."""
    global warnings
    warnings = 0

    counters = BugCounters()
    n_files = 0
    msgs = []
    outFiles = []

    commandQ = queue.Queue(0)
    responseQ = queue.Queue(0)

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    out_filename_root = args.input_files[0].split('.')[0]
    _make_logger(os.path.join(args.out_dir, out_filename_root + '.fix.txt'))

    if args.dryrun:
        logging.info("DRY RUN: will not output a new file")
        if args.forceTime:
            logging.info("-F (forceTimes) IGNORED during dry run")
            args.forceTime = False

    # If a separate header file is present, process it first.
    for fname in list(args.input_files):
        if '.header.' in fname:
            args.input_files.remove(fname)
            args.input_files.insert(0, fname)
            break

    numInFiles = len(args.input_files)
    firstFile = True

    for fname in args.input_files:
        input_path = os.path.join(args.in_dir, fname)
        ifp1 = open(input_path, 'rb', buffering=FILE_BUFFER_SIZE)

        try:
            if firstFile:
                lcHeader, firstInpBlock = __readLCHeader(ifp1)
                if args.verbosity:
                    lcHeader.printHeader()
                if '.header.' in fname:
                    firstFile = False
                    continue
            else:
                firstInpBlock = 0
                lcHeader.dirCount = 0

            logging.info(
                '=' * 14 + f" PROCESSING FILE {fname} " + '=' * 13
            )

            ifp1.seek(0, 2)
            lastInpBlock = ifp1.tell() // BLOCK_SIZE - 1

            if lastInpBlock <= firstInpBlock + 4:
                print("No data, skipping file")
                firstFile = False
                continue

            if __stopProcess(commandQ):
                return 2, outFiles, msgs, [Path(x).name for x in outFiles]

            firstInpBlock = __findFirstMux0Block(firstInpBlock, ifp1)

            outFileRoot = __makeOutFileRoot(
                args.out_dir, fname, numInFiles, ifp1, firstInpBlock
            )

            loopcounters, new_msgs, ofname = _process_input_file(
                ifp1, fname, outFileRoot, lcHeader, firstInpBlock,
                lastInpBlock, firstFile, args, commandQ, responseQ
            )
        finally:
            ifp1.close()

        counters += loopcounters
        n_files += 1
        msgs.extend(new_msgs)
        outFiles.append(ofname)
        firstFile = False

    _print_final_message(args.forceTime, counters, n_files)

    exit_status = 0
    if not args.dryrun:
        if counters.time_tear:
            exit_status = -1
        elif warnings != 0:
            exit_status = 2

        output_names = [Path(x).name for x in outFiles]
        if write_process_step:
            global process_step
            process_step.messages = msgs
            process_step.exit_status = exit_status
            process_step.output_files = output_names
            process_step.write(args.in_dir, str(process_step_out_dir))
    else:
        output_names = []

    return exit_status, outFiles, msgs, output_names


def _check_local_space(args, work_dir):
    """Check that local storage can hold the expected output files."""
    required = 0
    for fname in args.input_files:
        if '.header.' not in fname:
            required += (Path(args.in_dir) / fname).stat().st_size

    # Output data is approximately the input size. Add 10 percent and 256 MiB
    # for reports, filesystem overhead, and safety margin.
    required = int(required * 1.10) + 256 * 1024 * 1024
    available = shutil.disk_usage(work_dir).free

    if available < required:
        raise OSError(
            "Insufficient local disk space: need approximately "
            f"{required / 1024**3:.1f} GiB, but only "
            f"{available / 1024**3:.1f} GiB is available in {work_dir}"
        )


def _copy_results_back(work_dir, final_out_dir):
    """Copy completed local files back without exposing partial results."""
    final_out_dir.mkdir(parents=True, exist_ok=True)
    copied = []

    for source in sorted(work_dir.iterdir()):
        if not source.is_file():
            continue

        destination = final_out_dir / source.name
        temporary_destination = destination.with_name(
            destination.name + ".lcfix-copying"
        )

        if destination.exists():
            raise FileExistsError(
                f"Final output file already exists: {destination}"
            )

        try:
            shutil.copy2(source, temporary_destination)
            os.replace(temporary_destination, destination)
        except Exception:
            temporary_destination.unlink(missing_ok=True)
            raise

        copied.append(destination)

    return copied


def _parse_arguments():
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
    parser.add_argument(
        "--local",
        nargs="?",
        const="",
        default=None,
        metavar="DIRECTORY",
        help=(
            "Write outputs on a local disk, then copy completed files back "
            "to OUT_DIR. If DIRECTORY is omitted, use the operating system's "
            "default temporary directory."
        ),
    )
    parser.add_argument(
        "--keep-local",
        action="store_true",
        help="Keep the local working directory after successful processing.",
    )
    parser.add_argument("-c", "--lccut", dest="lccut_file", default=False,
                        action="store_true",
                        help="generate an lccut script file if there are time"
                             "tears (USE ONLY IF ALL TIME TEARS ARE VERIFIED"
                             "TRUE HOLES IN THE DATA, NOT A CLOCK PROBLEM)")
    parser.add_argument("-F", "--forceTimes", dest="forceTime", default=False,
                        action="store_true",
                        help="Force timetags to be consecutive (USE ONLY IF"
                             "YOU HAVE TIME TEARS AND YOU ARE SURE THE DATA "
                             "ARE CONSECUTIVE)")
    parser.add_argument("-s", "--forceStartTime", dest="forceStartTime", default=None,
                        help="If forcing timetags to be consecutive, force "
                             "the first timetag to this value (yyyy-mm-ddTHH:MM:SS.FFF)")
    args = parser.parse_args()
    if args.keep_local and args.local is None:
        parser.error("--keep-local requires --local")
    global process_step
    process_step = ProcessStep(
        'lcfix',
        " ".join(sys.argv),
        app_description='Fix common bugs in LCHEAPO data files',
        app_version=__version__,
        parameters=args)
    args.in_dir, args.out_dir, args.input_files = ProcessStep.setup_paths(args)
    
    if args.forceStartTime is not None:
        if args.forceTime is not True:
            raise ValueError("Specified a forceStartTime without activating forceTimes")
        args.forceStartTime = UTCDateTime(args.forceStartTime)
        logging.warning(f"First data block's starttime will be forced to {args.forceStartTime.isoformat()}")
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
        print()  # Newline after progress bar
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
                                  curr_block):
    if ((lcData.blockFlag != 73) | (lcData.numberOfSamples != 166) |
            (lcData.U1 != 3) | (lcData.U2 != 166)):
        if (n_bad_hdr < 100):
            logging.info("{}{:8d}: Unexpected non-time header values:".format(
                printHeader, curr_block))
            lcData.prettyPrintHeader(True)
        elif (n_bad_hdr == 100):
            logging.info("{}{:8d}: >100 Unexpected non-time headers:".format(
                printHeader, curr_block))
            logging.info("    WON'T PRINT ANY MORE!")
        n_bad_hdr += 1
    return n_bad_hdr


def verify_channel_number(mux_channel, num_channels, prev_mux_chan,
                          warnings, printHeaer, curr_block):
    if prev_mux_chan != -1:
        predictedChannel = prev_mux_chan + 1
        if predictedChannel >= num_channels:
            predictedChannel = 0
        if mux_channel != predictedChannel:
            if ((mux_channel >= num_channels) | (mux_channel < 0)):
                txt = "{}{:8d}: WARNING: Channel = {:d} IS IMPOSSIBLE, " +\
                    "setting to predicted {:d}"
                logging.warning(txt.format(printHeader, curr_block,
                                           mux_channel, predictedChannel))
                mux_channel = predictedChannel
            else:
                txt = "{}{:8d}: WARNING: Channel = {:d}, predicted was {:d}"
                logging.warning(txt.format(printHeader, curr_block,
                                           mux_channel, predictedChannel))
            warnings += 1
    return mux_channel, warnings


def _process_input_file(ifp1, fname, outFileRoot, lcHeader,
                        firstInpBlock, lastInpBlock, hasHeader, args,
                        commandQ=None, responseQ=None, debug=False):
    """
    Process one LCHEAPO file

    Args:
        ifp1 (file object): input file pointer
        fname (str): input file name (without path)
        outFileRoot (str): base output file name (with path)
        lcHeader (class: `lcheapo:lcHeader`): header taken from the first
            input file
        firstInpBlock (int): First block with channel 0 data
        lastInpBlock (int): Last block number in the input file
        hasHeader (bool): Does the input file have a header?
        args (:class: `argparse.Namespace`): command line arguments
        commandQ (:class: `Queue.Queue`): something for elegant quitting?
        responseQ (:class: `Queue.Queue`): something for elegant quitting?
        debug (bool): Print out debugging information

    Returns:
        (tuple): counters, message, fname_timetears
    """
    # Declare variables
    global startBUG1A, printHeader, lcDir, warnings
    i = 0
    counters = BugCounters()
    lastBUG1s = [0, 0, 0, 0]
    printHeader = ''
    startBUG1A = -1
    prev_mux_chan = -1
    # placeholder to avoid writing multiple lccut lines for one time tear
    lccut_prev_time = None
    lccut_prev_block = 0
    verbosity = args.verbosity
    consecIdentTimeErrors, oldDiff = 0, 0
    lcData = LCDataBlock()

    outfilename = outFileRoot + ".fix.lch"
    if not args.dryrun:
        if os.path.exists(outfilename):
            print(f"output file {outfilename} exists already! Quitting")
            sys.exit(2)
        ofp1 = open(outfilename, 'wb', buffering=FILE_BUFFER_SIZE)
    fname_timetears = outFileRoot + '.fix.timetears.txt'
    oftt = open(fname_timetears, 'w')
    of_lccut = None
    if args.lccut_file is True:
        of_lccut = open(os.path.join(args.out_dir, 'run_lccut.sh'), 'w')

    # -----------------------------
    # Copy the disk header to the output file
    # -----------------------------
    if not args.dryrun:
        lcHeader.seekHeaderPosition(ofp1)
        lcHeader.writeHeader(ofp1)
    if __stopProcess(commandQ):
        return

    block_time_ms = int((166 * (1.0 / lcHeader.realSampleRate)) * 1000)

    # -----------------------------
    # Grab the first time entries (one for each channel) and adjust them
    # so that they point one block duration into the past. This primes the
    # expected-time calculation for the first block of each channel.
    # -----------------------------
    lcData.seekBlock(ifp1, firstInpBlock)
    last_time_ms = []
    force_start_ms = None
    if args.forceStartTime is not None:
        force_start_ms = round(args.forceStartTime.timestamp * 1000)

    for _ in range(lcHeader.numberOfChannels):
        lcData.readBlock(ifp1)
        if force_start_ms is None:
            last_time_ms.append(lcData.get_time_ms() - block_time_ms)
        else:
            last_time_ms.append(force_start_ms - block_time_ms)

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

    bar = IncrementalBar(
        f' {fname}',
        index=firstInpBlock,
        max=lastInpBlock,
    )
    progress_pending = 0
    lookahead_data = LCDataBlock()

    # Loop over blocks, comparing expected and actual times.
    for i in range(firstInpBlock, lastInpBlock + 1):
        progress_pending += 1
        if progress_pending >= PROGRESS_INTERVAL:
            bar.next(progress_pending)
            progress_pending = 0
        if debug and (i > lastInpBlock-10):
            logging.info("  BLOCK {:d}".format(i))
        lcData.readBlock(ifp1)
        if debug and (i > lastInpBlock - 10):
            logging.info("  READ")
        # The sequential loop index is the block number. Calling tell() for
        # every record is unnecessary overhead; retain the check in debug mode.
        curr_block = i
        if debug:
            actual_block = ifp1.tell() // BLOCK_SIZE - 1
            if actual_block != curr_block:
                raise ValueError(
                    f"Current Block ({actual_block:d}) != expected "
                    f"({curr_block:d})"
                )
        if startBUG1A >= 0 and curr_block > (lastBUG1s[0] + 500):
            __endBUG1A(startBUG1A, curr_block)
        if verbosity > 1:  # Very verbose, print each block header
            logging.info("{:8d}({:d}): ".format(i, ifp1.tell()))
            lcData.prettyPrintHeader()
        # VERIFY NON-TIME HEADER VALUES ############
        counters.bad_hdr = verify_non_time_header_values(
            lcData, counters.bad_hdr, printHeader, curr_block)
        # VERIFY CHANNEL NUMBER ############
        lcData.muxChannel, warnings = verify_channel_number(
            lcData.muxChannel, lcHeader.numberOfChannels,
            prev_mux_chan, warnings, printHeader, curr_block)
        # Handle bad chan numbers without crashing
        # iCh = lcData.muxChannel % lcHeader.numberOfChannels
        expect_time_ms = last_time_ms[lcData.muxChannel] + block_time_ms
        time_ms = lcData.get_time_ms()
        diff = abs(time_ms - expect_time_ms)
        if diff:
            if args.forceTime or (i > lastInpBlock
                                  - (3*lcHeader.numberOfChannels)):
                # FORCE TIME TO BE WHAT WE EXPECT
                if (consecIdentTimeErrors > 0) & (diff != oldDiff):
                    # Starting a new time offset
                    logging.debug("{:d} blocks".format(
                        consecIdentTimeErrors))
                    consecIdentTimeErrors = 0

                if consecIdentTimeErrors == 0:
                    # New time error or error offset
                    txt = "{}{:8d}:  CH{:d}: {:g}s offset" +\
                          " FORCED to conform..."
                    forceTimeErrorStr = txt.format(printHeader, curr_block,
                                                   lcData.muxChannel,
                                                   diff/1000.)
                    if not args.forceTime:
                        forceTimeErrorStr += " BECAUSE NEAR END OF FILE"
                time_ms = expect_time_ms
                lcData.change_time_ms(time_ms)
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
                    next_times_ms = _get_next_times_ms(
                        ifp1, channel, pos, lookahead_data, count=3
                    )
                    bug_type = None
                    for candidate_ms, multiplier, candidate_type in zip(
                            next_times_ms, (2, 3, 4), ("2", "2b", "2c")):
                        temp_diff = abs(candidate_ms - expect_time_ms)
                        # Preserve the tolerance test used by the original.
                        if temp_diff - multiplier * block_time_ms < 2:
                            bug_type = candidate_type
                            break

                    if bug_type is not None:
                        _log_error_2_ms(
                            bug_type, printHeader, curr_block,
                            lcData.muxChannel, expect_time_ms, time_ms
                        )
                        counters.bug2 += 1
                        time_ms = expect_time_ms
                        lcData.change_time_ms(time_ms)
                    else:
                        # Time tear (do not fix it!)
                        expected_time = _ms_to_datetime(expect_time_ms)
                        actual_time = _ms_to_datetime(time_ms)
                        fmt = (
                            "{:8d}: Time Tear in Data.   CH{:d} "
                            "Expected Time: {}, Got: {}"
                        )
                        txt = fmt.format(
                            curr_block, lcData.muxChannel,
                            expected_time, actual_time
                        )
                        print()  # Newline after progress bar
                        logging.warning(printHeader + txt)
                        warnings += 1
                        print(printHeader + txt, file=oftt)
                        if of_lccut is not None:
                            if lccut_prev_time is None:
                                of_lccut.write('DIR="cut"\n')
                            if time_ms != lccut_prev_time:
                                of_lccut.write(
                                    f'lccut --start {lccut_prev_block} '
                                    f'--end {curr_block - 1} -o $DIR {fname}\n'
                                )
                                lccut_prev_time = time_ms
                                lccut_prev_block = curr_block
                        counters.time_tear += 1
                    # _get_next_times_ms() restored the original position.
                    # End if diff > 1100:
                else:
                    # LCHEAPO BUG - A second is dropped (then recovered)
                    if lastBUG1s[0] == curr_block - 500:
                        if startBUG1A < 0:
                            txt = "{}{:8d}: LCHEAPO BUG #1a. BUG #1s " +\
                                  "repeating at 500-block intervals"
                            print()  # Newline after progress bar
                            logging.info(txt.format(printHeader,
                                                    curr_block))
                            startBUG1A = curr_block
                            printHeader = '      '
                    else:
                        txt = "{}{:8d}: LCHEAPO BUG #1. CH{:d} " +\
                              "Expected Time: {}, Got: {} "
                        print()  # Newline after progress bar
                        logging.info(
                            txt.format(
                                printHeader, curr_block, lcData.muxChannel,
                                _ms_to_datetime(expect_time_ms),
                                _ms_to_datetime(time_ms),
                            )
                        )
                    counters.bug1 += 1
                    time_ms = expect_time_ms
                    lcData.change_time_ms(time_ms)
                    # FIFO: remove 1st elem & add new last
                    lastBUG1s.pop(0)
                    lastBUG1s.append(curr_block)
        else:
            if args.forceTime and (consecIdentTimeErrors > 0):
                print()  # Newline after progress bar
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
        last_time_ms[lcData.muxChannel] = time_ms
        prev_mux_chan = lcData.muxChannel
        # prev_block_flag = lcData.blockFlag
        # prev_num_samps = lcData.numberOfSamples
        # prev_U1 = lcData.U1
        # prev_U2 = lcData.U2
    # END LOOP THROUGH EVERY BLOCK
    if progress_pending:
        bar.next(progress_pending)
    bar.finish()
    if responseQ:
        responseQ.put((i, lastInpBlock, counters.bug1, counters.time_tear))

    # ----------------------------------------------------------------------
    # Copy over the directory entries and modify the block time to correspond
    # to the actual time in the data block.
    # ----------------------------------------------------------------------

    # Open the output datafile for reading
    if not args.dryrun:
        ofp1.flush()    # explicitly flush the output files buffer
        ofp_data = open(outfilename, 'rb', buffering=FILE_BUFFER_SIZE)  # generally the output file
    else:
        # if no output file, read block data from input file
        ofp_data = open(ifp1.name, 'rb', buffering=FILE_BUFFER_SIZE)
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

    messages = _print_blockloop_message(fname, outfilename, args.forceTime, i,
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
    if of_lccut is not None:
        if not lccut_prev_block == 0:
            of_lccut.write('lccut --start {} -o $DIR {}\n'.format(
                lccut_prev_block, fname))
        of_lccut.close()

    # If there is no tear, remove the timetears file
    if counters.time_tear == 0:
        os.remove(fname_timetears)
    # Otherwise, if not forced time corrections, remove the output data file
    elif not args.forceTime:
        os.remove(outfilename)
        return counters, messages, fname_timetears
    return counters, messages, outfilename


def _ms_to_datetime(time_ms):
    """Convert integer milliseconds since the Unix epoch to UTC datetime."""
    return (TIME_EPOCH + time_ms / 1000.0).datetime


def _log_error_2_ms(bug_type, printHeader, curr_block, chan,
                    expect_time_ms, time_ms):
    # LCHEAPO BUG 2 - Isolated time tag error
    print()  # Newline after progress bar
    logging.info(
        "{}{:8d}: LCHEAPO BUG #{}.  CH{:d}  Expected Time: {}, Got: {}".
        format(
            printHeader, curr_block, bug_type, chan,
            _ms_to_datetime(expect_time_ms), _ms_to_datetime(time_ms),
        )
    )


def _print_blockloop_message(fname, outfilename, forceTime, i,
                             counters):
    msgs=[]
    # Print out end-of-loop message for one file
    msgs.append("  {}=>{}: Finished at block {:d}".format(
        fname, os.path.split(outfilename)[1], i))
    if forceTime:
        msgs.append(f"  ({counters.time_tear:d} time errors FORCEABLY corrected)")
    else:
        msgs.append(f"  {str(counters)}")
    for x in msgs:
        logging.info(x)
    return msgs


def _get_next_times_ms(ifp1, channel, pos, temp_data, count=3):
    """Return upcoming timestamps for one channel using one read-ahead pass.

    The input position is restored before returning. Reusing ``temp_data`` and
    scanning once replaces the original three separate scans and allocations.
    """
    times_ms = []
    try:
        while len(times_ms) < count:
            temp_data.readBlock(ifp1)
            if channel == temp_data.muxChannel:
                times_ms.append(temp_data.get_time_ms())
    except (EOFError, OSError):
        # Near EOF there may be fewer than ``count`` future occurrences.
        pass
    finally:
        ifp1.seek(pos)
    return times_ms


# ---------------------------------------------------------------------------
# Run 'main' if the script is not imported as a module
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    main()
