Attributes {
  time {
    String _CoordinateAxisType "Time";
    Float64 actual_range 4.811184e+8, 1.7914608e+9;
    String axis "T";
    String coverage_content_type "coordinate";
    String ioos_category "Time";
    String long_name "reference time of the ending day of the 7-day period";
    String standard_name "time";
    String time_origin "01-JAN-1970 00:00:00";
    String units "seconds since 1970-01-01T00:00:00Z";
  }
  latitude {
    String _CoordinateAxisType "Lat";
    Float32 actual_range -89.975, 89.975;
    String axis "Y";
    String comment "equirectangular projection and grid centers";
    String coverage_content_type "coordinate";
    String ioos_category "Location";
    String long_name "Latitude";
    String standard_name "latitude";
    String units "degrees_north";
    Float32 valid_max 89.975;
    Float32 valid_min -89.975;
  }
  longitude {
    String _CoordinateAxisType "Lon";
    Float32 actual_range 0.025, 359.975;
    String axis "X";
    String comment "equirectangular projection and grid centers";
    String coverage_content_type "coordinate";
    String ioos_category "Location";
    String long_name "Longitude";
    String standard_name "longitude";
    String units "degrees_east";
    Float32 valid_max 359.975;
    Float32 valid_min 0.025;
  }
  bleaching_alert_area {
    Byte _FillValue 127;
    String _Unsigned "false";
    Int32 colorBarMaximum 4;
    Int32 colorBarMinimum 0;
    String comment "Bleaching Alert Area (BAA) values are coral bleaching heat stress levels: 0 - No Stress; 1 - Bleaching Watch; 2 - Bleaching Warning; 3 - Bleaching Alert Level 1; 4 - Bleaching Alert Level 2. Product description is provided at https://coralreefwatch.noaa.gov/product/5km/index.php.";
    String coverage_content_type "thematicClassification";
    String grid_mapping "crs";
    String ioos_category "Physical Oceanography";
    String long_name "bleaching alert area 7-day maximum composite";
    String standard_name "n/a";
    String units "stress_level";
    Byte valid_max 4;
    Byte valid_min 0;
  }
  NC_GLOBAL {
    String _NCProperties "version=2,netcdf=4.8.1,hdf5=1.12.1";
    String acknowledgement "NOAA Coral Reef Watch program";
    String cdm_data_type "Grid";
    String comment "This is a product of the NOAA Coral Reef Watch Daily Global 5km Satellite Coral Bleaching Heat Stress Monitoring Product Suite Version 3.1.";
    String contributor_name "NOAA Coral Reef Watch Program";
    String contributor_role "Collecting source data and deriving products; performing quality control of products; disseminating, storing, and submitting data to archive";
    String Conventions "CF-1.6, ACDD-1.3, COARDS";
    String creator_email "coralreefwatch@noaa.gov";
    String creator_institution "NOAA/NESDIS/STAR Coral Reef Watch Program";
    String creator_name "NOAA Coral Reef Watch Program";
    String creator_type "group";
    String creator_url "https://coralreefwatch.noaa.gov/";
    String date_created "2018-03-01T12:00:00Z";
    String date_issued "2019-08-01T14:55:48Z";
    String date_metadata_modified "2019-02-05T12:00:00Z";
    String date_modified "2018-03-01T12:00:00Z";
    Float64 Easternmost_Easting 359.975;
    String geospatial_bounds "\"POLYGON((-90.0 360.0, 90.0 360.0, 90.0 0.0, -90.0 0.0, -90.0 360.0))\"";
    String geospatial_bounds_crs "EPSG:4326";
    Float64 geospatial_lat_max 89.975;
    Float64 geospatial_lat_min -89.975;
    Float64 geospatial_lat_resolution 0.049999999999999996;
    String geospatial_lat_units "degrees_north";
    Float64 geospatial_lon_max 359.975;
    Float64 geospatial_lon_min 0.025;
    Float64 geospatial_lon_resolution 0.05000000000000001;
    String geospatial_lon_units "degrees_east";
    String history "Fri Sep 11 06:25:12 2026: ncatted -O -a geospatial_bounds,global,o,c,\"POLYGON((-90.0 360.0, 90.0 360.0, 90.0 0.0, -90.0 0.0, -90.0 360.0))\" ct5km_baa-max-7d_v3.1_20260910-0-360.nc
Fri Sep 11 06:25:12 2026: ncatted -O -a geospatial_lon_max,global,o,f,359.975 ct5km_baa-max-7d_v3.1_20260910-0-360.nc
Fri Sep 11 06:25:12 2026: ncatted -O -a geospatial_lon_min,global,o,f,0.025 ct5km_baa-max-7d_v3.1_20260910-0-360.nc
Fri Sep 11 06:25:12 2026: ncatted -O -a valid_max,lon,o,f,359.975 ct5km_baa-max-7d_v3.1_20260910-0-360.nc
Fri Sep 11 06:25:12 2026: ncatted -O -a valid_min,lon,o,f,0.025 ct5km_baa-max-7d_v3.1_20260910-0-360.nc
Fri Sep 11 06:25:11 2026: ncap2 -O -s where(lon<0) lon=lon+360 ct5km_baa-max-7d_v3.1_20260910-0-360.nc ct5km_baa-max-7d_v3.1_20260910-0-360.nc
Fri Sep 11 06:25:10 2026: ncks -O --msa_usr_rdr -d lon,0.0,180.0 -d lon,-180.0,0.0 ct5km_baa-max-7d_v3.1_20260910.nc ct5km_baa-max-7d_v3.1_20260910-0-360.nc
This is a product data file of the NOAA Coral Reef Watch Daily Global 5km Satellite Coral Bleaching Heat Stress Monitoring Product Suite Version 3.1 (v3.1) in its NetCDF Version 1.0 (v1.0).
2026-10-09T17:27:08Z (local files)
2026-10-09T17:27:08Z https://oceanwatch.pifsc.noaa.gov/erddap/griddap/CRW_baa_max_7d_v1_0.das";
    String id "Satellite_Daily_Global_5km_7day_Maximum_Bleaching_Alert_Area_Composite";
    String infoUrl "https://coralreefwatch.noaa.gov/product/5km/index.php";
    String institution "NOAA/NESDIS/STAR Coral Reef Watch Program";
    String instrument "ATSR-1, ATSR-2, AATSR, AVHRR, AVHRR-2, AVHRR-3, VIIRS, GOES Imager, MTSAT Imager, MTSAT 2 Imager, AHI, ABI, SEVIRI, buoy - moored buoy, buoy - drifting buoy, buoy - TAO buoy, surface seawater intake";
    String instrument_vocabulary "NOAA NODC Ocean Archive System Instruments";
    String keywords "5km, 7-day, alert, area, bleaching, bleaching_alert_area, composite, coral, crw, daily, data, day, Earth Science > Oceans > Ocean Temperature > Bleaching Alert Area, Earth Science > Oceans > Ocean Temperature > Sea Surface Temperature, Earth Science > Oceans > Ocean Temperature > Water Temperature, Earth Science > Spectral/Engineering > Infrared Wavelengths > Thermal Infrared, engineering, environmental, global, information, infrared, maximum, national, nesdis, noaa, ocean, oceanography, oceans, physical, physical oceanography, program, reef, satellite, sea, seawater, service, spectral, spectral/engineering, star, surface, temperature, thermal, time, watch, water, wavelengths";
    String keywords_vocabulary "GCMD Science Keywords";
    String license "The data produced by Coral Reef Watch are available for use without restriction, but Coral Reef Watch relies on the ethics and integrity of the user to ensure that the source of the data and products is appropriately cited and credited. When using these data and products, credit and courtesy should be given to NOAA Coral Reef Watch. Please include the appropriate DOI associated with this dataset in the citation. For more information, visit the NOAA Coral Reef Watch website: https://coralreefwatch.noaa.gov. Recommendations for citing and providing credit are provided at https://coralreefwatch.noaa.gov/satellite/docs/recommendations_crw_citation.php. Users are referred to the footer section of the Coral Reef Watch website (https://coralreefwatch.noaa.gov/index.php) for disclaimers, policies, notices pertaining to the use of the data.";
    String metadata_link "https://coralreefwatch.noaa.gov/product/5km/index.php";
    String naming_authority "gov.noaa.coralreefwatch";
    String NCO "netCDF Operators version 5.0.7 (Homepage = http://nco.sf.net, Code = https://github.com/nco/nco)";
    Float64 Northernmost_Northing 89.975;
    String platform "Ships, drifting buoys, moored buoys, TOGA-TAO buoy arrays, GOES-8 satellite, GOES-9 satellite, GOES-10 satellite, GOES-11 satellite, GOES-12 satellite, GOES-13 satellite, GOES-14 satellite, GOES-15 satellite, GOES-16 satellite, MTSAT-1R satellite, MTSAT-2 satellite, Himawari-8 satellite, Meteosat-8 satellite, Meteosat-9 satellite, Meteoset-10 satellite, Meteosat-11 satellite, Suomi NPP, MetOp-A satellite, MetOp-B satellite, NOAA-9 satellite, NOAA-11 satellite, NOAA-12 satellite, NOAA-14 satellite, NOAA-15 satellite, NOAA-16 satellite, NOAA-17 satellite, NOAA-18 satellite, NOAA-19 satellite.";
    String platform_vocabulary "NOAA NODC Ocean Archive System Platforms";
    String processing_level "Derived from L4 satellite sea surface temperaure analysis";
    String product_version "3.1";
    String program "NOAA Coral Reef Watch Program";
    String project "NOAA Coral Reef Watch Program";
    String publisher_email "coralreefwatch@noaa.gov";
    String publisher_institution "NOAA/NESDIS/STAR Coral Reef Watch Program";
    String publisher_name "NOAA Coral Reef Watch Program";
    String publisher_type "group";
    String publisher_url "https://coralreefwatch.noaa.gov";
    String references "https://coralreefwatch.noaa.gov/product/5km/index.php";
    String source "Coral Reef Watch Daily Global 5km Satellite Sea Surface Temperature v3.1 (CoralTemp v3.1)";
    String sourceUrl "(local files)";
    Float64 Southernmost_Northing -89.975;
    String spatial_resolution "0.05 degrees";
    String standard_name_vocabulary "CF Standard Name Table v27";
    String summary "This is a product of NOAA Coral Reef Watch Daily Global 5km Satellite Coral Bleaching Heat Stress Monitoring Product Suite, derived from CoralTemp v1.0. Bleaching Alert Levels: 0 - No stress, 1 - Watch, 2 - Warning, 3 - Alert Level 1, 4 - Alert LEvel 2. For more information: https://coralreefwatch.noaa.gov/product/5km/index_5km_baa_max_r07d.php";
    String time_coverage_duration "P7D";
    String time_coverage_end "2026-10-08T12:00:00Z";
    String time_coverage_resolution "P7D";
    String time_coverage_start "1985-03-31T12:00:00Z";
    String title "Coral Bleaching Alert Area 7-day Maximum Composite, Coral Reef Watch - Daily, 1985-
present";
    Float64 Westernmost_Easting 0.025;
  }
}
