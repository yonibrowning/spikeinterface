from pathlib import Path
import numpy as np

from spikeinterface.core import load_extractor
from spikeinterface.extractors import BinaryRecordingExtractor,read_kilosort
from ..basesorter import BaseSorter

try:
    import pykilosort
    from pykilosort import Bunch, add_default_handler, run

    HAVE_PYKILOSORT = True
except ImportError:
    HAVE_PYKILOSORT = False


class PyKilosortSorter(BaseSorter):
    """Pykilosort Sorter object."""

    sorter_name = 'pykilosort'
    requires_locations = False
    docker_requires_gpu = True
    compatible_with_parallel = {'loky': True, 'multiprocessing': False, 'threading': False}

    _default_params = {
        "nfilt_factor": 8,
        "AUCsplit": 0.85,
        "nskip": 5,
        "low_memory":False,
        "seed":42,
        "preprocessing_function":'kilosort2',
        "save_drift_spike_detections":False,
        "perform_drift_registration":False,
        "do_whitening":True,
        "fs":30000.0,
        "probe":None,
        "n_channels":385,
        "data_dtype":'int16',
        "save_temp_files":True,
        "fshigh":300.0,
        "fslow":None,
        "minfr_goodchannels":.1,
        "genericSpkTh":8.0,
        "nblocks":5,
        "output_filename":None,
        "overwrite":True,
        "sig_datashift":20.0,
        "stable_mode":True,
        "deterministic_mode":True,
        "datashift":None,
        "Th":[10,4],
        "ThPre":8,
        "lam":10,
        "minFR":1.0/50,
        "momentum":[20,400],
        "sigmaMask":30,
        "spkTh":-6
        "reorder":1,
        "nSkipCov":25,
        "ntbuff":64,
        "whiteningRange":32,
        "scaleproc":200,
        "nPCs":3,
        "nt0":61,
        "nup":10,
        "sig":1,
        "gain":1,
        "templateScaling":20.0,
        "loc_range":[5, 4],
        "long_range":[30, 6],
    }

    _params_description = {
        "nfilt_factor": 8,
        "AUCsplit": "splitting a cluster at the end requires at least this much isolation for each sub-cluster (max=1)",
        "nskip": 5,
        "low_memory":False,
        "seed":"seed for deterministic output",
        "preprocessing_function":'pre-processing function used choices are "kilosort2" or "destriping"',
        "save_drift_spike_detections":'save detected spikes in drift correction',
        "perform_drift_registration":'Estimate electrode drift and apply registration',
        "do_whitening":'whether or not to whiten data, if disabled channels are individually z-scored',
        "fs":"sample rate",
        "probe":'data type of raw data',
        "n_channels":'number of channels in the data recording',
        "data_dtype":'data type of raw data',
        "save_temp_files":"keep temporary files created while running",
        "fshigh":"high pass filter frequency",
        "fslow":"low pass filter frequency",
        "minfr_goodchannels":"minimum firing rate on a 'good' channel (0 to skip)",
        "genericSpkTh":"threshold for crossings with generic templates",
        "nblocks":"number of blocks used to segment the probe when tracking drift, 0 == don't track, 1 == rigid, > 1 == non-rigid",
        "output_filename":"optionally save registered data to a new binary file",
        "overwrite":"overwrite proc file with shifted data",
        "sig_datashift":"sigma for the Gaussian process smoothing",
        "stable_mode":"make output more stable",
        "deterministic_mode":"make output deterministic by sorting spikes before applying kernels",
        "datashift":"parameters for 'datashift' drift correction. not required",
        "Th":"threshold on projections (like in Kilosort1, can be different for last pass like [10 4])",
        "ThPre":"threshold crossings for pre-clustering (in PCA projection space)",
        "lam": "how important is the amplitude penalty (like in Kilosort1, 0 means not used, 10 is average, 50 is a lot)",
        "minFR":" minimum spike rate (Hz), if a cluster falls below this for too long it gets removed",
        "momentum":"number of samples to average over (annealed from first to second value)",
        "sigmaMask":"spatial constant in um for computing residual variance of spike",
        "spkTh":"spike threshold in standard deviations",
        "reorder":"whether to reorder batches for drift correction.",
        "nSkipCov":"compute whitening matrix from every nth batch",
        "ntbuff":"samples of symmetrical buffer for whitening and spike detection; Must be multiple of 32 + ntbuff. This is the batch size (try decreasing if out of memory).",
        "whiteningRange":"number of channels to use for whitening each channel",
        "scaleproc":"int16 scaling of whitened data",
        "nPCs":"how many PCs to project the spikes into",
        "nt0":None,
        "nup":None,
        "sig":None,
        "gain":None,
        "templateScaling":None
        "loc_range":None,
        "long_range":None,
    }

    sorter_description = """pykilosort is a port of kilosort to python"""

    installation_mesg = """\nTo use pykilosort:\n
       >>> pip install cupy
        >>> git clone https://github.com/MouseLand/pykilosort
        >>> cd pykilosort
        >>>python setup.py install
    More info at https://github.com/MouseLand/pykilosort#installation
    """

    #
    handle_multi_segment = False

    @classmethod
    def is_installed(cls):
        return HAVE_PYKILOSORT

    @classmethod
    def get_sorter_version(cls):
        return pykilosort.__version__

    @classmethod
    def _check_params(cls, recording, output_folder, params):
        return params

    @classmethod
    def _setup_recording(cls, recording, output_folder, params, verbose):
        probe = recording.get_probe()

        # local copy
        recording.save(format='binary', folder=output_folder / 'bin_folder')

    @classmethod
    def _run_from_folder(cls, output_folder, params, verbose,*args,**kwargs):
        recording = load_extractor(output_folder / 'spikeinterface_recording.json')

        assert isinstance(recording, BinaryRecordingExtractor)
        assert recording.get_num_segments() == 1
        dat_path = recording._kwargs['file_paths'][0]
        print('dat_path', dat_path)

        num_chans = recording.get_num_channels()
        locations = recording.get_channel_locations()
        print(locations)
        print(type(locations))

        # ks_probe is not probeinterface Probe at all
        ks_probe = Bunch()
        ks_probe.NchanTOT = num_chans
        ks_probe.chanMap = np.arange(num_chans)
        ks_probe.kcoords = np.ones(num_chans)
        ks_probe.xc = locations[:, 0]
        ks_probe.yc = locations[:, 1]

        run(
            dat_path,
            params=params,
            probe=ks_probe,
            dir_path=output_folder,
            n_channels=num_chans,
            dtype=recording.get_dtype(),
            sample_rate=recording.get_sampling_frequency(),
            *args,**kwargs,
        )

    @classmethod
    def _get_result_from_folder(cls, output_folder):
        #return read_kilosort(output_folder/'output')
        return KiloSortSortingExtractor(folder_path = output_folder/'output')
