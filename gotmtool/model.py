#--------------------------------
# GOTM Model object
#--------------------------------

import os
import subprocess as sp
import xarray as xr
from netCDF4 import Dataset
from .io import *
from .utils import *

class Model:

    """A GOTM model

    """

    def __init__(
            self,
            name = 'GOTM test',
            environ = os.environ['HOME']+'/.gotm_env.yaml'
            ):
        """Initialization

        :name:    (str) name of the model
        :environ: (str or dict-like) path of a YAML file or a dictionary containing the GOTM environment variables

        """
        if not os.path.exists(environ):
            print_error('GOTM environment file \'{}\' not found'.format(environ))
            print_hints('Please run gotm_env_init.py to set it up')
        self.name = name
        self.environ = config_load(environ)
        self._exe = self.environ['gotmdir_exe']+'/bin/gotm'

    def _is_built(self):
        """Check if the model has been built

        :returns: (bool) True if a GOTM executable has been built, False otherwise

        """
        return os.path.isfile(self._exe) and os.access(self._exe, os.X_OK)

    def _is_clean(self):
        """Check if the source code directory is clean

        :returns: (bool) True if the source code directory is clean, False otherwise

        """
        # check if the source code directory is clean, return False if dirty
        cmd = ['git', 'status', '--short']
        clean_info = sp.run(cmd, cwd=self.environ['gotmdir_code'], check=True, stdout=sp.PIPE, stderr=sp.STDOUT, text=True)
        return clean_info.stdout == ''

    def _is_updated(self):
        """Check if the executable is updated with the source code

        :returns: (bool) True if the GOTM executable is updated, False otherwise

        """
        # return False if not built
        if not self._is_built():
            return False
        if not self._is_clean():
            return False
        # get the version of the compiled GOTM executable
        cmd = [self._exe, '--version']
        version_info = sp.run(cmd, check=True, stdout=sp.PIPE, stderr=sp.STDOUT, text=True)
        # get the hash tag of the source code
        cmd = ['git', 'show', '-s', '--format=%h']
        hash_info = sp.run(cmd, cwd=self.environ['gotmdir_code'], check=True, stdout=sp.PIPE, stderr=sp.STDOUT, text=True)
        # return False if the hash tag does not match the GOTM version
        return hash_info.stdout.strip() in version_info.stdout

    def build(
            self,
            clean = False,
            use_cvmix = True,
            use_fabm = False,
            use_stim = False,
            use_netcdf = True,
            extra_output = False,
            debug = False,
            ):
        """Build GOTM source code

        :clean:        (bool) flag to force a clean build
        :use_cvmix:    (bool) flag to compile GOTM with CVMix
        :use_fabm:     (bool) flag to compile GOTM with FABM
        :use_stim:     (bool) flag to compile GOTM with STIM
        :use_netcdf:   (bool) flag to compile GOTM with NetCDF
        :extra_output: (bool) flag to output additional turbulence diagnostics
        :debug:        (bool) flag to build in debug mode

        """
        if clean:
            print('Cleaning up old build...\n')
            # clean up
            cleanup_dir(self.environ['gotmdir_build'])
            cleanup_dir(self.environ['gotmdir_exe'])
        if not self._is_updated():
            # build the source code
            cmd = ['cmake']
            cmd.append(self.environ['gotmdir_code'])
            cmd.append('-DCMAKE_INSTALL_PREFIX:PATH='+self.environ['gotmdir_exe'])
            cmd.append('-DGOTM_USE_CVMIX='+str(use_cvmix).lower())
            cmd.append('-DGOTM_USE_FABM='+str(use_fabm).lower())
            cmd.append('-DGOTM_USE_STIM='+str(use_stim).lower())
            cmd.append('-DGOTM_USE_NetCDF='+str(use_netcdf).lower())
            cmd.append('-DGOTM_EXTRA_OUTPUT='+str(extra_output).lower())
            if debug:
                cmd.append('-DCMAKE_BUILD_TYPE=Debug')
            print('Building GOTM...\n')
            print(' '.join(cmd))
            proc = sp.run(cmd, cwd=self.environ['gotmdir_build'], check=True, stdout=sp.PIPE, text=True)
            print('\n'+proc.stdout+'\n')
            print('make install')
            proc = sp.run(['make','install'], cwd=self.environ['gotmdir_build'], check=True, stdout=sp.PIPE, text=True)
            print('\n'+proc.stdout+'\n')
            print_ok('Done!')
        else:
            print_warning('GOTM is updated. Skipping the build step. Use \'clean=True\' to rebuild')

    def init_config(
            self,
            filename = None,
            ):
        """Initialize the configuration file with default values

        :filename: (str) name of the output configuration file
        :returns:  (dict) configurations in a dictionary

        """
        if not self._is_built():
            print_error('Please build GOTM first!')
        if not self._is_updated():
            print_warning('GOTM not updated. Please double-check on the generated configuration file')
        # default output
        if filename is None:
            filename = self.environ['gotmdir_run']+'/'+self.name+'/gotm.yaml'
        # generate configuration file
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        cmd = [self._exe, '--write_yaml', filename, '--detail', '2']
        proc = sp.run(cmd, check=True)
        print('Generating default configuration at \'{:s}\'...'.format(filename))
        print_ok('Done!')
        return yaml_load(filename)

    def run(
            self,
            config = None,
            quiet = True,
            ):
        """Run a single instance of the model with the given configuration

        :config:  (str or dict-like) path of a YAML file or a dictionary containing the GOTM configurations
        :quiet:  (bool) flag to run the model quietly and write a log, otherwise print the log on screen

        """
        if config is None:
            print_error('GOTM configuration required')
            print_hints('A GOTM configuration can either be a dictionary-like object or a YAML file containing all the configurations')
        # create run directory
        rundir = self.environ['gotmdir_run']+'/'+self.name
        os.makedirs(rundir, exist_ok=True)
        # write yaml configuration file
        config_dump(config, rundir+'/gotm.yaml')
        # run the model
        proc = sp.run(self._exe, cwd=rundir, check=True, stdout=sp.PIPE, stderr=sp.STDOUT, text=True)
        if quiet:
            # write to log
            with open(rundir+'/gotm.log', 'w') as f:
                f.write(proc.stdout)
        else:
            # print on screen
            print('\n'+proc.stdout+'\n')
            print_ok('Done!')
        return Simulation(path=rundir, logname='gotm.log', configname='gotm.yaml')

    def run_batch(
            self,
            configs = None,
            ):
        """Run a batch of instances of the model with given configurations

        :configs: (dict-like) a dictionary with keys being the name of each instance and the values being the configuration for each instance

        """
        pass

#--------------------------------
# Simulation object
#--------------------------------

class Simulation:

    """A GOTM simulation

    """

    def __init__(
            self,
            path = '',
            logname = 'gotm.log',
            configname = 'gotm.yaml',
            ):
        """Initialization

        """
        if not os.path.isdir(path):
            print_error('Path {:s} not exist'.format(path))
        else:
            self.path = path
            self.log = path+'/'+logname
            self.config = path+'/'+configname
            self.data = path+'/gotm_out.nc'
            self.restart = path+'/restart.nc'

    def load_data(self, **kwargs):
        """Load data to xarray dataset

        :returns: (xarray.Dataset) simulation output data

        """
        # load z and zi
        with Dataset(self.data, 'r') as ncfile:
            nc_z =  ncfile.variables['z']
            nc_zi = ncfile.variables['zi']
            z = xr.DataArray(
                    nc_z[0,:,0,0],
                    dims=('z'),
                    coords={'z': nc_z[0,:,0,0]},
                    attrs={'long_name': nc_z.long_name, 'units': nc_z.units}
                    )
            zi = xr.DataArray(
                    nc_zi[0,:,0,0],
                    dims=('zi'),
                    coords={'zi': nc_zi[0,:,0,0]},
                    attrs={'long_name': nc_zi.long_name, 'units': nc_zi.units}
                    )
        # load other variables
        out = xr.load_dataset(
                self.data,
                drop_variables=['z', 'zi'],
                **kwargs,
                )
        out = out.assign_coords({
            'z': z,
            'zi': zi,
            })
        for var in out.data_vars:
            if 'z' in out.data_vars[var].dims:
                out.data_vars[var].assign_coords({'z':z})
            elif 'zi' in out.data_vars[var].dims:
                out.data_vars[var].assign_coords({'zi':zi})
        # return a reorderd view
        return out.transpose('z', 'zi', 'time', 'lon', 'lat')
