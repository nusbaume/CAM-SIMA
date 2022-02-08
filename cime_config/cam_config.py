"""
Location of CAM's "config" python data structure, which
is used to pass any needed data between the relevant CAM
"cime_config" scripts, and which stores all meta-data and
descriptions associated with the CAM configuration of a
CIME case.
"""

#----------------------------------------
# Import generic python libraries/modules
#----------------------------------------

import re
import sys
import argparse
import os.path

#-----------------------------------
# Import CAM-specific python modules
#-----------------------------------

# Import internal CAM configuration classes:
from cam_config_classes import ConfigInteger, ConfigString, ConfigList
from cam_config_classes import CamConfigValError, CamConfigTypeError

# Import build cache object:
from cam_build_cache import BuildCacheCAM # Re-build consistency cache

# Import fortran auto-generation routines:
from cam_autogen import generate_registry, generate_physics_suites
from cam_autogen import generate_init_routines

###############################################################################
# MAIN CAM CONFIGURE OBJECT
###############################################################################

class ConfigCAM:

    """
    Main CAM configuration object.

    Inputs to initalize class are:
    case                   -> CIME case that uses CAM
    logger                 -> Python logger object (ususally the CIME log)

    Doctests:

    1.  Check that "create_config" works properly:

    With a given integer value:
    >>> FCONFIG.create_config("test_int", "test object description", 5)
    >>> FCONFIG.get_value("test_int")
    5

    With a given string value:
    >>> FCONFIG.create_config("test_str", "test object description", "test_val")
    >>> FCONFIG.get_value("test_str")
    'test_val'

    With a given list value:
    >>> FCONFIG.create_config("test_list", "test object description", [1, 2])
    >>> FCONFIG.get_value("test_list")
    [1, 2]

    2.  Check that the same configure object can't be created twice:

    >>> FCONFIG.create_config("test_int", "test object description", 5)
    Traceback (most recent call last):
    ...
    cam_config_classes.CamConfigValError: ERROR:  The CAM config variable, 'test_int', already exists!  Any new config variable must be given a different name

    3.  Check that a configure object's given value must be either a string, integer or list:

    >>> FCONFIG.create_config("test_dict", "test_object_description", {"x": "y"})
    Traceback (most recent call last):
    ...
    cam_config_classes.CamConfigTypeError: ERROR:  The input value for new CAM config variable, 'test_dict', must be an integer, string, or list, not <class 'dict'>

    """

    def __init__(self, case, case_log):

        # pylint: disable=too-many-locals
        """
        Initalize configuration object
        and associated dictionary.
        """

        # Read in needed case variables
        atm_grid = case.get_value("ATM_GRID")               # Atmosphere (CAM) grid
        cam_config_opts = case.get_value("CAM_CONFIG_OPTS") # CAM configuration options
        case_nx = case.get_value("ATM_NX")                  # Number of x-dimension grid-points (longitudes)
        case_ny = case.get_value("ATM_NY")                  # Number of y-dimension grid-points (latitudes)
        comp_ocn = case.get_value("COMP_OCN")               # CESM ocean component
        exeroot = case.get_value("EXEROOT")                 # Model executable path
        nthrds = case.get_value("NTHRDS_ATM")               # Number of model OpenMP threads
        start_date = case.get_value("RUN_STARTDATE")        # Model simulation start date
        debug_case = case.get_value("DEBUG")                # Case debug flag

        # Save case variables needed for code auto-generation:
        self.__atm_root = case.get_value("COMP_ROOT_DIR_ATM")
        self.__caseroot = case.get_value("CASEROOT")
        self.__bldroot = os.path.join(exeroot, "atm", "obj")
        self.__atm_name = case.get_value("COMP_ATM")

        # Save CPP definitions as a list:
        self.__cppdefs = [x for x in case.get_value("CAM_CPPDEFS").split() if x]

        # If only "UNSET" is present in the list, then convert to
        # empty list:
        if len(self.__cppdefs) == 1 and "UNSET" in self.__cppdefs:
            self.__cppdefs = list()

        # The following translation is hard-wired for backwards compatibility
        # to support the differences between how the config_grids specifies the
        # atmosphere grid and how it is specified internally

        if atm_grid == 'ne30pg3':
            atm_grid = 'ne30np4.pg3'
        # End if

        # Level information for CAM is part of the atm grid name
        #    and must be stripped out
        match = re.match(r'(.+)z(\d+)', atm_grid)
        if match:
            atm_grid = match.groups()[0]
        # End if

        # Save user options as list
        user_config_opts = ConfigCAM.parse_config_opts(cam_config_opts)

        #-----------------------------------------------

        # Check if "-dyn" is specifed in user_config_opts
        user_dyn_opt = user_config_opts.dyn
        dyn_valid_vals = ["eul", "fv", "se", "fv3", "mpas", "none"]
        if user_dyn_opt == "none":
            # If so, then set the atmospheric grid to "null"
            atm_grid = "null"
            case_nx = "null"
            case_ny = "null"
        elif not user_dyn_opt:
            user_dyn_opt = None
        elif user_dyn_opt not in dyn_valid_vals:
            emsg = "ERROR: '{}' is not a valid dycore,".format(user_dyn_opt)
            emsg += "\n       Valid values: {}".format(dyn_valid_vals)
            raise CamConfigValError(emsg)
        # End if (no else, dyn is valid
        #-----------------------------------------------

        # Create empty dictonary
        self.__config_dict = dict()

        # Create namelist group list, starting with default namelist groups
        self.__nml_groups = ['cam_initfiles_nl',
                             'cam_logfile_nl',
                             'physics_nl',
                             'qneg_nl',
                             'vert_coord_nl',
                             'ref_pres_nl']

        #----------------------------------------------------
        # Set CAM start date (needed for namelist generation)
        #----------------------------------------------------

        # Remove dashes from CIME-provided start date:
        start_date_cam = start_date.replace('-','')

        self.create_config("ic_ymd", "Start date of model run.",
                           start_date_cam, is_nml_attr=True)

        #----------------------------------------------------
        # Set CAM debug flag (needed for namelist generation)
        #----------------------------------------------------

        #Please note that the boolean debug_case is converted to
        #an integer in order to match other namelist XML attribute
        #logicals.

        self.create_config("debug",
                           "Flag to check if debug mode is enabled.",
                           int(debug_case), is_nml_attr=True)

        #------------------------
        # Set CAM physics columns
        #------------------------

        # Physics column per chunk
        pcols_desc = "Maximum number of columns assigned to a thread."
        self.create_config("pcols", pcols_desc, 16,
                           (1, None), is_nml_attr=True)

        # Physics sub-columns
        psubcols_desc = "Maximum number of sub-columns in a column."
        self.create_config("psubcols", psubcols_desc, 1,
                           (1, None), is_nml_attr=True)

        #-----------------------
        # Set CAM dynamical core
        #-----------------------

        # Cam dynamics package (dynamical core) meta-data
        dyn_desc = "Dynamics package, which is set by the horizontal grid" \
                   " specified."

        # Cam horizontal grid meta-data
        hgrid_desc = "Horizontal grid specifier."

        # dynamics package source directories meta-data
        dyn_dirs_desc = ["Comma-separated list of local directories containing",
                         "dynamics package source code.",
                         "These directories are assumed to be located under",
                         "src/dynamics, with a slash ('/') indicating directory hierarchy."]

        # Create regex expressions to search for the different dynamics grids
        eul_grid_re = re.compile(r"T[0-9]+")                      # Eulerian dycore
        fv_grid_re = re.compile(r"[0-9][0-9.]*x[0-9][0-9.]*")     # FV dycore
        se_grid_re = re.compile(r"ne[0-9]+np[1-8](.*)(pg[1-9])?") # SE dycore
        fv3_grid_re = re.compile(r"C[0-9]+")                      # FV3 dycore
        mpas_grid_re = re.compile(r"mpasa[0-9]+")                 # MPAS dycore (not totally sure about this pattern)

        # Check if specified grid matches any of the pre-defined grid options.
        #   If so, then add both the horizontal grid and dynamical core
        #   to the configure object
        if fv_grid_re.match(atm_grid) is not None:
            # Dynamical core
            self.create_config("dyn", dyn_desc, "fv",
                               dyn_valid_vals, is_nml_attr=True)
            # Horizontal grid
            self.create_config("hgrid", hgrid_desc, atm_grid,
                               fv_grid_re, is_nml_attr=True)

        elif se_grid_re.match(atm_grid) is not None:
            # Dynamical core
            self.create_config("dyn", dyn_desc, "se",
                               dyn_valid_vals, is_nml_attr=True)
            # Horizontal grid
            self.create_config("hgrid", hgrid_desc, atm_grid,
                               se_grid_re, is_nml_attr=True)

            # Source code directories
            self.create_config("dyn_src_dirs", dyn_dirs_desc, ["se",os.path.join("se","dycore")],
                               valid_list_type="str")

            # Add SE namelist groups to nmlgen list
            self.__nml_groups.append("air_composition_nl")
            self.__nml_groups.append("dyn_se_nl")

            # Add required CPP definitons:
            self.add_cppdef("_MPI")
            self.add_cppdef("SPMD")

            # Add OpenMP CPP definitions, if needed:
            if nthrds > 1:
                self.add_cppdef("_OPENMP")

        elif fv3_grid_re.match(atm_grid) is not None:
            # Dynamical core
            self.create_config("dyn", dyn_desc, "fv3",
                               dyn_valid_vals, is_nml_attr=True)
            # Horizontal grid
            self.create_config("hgrid", hgrid_desc, atm_grid,
                               fv3_grid_re, is_nml_attr=True)

        elif mpas_grid_re.match(atm_grid) is not None:
            # Dynamical core
            self.create_config("dyn", dyn_desc, "mpas",
                               dyn_valid_vals, is_nml_attr=True)
            # Horizontal grid
            self.create_config("hgrid", hgrid_desc, atm_grid,
                               mpas_grid_re, is_nml_attr=True)

        elif eul_grid_re.match(atm_grid) is not None:
            # Dynamical core
            self.create_config("dyn", dyn_desc, "eul",
                               dyn_valid_vals, is_nml_attr=True)
            # Horizontal grid
            self.create_config("hgrid", hgrid_desc, atm_grid,
                               eul_grid_re, is_nml_attr=True)

            # If using the Eulerian dycore, then add wavenumber variables

            # Wavenumber variable descriptions
            trm_desc = "Maximum Fourier wavenumber."
            trn_desc = "Highest degree of the Legendre polynomials for m=0."
            trk_desc = "Highest degree of the associated Legendre polynomials."

            # Add variables to configure object
            self.create_config("trm", trm_desc, 1, (1, None))
            self.create_config("trn", trn_desc, 1, (1, None))
            self.create_config("trk", trk_desc, 1, (1, None))

        elif atm_grid == "null":
            # Dynamical core
            self.create_config("dyn", dyn_desc, "none",
                               dyn_valid_vals, is_nml_attr=True)
            # Atmospheric grid
            self.create_config("hgrid", hgrid_desc, atm_grid,
                               None, is_nml_attr=True)

            # Source code directories
            self.create_config("dyn_src_dirs", dyn_dirs_desc, ["none"],
                               valid_list_type="str")

        else:
            emsg = "ERROR: The specified CAM horizontal grid, '{}', "
            emsg += "does not match any known format."
            raise CamConfigValError(emsg.format(atm_grid))
        #End if

        # Extract dynamics option
        dyn = self.get_value("dyn")

        # If user-specified dynamics option is present,
        #    check that it matches the grid-derived value
        if user_dyn_opt is not None and user_dyn_opt != dyn:
            emsg = "ERROR:  User-specified dynamics option, '{}', "
            emsg += "does not match dycore expected from case grid: '{}'"
            raise CamConfigValError(emsg.format(user_dyn_opt, dyn))
        # End if

        #---------------------------------------
        # Set CAM grid variables (nlat and nlon)
        #---------------------------------------

        #Set horizontal dimension variables:
        if dyn == "se":

            # Determine location of "np" in atm_grid string:
            np_idx = atm_grid.find("np")

            #Determine location of "pg" in atm_grid string:
            pg_idx = atm_grid.find(".pg")

            # Extract cubed-sphere grid values from atm_grid/hgrid string:
            # Note that the string always starts with "ne".

            csne_val = int(atm_grid[2:np_idx])
            if pg_idx > -1:
                csnp_val = int(atm_grid[np_idx+2:pg_idx])
                npg_val  = int(atm_grid[pg_idx+3:])
            else:
                csnp_val = int(atm_grid[np_idx+2:])
                npg_val  = 0

            # Add number of elements along edge of cubed-sphere grid
            csne_desc = "Number of elements along one edge of a cubed sphere grid."
            self.create_config("csne", csne_desc, csne_val, is_nml_attr=True)

            # Add number of points on each cubed-sphere element edge
            csnp_desc = "Number of points on each edge of each element in a cubed sphere grid."
            self.create_config("csnp", csnp_desc, csnp_val)

            # Add number of CSLAM physics grid points:
            npg_desc = "Number of finite volume grid cells on each edge of" \
                       " each element in a cubed sphere grid."
            self.create_config("npg", npg_desc, npg_val, is_nml_attr=True)

            # Add number of points (NP) CPP definition:
            self.add_cppdef("NP", csnp_val)

        else:
            # Additional dyn value checks are not required,
            # as the "dyn_valid_vals" list in the "create_config" call
            # prevents non-supported dycores from being used, and all
            # dycores are lat/lon-based.

            # Add number of latitudes in grid to configure object
            nlat_desc = ["Number of unique latitude points in rectangular lat/lon grid.",
                         "Set to 1 (one) for unstructured grids."]
            self.create_config("nlat", nlat_desc, case_ny)

            # Add number of longitudes in grid to configure object
            nlon_desc = ["Number of unique longitude points in rectangular lat/lon grid.",
                         "Total number of columns for unstructured grids."]
            self.create_config("nlon", nlon_desc, case_nx)

        #---------------------------------------
        # Set initial and/or boundary conditions
        #---------------------------------------

        # Check if user specified Analytic Initial Conditions (ICs):
        if user_config_opts.analytic_ic:
            # Set "analytic_ic" to True (1):
            analy_ic_val = 1 #Use Analytic ICs

            # Add analytic_ic to namelist group list:
            self.__nml_groups.append("analytic_ic_nl")

            #Add new CPP definition:
            self.add_cppdef("ANALYTIC_IC")

        else:
            analy_ic_val = 0 #Don't use Analytic ICs

        analy_ic_desc = ["Switch to turn on analytic initial conditions for the dynamics state: ",
                         "0 => no ",
                         "1 => yes."]

        self.create_config("analytic_ic", analy_ic_desc,
                           analy_ic_val, [0, 1], is_nml_attr=True)

        #--------------------
        # Set ocean component
        #--------------------

        ocn_valid_vals = ["docn", "dom", "som", "socn",
                          "aquaplanet", "pop", "mom"]

        ocn_desc = ["The ocean model being used.",
                    "Valid values include prognostic ocean models (POP or MOM),",
                    "data ocean models (DOCN or DOM), a stub ocean (SOCN), ",
                    "and an aqua planet ocean (aquaplanet).",
                    "This does not impact how the case is built, only how",
                    "attributes are matched when searching for namelist defaults."]

        self.create_config("ocn", ocn_desc, comp_ocn,
                           ocn_valid_vals, is_nml_attr=True)

        phys_desc = ["A semicolon-separated list of physics suite definition "
                     "file (SDF) names.",
                     "To specify the Kessler and Held-Suarez suites as ",
                     "run time options, use '--physics-suites kessler;held_suarez_1994'."]

        self.create_config("physics_suites", phys_desc,
                           user_config_opts.physics_suites)

        #------------------------------------------------------------------
        # Set Fortran kinds for real-type variables in dynamics and physics
        #------------------------------------------------------------------

        kind_valid_vals = ["REAL32","REAL64"]

        #dycore kind:
        self.create_config("dyn_kind",
                           "Fortran kind used in dycore for type real.",
                           user_config_opts.dyn_kind, kind_valid_vals)

        #physics kind:
        self.create_config("phys_kind",
                           "Fortran kind used in physics for type real.",
                           user_config_opts.phys_kind, kind_valid_vals)

        #--------------------------------------------------------
        # Print CAM configure settings and values to debug logger
        #--------------------------------------------------------

        self.print_all(case_log)

    #+++++++++++++++++++++++
    # config_cam properties
    #+++++++++++++++++++++++

    # Create properties needed to return configure dictionary
    # and namelist groups list without underscores
    @property
    def config_dict(self):
        """Return the configure dictionary of this object."""
        return self.__config_dict

    @property
    def nml_groups(self):
        """Return the namelist groups list of this object."""
        return self.__nml_groups

    @property
    def cpp_defs(self):
        """Return the CPP definitions list of this object."""
        return self.__cppdefs

    #++++++++++++++++++++++
    # ConfigCAM functions
    #++++++++++++++++++++++

    @classmethod
    def parse_config_opts(cls, config_opts, test_mode=False):
        """Parse <config_opts> and return the results
        >>> ConfigCAM.parse_config_opts("", test_mode=True)
        Traceback (most recent call last):
        SystemExit: 2
        >>> ConfigCAM.parse_config_opts("--dyn se", test_mode=True)
        Traceback (most recent call last):
        SystemExit: 2
        >>> vlist(ConfigCAM.parse_config_opts("--physics-suites kessler"))
        [('analytic_ic', False), ('dyn', ''), ('dyn_kind', 'REAL64'), ('phys_kind', 'REAL64'), ('physics_suites', 'kessler')]
        >>> vlist(ConfigCAM.parse_config_opts("--physics-suites kessler --dyn se"))
        [('analytic_ic', False), ('dyn', 'se'), ('dyn_kind', 'REAL64'), ('phys_kind', 'REAL64'), ('physics_suites', 'kessler')]
        >>> vlist(ConfigCAM.parse_config_opts("--physics-suites kessler --dyn se --analytic_ic"))
        [('analytic_ic', True), ('dyn', 'se'), ('dyn_kind', 'REAL64'), ('phys_kind', 'REAL64'), ('physics_suites', 'kessler')]
        >>> vlist(ConfigCAM.parse_config_opts("--physics-suites kessler;musica"))
        [('analytic_ic', False), ('dyn', ''), ('dyn_kind', 'REAL64'), ('phys_kind', 'REAL64'), ('physics_suites', 'kessler;musica')]
        >>> ConfigCAM.parse_config_opts("--phys kessler musica", test_mode=True)
        Traceback (most recent call last):
        SystemExit: 2
        """
        cco_str = "CAM_CONFIG_OPTS"

        #Don't allow abbreviations if using python 3.5 or greater:
        if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 5):
            parser = argparse.ArgumentParser(description=cco_str,
                                             prog="ConfigCAM",
                                             epilog="Allowed values of "+cco_str)
        else:
            parser = argparse.ArgumentParser(description=cco_str,
                                             prog="ConfigCAM", allow_abbrev=False,
                                             epilog="Allowed values of "+cco_str)


        parser.add_argument("--physics-suites", "-physics-suites", type=str,
                            required=True, metavar='<CCPP_SDFs>',
                            help="""Semicolon-separated list of Physics Suite
                                 Definition Files (SDFs)""")
        parser.add_argument("--dyn", "-dyn", metavar='<dycore>',
                            type=str, required=False, default="",
                            help="""Name of dycore""")
        parser.add_argument("--analytic_ic", "-analytic_ic",
                            action='store_true', required=False,
                            help="""Flag to turn on Analytic Initial
                                 Conditions (ICs).""")
        parser.add_argument("--dyn_kind", "-dyn_kind",
                            type=str, required=False, default="REAL64",
                            help="""Fortran kind used in dycore for type real.""")
        parser.add_argument("--phys_kind", "-phys_kind",
                            type=str, required=False, default="REAL64",
                            help="""Fortran kind used in physics for type real.""")

        popts = [opt for opt in config_opts.split(" ") if opt]
        if test_mode:
            stderr_save = sys.stderr
            sys.stderr = sys.stdout
        # end if
        pargs = parser.parse_args(popts)
        if test_mode:
            sys.stderr = stderr_save
        # end if
        return pargs

    def create_config(self, name, desc, val, valid_vals=None,
                      valid_list_type=None, is_nml_attr=False):

        """
        Create new CAM "configure" object, and add it
        to the configure dictionary.
        """

        # Check for given value type
        if isinstance(val, int):
            # If integer, then call integer configure object
            conf_obj = ConfigInteger(name, desc, val,
                                     valid_vals, is_nml_attr=is_nml_attr)

        elif isinstance(val, str):
            # If string, then call string configure object
            conf_obj = ConfigString(name, desc, val,
                                    valid_vals, is_nml_attr=is_nml_attr)

        elif isinstance(val, list):
            # If list, then call list configure object
            conf_obj = ConfigList(name, desc, val,
                                  valid_type=valid_list_type,
                                  valid_vals=valid_vals)
        else:
            # If not an integer, string, or a list, then throw an error
            emsg = ("ERROR:  The input value for new CAM config variable, '{}', "
                    "must be an integer, string, or list, not {}")
            raise CamConfigTypeError(emsg.format(name, type(val)))

        # Next, check that object name isn't already in the config list
        if name in self.config_dict:
            # If so, then throw an error
            emsg = ("ERROR:  The CAM config variable, '{}', already exists! "
                    "Any new config variable must be given a different name")
            raise CamConfigValError(emsg.format(name))

        # If not, then add object to dictionary
        self.__config_dict[name] = conf_obj

    #++++++++++++++++++++++++

    def print_config(self, obj_name, case_log):

        """
        Print the value and description of a specified
        CAM configure object to the CIME debug log.
        """

        # Check that the given object name exists in the dictionary
        if obj_name in self.config_dict:
            obj = self.config_dict[obj_name]
        else:
            raise  CamConfigValError("ERROR:  Invalid configuration name, '{}'".format(obj_name))

        # Print variable to logger
        case_log.debug("{}".format(obj.desc))
        case_log.debug("{} = {}".format(obj.name, obj.value))

    #++++++++++++++++++++++++

    def print_all(self, case_log):

        """
        Print the names, descriptions, and values of all CAM
        configuration objects.
        """

        # Print separator
        case_log.debug("CAM configuration variables:")
        case_log.debug("-----------------------------")

        # Loop over config dictionary values
        for obj_name in self.config_dict:
            # Print variable to logger
            self.print_config(obj_name, case_log)

        # Also print CPP definitions, if any:
        if self.__cppdefs:
            case_log.debug("\nCAM CPP Defs: {}".format(" ".join(self.__cppdefs)))

        # Print additional separator (to help separate this output from
        #     additional CIME output)
        case_log.debug("-----------------------------")

    #++++++++++++++++++++++++

    def set_value(self, obj_name, val):

        """
        Set configure object's value to the value given.
        """

        # First, check that the given object name exists in the dictionary
        if obj_name in self.config_dict:
            obj = self.config_dict[obj_name]
        else:
            raise CamConfigValError("ERROR:  Invalid configuration name, '{}'".format(obj_name))

        # Next, check that the given value is either an integer or a string
        if not isinstance(val, (int, str)):
            emsg = ("ERROR:  Value provided for variable, '{}', "
                    "must be either an integer or a string."
                    "  Currently it is type {}")
            raise  CamConfigTypeError(emsg.format(obj_name, type(val)))

        # Finally, set configure object's value to the value given
        obj.set_value(val)

    #++++++++++++++++++++++++

    def add_cppdef(self, cppname, value=None):

        """
        Add a CPP definition value to be used during the
        building of the model.  An error is thrown if
        the CPP macro has already been defined.

        Check that add_cppdef works properly:
        >>> FCONFIG.add_cppdef("TEST"); FCONFIG.cpp_defs
        ['-DTEST_CPPDEF', '-DNEW_TEST=5', '-DTEST']

        Check that add_cppdef works properly with provided value:
        >>> FCONFIG.add_cppdef("COOL_VAR", 100); FCONFIG.cpp_defs
        ['-DTEST_CPPDEF', '-DNEW_TEST=5', '-DTEST', '-DCOOL_VAR=100']

        Check that a duplicate cppdef creates an error:
        >>> FCONFIG.add_cppdef("TEST_CPPDEF") # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        cam_config_classes.CamConfigValError: ERROR: CPP definition 'TEST_CPPDEF' has already been set

        Check that a duplicate cppdef creates an error even if an equals sign
        is present in the stored copy but not the passed variable:
        >>> FCONFIG.add_cppdef("NEW_TEST") # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        cam_config_classes.CamConfigValError: ERROR: CPP definition 'NEW_TEST' has already been set
        """

        #Create string to check if CPP definition is already present:
        check_str = r"-D"+cppname

        #Check if CPP definition name already exists in CPP string list.
        #This is done because a CPP definition should only be set once,
        #in order to avoid variable overwriting or other un-expected
        #compiler behaviors:
        if any([re.match(check_str+r"($|=)", cppdef.strip()) for cppdef in self.__cppdefs]):
            #If match is found, then raise an error:
            emsg = "ERROR: CPP definition '{}' has already been set"
            raise CamConfigValError(emsg.format(cppname.upper()))

        # Check if input value is a logical:
        if value is None:
            # Create CPP flag string with no equals sign:
            cpp_str = check_str
        else:
            # Create CPP definition flag string:
            cpp_str = "{}={}".format(check_str, value)

        # Add string to CPP definition list:
        self.__cppdefs.append(cpp_str)

    #++++++++++++++++++++++++

    def get_value(self, obj_name):

        """
        Return value for specified configure object.
        """

        # First check that the given object name exists in the dictionary
        if obj_name in self.config_dict:
            obj = self.config_dict[obj_name]
        else:
            raise  CamConfigValError("ERROR:  Invalid configuration name, '{}'".format(obj_name))

        # If it does, then return the object's value
        return obj.value

    #++++++++++++++++++++++++

    def generate_cam_src(self, gen_fort_indent):

        """
        Run CAM auto-generation functions, which
        check if the required Fortran source code
        and meta-data are present in the model bld
        directory and build cache, and if not,
        generates them based on CAM configure settings
        and the model registry file.
        """

        # Set SourceMods path:
        source_mods_dir = os.path.join(self.__caseroot, "SourceMods", "src.cam")

        # Set possible locations to search for generation routines
        # with the SourceMods directory searched first:
        data_path = os.path.join(self.__atm_root, "src", "data")
        data_search = [source_mods_dir, data_path]

        # Extract atm model config settings:
        dyn = self.get_value("dyn")
        phys_suites = self.get_value("physics_suites")

        #---------------------------------------------------------
        # Load a build cache, if available
        #---------------------------------------------------------
        build_cache = BuildCacheCAM(os.path.join(self.__bldroot,
                                                 "cam_build_cache.xml"))

        #---------------------------------------------------------
        # Create the physics derived data types using the registry
        #---------------------------------------------------------
        retvals = generate_registry(data_search, build_cache, self.__atm_root,
                                    self.__bldroot, source_mods_dir,
                                    dyn, gen_fort_indent)
        reg_dir, force_ccpp, reg_files, ic_names = retvals

        #Add registry path to config object:
        reg_dir_desc = "Location of auto-generated registry code."
        self.create_config("reg_dir", reg_dir_desc, reg_dir)

        #---------------------------------------------------------
        # Call SPIN (CCPP Framework) to generate glue code
        #---------------------------------------------------------
        retvals = generate_physics_suites(build_cache, self.__cppdefs,
                                          self.__atm_name, phys_suites,
                                          self.__atm_root, self.__bldroot,
                                          reg_dir, reg_files, source_mods_dir,
                                          force_ccpp)
        phys_dirs, force_init, cap_datafile, nl_groups, capgen_db = retvals
        # Add in the namelist groups from schemes
        self.__nml_groups.extend(nl_groups)

        #Convert physics directory list into a string:
        phys_dirs_str = ';'.join(phys_dirs)

        #Add physics directory paths to config object:
        phys_dirs_desc = "Locations of auto-generated CCPP physics codes."
        self.create_config("phys_dirs", phys_dirs_desc, phys_dirs_str)

        #---------------------------------------------------------
        # Create host model variable initialization routines
        #---------------------------------------------------------
        init_dir = generate_init_routines(build_cache, self.__bldroot,
                                          force_ccpp, force_init,
                                          source_mods_dir, gen_fort_indent,
                                          capgen_db, ic_names)

        #Add registry path to config object:
        init_dir_desc = "Location of auto-generated physics initilazation code."
        self.create_config("init_dir", init_dir_desc, init_dir)

        #--------------------------------------------------------------
        # write out the cache here as we have completed pre-processing
        #--------------------------------------------------------------
        build_cache.write()

    #++++++++++++++++++++++++

    def ccpp_phys_set(self, cam_nml_attr_dict, phys_nl_pg_dict):

        """
        Find the physics suite to run.

        If more than one physics suite is available,
        then make sure the user has specified a physics
        suite from the list of available suites.

        If exactly one physics suite is available,
        then make sure that either the user did not
        specify a suite or that they did specify a
        suite and that it matches the available suite.

        Inputs:

        cam_nml_attr_dict -> Dictionary of ParamGen (XML)
                             attribute values.

        phys_nl_pg_dict -> ParamGen data dictionary for
                           the "physics_nl" namelist group
        """

        #Extract physics suites list:
        phys_suites = self.get_value('physics_suites').split(';')

        #Determine current value of "physics_suite" namelist variable:
        phys_nl_val = phys_nl_pg_dict['physics_suite']['values'].strip()

        #Check if only one physics suite is listed:
        if len(phys_suites) == 1:
            #Check if "physics_suite" has been set by the user:
            if phys_nl_val != 'UNSET':
                #If so, then check that user-provided suite matches
                #suite in physics_suites config list:
                if phys_nl_val == phys_suites[0].strip():
                    #If so, then set attribute to phys_suites value:
                    cam_nml_attr_dict["phys_suite"] = phys_suites[0].strip()
                else:
                    #If not, then throw an error:
                    emsg  = "physics_suite specified in user_nl_cam, '{}', does not\n"
                    emsg += "match the suite listed in CAM_CONFIG_OPTS: '{}'"
                    raise CamConfigValError(emsg.format(user_nl_pg_dict['physics_suite'],
                                                        phys_suites[0]))

            else:
                #If not, then just set the attribute and nl value to phys_suites value:
                phys_nl_pg_dict['physics_suite']['values'] = phys_suites[0].strip()
                cam_nml_attr_dict["phys_suite"] = phys_suites[0].strip()

        else:
            #Check if "physics_suite" has been set by the user:
            if phys_nl_val != 'UNSET':
                #If so, then check if user-provided value is present in the
                #physics_suites config list:
                match_found = False
                for phys_suite in phys_suites:
                    if phys_nl_val == phys_suite.strip():
                        #If a match is found, then set attribute and leave loop:
                        cam_nml_attr_dict["phys_suite"] = phys_suite.strip()
                        match_found = True
                        break

                #Check that a match was found, if not, then throw an error:
                if not match_found:
                    emsg  = "physics_suite specified in user_nl_cam, '{}', doesn't match any suites\n"
                    emsg += "listed in CAM_CONFIG_OPTS: '{}'"
                    raise CamConfigValError(emsg.format(phys_nl_val,
                                                        self.get_value('physics_suites')))

            else:
                #If not, then throw an error, because one needs to be specified:
                emsg  = "No 'physics_suite' variable is present in user_nl_cam.\n"
                emsg += "This is required because more than one suite is listed\n"
                emsg += "in CAM_CONFIG_OPTS: '{}'"
                raise CamConfigValError(emsg.format(self.get_value('physics_suites')))


###############################################################################
#IGNORE EVERYTHING BELOW HERE UNLESS RUNNING TESTS ON CAM_CONFIG!
###############################################################################

#Call testing routine, if script is run directly
if __name__ == "__main__":

    # Import modules needed for testing
    import doctest
    import logging

    #--------------------------------------
    # Create fake case for Config_CAM tests
    #--------------------------------------

    class FakeCase:

        # pylint: disable=too-few-public-methods
        """
        Fake CIME case class with variables needed to test
        the "Config_CAM" object.
        """

        def __init__(self):


            # Create dictionary (so get_value works properly)
            self.conf_opts = {
                "ATM_GRID" : "f19_f19_mg17",
                "ATM_NX"   : 180,
                "ATM_NY"   : 90,
                "COMP_OCN" : "socn",
                "COMP_ATM" : "cam",
                "EXEROOT"  : "/some/made-up/path",
                "CASEROOT" : "/another/made-up/path",
                "CAM_CONFIG_OPTS" : "-dyn none --physics-suites adiabatic",
                "COMP_ROOT_DIR_ATM" : "/a/third/made-up/path",
                "CAM_CPPDEFS" : "-DTEST_CPPDEF -DNEW_TEST=5",
                "NTHRDS_ATM" : 1,
                "RUN_STARTDATE" : "101",
                "DEBUG" : False
                }

        def get_value(self, key):

            """
            Function used to return value
            from conf_opts dictionary,
            with the key as input.
            """

            val = self.conf_opts[key]

            return val


    def vlist(nspace):
        """Convert a namespace into an ordered list view"""
        vargs = vars(nspace)
        return [(x, vargs[x]) for x in sorted(vargs)]

    #-------------------------------------------
    # Create new "Config_CAM" object for testing
    #-------------------------------------------

    # Create new "fake" CIME case
    FCASE = FakeCase()

    # Create python logger object
    LOGGER = logging.getLogger("cam_config")

    # Create ConfigCAM object using "fake" CIME case and logger
    FCONFIG = ConfigCAM(FCASE, LOGGER)

    # Run doctests on this file's python objects
    OPTIONS = doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE
    TEST_SUCCESS = doctest.testmod(optionflags=OPTIONS)[0]

    # Exit script with error code matching number of failed tests:
    sys.exit(TEST_SUCCESS)

#############
# End of file
#############
