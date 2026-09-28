module cam_constituents

   use ccpp_kinds,                only: kind_phys
   use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t

   implicit none
   private

   ! Public system functions
   public :: cam_constituents_init
   ! Public accessor functions
   public :: const_name     ! Constituent standard name
   public :: const_longname
   public :: const_diag_name ! Constituent diagnostic (file output) name
   public :: const_molec_weight
   public :: const_get_index
   public :: const_is_advected
   public :: const_is_dry
   public :: const_is_moist
   public :: const_is_wet
   public :: const_is_thermo_active
   public :: const_is_water_species
   public :: const_set_thermo_active
   public :: const_set_water_species
   public :: const_qmin
   public :: const_set_qmin
   public :: const_mark_as_initialized ! Mark constituent initial value as set
   public :: const_is_initialized      ! Has constituent initial value been set?
   ! Public water tracer functions
   public :: num_water_tracer_constituents      ! Number of new water tracer constituents
   public :: register_water_tracer_constituents ! Instantiate the water tracer constituents
   public :: water_tracer_dycore_mapping        ! Water tracers needing initial values

   ! Private array of constituent properties (for property interface functions)
   type(ccpp_constituent_prop_ptr_t), pointer :: const_props(:) => NULL()

   ! Tracks constituents (by index) whose initial values have already been provided,
   ! e.g., read by the dycore on the dynamics grid, so that
   ! the initial conditions read does not overwrite them on the physics grid.
   ! phys_vars_init_check cannot track these because it only covers registry variables
   ! and not runtime constituents (which is why we have to use indices here:)
   logical, allocatable :: const_initialized(:)

   ! Total number of water tracer constituents, which is counted once the
   ! constituent table has been locked (see 'set_water_tracer_bulk_indices').
   ! No mapping of water tracers can ever hold more entries than this, so it
   ! is also the size which such mapping arrays are allocated to.
   integer, private :: num_water_tracers = 0

   ! Namelist variable
   ! Only allow initialization once
   logical, private :: initialized = .false.

   !> \section arg_table_cam_constituents  Argument Table
   !! \htmlinclude cam_constituents.html
   integer, public, protected :: num_advected = 0

   integer, public, protected :: num_constituents = 0

   !! Note: There are no <xxx>_name interfaces in function interfaces below
   !!       because use of this sort of interface is often for optional
   !!       constituents and there is no way to indicate a missing
   !!       constituent in these functions (e.g., a logical).

   interface const_is_advected
      module procedure const_is_advected_obj
      module procedure const_is_advected_index
   end interface const_is_advected

   interface const_is_dry
      module procedure const_is_dry_obj
      module procedure const_is_dry_index
   end interface const_is_dry

   interface const_is_moist
      module procedure const_is_moist_obj
      module procedure const_is_moist_index
   end interface const_is_moist

   interface const_is_wet
      module procedure const_is_wet_obj
      module procedure const_is_wet_index
   end interface const_is_wet

   interface const_is_thermo_active
      module procedure const_is_thermo_active_obj
      module procedure const_is_thermo_active_index
   end interface const_is_thermo_active

   interface const_is_water_species
      module procedure const_is_water_species_obj
      module procedure const_is_water_species_index
   end interface const_is_water_species

   interface const_set_thermo_active
      module procedure const_set_thermo_active_obj
      module procedure const_set_thermo_active_index
   end interface const_set_thermo_active

   interface const_set_water_species
      module procedure const_set_water_species_obj
      module procedure const_set_water_species_index
   end interface const_set_water_species

   interface const_qmin
      module procedure const_qmin_obj
      module procedure const_qmin_index
   end interface const_qmin

   interface const_set_qmin
      module procedure const_set_qmin_obj
      module procedure const_set_qmin_index
   end interface

   ! Private interfaces
   private :: check_index_bounds
   private :: concat_const_props
   private :: water_species_indices

CONTAINS

   !#######################################################################

   subroutine cam_constituents_init(cnst_prop_ptr, num_advect)
      use cam_abortutils, only: endrun, check_allocate
      use spmd_utils,     only: masterproc
      use cam_logfile,    only: iulog, debug_output
      use cam_logfile,    only: DEBUGOUT_VERBOSE

      ! Initialize module constituent variables
      type(ccpp_constituent_prop_ptr_t), pointer :: cnst_prop_ptr(:)
      integer, intent(in)                        :: num_advect

      !For log output:
      integer :: cnst_idx
      !For allocation:
      integer            :: iret
      character(len=256) :: errmsg

      if (initialized) then
         call endrun("cam_constituents_init: already initialized",            &
              file=__FILE__, line=__LINE__)
      end if
      const_props => cnst_prop_ptr
      num_advected = num_advect
      num_constituents = size(const_props)

      allocate(const_initialized(num_constituents), stat=iret, errmsg=errmsg)
      call check_allocate(iret, 'cam_constituents_init',                      &
           'const_initialized(num_constituents)', file=__FILE__,              &
           line=__LINE__, errmsg=errmsg)
      const_initialized = .false.

      initialized = .true.

      ! Now that the constituent table is locked, and so every constituent
      ! index is final, record which bulk water species each water tracer is
      ! tracking:
      call set_water_tracer_bulk_indices()

      !If log level is verbose, then print out
      !the names/order of all registered constituents:
      if ((debug_output >= DEBUGOUT_VERBOSE) .and. masterproc) then

         write(iulog,*) 'LIST OF REGISTERED CONSTITUENTS:'
         write(iulog,*) '********************************'
         write(iulog,*) ' Constituent index : Standard name : Advected (T or F)'
         do cnst_idx = 1, num_constituents
            write(iulog,'(I0,3A, L)') cnst_idx, ' : ', trim(const_name(cnst_idx)), ' : ', &
                                   const_is_advected(cnst_idx)
         end do
         write(iulog,*) '********************************'

      end if

   end subroutine cam_constituents_init

   !#######################################################################

   subroutine set_water_tracer_bulk_indices()
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str
      use ccpp_constituent_prop_mod, only: stdname_len

      ! Set the 'bulk_water_index' property of every water tracer constituent
      ! to the constituent index of the bulk water species it tracks, which
      ! is found by looking up the tracer's 'bulk_water_name' property.
      ! This must be called after the constituent table has been locked, as
      ! constituent indices are not final until then.
      !
      ! The module-level count of water tracer constituents,
      ! <num_water_tracers>, is also set here, as every constituent is
      ! already being checked for being a water tracer.

      ! Local variables
      integer                     :: tracer_idx
      integer                     :: bulk_idx
      integer                     :: err_code
      logical                     :: is_tracer
      character(len=256)          :: err_msg
      character(len=stdname_len)  :: bulk_name
      character(len=*), parameter :: subname = 'set_water_tracer_bulk_indices: '

      num_water_tracers = 0

      do tracer_idx = 1, num_constituents

         ! Only water tracers track a bulk water species:
         call const_props(tracer_idx)%is_water_tracer(is_tracer, err_code,    &
              err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if
         if (.not. is_tracer) then
            cycle
         end if

         num_water_tracers = num_water_tracers + 1

         ! Each water tracer was registered with the standard name of the bulk
         ! water species it tracks, so look that constituent up by name:
         call const_props(tracer_idx)%bulk_water_name(bulk_name, err_code,    &
              err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if
         if (len_trim(bulk_name) == 0) then
            call endrun(subname//"water tracer '"//                           &
                 trim(const_name(tracer_idx))//"' has no 'bulk_water_name' "//&
                 "property set", file=__FILE__, line=__LINE__)
         end if

         call const_get_index(trim(bulk_name), bulk_idx, abort=.true.,        &
              caller=subname)

         ! Note that this will fail if the index has already been set:
         call const_props(tracer_idx)%set_bulk_water_index(bulk_idx,          &
              err_code, err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if

      end do

   end subroutine set_water_tracer_bulk_indices

   !#######################################################################

   logical function check_index_bounds(const_ind, subname)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Return the standard name of the constituent at <const_ind>.
      ! Dummy arguments
      integer,          intent(in) :: const_ind
      character(len=*), intent(in) :: subname
      ! Local variables
      integer            :: err_code
      character(len=256) :: err_msg

      if (const_ind < LBOUND(const_props, 1)) then
         call endrun(subname//"index ("//to_str(const_ind)//") out of "//      &
              "bounds, lower bound is "//to_str(LBOUND(const_props, 1)),      &
              file=__FILE__, line=__LINE__)
         check_index_bounds = .false. ! safety in case abort becomes optionsl
      else if (const_ind > UBOUND(const_props, 1)) then
         call endrun(subname//"index ("//to_str(const_ind)//") out of "//      &
              "bounds, upper bound is "//to_str(UBOUND(const_props, 1)),      &
              file=__FILE__, line=__LINE__)
         check_index_bounds = .false. ! safety in case abort becomes optionsl
      else
         check_index_bounds = .true.
      end if

   end function check_index_bounds

   !#######################################################################

   subroutine const_mark_as_initialized(const_ind)

      ! Mark the constituent at <const_ind> as having had its initial value
      ! set (e.g., by the dycore on the dyn grid for advected constituents),
      ! so that the initial conditions read leaves it alone.

      ! Dummy argument
      integer, intent(in)         :: const_ind
      ! Local variable
      character(len=*), parameter :: subname = 'const_mark_as_initialized: '

      if (check_index_bounds(const_ind, subname)) then
         const_initialized(const_ind) = .true.
      end if

   end subroutine const_mark_as_initialized

   !#######################################################################

   logical function const_is_initialized(const_ind)

      ! Return whether the initial value of the constituent at <const_ind>
      ! has already been set (see const_mark_as_initialized).

      ! Dummy argument
      integer, intent(in)         :: const_ind
      ! Local variable
      character(len=*), parameter :: subname = 'const_is_initialized: '

      const_is_initialized = .false.
      if (check_index_bounds(const_ind, subname)) then
         const_is_initialized = const_initialized(const_ind)
      end if

   end function const_is_initialized

   !#######################################################################

   function const_name(const_ind)
      use cam_abortutils,       only: endrun
      use string_utils,         only: to_str
      use phys_vars_init_check, only: std_name_len

      ! Return the standard name of the constituent at <const_ind>.
      ! Dummy arguments
      integer, intent(in)         :: const_ind
      character(len=std_name_len) :: const_name
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_name: '

      if (check_index_bounds(const_ind, subname)) then
         call const_props(const_ind)%standard_name(const_name,                &
              err_code, err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if
      end if

   end function const_name

   !#######################################################################

   function const_longname(const_ind)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str
      use shr_kind_mod,   only: CL => shr_kind_cl

      ! Return the long name of the constituent at <const_ind>.
      ! Dummy arguments
      integer, intent(in)         :: const_ind
      character(len=CL)           :: const_longname
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_longname: '

      if (check_index_bounds(const_ind, subname)) then
         call const_props(const_ind)%long_name(const_longname,                &
              err_code, err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if
      end if

   end function const_longname

   !#######################################################################
   function const_diag_name(const_ind)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str
      use shr_kind_mod,   only: CL => shr_kind_cl

      ! Return the diagnostic name of the constituent at <const_ind>.
      ! Dummy arguments
      integer, intent(in)         :: const_ind
      character(len=CL)           :: const_diag_name
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_diag_name: '

      if (check_index_bounds(const_ind, subname)) then
         call const_props(const_ind)%diagnostic_name(const_diag_name,        &
              err_code, err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if
      end if

   end function const_diag_name

   !#######################################################################

   function const_molec_weight(const_ind)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Return the long name of the constituent at <const_ind>.
      ! Dummy arguments
      integer, intent(in) :: const_ind
      real(kind_phys)     :: const_molec_weight
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_molec_weight: '

      if (check_index_bounds(const_ind, subname)) then
         call const_props(const_ind)%molar_mass(const_molec_weight,         &
              err_code, err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if
      end if

   end function const_molec_weight

   !#######################################################################

   subroutine const_get_index(name, cindex, abort, warning, caller)
      ! from to_be_ccppized utility routine
      use ccpp_const_utils,     only: ccpp_const_get_idx

      use shr_kind_mod,         only: CX => SHR_KIND_CX
      use cam_abortutils,       only: endrun
      use cam_logfile,          only: iulog
      use phys_vars_init_check, only: std_name_len
      use string_utils,         only: stringify

      ! Get the index of a constituent with standard name, <name>.
      ! Setting optional <abort> argument to .false. returns control to
      !    the caller if the constituent name is not found.
      ! Default behavior is to call endrun when name is not found.
      ! If the optional argument, <caller>, is passed, it is used
      !    instead of <subname> in messages.

      !-----------------------------Arguments---------------------------------
      character(len=*),           intent(in)  :: name    ! constituent name
      integer,                    intent(out) :: cindex  ! global constituent index
      logical,          optional, intent(in)  :: abort   ! flag controlling abort
      logical,          optional, intent(in)  :: warning ! flag controlling warning
      character(len=*), optional, intent(in)  :: caller  ! calling routine

      !---------------------------Local workspace-----------------------------
      logical                     :: warning_on_error
      logical                     :: abort_on_error
      integer                     :: errcode
      character(len=CX)           :: errmsg
      character(len=*), parameter :: subname = 'const_get_index: '
      !-----------------------------------------------------------------------

      call ccpp_const_get_idx(const_props, name, cindex, errmsg, errcode)

      if (errcode /= 0) then
         call endrun(subname//"Error "//stringify((/errcode/))//": "//           &
                 trim(errmsg), file=__FILE__, line=__LINE__)
      endif

      if (cindex == -1) then
         ! Unrecognized name, set an error return and possibly abort
         cindex = -1
         if (present(abort)) then
            abort_on_error = abort
         else
            abort_on_error = .true.
         end if
         if (present(warning)) then
            warning_on_error = warning
         else
            warning_on_error = .true.
         end if

         if (abort_on_error) then
            if (present(caller)) then
               write(iulog, *) caller, 'FATAL: name:', trim(name),            &
                    ' not found in constituent table'
               call endrun(caller//'FATAL: name ('//trim(name)//') not found')
            else
               write(iulog, *) subname, 'FATAL: name:', trim(name),           &
                    ' not found in constituent table'
               call endrun(subname//'FATAL: name ('//trim(name)//') not found')
            end if
         else
            if (warning_on_error) then
               if (present(caller)) then
                  write(iulog, *) caller, 'WARNING: name:', trim(name),          &
                       ' not found in constituent table'
               else
                  write(iulog, *) subname, 'WARNING: name:', trim(name),         &
                       ' not found in constituent table'
               end if
            end if
         end if
      end if

   end subroutine const_get_index

   !#######################################################################

   logical function const_is_advected_obj(const_obj)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Return .true. if the constituent object, <const_obj>, is advected
      ! Dummy argument
      type(ccpp_constituent_prop_ptr_t), intent(in) :: const_obj
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_is_advected_obj: '

      call const_obj%is_advected(const_is_advected_obj, err_code, err_msg)
      if (err_code /= 0) then
         call endrun(subname//"Error "//to_str(err_code)//": "//           &
              trim(err_msg), file=__FILE__, line=__LINE__)
      end if

   end function const_is_advected_obj

   !#######################################################################

   logical function const_is_advected_index(const_ind)

      ! Return .true. if the constituent at <index> is advected
      ! Dummy argument
      integer, intent(in) :: const_ind
      ! Local variable
      character(len=*), parameter :: subname = 'const_is_advected_index: '

      if (check_index_bounds(const_ind, subname)) then
         const_is_advected_index = const_is_advected(const_props(const_ind))
      end if

   end function const_is_advected_index

   !#######################################################################

   logical function const_is_dry_obj(const_obj)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Return .true. if the constituent object, <const_obj>, is dry
      ! Dummy argument
      type(ccpp_constituent_prop_ptr_t), intent(in) :: const_obj
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_is_dry_obj: '

      call const_obj%is_dry(const_is_dry_obj, err_code, err_msg)
      if (err_code /= 0) then
         call endrun(subname//"Error "//to_str(err_code)//": "//           &
              trim(err_msg), file=__FILE__, line=__LINE__)
      end if

   end function const_is_dry_obj

   !#######################################################################

   logical function const_is_dry_index(const_ind)

      ! Return .true. if the constituent at <index> is dry
      ! Dummy argument
      integer, intent(in) :: const_ind
      ! Local variable
      character(len=*), parameter :: subname = 'const_is_dry_index: '

      if (check_index_bounds(const_ind, subname)) then
         const_is_dry_index = const_is_dry(const_props(const_ind))
      end if

   end function const_is_dry_index

   !#######################################################################

   logical function const_is_moist_obj(const_obj)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Return .true. if the constituent object, <const_obj>, is moist
      ! Dummy argument
      type(ccpp_constituent_prop_ptr_t), intent(in) :: const_obj
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_is_moist_obj: '

      call const_obj%is_moist(const_is_moist_obj, err_code, err_msg)
      if (err_code /= 0) then
         call endrun(subname//"Error "//to_str(err_code)//": "//           &
              trim(err_msg), file=__FILE__, line=__LINE__)
      end if

   end function const_is_moist_obj

   !#######################################################################

   logical function const_is_moist_index(const_ind)

      ! Return .true. if the constituent at <index> is moist
      ! Dummy argument
      integer, intent(in) :: const_ind
      ! Local variable
      character(len=*), parameter :: subname = 'const_is_moist_index: '

      if (check_index_bounds(const_ind, subname)) then
         const_is_moist_index = const_is_moist(const_props(const_ind))
      end if

   end function const_is_moist_index

   !#######################################################################

   logical function const_is_wet_obj(const_obj)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Return .true. if the constituent object, <const_obj>, is wet
      ! Dummy argument
      type(ccpp_constituent_prop_ptr_t), intent(in) :: const_obj
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_is_wet_obj: '

      call const_obj%is_wet(const_is_wet_obj, err_code, err_msg)
      if (err_code /= 0) then
         call endrun(subname//"Error "//to_str(err_code)//": "//           &
              trim(err_msg), file=__FILE__, line=__LINE__)
      end if

   end function const_is_wet_obj

   !#######################################################################

   logical function const_is_wet_index(const_ind)

      ! Return .true. if the constituent at <index> is wet
      ! Dummy argument
      integer, intent(in) :: const_ind
      ! Local variable
      character(len=*), parameter :: subname = 'const_is_wet_index: '

      if (check_index_bounds(const_ind, subname)) then
         const_is_wet_index = const_is_wet(const_props(const_ind))
      end if

   end function const_is_wet_index

   !#######################################################################

   logical function const_is_thermo_active_obj(const_obj)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Return .true. if the constituent object, <const_obj>, is
      ! thermodynamically-active
      ! Dummy argument
      type(ccpp_constituent_prop_ptr_t), intent(in) :: const_obj
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_is_thermo_active_obj: '

      call const_obj%is_thermo_active(const_is_thermo_active_obj, err_code, err_msg)
      if (err_code /= 0) then
         call endrun(subname//"Error "//to_str(err_code)//": "//           &
              trim(err_msg), file=__FILE__, line=__LINE__)
      end if

   end function const_is_thermo_active_obj

   !#######################################################################

   logical function const_is_thermo_active_index(const_ind)

      ! Return .true. if the constituent at <index> is
      ! thermodynamically-active
      ! Dummy argument
      integer, intent(in) :: const_ind
      ! Local variable
      character(len=*), parameter :: subname = 'const_is_thermo_active_index: '

      if (check_index_bounds(const_ind, subname)) then
         const_is_thermo_active_index = const_is_thermo_active(const_props(const_ind))
      end if

   end function const_is_thermo_active_index

   !#######################################################################

   logical function const_is_water_species_obj(const_obj)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Return .true. if the constituent object, <const_obj>, is
      ! a type (species) of water
      ! Dummy argument
      type(ccpp_constituent_prop_ptr_t), intent(in) :: const_obj
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_is_water_species_obj: '

      call const_obj%is_water_species(const_is_water_species_obj, err_code, err_msg)
      if (err_code /= 0) then
         call endrun(subname//"Error "//to_str(err_code)//": "//           &
              trim(err_msg), file=__FILE__, line=__LINE__)
      end if

   end function const_is_water_species_obj

   !#######################################################################

   logical function const_is_water_species_index(const_ind)

      ! Return .true. if the constituent at <index> is
      ! a type (species) of water
      ! Dummy argument
      integer, intent(in) :: const_ind
      ! Local variable
      character(len=*), parameter :: subname = 'const_is_water_species_index: '

      if (check_index_bounds(const_ind, subname)) then
         const_is_water_species_index = const_is_water_species(const_props(const_ind))
      end if

   end function const_is_water_species_index

   !#######################################################################

   subroutine const_set_thermo_active_obj(const_obj, thermo_active)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Set the value for the 'thermo_active' property for the constituent
      !object, <const_obj>.
      ! Dummy argument
      type(ccpp_constituent_prop_ptr_t), intent(inout) :: const_obj
      logical, intent(in)                              :: thermo_active
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_set_thermo_active_obj: '

      call const_obj%set_thermo_active(thermo_active, err_code, err_msg)
      if (err_code /= 0) then
         call endrun(subname//"Error "//to_str(err_code)//": "//           &
              trim(err_msg), file=__FILE__, line=__LINE__)
      end if

   end subroutine const_set_thermo_active_obj

   !#######################################################################

   subroutine const_set_thermo_active_index(const_ind, thermo_active)

      ! Set the value for the 'thermo_active' property for the constituent
      !object index, <const_ind>.
      ! Dummy argument
      integer, intent(in) :: const_ind
      logical, intent(in) :: thermo_active
      ! Local variable
      character(len=*), parameter :: subname = 'const_set_thermo_active_index: '

      if (check_index_bounds(const_ind, subname)) then
         call const_set_thermo_active(const_props(const_ind), thermo_active)
      end if

   end subroutine const_set_thermo_active_index

   !#######################################################################

   subroutine const_set_water_species_obj(const_obj, water_species)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Set the value for the 'water_species' property for the constituent
      !object, <const_obj>.
      ! Dummy argument
      type(ccpp_constituent_prop_ptr_t), intent(inout) :: const_obj
      logical, intent(in)                              :: water_species
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_set_water_species_obj: '

      call const_obj%set_water_species(water_species, err_code, err_msg)
      if (err_code /= 0) then
         call endrun(subname//"Error "//to_str(err_code)//": "//           &
              trim(err_msg), file=__FILE__, line=__LINE__)
      end if

   end subroutine const_set_water_species_obj

   !#######################################################################

   subroutine const_set_water_species_index(const_ind, water_species)

      ! Set the value for the 'water_species' property for the constituent
      !object index, <const_ind>.
      ! Dummy argument
      integer, intent(in) :: const_ind
      logical, intent(in) :: water_species
      ! Local variable
      character(len=*), parameter :: subname = 'const_set_water_species_index: '

      if (check_index_bounds(const_ind, subname)) then
         call const_set_water_species(const_props(const_ind), water_species)
      end if

   end subroutine const_set_water_species_index

   !#######################################################################

   real(kind_phys) function const_qmin_obj(const_obj)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Return the minimum allowed mixing ratio for, <const_obj>
      ! Dummy argument
      type(ccpp_constituent_prop_ptr_t), intent(in) :: const_obj
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_qmin_obj: '

      call const_obj%minimum(const_qmin_obj, err_code, err_msg)
      if (err_code /= 0) then
         call endrun(subname//"Error "//to_str(err_code)//": "//           &
              trim(err_msg), file=__FILE__, line=__LINE__)
      end if

   end function const_qmin_obj

   !#######################################################################

   real(kind_phys) function const_qmin_index(const_ind)

      ! Return the minimum allowed mxing ratio for the constituent at <index>
      ! Dummy argument
      integer, intent(in) :: const_ind
      ! Local variable
      character(len=*), parameter :: subname = 'const_qmin_index: '

      if (check_index_bounds(const_ind, subname)) then
         const_qmin_index = const_qmin(const_props(const_ind))
      end if

   end function const_qmin_index

   !#######################################################################

   subroutine const_set_qmin_obj(const_obj, qmin_val)
      use cam_abortutils, only: endrun
      use string_utils,   only: to_str

      ! Set the minimum value property for the constituent
      !object, <const_obj>.
      ! Dummy argument
      type(ccpp_constituent_prop_ptr_t), intent(inout) :: const_obj
      real(kind_phys),                   intent(in)    :: qmin_val
      ! Local variables
      integer                     :: err_code
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'const_set_qmin_obj: '

      call const_obj%set_minimum(qmin_val, err_code, err_msg)
      if (err_code /= 0) then
         call endrun(subname//"Error "//to_str(err_code)//": "//           &
              trim(err_msg), file=__FILE__, line=__LINE__)
      end if

   end subroutine const_set_qmin_obj

   !#######################################################################

   subroutine const_set_qmin_index(const_ind, qmin_val)

      ! Set the value for the minimu value property for the constituent
      !object index, <const_ind>.
      ! Dummy argument
      integer, intent(in)         :: const_ind
      real(kind_phys), intent(in) :: qmin_val
      ! Local variable
      character(len=*), parameter :: subname = 'const_set_qmin_index: '

      if (check_index_bounds(const_ind, subname)) then
         call const_set_qmin(const_props(const_ind), qmin_val)
      end if

   end subroutine const_set_qmin_index

   !#######################################################################

   subroutine concat_const_props(props_a, props_b, all_props)
      use cam_abortutils,            only: check_allocate
      use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t

      ! Return, in <all_props>, the concatenation of <props_a> and <props_b>.
      !
      ! The copy is done one element at a time so that the type's defined
      ! assignments are copied correclty.

      ! Dummy arguments
      type(ccpp_constituent_properties_t),              intent(in)  :: props_a(:)
      type(ccpp_constituent_properties_t),              intent(in)  :: props_b(:)
      type(ccpp_constituent_properties_t), allocatable, intent(out) :: all_props(:)
      ! Local variables
      integer                     :: idx
      integer                     :: size_a
      integer                     :: size_b
      integer                     :: iret
      character(len=512)          :: alloc_msg
      character(len=*), parameter :: subname = 'concat_const_props: '

      ! Determine size of input arrays:
      size_a = size(props_a)
      size_b = size(props_b)

      allocate(all_props(size_a + size_b), stat=iret, errmsg=alloc_msg)
      call check_allocate(iret, subname, 'all_props(size_a + size_b)',  &
           file=__FILE__, line=__LINE__, errmsg=alloc_msg)

      do idx = 1, size_a
         all_props(idx) = props_a(idx)
      end do
      do idx = 1, size_b
         all_props(size_a + idx) = props_b(idx)
      end do

   end subroutine concat_const_props

   !#######################################################################

   subroutine water_species_indices(all_props, species_idx, num_species)
      use cam_abortutils,            only: endrun, check_allocate
      use string_utils,              only: to_str
      use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
      use ccpp_constituent_prop_mod, only: stdname_len

      ! Return the indices, in <species_idx>, of every entry of <all_props>
      ! whose 'water_species' property is set, along with the number of such
      ! entries, <num_species>.
      !
      ! <all_props> holds the constituents the host is adding itself followed
      ! by the constituents the physics registered during the CCPP register
      ! phase (see 'ccpp_scheme_const_properties'), the latter reported
      ! verbatim and in registration order.  The host and the physics, or two
      ! schemes in the same suite, may legitimately register the same
      ! constituent, so repeated standard names are only reported once here.
      !
      ! <species_idx> is allocated to the size of <all_props>, so only its
      ! first <num_species> entries are meaningful.

      ! Dummy arguments
      type(ccpp_constituent_properties_t), intent(in)  :: all_props(:)
      integer, allocatable,                intent(out) :: species_idx(:)
      integer,                             intent(out) :: num_species
      ! Local variables
      integer                     :: prop_idx
      integer                     :: props_size
      integer                     :: iret
      integer                     :: err_code
      logical                     :: is_water
      character(len=256)          :: err_msg
      character(len=512)          :: alloc_msg
      character(len=stdname_len)  :: std_name
      character(len=stdname_len), allocatable :: species_names(:)
      character(len=*), parameter :: subname = 'water_species_indices: '

      ! Determine total number of already-known constituents:
      props_size = size(all_props)

      ! Allocate water species arrays:
      allocate(species_idx(props_size), stat=iret, errmsg=alloc_msg)
      call check_allocate(iret, subname, 'species_idx(props_size)',            &
           file=__FILE__, line=__LINE__, errmsg=alloc_msg)
      allocate(species_names(props_size), stat=iret, errmsg=alloc_msg)
      call check_allocate(iret, subname, 'species_names(props_size)',          &
           file=__FILE__, line=__LINE__, errmsg=alloc_msg)

      ! Find total number of registered water constituents and their indices:
      num_species = 0
      do prop_idx = 1, props_size
         call all_props(prop_idx)%is_water_species(is_water, err_code,        &
              err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if
         if (.not. is_water) then
            cycle
         end if

         call all_props(prop_idx)%standard_name(std_name, err_code, err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if

         ! Ignore a constituent that was already registered:
         if (any(species_names(1:num_species) == std_name)) then
            cycle
         end if

         num_species = num_species + 1
         species_idx(num_species)   = prop_idx
         species_names(num_species) = std_name
      end do

   end subroutine water_species_indices

   !#######################################################################

   integer function num_water_tracer_constituents(phys_scheme_const_props,    &
        host_props)
      use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
      use shr_wtracers_mod,          only: shr_wtracers_initialized
      use shr_wtracers_mod,          only: shr_wtracers_present
      use shr_wtracers_mod,          only: shr_wtracers_get_num_tracers

      ! Return the total number of new constituents that are needed to carry
      ! water tracers, which is the number of water tracers requested by the
      ! CESM/CAM-SIMA times the number of distinct constituents that were
      ! registered as water species.  Return zero if either count is zero.
      !
      ! <phys_scheme_const_props> is the list of constituents registered by
      ! the physics during the CCPP register phase, and <host_props> is the list of
      ! constituents the host is adding itself (i.e. water vapor when the
      ! physics did not ask for it).
      !

      ! Dummy arguments
      type(ccpp_constituent_properties_t), intent(in) :: phys_scheme_const_props(:)
      type(ccpp_constituent_properties_t), intent(in) :: host_props(:)
      ! Local variables
      integer              :: num_tracers
      integer              :: num_species
      integer, allocatable :: species_idx(:)
      type(ccpp_constituent_properties_t), allocatable :: all_props(:)

      num_water_tracer_constituents = 0

      ! Determine whether water tracers were set for this CAM-SIMA run:
      if (.not. shr_wtracers_initialized()) then
         return
      end if
      if (.not. shr_wtracers_present()) then
         return
      end if
      num_tracers = shr_wtracers_get_num_tracers()

      ! Determine how many registered constituents are water species.  Note
      ! that the 'water_species' property has to have been set at
      ! registration time to be seen here:
      call concat_const_props(host_props, phys_scheme_const_props, all_props)
      call water_species_indices(all_props, species_idx, num_species)
      if (num_species < 1) then
         return
      end if

      num_water_tracer_constituents = num_tracers * num_species

   end function num_water_tracer_constituents

   !#######################################################################

   subroutine register_water_tracer_constituents(phys_scheme_const_props,     &
        host_consts, first_index)
      use cam_abortutils,            only: endrun
      use spmd_utils,                only: masterproc
      use string_utils,              only: to_str
      use shr_kind_mod,              only: CL => shr_kind_cl
      use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
      use ccpp_constituent_prop_mod, only: stdname_len, kphys_unassigned
      use shr_wtracers_mod,          only: shr_wtracers_initialized
      use shr_wtracers_mod,          only: shr_wtracers_present
      use shr_wtracers_mod,          only: shr_wtracers_get_num_tracers
      use shr_wtracers_mod,          only: shr_wtracers_get_name
      use shr_wtracers_mod,          only: shr_wtracers_get_initial_ratio
      use shr_wtracers_mod,          only: WTRACER_NAME_MAXLEN

      ! Instantiate, in <host_consts> starting at index <first_index>, one new
      ! constituent for every (water tracer, registered water species) pair.
      ! Each new constituent carries the properties of the water species it
      ! tracks, with the tracer name prepended to the standard, diagnostic and
      ! long names, with the 'water_tracer' property set, with the
      ! prescribed ratio taken from the CESM-provided initial ratio, and with
      ! 'bulk_water_name' set to the standard name of the tracked species
      ! itself, so each tracer records which bulk water constituent it
      ! follows.
      !
      ! Water species are taken both from <phys_scheme_const_props>, the
      ! constituents the physics registered, and from
      ! <host_consts(1:first_index-1)>, the constituents the host already
      ! added itself, so that a host-registered water species (e.g., water
      ! vapor) gets water tracers too.
      !
      ! <host_consts> must already be allocated with room for the
      ! 'num_water_tracer_constituents' new entries, and the constituents
      ! object must not yet have been registered and locked.
      !
      ! Note that the new constituents are deliberately *not* marked as water
      ! species: schemes such as dme_adjust and geopotential_temp sum every
      ! thermodynamically active water species as real water, and a tracer
      ! counted there would double count the atmosphere's moisture.  The
      ! 'water_tracer' property is what identifies these constituents.

      ! Dummy arguments
      type(ccpp_constituent_properties_t), intent(in)    :: phys_scheme_const_props(:)
      type(ccpp_constituent_properties_t), intent(inout) :: host_consts(:)
      integer,                             intent(in)    :: first_index

      ! Local variables
      type(ccpp_constituent_properties_t), allocatable :: all_props(:)
      integer                     :: num_tracers
      integer                     :: num_species
      integer                     :: num_new
      integer                     :: tracer_idx
      integer                     :: species_num
      integer                     :: prop_idx
      integer                     :: host_idx
      integer                     :: err_code
      integer, allocatable        :: species_idx(:)
      logical                     :: advected
      logical                     :: is_dry
      logical                     :: is_moist
      logical                     :: is_wet
      real(kind_phys)             :: min_val
      real(kind_phys)             :: molar_mass
      real(kind_phys)             :: default_val
      real(kind_phys)             :: ratio_val
      character(len=256)          :: err_msg
      character(len=stdname_len)  :: std_name
      character(len=CL)           :: long_name
      character(len=CL)           :: diag_name
      character(len=CL)           :: units
      character(len=CL)           :: vert_dim
      character(len=5)            :: mix_type
      character(len=WTRACER_NAME_MAXLEN) :: tracer_name
      character(len=*), parameter :: subname = 'register_water_tracer_constituents: '

      ! Nothing to do if there are no water tracers:
      if (.not. shr_wtracers_initialized()) then
         return
      end if
      if (.not. shr_wtracers_present()) then
         return
      end if
      num_tracers = shr_wtracers_get_num_tracers()

      ! Check provided 'first_index' lower-bound:
      if (first_index < 1) then
         call endrun(subname//"first_index ("//to_str(first_index)//          &
              ") must be positive", file=__FILE__, line=__LINE__)
      end if

      ! Everything before <first_index> is a constituent the host already
      ! added, so scan those alongside the physics-registered constituents:
      call concat_const_props(host_consts(1:first_index-1),                   &
           phys_scheme_const_props, all_props)
      call water_species_indices(all_props, species_idx, num_species)
      if (num_species < 1) then
         return
      end if

      ! Make sure the caller left room for every new constituent:
      num_new = num_tracers * num_species
      if ((first_index + num_new - 1) > SIZE(host_consts)) then
         call endrun(subname//"host constituents array has room for "//       &
              to_str(SIZE(host_consts) - first_index + 1)//" new "//          &
              "constituents but "//to_str(num_new)//" water tracer "//        &
              "constituents are needed", file=__FILE__, line=__LINE__)
      end if

      host_idx = first_index - 1
      ! Loop over all of the water tracers listed in CESM share:
      do tracer_idx = 1, num_tracers

         ! Get water tracer name
         tracer_name = shr_wtracers_get_name(tracer_idx)

         ! Use the provided "initial" ratio as the "prescribed" ratio
         ratio_val = shr_wtracers_get_initial_ratio(tracer_idx)

         ! Loop over each water species the physics registered:
         do species_num = 1, num_species
            prop_idx = species_idx(species_num)

            ! Collect the properties of the constituent being tracked:
            call all_props(prop_idx)%standard_name(std_name, err_code,     &
                 err_msg)
            if (err_code == 0) then
               call all_props(prop_idx)%long_name(long_name, err_code,     &
                    err_msg)
            end if
            if (err_code == 0) then
               call all_props(prop_idx)%diagnostic_name(diag_name,         &
                    err_code, err_msg)
            end if
            if (err_code == 0) then
               call all_props(prop_idx)%units(units, err_code, err_msg)
            end if
            if (err_code == 0) then
               call all_props(prop_idx)%vertical_dimension(vert_dim,       &
                    err_code, err_msg)
            end if
            if (err_code == 0) then
               call all_props(prop_idx)%is_advected(advected, err_code,    &
                    err_msg)
            end if
            if (err_code == 0) then
               call all_props(prop_idx)%minimum(min_val, err_code, err_msg)
            end if
            if (err_code == 0) then
               call all_props(prop_idx)%molar_mass(molar_mass, err_code,   &
                    err_msg)
            end if
            if (err_code == 0) then
               call all_props(prop_idx)%default_value(default_val,         &
                    err_code, err_msg)
            end if
            if (err_code == 0) then
               call all_props(prop_idx)%is_dry(is_dry, err_code, err_msg)
            end if
            if (err_code == 0) then
               call all_props(prop_idx)%is_moist(is_moist, err_code,       &
                    err_msg)
            end if
            if (err_code == 0) then
               call all_props(prop_idx)%is_wet(is_wet, err_code, err_msg)
            end if
            if (err_code /= 0) then
               call endrun(subname//"Error "//to_str(err_code)//": "//        &
                    trim(err_msg), file=__FILE__, line=__LINE__)
            end if

            ! Every instantiated constituent is dry, moist or wet, so pass the
            ! type along explicitly rather than have it re-derived from the
            ! new (prefixed) standard name:
            if (is_dry) then
               mix_type = 'dry'
            else if (is_moist) then
               mix_type = 'moist'
            else if (is_wet) then
               mix_type = 'wet'
            else
               call endrun(subname//"constituent '"//trim(std_name)//         &
                    "' has no mixing ratio type", file=__FILE__,              &
                    line=__LINE__)
            end if

            ! A truncated standard name could silently collide with another
            ! constituent, so check the prefixed name will fit:
            if ((len_trim(tracer_name) + len_trim(std_name) + 1) >            &
                 stdname_len) then
               call endrun(subname//"water tracer standard name '"//          &
                    trim(tracer_name)//"_"//trim(std_name)//"' is longer "//  &
                    "than the maximum of "//to_str(stdname_len)//             &
                    " characters", file=__FILE__, line=__LINE__)
            end if

            host_idx = host_idx + 1

            ! Register the new water tracer constituent:
            call host_consts(host_idx)%instantiate(                           &
                 std_name=trim(tracer_name)//'_'//trim(std_name),             &
                 long_name=trim(tracer_name)//' '//trim(long_name),           &
                 diag_name=trim(tracer_name)//'_'//trim(diag_name),           &
                 units=trim(units),                                           &
                 vertical_dim=trim(vert_dim),                                 &
                 advected=advected,                                           &
                 default_value=default_val,                                   &
                 min_value=min_val,                                           &
                 molar_mass=molar_mass,                                       &
                 water_species=.false.,                                       &
                 mixing_ratio_type=trim(mix_type),                            &
                 water_tracer=.true.,                                         &
                 prescribed_ratio=ratio_val,                                  &
                 bulk_water_name=trim(std_name),                              &
                 errcode=err_code, errmsg=err_msg)
            if (err_code /= 0) then
               call endrun(subname//"Error "//to_str(err_code)//": "//        &
                    trim(err_msg), file=__FILE__, line=__LINE__)
            end if

         end do
      end do

   end subroutine register_water_tracer_constituents

   subroutine water_tracer_dycore_mapping(advected_const_index, tracer_slot,  &
        bulk_slot, tracer_ratio, num_pairs)
      use cam_abortutils,            only: endrun, check_allocate
      use cam_logfile,               only: iulog, debug_output
      use cam_logfile,               only: DEBUGOUT_VERBOSE
      use spmd_utils,                only: masterproc
      use string_utils,              only: to_str
      use ccpp_constituent_prop_mod, only: int_unassigned, kphys_unassigned

      ! Build the list of water tracer constituents whose initial values still
      ! need to be set from the bulk water species that each one tracks.  This
      ! is for a caller which holds constituent data indexed by a dycore's
      ! advected constituent index, e.g. the dycore itself while it is reading
      ! initial conditions.
      !
      ! For every entry <n> of the returned mapping the caller should set
      !
      !    q(..., tracer_slot(n)) = q(..., bulk_slot(n)) * tracer_ratio(n)
      !
      ! (clipped at the tracer's minimum value) and then mark the constituent
      ! advected_const_index(tracer_slot(n)) as initialized.  Bulk water
      ! species are never themselves water tracers, so the entries of the
      ! mapping may be applied in any order.
      !
      ! A water tracer which is already marked as initialized is left out of
      ! the mapping, so a tracer that was found on the initial conditions file
      ! keeps the values which were read for it.
      !

      ! Dummy arguments

      ! Constituent index of each of the caller's advected slots, so that
      ! advected_const_index(m) is the constituent held in the caller's
      ! slot <m>:
      integer,                      intent(in)  :: advected_const_index(:)
      ! Caller's advected slot holding the water tracer to be initialized:
      integer,         allocatable, intent(out) :: tracer_slot(:)
      ! Caller's advected slot holding the bulk water species that the
      ! water tracer in the matching 'tracer_slot' entry tracks:
      integer,         allocatable, intent(out) :: bulk_slot(:)
      ! Ratio of the water tracer to its bulk water species:
      real(kind_phys), allocatable, intent(out) :: tracer_ratio(:)
      ! Number of entries which were filled in the three arrays above:
      integer,                      intent(out) :: num_pairs

      ! Local variables
      integer                     :: adv_idx
      integer                     :: num_slots
      integer                     :: const_idx
      integer                     :: bulk_const_idx
      integer                     :: bulk_adv_idx
      integer                     :: search_idx
      integer                     :: err_code
      integer                     :: iret
      logical                     :: is_tracer
      real(kind_phys)             :: ratio_val
      character(len=256)          :: err_msg
      character(len=*), parameter :: subname = 'water_tracer_dycore_mapping: '

      num_slots = SIZE(advected_const_index)

      allocate(tracer_slot(num_water_tracers), stat=iret, errmsg=err_msg)
      call check_allocate(iret, subname, 'tracer_slot(num_water_tracers)',    &
           file=__FILE__, line=__LINE__, errmsg=err_msg)
      allocate(bulk_slot(num_water_tracers), stat=iret, errmsg=err_msg)
      call check_allocate(iret, subname, 'bulk_slot(num_water_tracers)',      &
           file=__FILE__, line=__LINE__, errmsg=err_msg)
      allocate(tracer_ratio(num_water_tracers), stat=iret, errmsg=err_msg)
      call check_allocate(iret, subname, 'tracer_ratio(num_water_tracers)',   &
           file=__FILE__, line=__LINE__, errmsg=err_msg)

      num_pairs = 0

      do adv_idx = 1, num_slots
         const_idx = advected_const_index(adv_idx)
         if (.not. check_index_bounds(const_idx, subname)) then
            cycle
         end if

         ! Only water tracers are initialized from another constituent:
         call const_props(const_idx)%is_water_tracer(is_tracer, err_code,     &
              err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if
         if (.not. is_tracer) then
            cycle
         end if

         ! A tracer which already has initial values, e.g. because it was
         ! found on the initial conditions file, is left exactly as it was:
         if (const_is_initialized(const_idx)) then
            cycle
         end if

         ! Extract bulk water constituent index associated with the given
         ! water tracer constituent:
         call const_props(const_idx)%bulk_water_index(bulk_const_idx,         &
              err_code, err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if
         if (bulk_const_idx == int_unassigned) then
            call endrun(subname//"water tracer '"//                           &
                 trim(const_name(const_idx))//"' has no 'bulk_water_index' "//&
                 "property set", file=__FILE__, line=__LINE__)
         end if
         if (.not. check_index_bounds(bulk_const_idx, subname)) then
            cycle
         end if

         ! The caller can only read the bulk water species if it is holding it
         ! as well, so find which of the caller's slots that species is in:
         bulk_adv_idx = -1
         do search_idx = 1, num_slots
            if (advected_const_index(search_idx) == bulk_const_idx) then
               bulk_adv_idx = search_idx
               exit
            end if
         end do
         if (bulk_adv_idx < 1) then
            call endrun(subname//"water tracer '"//                           &
                 trim(const_name(const_idx))//"' tracks bulk water species '" &
                 //trim(const_name(bulk_const_idx))//"', which the caller "// &
                 "is not holding", file=__FILE__, line=__LINE__)
         end if

         call const_props(const_idx)%prescribed_ratio(ratio_val, err_code,    &
              err_msg)
         if (err_code /= 0) then
            call endrun(subname//"Error "//to_str(err_code)//": "//           &
                 trim(err_msg), file=__FILE__, line=__LINE__)
         end if
         if (ratio_val == kphys_unassigned) then
            call endrun(subname//"water tracer '"//                           &
                 trim(const_name(const_idx))//"' has no 'prescribed_ratio' "//&
                 "property set", file=__FILE__, line=__LINE__)
         end if

         num_pairs               = num_pairs + 1
         tracer_slot(num_pairs)  = adv_idx
         bulk_slot(num_pairs)    = bulk_adv_idx
         tracer_ratio(num_pairs) = ratio_val

         if ((debug_output >= DEBUGOUT_VERBOSE) .and. masterproc) then
            write(iulog, *) subname, "setting water tracer '",                &
                 trim(const_name(const_idx)), "' to ", ratio_val,             &
                 " * '", trim(const_name(bulk_const_idx)), "'"
         end if
      end do

   end subroutine water_tracer_dycore_mapping

   !#######################################################################

   !#######################################################################

end module cam_constituents
