#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Read LCHEAPO data into an obspy stream
"""
import warnings
import struct
import os
import sys
import inspect

import numpy as np
from obspy.core import UTCDateTime, Stream, Trace
from obspy import read_inventory

from lcheapo_utils import (LCDataBlock, LCDiskHeader)
from chan_maps import chan_maps


def read(filename, starttime=None, endtime=None, network='XX', station='SSSSS',
         obs_type=None, verbose=False):
    """
    Read LCHEAPO data into an obspy stream

    To avoid overlaps, starttime is inclusive and endtime is exclusive

    Args:
        filename (str): LCHEAPO filename
        starttime (:class:`~obspy.core.utcdatetime.UTCDateTime`): 
            Start time as a ISO8601 string, a UTCDateTime object,
            or a number (seconds after the file start)
        endtime (:class:`~obspy.core.utcdatetime.UTCDateTime`):
            End time as a ISO8601 string, a UTCDateTime object,
            or a number (seconds after starttime)
        network (str): Set network code (up to two characters)
        station (str): Set FDSN station name (up to five characters)
        obs_type (str): OBS type (must match a key in chan_maps)
        verbose (bool): print out info about first and last read data

    Returns: 
        stream (:class:`~obspy.core.stream.Stream`): read data

    Example:
        >>> from lcheapo import read
        >>> st = read("/path/to/four_channels.lch")
        >>> print(st)  # doctest: +ELLIPSIS
        2 Trace(s) in Stream:
        BW.UH3..EHE | 2010-06-20T00:00:00.279999Z - ... | 200.0 Hz, 386 samples
        BW.UH3..EHZ | 2010-06-20T00:00:00.279999Z - ... | 200.0 Hz, 386 samples
    """
    # Check/complete input variables
    if len(network) > 2:
        network = network[:2]
    if len(station) > 5:
        network = network[:5]
    if not obs_type:
        warnings.warn('No obs_type provided, assuming SPOBS2')
        obs_type = 'SPOBS2'

    with open(filename, 'rb') as fp:
        data = _read_data(starttime, endtime, fp, verbose)
        if data is None:
            print(f'Did not read from file {filename}')
            return None
    data = _stuff_info(data, network, station, obs_type)
    return data


def get_data_timelimits(lcheapo_object):
    """
    Return data start and end times

    Args:
        lcheapo_object (str or file-like object):
            filename or open file-like object that contains the
            binary Mini-SEED data.  Any object that provides a read()
            method will be considered a file-like object.
    Returns:
        tuple (tuple): 2-tuple:
            startime (:class:`obspy.core.UTCDateTime``): start of data
            endime (:class:`obspy.core.UTCDateTime``): end of data
    """

    if hasattr(lcheapo_object, "read"):
        fp = lcheapo_object
    else:
        fp = open(lcheapo_object, 'rb')

    lcHeader = LCDiskHeader()
    block = LCDataBlock()
    status = lcHeader.readHeader(fp)
    if status == 0:
        return None, None

    # read starttime
    startBlock = lcHeader.dataStart
    block.seekBlock(fp, startBlock)
    block.readBlock(fp)
    starttime = block.getDateTime()

    # read endtime
    lastBlock = block.determineLastBlock(fp)
    block.seekBlock(fp, lastBlock)
    block.readBlock(fp)
    endtime = block.getDateTime()

    return UTCDateTime(starttime), UTCDateTime(endtime)


def band_code_sps(band_code, sps):
    """
    Verify/correct a channel's band code for a given sampling rate.
    Band codes are from
    http://docs.fdsn.org/projects/source-identifiers/en/v1.0/channel-codes.html

    Args:
        band_code (str): SEED channel code
        sps (float): sampling rate

    Returns:
        new_band_code (str): SEED channel band code corresponding to
            sampling rate
    """
    # print(f"{band_code=}, {sps=}")
    band_codes_SP = 'GDES'
    band_codes_LP = 'FCHBMLVUWRPTQ'
    if sps > 5000:
        return 'J'
    if band_code in band_codes_SP:
        if sps >= 1000:
            return "G"
        elif sps >= 250:
            return "D"
        elif sps >= 80:
            return "E"
        elif sps >= 10:
            return "S"
        else:
            raise NameError(
                "You should not have short period data at < 10 sps")
    elif band_code in band_codes_LP:
        if sps >= 1000:
            return "F"
        elif sps >= 250:
            return "C"
        elif sps >= 80:
            return "H"
        elif sps >= 10:
            return "B"
        elif sps > 1:
            return "M"
        elif sps == 1:
            return "L"
        elif sps >= 0.1:
            return "V"
        elif sps >= 0.01:
            return "U"
        elif sps >= 0.001:
            return "W"
        elif sps >= 0.0001:
            return "R"
        elif sps >= 0.00001:
            return "P"
        elif sps >= 0.000001:
            return "T"
        else:
            return "Q"
    raise NameError(f'Unknown band code "{band_code}"')


def _read_data(starttime, endtime, fp, verbose=False):
    """
    Return data.

    Returns from the start of the block containing starttime to the end of the
    block containing endtime

    Args:
        starttime (:class:`~obspy.UTCDateTime`): start time
        endtime (:class:`~obspy.UTCDateTime`): end time
        fp (:class:`file`): file pointer
    
    Returns
        stream (:class:`obspy.core.Stream`):

    For speed, reads all blocks at once and extracts as slices
    """
    starttime, endtime = _convert_time_bounds(starttime, endtime, fp)
    if starttime is None:
        return None

    lcHeader = LCDiskHeader()
    block = LCDataBlock()
    lcHeader.readHeader(fp)
    # lcHeader.printHeader()
    sample_rate = lcHeader.realSampleRate
    n_chans = lcHeader.numberOfChannels
    n_start_block = _get_block_number(starttime, fp)
    n_end_block = _get_block_number(endtime, fp) + n_chans - 1
    stream = Stream()

    chan_blocks = int(((n_end_block - n_start_block + 1) / n_chans))
    read_blocks = chan_blocks * n_chans
    block.seekBlock(fp, n_start_block)

    # Read the data and arrange in read_blocks*512 array
    buf = fp.read(read_blocks * 512)
    dt = np.dtype('b')
    all = np.frombuffer(buf, dtype=dt)
    a = np.reshape(all, (read_blocks, 512))  # keep data contiguous
    # The following takes the same amount of time ...
    # a = all.view()
    # a.shape = (read_blocks,512)
    headers = a[:, :14]
    data = a[:, 14:]

    # Get header information and determine if data are contiguous
    samples_per_block = _get_header_nsamples(headers[0, :])
    seconds_per_block = samples_per_block / sample_rate
    last_time = _get_header_time(headers[-n_chans, :])
    first_time = _get_header_time(headers[0, :])
    if verbose:
        print(f'First read block = {n_start_block:d}, time = {first_time}')
        print(f'Last read block =  {n_end_block:d}, time = {last_time}')
    timerange = last_time - first_time
    expected_timerange = (chan_blocks - 1) * seconds_per_block
    offset = timerange - expected_timerange
    if offset > 0.1/sample_rate:
        warnings.warn(f"Last block late by {offset:g} seconds! "
                      f"({offset*sample_rate:g} samples, "
                      f"{offset/seconds_per_block:g} blocks)")
    elif offset < -0.1/sample_rate:
        warnings.warn(f"Last block early by {-offset:g} seconds! "
                      f"({-offset*sample_rate:g} samples, "
                      f"{-offset/seconds_per_block:g} blocks)")
    stats = {'sampling_rate': sample_rate, 'starttime': first_time}

    # Extract channels
    for i in range(0, n_chans):
        # Get data
        chan_data = data[i:read_blocks:n_chans, :].flatten()
        # could be quicker using the np.flat() iterator ?
        t32 = np.array(chan_data[0: 498*chan_blocks: 3]*(1 << 16)
                       + chan_data[1: 498*chan_blocks: 3].astype('B')
                       * (1 << 8)
                       + chan_data[2: 498*chan_blocks: 3].astype('B'),
                       dtype='int32')
        stream.append(Trace(data=t32, header=stats))
    eps = 1e-6
    stream.trim(starttime=starttime, endtime=endtime-eps, nearest_sample=False)
    return stream


def _get_header_time(header):
    """
    Return time from an LCHEAPO header

    Args:
        header: 14-byte LCHEAPO HEADER
    """
    (msec, second, minute, hour, day, month, year) = struct.unpack(
        '>HBBBBBB', header.data[:8])
    try:
        return UTCDateTime(year + 2000, month, day, hour, minute,
                           second + msec/1000)
    except Exception as err:
        raise ValueError(
            '{}. header fields= {}, {}, {}, {}, {}, {}, {}'
            .format(err, year, month, day, hour, minute, second, msec))


def _get_header_nsamples(header):
    """
    Return number of samples from an LCHEAPO header

    Args:
        header = 14-byte LCHEAPO HEADER
    """
    (U1, U2) = struct.unpack('>BB', header.data[12:])
    return U2


def _convert_time_bounds(starttime, endtime, fp):
    """
    Return starttime and endtime as UTCDateTimes

    Also makes sure that starttime and endtime are within the data bounds
    
    Args:
        startime (str, float or UTCDate time): starttime.  If float, 
            seconds from file start
        endtime (str, float or UTCDate time): end time.  If float, seconds
            after starttime
        fp: file pointer (for checking if the times are within the
            data bounds)
    """
    data_start, data_end = get_data_timelimits(fp)
    if data_start is None:
        return None, None
    if not starttime:
        starttime = 0
    if endtime == 0:
        endtime = data_end
    if not endtime:
        endtime = 3600
    if isinstance(starttime, (float, int)):
        starttime = data_start + starttime
    else:
        starttime = UTCDateTime(starttime)
    if isinstance(endtime, (float, int)):
        endtime = starttime + endtime
    # Handle bad time ranges
    if endtime <= starttime:
        print("{endtime=} is before {starttime=}")
        return None, None
    if starttime >= data_end:
        print(f"{starttime=} is after {data_end}=")
        return None, None
    if endtime <= data_start:
        print(f"{endtime=} is before {data_start=}")
        return None, None
    if starttime < data_start:
        starttime = data_start
    if endtime > data_end:
        endtime = data_end
    return UTCDateTime(starttime), UTCDateTime(endtime)


def _get_block_number(time, fp):
    """
    Return block number containing first channel containing the given time

    Args:
        time (:class:`~obspy.UTCDateTime`): the time
        fp (:class:`~file`): file pointer
    """
    lcHeader = LCDiskHeader()
    block = LCDataBlock()
    lcHeader.readHeader(fp)
    data_start_block = lcHeader.dataStart
    block.seekBlock(fp, data_start_block)
    block.readBlock(fp)

    starttime, _ = get_data_timelimits(fp)
    block_len_s = block.numberOfSamples / lcHeader.realSampleRate
    num_chans = lcHeader.numberOfChannels
    record_offset = int((UTCDateTime(time)-starttime) / block_len_s)

    return data_start_block + record_offset * num_chans


def _stuff_info(stream, network, station, obs_type):
    """
    Put network, station and channel information into station stream

    Args:
        stream (:class:`~obspy.stream.Stream`): obspy stream
        network (str): network code
        station (str): station code
        obs_type (str): type of obs (must be in channel_maps)

    Returns:
        data (:class:`~obspy.stream.Stream`): informed data
    """
    assert obs_type in chan_maps
    chan_map = chan_maps[obs_type]
    # chan_map_list = list(chan_map)
    for trace, chan_loc in zip(stream, chan_map):
        trace.stats.network = network
        trace.stats.station = station
        sps = trace.stats.sampling_rate
        # if len(chan_map) >= 1:
        chan, loc = chan_loc.split(':')
        trace.stats.channel = band_code_sps(chan[0], sps) + chan[1:3]
        if len(loc) > 1:
            trace.stats.location = loc
        trace.stats.response = _load_response(obs_type, trace.stats.channel,
                                              trace.stats.starttime)
    return stream


def _load_response(obs_type, channel, start_time):
    """
    Load response corresponding to OBS type and component

    Args:
        obs_type (str): obs type (must be in channel_maps)
        channel (str): trace channel code
        datetime (:class:`~obspy.UTCDateTime`): time for which to get response

    Returns:
        resp (:class:`~obspy.core.response.Response`): instrument response
    """
    assert obs_type in chan_maps
    try:
        basepath = os.path.dirname(os.path.abspath(inspect.getfile(
                                       inspect.currentframe())))
        inv_file = os.path.join(basepath, 'data', f'{obs_type}.station.xml')
        inv = read_inventory(inv_file)
    except Exception:
        print(f'Could not read inventory file {inv_file}')
        sys.exit()

    try:
        resp = inv.select(channel=channel, time=start_time)[0][0][0].response
    except Exception:
        print(f'No response matching "{channel}" at {start_time}')
        print('Options were: ')
        for net in inv:
            for sta in net:
                for ch in sta:
                    print(' "{}" : {} - {}'.format(ch.code, ch.start_date,
                                                   ch.end_date))
        return []
    return resp


def _valid_chan_map(chan_map):
    """
    Verify that chan_map is valid
    """
    if not isinstance(chan_map, list):
        return False
    for elem in chan_map:
        if not isinstance(elem, str):
            return False
        if len(elem) <= 3:
            return True
        else:
            if ':' in elem:
                elems = elem.split(':')
                if len(elems) == 2:
                    if len(elems[0]) <= 3 and len(elems[1]) <= 2:
                        return True
    return False

### THE FOLLOWING DUPICATES LCPLOT.PY BECAUSE I CAN'T CHANGE MODULE REFERENCES
### WITHOUT INTERNET


import argparse
import re

def _plot_command():
    """
    Command-line plotting interface
    """
    obs_types = [s for s in chan_maps]
    epilog = "--sfilt returns the first parenthetised subgroup, using \n"
    epilog += "  python's re.search().  Some useful codes are: \n"
    epilog += "   '.': matches any character\n"
    epilog += "   '+': matches 1 or more repetitions of the preceding RE\n"
    epilog += "   '?': matches 0 or 1 repetitions of the preceding RE\n"
    epilog += "  '+?': like +, but non-greedy (don't match as many as possible)\n"
    epilog += "   '\\': escapes special characters, like '*', '-' and '/')\n"
    epilog += "  '()': delimit the subgroup to return\n\n"
    epilog += " Some examples are: \n"
    epilog += "    FILENAME                 |   PATTERN      |     RESULT\n"
    epilog += "    =========================+================+=============\n"
    epilog += "    haha-MOVA-OBS1-blah.lch | '\-(.+)\-'     | MOVA-OBS1 \n"
    epilog += "    haha-MOVA-OBS1-blah.lch | '\(-.+)\-.+\-' | MOVA \n"
    epilog += "    haha-MOVA-OBS1-blah.lch | '\-.+\-(.+)\-' | OBS1 \n"
    epilog += "    MOVA/haha.raw.lch       | '([^\/]+)'     | MOVA \n"

    parser = argparse.ArgumentParser(
        description=__doc__, epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("infiles", nargs="+", help="Input filename(s)")
    parser.add_argument("-s", "--start", dest="starttime", metavar="TIME",
                        default=0,
                        help="start time (ISO8601, or seconds after last file "
                             "start) (default: %(default)s)")
    parser.add_argument("-e", "--end",
                        dest="endtime", metavar="TIME", default=3600.,
                        help="end time (ISO8601, or seconds from start time) "
                        "(default: %(default)s)")
    parser.add_argument("-t", "--type", choices=obs_types,
                        dest="obs_type", metavar='TYPE', default='SPOBS2',
                        help="obs type.  Allowed choices are " +
                             ", ".join(obs_types) +
                             " (default: %(default)s)")
    parser.add_argument("--net", dest="network", default='NN',
                        help="network code (default: %(default)s)")
    parser.add_argument("--chan", dest="channel", default='*',
                        help="Plot only the given SEED channel/s (default: "
                             "%(default)s)")
    parser.add_argument("--equal_scale", action="store_true",
                        help="Force all traces equal y scale")
    parser.add_argument('-v', "--verbose",
                        dest="verbose", action="store_true",
                        help="Print information about the first and last "
                             "read blocks")
    my_group = parser.add_mutually_exclusive_group(required=False)
    my_group.add_argument("--sta", dest="station", default='STA',
                          help="station code.  A 2-digit counter will be "
                               "appended if more than one file is read. "
                               "(default: %(default)s)")
    my_group.add_argument("--sfilt", dest="station_filt",
                          help="regex filter to find station name in filename "
                               "(see examples below)")
    args = parser.parse_args()

    # Set/normalize start and end times
    endtime = _normalize_time_arg(args.endtime)
    if endtime == 0:
        endtime = 3600.
    if not args.starttime:  # set starttime to latest-starting file
        args.starttime = UTCDateTime(0)
        for infile in args.infiles:
            s, e = get_data_timelimits(infile)
            if s > args.starttime:
                args.starttime = s
    # Read file(s)
    station_code = None
    if args.station:
        if len(args.infiles) == 1:
            station_code = args.station
    stream = Stream()
    for (infile, i) in zip(args.infiles, range(len(args.infiles))):
        if args.station_filt:
            # print(re.search(args.station_filt, infile))
            try:
                station_code = re.search(args.station_filt, infile).group(1)
            except Exception:
                print('no station code found using re.search("{}", "{}"'.
                      format(args.station_filt, infile))
                station_code = None
        if station_code is None:
            station_code = f'STA{i:02d}'
        s = read(infile,
                 _normalize_time_arg(args.starttime),
                 _normalize_time_arg(args.endtime),
                 network=args.network,
                 station=station_code,
                 obs_type=args.obs_type,
                 verbose=args.verbose)
        if s is not None:
            s = s.select(channel=args.channel)
            stream += s
            station_code = None
    if len(stream) > 0:
        stream.plot(size=(800, 600), equal_scale=args.equal_scale,
                    method='full')
    else:
        print('Nothing read, nothing plotted!')


def _normalize_time_arg(a):
    """
    Convert time from string to float if it is numeric
    """
    if isinstance(a, UTCDateTime):
        return a
    try:
        temp = float(a)
    except ValueError:
        return a
    else:
        return temp


# ---------------------------------------------------------------------------
# Run 'main' if the script is not imported as a module
# ---------------------------------------------------------------------------
# if __name__ == '__main__':
#     main()
