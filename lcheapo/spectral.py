"""
Functions to calculate spectra, coherences and transfer functions
"""
from obspy.signal.invsim import cosine_taper
from obspy.core.trace import Trace
import scipy.signal as ssig
from matplotlib import mlab
import matplotlib.pyplot as plt
import numpy as np
import math as m
import warnings

from Peterson_noise_model import PetersonNoiseModel

# Set variables
spect_library = 'scipy'  # 'mlab' or 'scipy': mlab gives weird coherences!


class PSD:
    """
    Power Spectral Density class
    """
    def __init__(self, freqs=None, data=None, units=None, stats=None):
        """
        :parm freqs: 1-D array of frequencies
        :parm data: 1-D array of PSD values
        :parm units: data units (str)
        :type stats: :class:`~obspy.core.trace.Stats`
        """
        self.freqs = np.array(freqs)
        self.data = np.array(data)
        assert freqs.shape == data.shape
        self.units = units
        self.stats = stats

    def __repr__(self):
        """
        String describing object
        """
        s = 'PSD(freqs, data, units={}, stats=stats) '.format(
            self.units, self.stats)
        s += '<data.shape={}, freqs={:g}-{:g}, seed_code={}>'.format(
            self.data.shape, self.freqs[0], self.freqs[-1],
            _seed_code(self.stats))
        return s

    @classmethod
    def calc(cls, tr, window_length=1000):
        """
        Calculate PSD of a data trace
        Based on obspy PPSD function

        REMOVING PART COHERENT WITH ANOTHER CHANNEL WILL REQUIRE DOING
        WELCH MYSELF (MUST APPLY REMOVAL AT THE LEVEL OF EACH FFT)

        :type st: :class:`~obspy.core.stream.Stream`
        :param tr: Trace to be processed, should have response attached
        :type window_length: `numeric`
        :param window_length: minimum FFT window length in seconds
        """
        assert type(tr) == Trace
        
        sampling_rate = tr.stats.sampling_rate
        data_len = tr.stats.endtime - tr.stats.starttime
        if window_length > data_len/2:
            window_length = int(data_len/3)
        nfft = 2**(m.ceil(m.log2(window_length * sampling_rate)))
        nlap = int(0.75 * nfft)

        if spect_library == 'mlab':
            spec, _freq = mlab.psd(tr.data, nfft, sampling_rate,
                                   detrend=mlab.detrend_linear,
                                   window=_fft_taper, noverlap=nlap,
                                   sides='onesided', scale_by_freq=True)
        elif spect_library == 'scipy':
            _freq, spec = ssig.welch(tr.data, sampling_rate, nperseg=nfft,
                                     detrend="linear", noverlap=nlap)
        else:
            warnings.warn('Unknown spectra library: "{}"'.format(
                spect_library))
            return False

        # leave out first entry (offset)
        spec = spec[1:]

        # Remove the response using the same conventions
        # since the power is squared we must square the sensitivity
        # determine instrument response from metadata
        try:
            resp, _ = tr.stats.response.get_evalresp_response(
                t_samp=1 / sampling_rate, nfft=nfft, output="VEL")
            resp = resp[1:]
        except Exception as e:
            msg = ("Error getting response from provided metadata:\n"
                   "%s: %s\n"
                   "Skipping time segment(s).")
            msg = msg % (e.__class__.__name__, str(e))
            warnings.warn(msg)
            resp = None

        _freq = _freq[1:]
        if resp[0]:
            # Get the amplitude response (squared)
            respamp = np.absolute(resp * np.conjugate(resp))
            # Make omega with the same conventions as spec
            w = 2.0 * m.pi * _freq
            # Remove response
            if tr.stats.response.response_stages[0].input_units.upper()[:2] == "PA":
                print('Channel {} has input_units "{}": treating as hydrophone'.
                      format(tr.stats.channel,
                             tr.stats.response.response_stages[0].input_units))
                spec = spec / respamp
                PSD_units = "dB ref 1 Pa^2/Hz"
            else:
                spec = (w**2) * spec / respamp
                PSD_units = "dB ref 1 (m/s^2)^2/Hz"
        else:
            PSD_units = "dB ref 1 count^2/Hz"
        return cls(_freq, spec, PSD_units, tr.stats)

    def plot(self, ax=None, show=True, outfile=None, show_Peterson=True):
        """
        Plot a PSD
        """
        if ax:
            pass
            # plt.gca = ax
        else:
            plt.figure()
            ax = plt.gca()
        ax.semilogx(self.freqs, 10 * np.log10(self.data))
        if show_Peterson and not _seed_code(self.stats)[-1] == 'H':
            lownoise, highnoise = PetersonNoiseModel(self.freqs, True)
            ax.semilogx(self.freqs, lownoise,'--')
            ax.semilogx(self.freqs, highnoise,'--')
        ax.set_ylabel(self.units)
        # ax.title()
        ax.set_title(_seed_code(self.stats))
        if outfile:
            plt.savefig(outfile)
        elif show:
            plt.show()


class PSDs:
    """
    List of PSD
    """
    def __init__(self, PSDs=None):
        assert isinstance(PSDs, list)
        for p in PSDs:
            assert isinstance(p,PSD)
        self.PSDs = PSDs

    def __str__(self):
        s = ''
        for PSD in self.PSDs:
            s += PSD.__str__() + '\n'

    def __len__(self):
        return len(self.PSDs)

    @classmethod
    def calc(cls, st, window_length=1000):
        """
        Calculate PSDs of a data stream

        :type st: :class:`~obspy.core.stream.Stream`
        :param st: Stream to be processed
        :type window_length: `numeric`
        :param window_length: minimum FFT window length in seconds
        :returns: list of dictionaries containing freqs, data, units, name
        """
        PSDs = []
        for tr in st:
            PSDs.append(PSD.calc(tr, window_length))
        return cls(PSDs=PSDs)

    def plot(self, outfile=None):
        """
        plot PSDs
        """
        nPSDs = len(self.PSDs)
        nRows = m.floor(m.sqrt(nPSDs))
        nCols = m.ceil(nPSDs/nRows)
        plt.figure(1)
        i = 0
        for p in self.PSDs:
            i += 1
            ax = plt.subplot(nRows, nCols, i)
            p.plot(ax=ax, show=False)
        if outfile:
            plt.savefig(outfile)
        else:
            plt.show()
        return


class Coherence:
    def __init__(self, data, chan_nums):
        self.data = data
        self.chan_nums = chan_nums


class Coherences:
    def __init__(self, freqs, cohs, num_windows, signif_level,
                 starttime, endtime, stats):
        self.freqs = np.array(freqs)
        self.cohs = cohs
        for coh in cohs:
            assert self.freqs.shape == self.cohs.shape
        self.num_window = num_windows
        self.signif_level = signif_level
        self.starttime = starttime
        self.endtime = endtime

    @classmethod
    def calc(cls, st, window_length=1000):
        """
        Calculate coherences between channels of a data stream

        TO REMOVE PART COHERENT WITH ANOTHER CHANNEL, WILL HAVE TO DO
        WELCH MYSELF (MUST APPLY REMOVAL AT THE LEVEL OF EACH FFT)

        :type st: :class:`~obspy.core.stream.Stream`
        :param tr: Stream to be processed
        :type window_length: `numeric`
        :param window_length: minimum FFT window length in seconds
        :returns: list of dictionaries containing freqs, data, units, name
        """
        cohers = []
        for i in range(len(st)-1):
            for j in range(i+1, len(st)):
                # print(i,j)
                tr_i = st[i]
                tr_j = st[j]
                tr_i.data = tr_i.data.astype(np.float64)
                tr_j.data = tr_j.data.astype(np.float64)

                # Verify that channels are compatible (same sampling rate,
                # length and starttime)
                tmp = 'Channels {:d} and {:d}'.format(i, j)
                if tr_i.stats.sampling_rate != tr_j.stats.sampling_rate:
                    warnings.warn(tmp + 'have different samp rates')
                    cohers.append([])
                    continue
                sampling_rate = tr_i.stats.sampling_rate
                if len(tr_i.data) != len(tr_j.data):
                    warnings.warn(tmp + 'have different lengths')
                    cohers.append([])
                    continue
                data_samples = len(tr_i.data)
                if abs(tr_i.stats.starttime - tr_j.stats.starttime) >\
                        1 / sampling_rate:
                    warnings.warn('tmp +  ' + 'are offset by > one sample')
                    cohers.append([])
                    continue
                starttime = tr_i.stats.starttime

                # Calculate Coherence
                nfft = 2**(m.ceil(m.log2(window_length * sampling_rate)))
                nlap = int(0.75 * nfft)
                if spect_library == 'mlab':   # MLAB GIVES STRANGE ANSWER
                    Cxy, _freq = mlab.cohere(tr_i.data, tr_j.data, nfft,
                                             sampling_rate,
                                             detrend=mlab.detrend_linear,
                                             window=_fft_taper,
                                             noverlap=nlap, sides='onesided',
                                             scale_by_freq=False)
                # SCIPY GIVES SIMILAR ANSWER TO MATLAB
                elif spect_library == 'scipy':
                    _freq, Cxy = ssig.coherence(tr_i.data, tr_j.data,
                                                sampling_rate,
                                                # window=_fft_taper,
                                                nperseg=nfft,
                                                detrend="linear",
                                                noverlap=nlap)
                else:
                    warnings.warn('Unknown spectra library: "{}"'.format(
                        spect_library))
                    return False

                nW = 1 + np.floor((data_samples - nfft) / nlap)
                csl = np.sqrt(2. / nW)  # coherency 95% significance level

                # Make dictionary, leaving out first freq/Cxy entry (offset)
                cohers.append(Coherence(Cxy[1:], (i, j)))
        return cls(_freq[1:], cohers, nW, csl, starttime,
                   starttime + data_samples / sampling_rate,
                   [s.stats for s in st])

    def plot(self, outfile=None):
        """
        plot coherences calculated using calc_cohers (should become a class)
        """
        nCohers = len(self.cohers)
        nRows = m.ceil(m.sqrt(nCohers))
        nCols = m.ceil(nCohers / nRows)
        plt.figure(1)
        i = 0
        for coher in self.cohers:
            i += 1
            plt.subplot(nRows, nCols, i)
            plt.semilogx(self.freqs, np.absolute(coher.data))
            plt.title(_seed_code(self.stats[coher.chan_nums[0]]) + '-' +
                      _seed_code(self.stats[coher.chan_nums[1]]))
            plt.ylim([0, 1])
        if outfile:
            plt.savefig(outfile)
        else:
            plt.show()
        return


class TransferFunction:
    def __init__(self, freqs, data, uncerts, drive_stats, resp_stats,
                 gooddata=None, noisechan='response'):
        """
        :parm freqs: 1-D array of frequencies
        :parm data: 1-D array of transfer function
        :parm uncerts: 1-D array of uncertainties
        :parm units: data units (str)
        :parm noisechan: 'response', 'driving', 'equal' or 'unknown'
        :type drive_stats, resp_stats: :class:`~obspy.core.trace.Stats`
        """
        self.freqs = freqs
        self.data = data
        self.uncerts = uncerts
        self.drive_stats = drive_stats
        self.resp_stats = resp_stats
        self.gooddata = gooddata
        self.noisechan = noisechan

    @classmethod
    def calc(cls, spects, cohers, drivechan='H', respchan='Z',
             noisechan='response', verbose=True):
        """
        Calculate the transfer function between 2 channels

        XF = calcXF(spect,cohers,drivechan,respchan,noisechan)
        input:
            spects    (list)  contains PSDs calculated using calc_PSDs()
            cohers    (list)  contains coherences
            drivechan (str)   the driving channel name (or last character(s))
            respchan  (str)   the response channel name (or last character(s))
            noisechan (str)	  is which channel to assume contains the noise
                'response'	[default] Assume all noise on the response channel
                'driving'	Assume all noise on the driving channel
                'equal'		Assume the same signal/noise on the driving  and
                            response channels
                'unknown'	Make no assumption about noise
        output:
            dictionary containing the transfer function
        """

        if verbose:
            print(f'Calculating XF between "{drivechan}" (driving) and'
                  f'"{respchan}" (response) channels, assume noise is on'
                  f'{noisechan}')

        # FIND PSD and coherence channels matching drivechan and respchan
        coh = None
        for c in cohers:
            chan_i = cohers.stats[c.ch_nums[0]].channel
            chan_j = cohers.stats[c.ch_nums[1]].channel
            if (chan_i.endswith(drivechan) and chan_j.endswith(respchan)) or \
               (chan_i.endswith(respchan) and chan_j.endswith(drivechan)):
                coh = c
                break
        if not coh:
            warnings.warn('Did no t find a coherence with channels {}, {}'.
                          format(drivechan, respchan))
            return False
        drive_spect = None
        resp_spect = None
        for s in spects:
            if s['chan'].endswith(drivechan):
                drive_spect = s
                if verbose:
                    print('drive_spect channel is "{}"'.format(s['chan']))
            elif s['chan'].endswith(respchan):
                resp_spect = s
                if verbose:
                    print('resp_spect channel is "{}"'.format(s['chan']))
        if not drive_spect:
            warnings.warn('Did not find a spectra with channel {}'.
                          format(drivechan))
            return False
        if not resp_spect:
            warnings.warn('Did not find a spectra with channel {}'.
                          format(respchan))
            return False

        # CALCULATE RESP/DRIVE
        RespOverDrive = np.sqrt(np.divide(resp_spect['data'],
                                          drive_spect['data']))

        # CALCULATE TRANSFER FUNCTION
        # Equations from Bendat&Piersol "Random Data" 1986, pp 176-181 (xfs)
        # & pp 317, Table 9.6
        cohmagsq = np.multiply(np.absolute(coh['data']),
                               np.absolute(coh['data']))
        errbase = np.divide(np.sqrt(np.ones(cohmagsq.shape) - cohmagsq),
                            2 * coh['num_windows'] * cohmagsq)
        if noisechan == 'response':
            xf = np.multiply(RespOverDrive, coh['data'])
            xferr = np.multiply(np.abs(xf), errbase)
        elif noisechan == 'driving':
            xf = np.divide(RespOverDrive, coh['data'])
            xferr = np.multiply(np.abs(xf), errbase)
        elif noisechan == 'equal':
            xf = RespOverDrive
            xferr = np.abs(np.multiply(xf, errbase))
        elif noisechan == 'unknown':
            xf = RespOverDrive
            # Ad-hoc error guesstimate
            maxerr = np.abs(np.power(coh['data'], -1.)) + errbase
            minerr = np.abs(coh['data']) - errbase
            xferr = np.abs(np.multiply(xf, (maxerr-minerr) / 2))
        else:
            warnings.warn('Invalid: noisechan = ' + noisechan)
            return False
        return cls(drive_spect.freqs, xf, xferr,
                   drive_spect.stats, resp_spect.stats,
                   np.absolute(coh['data']) > coh['signif_level'],
                   noisechan)
        # XF=dict(drive_info=dict(channel=drive_spect['chan'],
        #                         units=drive_spect['units']),
        #         resp_info= dict(channel=resp_spect['chan'],
        #                         units=resp_spect['units']),
        #         freq=     drive_spect['freq'],
        #         data=      xf,
        #         error=     xferr,
        #         noisechan=noisechan,
        #         gooddata=  np.absolute(coh['data']) > coh['signif_level'])

    def plot(self, outfile=None, debug=False):
        """
        plot transfer function
        """
        plt.figure(1)
        plt.clf()
        if debug:
            print(self.freqs[0])
            print(self.data[0])
            print(self.uncert[0])
        # plt.errorbar(np.log10(XF['freq']), np.absolute(XF['data']),
        #              yerr=np.absolute(XF['error']))
        # plt.ylim(0 , np.max(np.absolute(XF['data'])))
        plt.loglog(self.freqs, np.absolute(self.data), marker='o',
                   linestyle='')
        plt.loglog(self.freqs, np.absolute(self.data) + self.uncert)
        plt.loglog(self.freqs, np.absolute(self.data) - self.uncert)
        plt.ylim(np.min(np.absolute(self.data)),
                 np.max(np.absolute(self.data)))
        plt.title(f'Transfer function, noise channel: ({self.noisechan})')
        plt.ylabel(self.resp_stats.channel + '/' + self.drive_stats.channel)
        plt.xlabel('log(freq)')
        if outfile:
            plt.savefig(outfile)
        else:
            plt.show()
        return


def _fft_taper(data):
    """
    Cosine taper, 10 percent at each end (like done by [McNamara2004]_).

    .. warning::
        Inplace operation, so data should be float.
    """
    data *= cosine_taper(len(data), 0.2)
    return data


def _seed_code(stats):
    """
    Returns SEED code from obspy stats container

    >>> from obspy.core.trace import Stats
    >>> stats = Stats()
    >>> stats.network = 'YV'
    >>> stats.station = 'TEST'
    >>> stats.channel = 'BHZ'
    >>> _seed_code(stats)
    'YV.TEST..BHZ'
    """
    try:
        return '{}.{}.{}.{}'.format(stats.network, stats.station,
                                    stats.location, stats.channel)
    except AttributeError:
        return ''


if __name__ == "__main__":
    import doctest
    doctest.testmod()
