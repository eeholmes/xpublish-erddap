Attributes {
  time {
    String _CoordinateAxisType "Time";
    Float64 actual_range 4.734288e+8, 1.5962832e+9;
    String axis "T";
    String coverage_content_type "coordinate";
    String ioos_category "Time";
    String long_name "reference time of the sst field";
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
  analysed_sst {
    Float64 _FillValue NaN;
    Float64 colorBarMaximum 32.0;
    Float64 colorBarMinimum 0.0;
    String coverage_content_type "physicalMeasurement";
    String grid_mapping "crs";
    String ioos_category "Temperature";
    String long_name "analysed sea surface temperature";
    String standard_name "sea_surface_temperature";
    String units "degree_C";
    Float64 valid_max 5000.0;
    Float64 valid_min -200.0;
  }
  NC_GLOBAL {
    String acknowledgement "NOAA Coral Reef Watch Program";
    String cdm_data_type "Grid";
    String comment "This product is designed to improve on and replace the use of AVHRR Pathfinder SST for use within the Coral Reef Watch Program.";
    String contributor_name "NOAA Coral Reef Watch program";
    String contributor_role "Collecting source data and deriving products; performing quality control of products; disseminating, storing, and submitting data to archive";
    String Conventions "CF-1.6, ACDD-1.3, COARDS";
    String creator_email "coralreefwatch@noaa.gov";
    String creator_institution "NOAA/NESDIS/STAR Coral Reef Watch program";
    String creator_name "NOAA Coral Reef Watch program";
    String creator_type "group";
    String creator_url "https://coralreefwatch.noaa.gov/";
    String data_source "NOAA Daily Global 5km Geo-Polar Blended Night-only Sea Surface Temperature Analysis from the date specified in the global attribute time_coverage_start. Note, if the text of this global attribute begins with \"Due to ...\", one of the following situations occurred: (1) the source data file for the CoralTemp of data file for the CoralTemp of the day was missing; (2) the sea_ice_fraction data array in the source data was missing, (3) some alternation was made on the source data to derive the CoralTemp data of the day.";
    String date_created "2018-01-01T00:00:00Z";
    String date_issued "2018-12-02T15:20:07Z";
    String date_metadata_modified "2018-09-01T00:00:00Z";
    String date_modified "2018-01-01T00:00:00Z";
    Float64 Easternmost_Easting 359.975;
    String geospatial_bounds "\"POLYGON((-90.0 360.0, 90.0 360.0, 90.0 0.0, -90.0 0.0, -90.0 360.0))\"";
    String geospatial_bounds_crs "EPSG:32663";
    Float64 geospatial_lat_max 89.975;
    Float64 geospatial_lat_min -89.975;
    Float64 geospatial_lat_resolution 0.049999999999999996;
    String geospatial_lat_units "degrees_north";
    Float64 geospatial_lon_max 359.975;
    Float64 geospatial_lon_min 0.025;
    Float64 geospatial_lon_resolution 0.05000000000000001;
    String geospatial_lon_units "degrees_east";
    String history "Mon Aug  3 06:00:38 2020: ncatted -O -a geospatial_bounds,global,o,c,\"POLYGON((-90.0 360.0, 90.0 360.0, 90.0 0.0, -90.0 0.0, -90.0 360.0))\" coraltemp_v1.0_20200801-0-360.nc
Mon Aug  3 06:00:38 2020: ncatted -O -a geospatial_lon_max,global,o,f,359.975 coraltemp_v1.0_20200801-0-360.nc
Mon Aug  3 06:00:38 2020: ncatted -O -a geospatial_lon_min,global,o,f,0.025 coraltemp_v1.0_20200801-0-360.nc
Mon Aug  3 06:00:38 2020: ncatted -O -a valid_max,lon,o,f,359.975 coraltemp_v1.0_20200801-0-360.nc
Mon Aug  3 06:00:38 2020: ncatted -O -a valid_min,lon,o,f,0.025 coraltemp_v1.0_20200801-0-360.nc
Mon Aug  3 06:00:36 2020: ncap2 -O -s where(lon<0) lon=lon+360 coraltemp_v1.0_20200801-0-360.nc coraltemp_v1.0_20200801-0-360.nc
Mon Aug  3 06:00:34 2020: ncks -O --msa_usr_rdr -d lon,0.0,180.0 -d lon,-180.0,0.0 coraltemp_v1.0_20200801.nc coraltemp_v1.0_20200801-0-360.nc
This is the first version of CoralTemp
2026-09-16T19:47:37Z (local files)
2026-09-16T19:47:37Z https://oceanwatch.pifsc.noaa.gov/erddap/griddap/CRW_sst_v1_0_monthly.das";
    String id "CoralTemp-v1.0";
    String infoUrl "https://coralreefwatch.noaa.gov/satellite/bleaching5km";
    String institution "NOAA/NESDIS/STAR Coral Reef Watch program";
    String instrument "ATSR-1, ATSR-2, AATSR, AVHRR, AVHRR-2, AVHRR-3, VIIRS, GOES Imager, MTSAT Imager, MTSAT 2 Imager, AHI, ABI, SEVIRI, buoy - moored buoy, buoy - drifting buoy, buoy - TAO buoy, surface seawater intake";
    String instrument_vocabulary "NOAA NODC Ocean Archive System Instruments";
    String keywords "5km, analysed, analysed_sst, analysis, blended, coral, coraltemp, data, earth, Earth Science > Oceans > Ocean Temperature > Sea Surface Temperature, Earth Science > Oceans > Ocean Temperature > Water Temperature, Earth Science > Spectral/Engineering > Infrared Wavelengths > Thermal Infrared, engineering, environmental, free, gap, gap-free, global, ice, information, infrared, national, near, nesdis, noaa, nrt, ocean, oceans, operational, ostia, over, program, real, reef, satellite, science, sea, sea_surface_temperature, seawater, service, spectral, spectral/engineering, sst, star, surface, temperature, thermal, time, watch, water, wavelengths";
    String keywords_vocabulary "GCMD Science Keywords";
    String license "OSTIA Usage Statement (1985-2002): IMPORTANT usage statement. Unless otherwise agreed in writing, these data may be used for pure academic research only, with no commercial or other application and all usage must meet the Met Office Standard Terms and Conditions, which may be found here: https://www.metoffice.gov.uk/corporate/legal/tandc.html. The data may be used for a maximum period of 5 years. Reproduction of the data is permitted provided the following copyright statement is included: (C) Crown Copyright 2010, published by the Met Office. You must submit a completed reproduction license application form (here https://www.metoffice.gov.uk/corporate/legal/repro_licence.html) before using the data. This only needs to be completed once for each user. WARNING Some applications are unable to properly handle signed byte values. If values are encountered > 127, please subtract 256 from this reported value. GHRSST statement (2002-present): GHRSST protocol describes data use as free and open. Coral Reef Watch program statement: The data produced by Coral Reef Watch are available for use without restriction, but Coral Reef Watch relies on the ethics and integrity of the user to ensure that the source of the data and products is appropriately cited and credited. When using these data and products, credit and courtesy should be given to NOAA Coral Reef Watch. Please include the appropriate DOI associated with this dataset in the citation. For more information, visit the NOAA Coral Reef Watch website: https://coralreefwatch.noaa.gov. Recommendations for citing and providing credit are provided at https://coralreefwatch.noaa.gov/satellite/docs/recommendations_crw_citation.php. Users are referred to the footer section of Coral Reef Watch's website (https://coralreefwatch.noaa.gov/index.php) for disclaimers, policies, notices pertaining to the use of the data.";
    String metadata_link "https://coralreefwatch.noaa.gov/satellite/bleaching5km";
    String naming_authority "gov.noaa.coralreefwatch";
    String NCO "4.3.7";
    Int32 nco_openmp_thread_number 1;
    Float64 Northernmost_Northing 89.975;
    String platform "Ships, drifting buoys, moored buoys, TOGA-TAO buoy arrays, GOES-8 satellite, GOES-9 satellite, GOES-10 satellite, GOES-11 satellite, GOES-12 satellite, GOES-13 satellite, GOES-14 satellite, GOES-15 satellite, GOES-16 satellite, MTSAT-1R satellite, MTSAT-2 satellite, Himawari-8 satellite, Meteosat-8 satellite, Meteosat-9 satellite, Meteoset-10 satellite, Meteosat-11 satellite, Suomi NPP, MetOp-A satellite, MetOp-B satellite, NOAA-9 satellite, NOAA-11 satellite, NOAA-12 satellite, NOAA-14 satellite, NOAA-15 satellite, NOAA-16 satellite, NOAA-17 satellite, NOAA-18 satellite, NOAA-19 satellite.";
    String platform_vocabulary "NOAA NODC Ocean Archive System Platforms";
    String processing_level "L4";
    String product_version "1.0";
    String program "NOAA Coral Reef Watch program";
    String project "NOAA Coral Reef Watch program";
    String publisher_email "coralreefwatch@noaa.gov";
    String publisher_institution "NOAA/NESDIS/STAR Coral Reef Watch program";
    String publisher_name "NOAA Coral Reef Watch program";
    String publisher_type "group";
    String publisher_url "https://coralreefwatch.noaa.gov/";
    String references "Donlon, et al., 2011. The Operational Sea Surface Temperature and Sea Ice analysis (OSTIA). Maturi, et al., 2017. A new high-resolution sea surface temperature analysis. https://coralreefwatch.noaa.gov/satellite/coraltemp.php";
    String source "OSTIA Sea Surface Temperature Reanalysis (night-only), NOAA Geo-Polar Blended Night-only Sea Surface Temperature Reanalysis, NOAA Geo-Polar Blended Night-only Sea Surface Temperature (near real-time)";
    String sourceUrl "(local files)";
    Float64 Southernmost_Northing -89.975;
    String standard_name_vocabulary "CF Standard Name Table v27";
    String summary "CoralTemp 5km gap-free analysed blended sea surface temperature over the global ocean. CoralTemp is derived from three different but related 5km daily gap-free SST data sets and provides an internally consistent SST product that stretches from 1985 to present: Operational Sea Surface Temperature and Sea Ice Analysis (OSTIA) Sea Surface Temperature Reanalysis (1985-2002), Geo-Polar Blended Night-only Sea Surface Temperature Reanalysis (2002-2016), Geo-Polar Blended Night-only Sea Surface Temperature Near Real-Time (2017 to present). Monthly composites were generated from daily files by OceanWatch Central Pacific";
    String time_coverage_duration "P1D";
    String time_coverage_end "2020-08-01T12:00:00Z";
    String time_coverage_resolution "P1D";
    String time_coverage_start "1985-01-01T12:00:00Z";
    String title "ZZZ - DEPRECATED - Sea Surface Temperature, Coral Reef Watch, CoralTemp - Monthly, 1985-present";
    Float64 Westernmost_Easting 0.025;
  }
}
