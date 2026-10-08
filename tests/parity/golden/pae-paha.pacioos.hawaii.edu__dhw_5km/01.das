Attributes {
  time {
    String _CoordinateAxisType "Time";
    Float64 actual_range 4.812048e+8, 1.7913744e+9;
    String axis "T";
    String coverage_content_type "coordinate";
    String ioos_category "Time";
    String long_name "reference time";
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
    Float32 actual_range -179.975, 179.975;
    String axis "X";
    String comment "equirectangular projection and grid centers";
    String coverage_content_type "coordinate";
    String ioos_category "Location";
    String long_name "Longitude";
    String standard_name "longitude";
    String units "degrees_east";
    Float32 valid_max 179.975;
    Float32 valid_min -179.975;
  }
  CRW_BAA {
    Byte _FillValue -5;
    String _Unsigned "true";
    Float64 colorBarMaximum 4.0;
    Float64 colorBarMinimum 0.0;
    String comment "Bleaching Alert Area (BAA) values are coral bleaching heat stress levels: 0 - No Stress; 1 - Bleaching Watch; 2 - Bleaching Warning; 3 - Bleaching Alert Level 1; 4 - Bleaching Alert Level 2. Product description is provided at https://coralreefwatch.noaa.gov/product/5km/index.php.";
    String coverage_content_type "thematicClassification";
    String flag_meanings "no_stress watch warning alert_level1 alert_level2";
    Byte flag_values 0, 1, 2, 3, 4;
    String ioos_category "Temperature";
    String long_name "bleaching alert area";
    String units "1";
    Byte valid_max 4;
    Byte valid_min 0;
  }
  CRW_BAA_mask {
    Byte _FillValue -5;
    String _Unsigned "true";
    Float64 colorBarMaximum 4.0;
    Float64 colorBarMinimum 0.0;
    String comment "A 2D array, in the same size as the data array in the X and Y directions, classifying land, missing, and ice pixels that are all flagged by the same missing_value (specified by the variable attribute _FillValue) in the data array(s), along with water (data) pixels.";
    String coverage_content_type "thematicClassification";
    String flag_meanings "valid-water land missing ice";
    Byte flag_values 0, 1, 2, 4;
    String ioos_category "Other";
    String long_name "CRW_BAA pixel characteristics flag array";
    String units "1";
  }
  CRW_BAA_7D_MAX {
    Byte _FillValue -5;
    String _Unsigned "true";
    Float64 colorBarMaximum 4.0;
    Float64 colorBarMinimum 0.0;
    String comment "Bleaching Alert Area (BAA) values are coral bleaching heat stress levels: 0 - No Stress; 1 - Bleaching Watch; 2 - Bleaching Warning; 3 - Bleaching Alert Level 1; 4 - Bleaching Alert Level 2. Product description is provided at https://coralreefwatch.noaa.gov/product/5km/index.php.";
    String coverage_content_type "thematicClassification";
    String flag_meanings "no_stress watch warning alert_level1 alert_level2";
    Byte flag_values 0, 1, 2, 3, 4;
    String ioos_category "Temperature";
    String long_name "bleaching alert area 7-day maximum composite";
    String units "1";
    Byte valid_max 4;
    Byte valid_min 0;
  }
  CRW_BAA_7D_MAX_mask {
    Byte _FillValue -5;
    String _Unsigned "true";
    Float64 colorBarMaximum 4.0;
    Float64 colorBarMinimum 0.0;
    String comment "A 2D array, in the same size as the data array in the X and Y directions, classifying land, missing, and ice pixels that are all flagged by the same missing_value (specified by the variable attribute _FillValue) in the data array(s), along with water (data) pixels.";
    String coverage_content_type "thematicClassification";
    String flag_meanings "valid-water land missing ice";
    Byte flag_values 0, 1, 2, 4;
    String ioos_category "Other";
    String long_name "CRW_BAA_7D_MAX pixel characteristics flag array";
    String units "1";
  }
  CRW_DHW {
    Float64 _FillValue -327.68;
    Float64 colorBarMaximum 16.0;
    Float64 colorBarMinimum 0.0;
    String coverage_content_type "physicalMeasurement";
    String ioos_category "Temperature";
    String long_name "degree heating week";
    String units "Celsius weeks";
    Float64 valid_max 100.0;
    Float64 valid_min 0.0;
  }
  CRW_DHW_mask {
    Byte _FillValue -5;
    String _Unsigned "true";
    Float64 colorBarMaximum 4.0;
    Float64 colorBarMinimum 0.0;
    String comment "A 2D array, in the same size as the data array in the X and Y directions, classifying land, missing, and ice pixels that are all flagged by the same missing_value (specified by the variable attribute _FillValue) in the data array(s), along with water (data) pixels.";
    String coverage_content_type "thematicClassification";
    String flag_meanings "valid-water land missing ice";
    Byte flag_values 0, 1, 2, 4;
    String ioos_category "Other";
    String long_name "CRW_DHW pixel characteristics flag array";
    String units "1";
  }
  CRW_HOTSPOT {
    Float64 _FillValue -327.68;
    Float64 colorBarMaximum 1.0;
    Float64 colorBarMinimum 0.0;
    String coverage_content_type "physicalMeasurement";
    String ioos_category "Temperature";
    String long_name "coral bleaching hotspot";
    String units "Celsius";
    Float64 valid_max 15.0;
    Float64 valid_min -15.0;
  }
  CRW_HOTSPOT_mask {
    Byte _FillValue -5;
    String _Unsigned "true";
    Float64 colorBarMaximum 4.0;
    Float64 colorBarMinimum 0.0;
    String comment "A 2D array, in the same size as the data array in the X and Y directions, classifying land, missing, and ice pixels that are all flagged by the same missing_value (specified by the variable attribute _FillValue) in the data array(s), along with water (data) pixels.";
    String coverage_content_type "thematicClassification";
    String flag_meanings "valid-water land missing ice";
    Byte flag_values 0, 1, 2, 4;
    String ioos_category "Other";
    String long_name "CRW_HOTSPOT pixel characteristics flag array";
    String units "1";
  }
  CRW_SEAICE {
    Float64 _FillValue 0.0;
    Float64 colorBarMaximum 1.0;
    Float64 colorBarMinimum 0.0;
    String comment "0 is 0% ice, 1 is 100% ice";
    String coverage_content_type "physicalMeasurement";
    String ioos_category "Ice Distribution";
    String long_name "sea ice fraction";
    String standard_name "sea_ice_area_fraction";
    String units "1";
    Float64 valid_max 1.0;
    Float64 valid_min 0.0;
  }
  CRW_SST {
    Float64 _FillValue -327.68;
    Float64 colorBarMaximum 34.0;
    Float64 colorBarMinimum -2.0;
    String coverage_content_type "physicalMeasurement";
    String ioos_category "Temperature";
    String long_name "sea surface temperature";
    String standard_name "sea_surface_temperature";
    String units "Celsius";
    Float64 valid_max 50.0;
    Float64 valid_min -2.0;
  }
  CRW_SSTANOMALY {
    Float64 _FillValue -327.68;
    Float64 colorBarMaximum 5.0;
    Float64 colorBarMinimum -5.0;
    String coverage_content_type "physicalMeasurement";
    String ioos_category "Temperature";
    String long_name "sea surface temperature anomaly";
    String units "Celsius";
    Float64 valid_max 15.0;
    Float64 valid_min -15.0;
  }
  CRW_SSTANOMALY_mask {
    Byte _FillValue -5;
    String _Unsigned "true";
    Float64 colorBarMaximum 4.0;
    Float64 colorBarMinimum 0.0;
    String comment "A 2D array, in the same size as the data array in the X and Y directions, classifying land, missing, and ice pixels that are all flagged by the same missing_value (specified by the variable attribute _FillValue) in the data array(s), along with water (data) pixels.";
    String coverage_content_type "thematicClassification";
    String flag_meanings "valid-water land missing ice";
    Byte flag_values 0, 1, 2, 4;
    String ioos_category "Other";
    String long_name "CRW_SSTANOMALY pixel characteristics flag array";
    String units "1";
  }
  NC_GLOBAL {
    String acknowledgement "NOAA Coral Reef Watch (CRW)";
    String cdm_data_type "Grid";
    String comment "This product is designed to improve on and replace the use of AVHRR Pathfinder SST for use within the Coral Reef Watch Program.";
    String Conventions "CF-1.6, ACDD-1.3";
    String creator_email "coralreefwatch@noaa.gov";
    String creator_institution "NOAA Coral Reef Watch (CRW)";
    String creator_name "NOAA Coral Reef Watch (CRW)";
    String creator_type "institution";
    String creator_url "https://coralreefwatch.noaa.gov";
    String date_created "2017-05-19";
    String date_issued "2017-05-19";
    String date_metadata_modified "2021-03-30";
    String date_modified "2020-06-04";
    Float64 Easternmost_Easting 179.975;
    String geospatial_bounds "POLYGON ((-90 -180, 90 -180, 90 180, -90 180, -90 -180))";
    String geospatial_bounds_crs "EPSG:4326";
    Float64 geospatial_lat_max 89.975;
    Float64 geospatial_lat_min -89.975;
    Float64 geospatial_lat_resolution 0.049999999999999996;
    String geospatial_lat_units "degrees_north";
    Float64 geospatial_lon_max 179.975;
    Float64 geospatial_lon_min -179.975;
    Float64 geospatial_lon_resolution 0.049999999999999996;
    String geospatial_lon_units "degrees_east";
    String history "2017-05-19T00:00:00Z Data obtained from NOAA Coral Reef Watch and re-distributed via THREDDS Data Server (TDS) at PacIOOS to provide temporal aggregation and distribution through NetCDF/OPeNDAP utilities like ncWMS and ERDDAP.
2018-11-26T00:00:00Z Upgraded dataset from v3.0 to v3.1, which also extends start date from 2013-06-03 back to 1985-04-01.
2020-06-04T00:00:00Z Although still v3.1, CRW implemented some changes to metadata and ice masks for transition to NOAA/NESDIS operational products.
2026-10-08T19:23:47Z (local files)
2026-10-08T19:23:47Z https://pae-paha.pacioos.hawaii.edu/erddap/griddap/dhw_5km.das";
    String id "CoralTemp-v3.1";
    String infoUrl "https://coralreefwatch.noaa.gov/satellite/";
    String institution "NOAA Coral Reef Watch (CRW)";
    String instrument "Earth Remote Sensing Instruments > Passive Remote Sensing > Spectrometers/Radiometers > Imaging Spectrometers/Radiometers > AHI > Advanced Himawari Imager, Earth Remote Sensing Instruments > Passive Remote Sensing > Spectrometers/Radiometers > Imaging Spectrometers/Radiometers > AVHRR > Advanced Very High Resolution Radiometer, Earth Remote Sensing Instruments > Passive Remote Sensing > Spectrometers/Radiometers > Imaging Spectrometers/Radiometers > GOES-13 Imager > Geostationary Operational Environmental Satellite 13-Imager, Earth Remote Sensing Instruments > Passive Remote Sensing > Spectrometers/Radiometers > Imaging Spectrometers/Radiometers > GOES-15 Imager > Geostationary Operational Environmental Satellite 15-Imager, Earth Remote Sensing Instruments > Passive Remote Sensing > Spectrometers/Radiometers > Imaging Spectrometers/Radiometers > SEVIRI > Spinning Enhanced Visible and Infrared Imager, Earth Remote Sensing Instruments > Passive Remote Sensing > Spectrometers/Radiometers > Imaging Spectrometers/Radiometers > VIIRS > Visible-Infrared Imager-Radiometer Suite";
    String instrument_vocabulary "GCMD Instrument Keywords";
    String ISO_Topic_Categories "biota, oceans";
    String keywords "Earth Science > Oceans > Coastal Processes > Coral Reefs, Earth Science > Oceans > Ocean Temperature > Sea Surface Temperature";
    String keywords_vocabulary "GCMD Science Keywords";
    String license "OSTIA Usage Statement (1985-2002): IMPORTANT usage statement. Unless otherwise agreed in writing, these data may be used for pure academic research only, with no commercial or other application and all usage must meet the Met Office Standard Terms and Conditions, which may be found here: https://www.metoffice.gov.uk/corporate/legal/tandc.html. The data may be used for a maximum period of 5 years. Reproduction of the data is permitted provided the following copyright statement is included: (C) Crown Copyright 2010, published by the Met Office. You must submit a completed reproduction license application form (here https://www.metoffice.gov.uk/corporate/legal/repro_licence.html) before using the data. This only needs to be completed once for each user. WARNING Some applications are unable to properly handle signed byte values. If values are encountered > 127, please subtract 256 from this reported value. GHRSST statement (2002-present): GHRSST protocol describes data use as free and open. Coral Reef Watch program statement: The data produced by Coral Reef Watch are available for use without restriction, but Coral Reef Watch relies on the ethics and integrity of the user to ensure that the source of the data and products is appropriately cited and credited. When using these data and products, credit and courtesy should be given to NOAA Coral Reef Watch. Please include the appropriate DOI associated with this dataset in the citation. For more information, visit the NOAA Coral Reef Watch website: https://coralreefwatch.noaa.gov. Recommendations for citing and providing credit are provided at https://coralreefwatch.noaa.gov/satellite/docs/recommendations_crw_citation.php. Users are referred to the footer section of Coral Reef Watch's website (https://coralreefwatch.noaa.gov/index.php) for disclaimers, policies, notices pertaining to the use of the data.";
    String locations "Geographic Region > Global Ocean";
    String locations_vocabulary "GCMD Location Keywords";
    String metadata_link "https://www.pacioos.hawaii.edu/metadata/dhw_5km.html";
    String naming_authority "org.pacioos";
    Float64 Northernmost_Northing 89.975;
    String platform "Earth Observation Satellites > GOES (Geostationary Operational Environmental Satellite) > GOES-13, Earth Observation Satellites > GOES (Geostationary Operational Environmental Satellite) > GOES-15, Earth Observation Satellites > Himawari > Himawari Meteorological Satellites, Earth Observation Satellites > Joint Polar Satellite System (JPSS) > SUOMI-NPP > Suomi National Polar-orbiting Partnership, Earth Observation Satellites > METEOSAT > METEOSAT-8, Earth Observation Satellites > METEOSAT > METEOSAT-11, Earth Observation Satellites > METOP > METOP-B > Meteorological Operational Satellite - B";
    String platform_vocabulary "GCMD Platform Keywords";
    String processing_level "Level 4";
    String product_version "3.1";
    String program "NOAA Coral Reef Watch (CRW)";
    String project "NOAA Coral Reef Watch (CRW)";
    String publisher_email "info@pacioos.org";
    String publisher_institution "Pacific Islands Ocean Observing System (PacIOOS)";
    String publisher_name "Pacific Islands Ocean Observing System (PacIOOS)";
    String publisher_type "institution";
    String publisher_url "http://www.pacioos.hawaii.edu";
    String references "https://coralreefwatch.noaa.gov/product/5km/methodology.php";
    String source "satellite data";
    String sourceUrl "(local files)";
    Float64 Southernmost_Northing -89.975;
    String standard_name_vocabulary "CF Standard Name Table v39";
    String summary "Contains a suite of NOAA Coral Reef Watch (CRW) version 3.1 operational global satellite coral bleaching heat stress monitoring products at 5-km resolution produced daily in near real-time, including sea surface temperature (SST), SST anomaly, HotSpot, Degree Heating Week (DHW), and Bleaching Alert Area (BAA). These data are based on CoralTemp Version 1.0, a daily global 5-km sea surface temperature dataset combined from: (1.) NOAA/NESDIS operational near-real-time daily global 5-km geostationary-polar-orbiting (geo-polar) blended night-only SST analysis, (2.) NOAA/NESDIS 2002-2016 reprocessed daily global 5-km geo-polar blended night-only SST analysis, and (3.) United Kingdom Met Office 1985-2002 daily global 5-km night-only SST reanalysis of Operational SST and Sea Ice Analysis (OSTIA). The SST anomaly is the difference of SST compared to daily SST climatology. The coral bleaching HotSpot is a special type of sea surface temperature (SST) anomaly and shows the difference of SST compared to a coral bleaching SST threshold climatology. DHW is the accumulation of Coral Bleaching HotSpots over a period of 12 consecutive weeks. The DHW value at any particular location at any particular time is the summation of the product of HotSpot values which are at least 1 deg C above the bleaching threshold SST and their durations in weeks over the most recent 12-week period. One DHW is equivalent to 1 week of SST at 1 deg C above the threshold or 0.5 week of SST at 2 deg C above the threshold, etc. The units for DHW are deg C-weeks, combining the intensity and duration of heat stress into one single number. Based on research at Coral Reef Watch, when the heat stress reaches 4 deg C-weeks, you can expect to see significant coral bleaching, especially in more sensitive species. When heat stress is 8 deg C-weeks or higher, you would likely see widespread bleaching and mortality from the heat stress.";
    String testOutOfDate "now-60hours";
    String time_coverage_duration "P1D";
    String time_coverage_end "2026-10-07T12:00:00Z";
    String time_coverage_resolution "P1D";
    String time_coverage_start "1985-04-01T12:00:00Z";
    String title "NOAA Coral Reef Watch Operational Daily Near-Real-Time Global 5-km Satellite Coral Bleaching Monitoring Products";
    Float64 Westernmost_Easting -179.975;
  }
}
