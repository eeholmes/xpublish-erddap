Attributes {
  time {
    String _CoordinateAxisType "Time";
    Float64 actual_range 4.760208e+8, 1.7881776e+9;
    String axis "T";
    String coverage_content_type "coordinate";
    String ioos_category "Time";
    String long_name "reference time of the last day of the month";
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
  sea_surface_temperature {
    Float32 _FillValue NaN;
    Float64 colorBarMaximum 32.0;
    Float64 colorBarMinimum 0.0;
    String coverage_content_type "physicalMeasurement";
    String ioos_category "Temperature";
    String long_name "analysed sea surface temperature";
    String standard_name "sea_surface_temperature";
    String units "degree_C";
    Float32 valid_max 50.0;
    Float32 valid_min -2.0;
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
    String date_issued "2021-03-01T15:05:30Z";
    String date_metadata_modified "2020-11-18T12:00:00Z";
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
    String grid_mapping_epsg_code "EPSG:4326";
    Float32 grid_mapping_inverse_flattening 298.2572;
    String grid_mapping_name "latitude_longitude";
    Float32 grid_mapping_semi_major_axis 6378137.0;
    String history "Tue Sep  1 07:31:19 2026: ncatted -O -a geospatial_bounds,global,o,c,\"POLYGON((-90.0 360.0, 90.0 360.0, 90.0 0.0, -90.0 0.0, -90.0 360.0))\" ct5km_sst-mean_v3.1_202608-0-360.nc
Tue Sep  1 07:31:19 2026: ncatted -O -a geospatial_lon_max,global,o,f,359.975 ct5km_sst-mean_v3.1_202608-0-360.nc
Tue Sep  1 07:31:19 2026: ncatted -O -a geospatial_lon_min,global,o,f,0.025 ct5km_sst-mean_v3.1_202608-0-360.nc
Tue Sep  1 07:31:19 2026: ncatted -O -a valid_max,lon,o,f,359.975 ct5km_sst-mean_v3.1_202608-0-360.nc
Tue Sep  1 07:31:19 2026: ncatted -O -a valid_min,lon,o,f,0.025 ct5km_sst-mean_v3.1_202608-0-360.nc
Tue Sep  1 07:31:17 2026: ncap2 -O -s where(lon<0) lon=lon+360 ct5km_sst-mean_v3.1_202608-0-360.nc ct5km_sst-mean_v3.1_202608-0-360.nc
Tue Sep  1 07:31:15 2026: ncks -O --msa_usr_rdr -d lon,0.0,180.0 -d lon,-180.0,0.0 ct5km_sst-mean_v3.1_202608.nc ct5km_sst-mean_v3.1_202608-0-360.nc
This is a product data file of the NOAA Coral Reef Watch Daily Global 5km Satellite Coral Bleaching Heat Stress Monitoring Product Suite Version 3.1 (v3.1) in its NetCDF Version 1.0 (v1.0).
2026-09-16T19:48:19Z (local files)
2026-09-16T19:48:19Z https://oceanwatch.pifsc.noaa.gov/erddap/griddap/CRW_sst_v3_1_monthly.das";
    String id "Satellite_Global_5km_SST_Monthly_Mean_Composite";
    String infoUrl "https://coralreefwatch.noaa.gov/product/5km/index.php";
    String institution "NOAA/NESDIS/STAR Coral Reef Watch Program";
    String instrument "ATSR-1, ATSR-2, AATSR, AVHRR, AVHRR-2, AVHRR-3, VIIRS, GOES Imager, MTSAT Imager, MTSAT 2 Imager, AHI, ABI, SEVIRI, buoy - moored buoy, buoy - drifting buoy, buoy - TAO buoy, surface seawater intake";
    String instrument_vocabulary "NOAA NODC Ocean Archive System Instruments";
    String keywords "5km, analysed, composite, coral, coraltemp, crw, data, earth, Earth Science > Oceans > Ocean Temperature > Sea Surface Temperature, Earth Science > Oceans > Ocean Temperature > Water Temperature, Earth Science > Spectral/Engineering > Infrared Wavelengths > Thermal Infrared, engineering, environmental, global, information, infrared, mean, month, monthly, national, nesdis, noaa, ocean, oceans, program, reef, satellite, science, sea, sea_surface_temperature, seawater, service, spectral, spectral/engineering, sst, star, surface, temperature, thermal, time, version, watch, water, wavelengths";
    String keywords_vocabulary "GCMD Science Keywords";
    String license "The data produced by Coral Reef Watch are available for use without restriction, but Coral Reef Watch relies on the ethics and integrity of the user to ensure that the source of the data and products is appropriately cited and credited. When using these data and products, credit and courtesy should be given to NOAA Coral Reef Watch. Please include the appropriate DOI associated with this dataset in the citation. For more information, visit the NOAA Coral Reef Watch website: https://coralreefwatch.noaa.gov. Recommendations for citing and providing credit are provided at https://coralreefwatch.noaa.gov/satellite/docs/recommendations_crw_citation.php. Users are referred to the footer section of the Coral Reef Watch website (https://coralreefwatch.noaa.gov/index.php) for disclaimers, policies, notices pertaining to the use of the data.";
    String metadata_link "https://coralreefwatch.noaa.gov/product/5km/index.php";
    String naming_authority "gov.noaa.coralreefwatch";
    String NCO "netCDF Operators version 4.7.5 (Homepage = http://nco.sf.net, Code = https://github.com/nco/nco)";
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
    String summary "NOAA Coral Reef Watch Global 5km Satellite Sea Surface Temperature (CoralTemp Version 1.0) Monthly Mean Composite for February 2021. This is a product of NOAA Coral Reef Watch Global 5km Satellite Coral Bleaching Heat Stress Monitoring Product Suite, derived from CoralTemp v1.0.";
    String time_coverage_duration "P1M";
    String time_coverage_end "2026-08-31T12:00:00Z";
    String time_coverage_resolution "P1M";
    String time_coverage_start "1985-01-31T12:00:00Z";
    String title "Sea Surface Temperature, Coral Reef Watch, CoralTemp, v3.1 - Monthly, 1985-present";
    Float64 Westernmost_Easting 0.025;
  }
}
