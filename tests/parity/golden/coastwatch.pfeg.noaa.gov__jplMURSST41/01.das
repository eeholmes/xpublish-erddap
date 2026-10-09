Attributes {
  time {
    String _CoordinateAxisType "Time";
    Float64 actual_range 1.022922e+9, 1.79145e+9;
    String axis "T";
    String comment "Nominal time of analyzed fields";
    String ioos_category "Time";
    String long_name "reference time of sst field";
    String standard_name "time";
    String time_origin "01-JAN-1970 00:00:00";
    String units "seconds since 1970-01-01T00:00:00Z";
  }
  latitude {
    String _CoordinateAxisType "Lat";
    Float32 actual_range -89.99, 89.99;
    String axis "Y";
    String ioos_category "Location";
    String long_name "Latitude";
    String standard_name "latitude";
    String units "degrees_north";
    Float32 valid_max 90.0;
    Float32 valid_min -90.0;
  }
  longitude {
    String _CoordinateAxisType "Lon";
    Float32 actual_range -179.99, 180.0;
    String axis "X";
    String ioos_category "Location";
    String long_name "Longitude";
    String standard_name "longitude";
    String units "degrees_east";
    Float32 valid_max 180.0;
    Float32 valid_min -180.0;
  }
  analysed_sst {
    Float64 _FillValue -7.768000000000001;
    Float64 colorBarMaximum 32.0;
    Float64 colorBarMinimum 0.0;
    String comment "\"Final\" version using Multi-Resolution Variational Analysis (MRVA) method for interpolation";
    String ioos_category "Temperature";
    String long_name "Analysed Sea Surface Temperature";
    String source "MODIS_T-JPL, MODIS_A-JPL, AMSR2-REMSS, AVHRRMTB_G-NAVO, iQUAM-NOAA/NESDIS, Ice_Conc-OSISAF";
    String standard_name "sea_surface_foundation_temperature";
    String units "degree_C";
    Float64 valid_max 57.767;
    Float64 valid_min -7.767000000000003;
  }
  analysis_error {
    Float64 _FillValue -327.68;
    Float64 colorBarMaximum 5.0;
    Float64 colorBarMinimum 0.0;
    String ioos_category "Statistics";
    String long_name "Estimated Error Standard Deviation of analysed_sst";
    String units "degree_C";
    Float64 valid_max 327.67;
    Float64 valid_min 0.0;
  }
  mask {
    Byte _FillValue -128;
    String _Unsigned "false";
    Float64 colorBarMaximum 20.0;
    Float64 colorBarMinimum 0.0;
    String comment "mask can be used to further filter the data.";
    Byte flag_masks 1, 2, 4, 8, 16;
    String flag_meanings "open_sea land open_lake open_sea_with_ice_in_the_grid open_lake_with_ice_in_the_grid";
    String ioos_category "Identifier";
    String long_name "Sea/Land Field Composite Mask";
    String source "GMT \"grdlandmask\", ice flag from sea_ice_fraction data";
    String standard_name "land_binary_mask";
    Byte valid_max 31;
    Byte valid_min 1;
  }
  sea_ice_fraction {
    Float64 _FillValue -1.28;
    Float64 colorBarMaximum 1.0;
    Float64 colorBarMinimum 0.0;
    String comment "ice fraction is a dimensionless quantity between 0 and 1; it has been interpolated by a nearest neighbor approach; EUMETSAT OSI-SAF files used: ice_conc_nh_polstere-100_amsr3_202610031200.nc, ice_conc_sh_polstere-100_amsr3_202610031200.nc.";
    String ioos_category "Ice Distribution";
    String long_name "Sea Ice Area Fraction";
    String source "EUMETSAT OSI-SAF, copyright EUMETSAT";
    String standard_name "sea_ice_area_fraction";
    String units "1";
    Float64 valid_max 1.0;
    Float64 valid_min 0.0;
  }
  NC_GLOBAL {
    String _NCProperties "version=2,netcdf=4.7.4,hdf5=1.8.12";
    String acknowledgement "Please acknowledge the use of these data with the following statement:  These data were provided by JPL under support by NASA MEaSUREs program.";
    String cdm_data_type "Grid";
    String comment "MUR = \"Multi-scale Ultra-high Resolution\"";
    String Conventions "CF-1.6, COARDS, ACDD-1.3";
    String creator_email "ghrsst@podaac.jpl.nasa.gov";
    String creator_name "JPL MUR SST project";
    String creator_type "group";
    String creator_url "https://podaac.jpl.nasa.gov/dataset/MUR-JPL-L4-GLOB-v4.1";
    String date_created "2026-10-09T07:57:52Z";
    Float64 Easternmost_Easting 180.0;
    Int32 file_quality_level 3;
    String gds_version_id "2.0";
    Float64 geospatial_lat_max 89.99;
    Float64 geospatial_lat_min -89.99;
    Float64 geospatial_lat_resolution 0.01;
    String geospatial_lat_units "degrees_north";
    Float64 geospatial_lon_max 180.0;
    Float64 geospatial_lon_min -179.99;
    Float64 geospatial_lon_resolution 0.01;
    String geospatial_lon_units "degrees_east";
    String history "created at nominal 4-day latency; replaced nrt (1-day latency) version.
Data is downloaded daily from https://podaac-opendap.jpl.nasa.gov/opendap/allData/ghrsst/data/GDS2/L4/GLOB/JPL/MUR/v4.1/ to NOAA NMFS SWFSC ERD by erd.data@noaa.gov .
The data for the most recent 7 days is usually revised everyday. The data for other days is sometimes revised.
2026-10-09T17:26:32Z (local files)
2026-10-09T17:26:32Z https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.das";
    String id "MUR-JPL-L4-GLOB-v04.1";
    String infoUrl "https://podaac.jpl.nasa.gov/dataset/MUR-JPL-L4-GLOB-v4.1";
    String institution "NASA JPL";
    String keywords "analysed, analysed_sst, analysis, analysis_error, area, binary, composite, daily, data, day, deviation, distribution, Earth Science > Oceans > Ocean Temperature > Sea Surface Temperature, error, estimated, field, final, foundation, fraction, ghrsst, high, ice, ice distribution, identifier, jet, jpl, laboratory, land, land_binary_mask, mask, multi, multi-scale, mur, nasa, ocean, oceans, product, propulsion, resolution, scale, sea, sea ice area fraction, sea/land, sea_ice_fraction, sea_surface_foundation_temperature, sst, standard, statistics, surface, temperature, time, ultra, ultra-high";
    String keywords_vocabulary "GCMD Science Keywords";
    String license "These data are available free of charge under the JPL PO.DAAC data policy.

The data may be used and redistributed for free but is not intended
for legal use, since it may contain inaccuracies. Neither the data
Contributor, ERD, NOAA, nor the United States Government, nor any
of their employees or contractors, makes any warranty, express or
implied, including warranties of merchantability and fitness for a
particular purpose, or assumes any legal liability for the accuracy,
completeness, or usefulness, of this information.";
    String naming_authority "org.ghrsst";
    String netcdf_version_id "4.1";
    Float64 Northernmost_Northing 89.99;
    String platform "Terra, Aqua, GCOM-W, MetOp-B, Buoys/Ships";
    String processing_level "L4";
    String product_version "04.1";
    String project "NASA Making Earth Science Data Records for Use in Research Environments (MEaSUREs) Program";
    String publisher_email "ghrsst-po@nceo.ac.uk";
    String publisher_name "GHRSST Project Office";
    String publisher_url "https://www.ghrsst.org";
    String references "https://podaac.jpl.nasa.gov/dataset/MUR-JPL-L4-GLOB-v4.1";
    String sensor "MODIS, AMSR2, AVHRR, in-situ";
    String source "MODIS_T-JPL, MODIS_A-JPL, AMSR2-REMSS, AVHRRMTB_G-NAVO, iQUAM-NOAA/NESDIS, Ice_Conc-OSISAF";
    String sourceUrl "(local files)";
    Float64 Southernmost_Northing -89.99;
    String spatial_resolution "0.01 degrees";
    String standard_name_vocabulary "CF Standard Name Table v70";
    String summary "This is a merged, multi-sensor L4 Foundation Sea Surface Temperature (SST) analysis product from Jet Propulsion Laboratory (JPL). This daily, global, Multi-scale, Ultra-high Resolution (MUR) Sea Surface Temperature (SST) 1-km data set, Version 4.1, is produced at JPL under the NASA MEaSUREs program. For details, see https://podaac.jpl.nasa.gov/dataset/MUR-JPL-L4-GLOB-v4.1 . This dataset is part of the Group for High-Resolution Sea Surface Temperature (GHRSST) project. The data for the most recent 7 days is usually revised everyday.  The data for other days is sometimes revised.";
    String testOutOfDate "now-3days";
    String time_coverage_end "2026-10-08T09:00:00Z";
    String time_coverage_start "2002-06-01T09:00:00Z";
    String title "Multi-scale Ultra-high Resolution (MUR) SST Analysis fv04.1, Global, 0.01°, 2002-present, Daily";
    Float64 Westernmost_Easting -179.99;
  }
}
