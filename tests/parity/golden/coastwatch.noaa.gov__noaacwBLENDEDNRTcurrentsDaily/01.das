Attributes {
  time {
    String _CoordinateAxisType "Time";
    Float64 actual_range 1.42128e+9, 1.7913312e+9;
    String axis "T";
    String bounds "time_bnds";
    String calendar "gregorian";
    String ioos_category "Time";
    String long_name "Time";
    String standard_name "time";
    String time_origin "01-JAN-1970 00:00:00";
    String units "seconds since 1970-01-01T00:00:00Z";
  }
  latitude {
    String _CoordinateAxisType "Lat";
    Float32 actual_range -89.875, 89.875;
    String axis "Y";
    String bounds "lat_bnds";
    String ioos_category "Location";
    String long_name "Latitude";
    String standard_name "latitude";
    String units "degrees_north";
    Float32 valid_max 89.875;
    Float32 valid_min -89.875;
  }
  longitude {
    String _CoordinateAxisType "Lon";
    Float32 actual_range -179.875, 179.875;
    String axis "X";
    String bounds "lon_bnds";
    String ioos_category "Location";
    String long_name "Longitude";
    String standard_name "longitude";
    String units "degrees_east";
    Float32 valid_max 179.875;
    Float32 valid_min -179.875;
  }
  u_current {
    UInt32 _ChunkSizes 1, 720, 1440;
    Float64 _FillValue -214748.3648;
    String comment "The Mean Dynamic Topography (MDT) used in the derivation of the geostrophic currents is the MDT CNES/CLS 2013";
    String coordinates "longitude latitude";
    String coordsys "geographic";
    String grid_mapping "crs";
    String ioos_category "Currents";
    String long_name "U Current";
    Float64 missing_value -214748.3648;
    String standard_name "surface_geostrophic_eastward_sea_water_velocity";
    String units "m/s";
    Float64 valid_max 4.6429;
    Float64 valid_min -4.8486;
  }
  v_current {
    UInt32 _ChunkSizes 1, 720, 1440;
    Float64 _FillValue -214748.3648;
    String comment "The Mean Dynamic Topography (MDT) used in the derivation of the geostrophic currents is the MDT CNES/CLS 2013";
    String coordinates "longitude latitude";
    String coordsys "geographic";
    String grid_mapping "crs";
    String ioos_category "Currents";
    String long_name "V Current";
    Float64 missing_value -214748.3648;
    String standard_name "surface_geostrophic_northward_sea_water_velocity";
    String units "m/s";
    Float64 valid_max 4.5456;
    Float64 valid_min -4.805400000000001;
  }
  NC_GLOBAL {
    String _NCProperties "version=2,netcdf=4.9.2,hdf5=1.14.3";
    String cdm_data_type "Grid";
    String Conventions "COARDS, CF-1.0, Unidata Dataset Discovery v1.0";
    String creator_email "Eric.Leuliette@noaa.gov";
    String creator_name "Eric.Leuliette@noaa.gov";
    String date_created "2026-10-08T11:32:11.781054Z";
    String date_modified "2026-10-08T11:32:11.781054Z";
    Float64 Easternmost_Easting 179.875;
    Float64 geospatial_lat_max 89.875;
    Float64 geospatial_lat_min -89.875;
    Float64 geospatial_lat_resolution 0.25;
    String geospatial_lat_units "degrees_north";
    Float64 geospatial_lon_max 179.875;
    Float64 geospatial_lon_min -179.875;
    Float64 geospatial_lon_resolution 0.25;
    String geospatial_lon_units "degrees_east";
    String history "2026-10-09T03:51:29Z (local files)
2026-10-09T03:51:29Z https://coastwatch.noaa.gov/erddap/griddap/noaacwBLENDEDNRTcurrentsDaily.das";
    String infoUrl "https://coastwatch.noaa.gov";
    String institution "NOAA NESDIS CoastWatch";
    String license "Data courtesy of NOAA; Sentinel data courtesy of Copernicus Program; Generated using AVISO+ products. The data may be used and redistributed for free but is not intended
for legal use, since it may contain inaccuracies. Neither the data
Contributor, ERD, NOAA, nor the United States Government, nor any
of their employees or contractors, makes any warranty, express or
implied, including warranties of merchantability and fitness for a
particular purpose, or assumes any legal liability for the accuracy,
completeness, or usefulness, of this information.";
    String ncei_template_version "NCEI_NetCDF_Grid_Template_v2.0";
    Int32 nco_openmp_thread_number 1;
    Int32 node_offset 0;
    Float64 Northernmost_Northing 89.875;
    String source "Altimetry measurements";
    String sourceUrl "(local files)";
    Float64 Southernmost_Northing -89.875;
    String standard_name_vocabulary "CF-1.0";
    String summary "The altimetry data are from RADS (http://rads.tudelft.nl/rads/rads.shtml), the Radar Altimetry Database System, first developed at Delft University of Technology, now also at the NOAA and the European Organisation for the Exploitation of Meteorological Satellites (EUMETSAT). The RADS data for each mission is updated with state of the art corrections for tides, atmospheric path delay, etc. Because they are all computed consistently between the various missions, this avoids the possibility of introducing biases and drifts because of the different implementation of the various corrections by different agencies. The goals of RADS are to provide a homogenous dataset of sea level anomalies, wave heights, and wind speeds, along with database selection and analysis tools.";
    String testOutOfDate "now-2days";
    String time_coverage_end "2026-10-07T00:00:00Z";
    String time_coverage_start "2015-01-15T00:00:00Z";
    String title "Sea Surface Currents (Geostrophic), Altimetry (S-3A/B,CryoSat2,Jason-2/3,SARAL), Near Real-Time,
Global 0.25°, 2017-present, Daily";
    Float64 Westernmost_Easting -179.875;
  }
}
