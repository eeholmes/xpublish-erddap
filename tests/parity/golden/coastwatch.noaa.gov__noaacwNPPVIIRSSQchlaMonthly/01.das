Attributes {
  time {
    String _CoordinateAxisType "Time";
    Float64 actual_range 1.3255056e+9, 1.7855856e+9;
    String axis "T";
    String calendar "gregorian";
    String coverage_content_type "coordinate";
    String ioos_category "Time";
    String long_name "Centered Time";
    String standard_name "time";
    String time_origin "01-JAN-1970 00:00:00";
    String units "seconds since 1970-01-01T00:00:00Z";
  }
  altitude {
    String _CoordinateAxisType "Height";
    String _CoordinateZisPositive "up";
    Float64 actual_range 0.0, 0.0;
    String axis "Z";
    String coverage_content_type "coordinate";
    String ioos_category "Location";
    String long_name "Altitude";
    String positive "up";
    String standard_name "altitude";
    String units "m";
  }
  latitude {
    String _CoordinateAxisType "Lat";
    Float64 actual_range -89.75625, 89.75625;
    String axis "Y";
    String comment "The latitude values are the centers of the grid cells.";
    String coverage_content_type "coordinate";
    String ioos_category "Location";
    String long_name "Latitude";
    String standard_name "latitude";
    String units "degrees_north";
    Float64 valid_max 90.0;
    Float64 valid_min -90.0;
  }
  longitude {
    String _CoordinateAxisType "Lon";
    Float64 actual_range -179.98125, 179.98125;
    String axis "X";
    String comment "The longitude values are the centers of the grid cells.";
    String coverage_content_type "coordinate";
    String ioos_category "Location";
    String long_name "Longitude";
    String standard_name "longitude";
    String units "degrees_east";
    Float64 valid_max 180.0;
    Float64 valid_min -180.0;
  }
  chlor_a {
    Float32 _FillValue -999.0;
    String C_format "%.4g";
    String cell_methods "time:mean(interval:1 month)";
    Float64 colorBarMaximum 30.0;
    Float64 colorBarMinimum 0.03;
    String colorBarScale "Log";
    String coverage_content_type "physicalMeasurement";
    String grid_mapping "coord_ref";
    String ioos_category "Ocean Color";
    String long_name "Chlorophyll Concentration, Default Algorithm";
    String references "O and #39;Reilly J. E. et al. (1998), Ocean color chlorophyll algorithms for SeaWiFS, J. Geophys. Res., 103(C11), 2493724953";
    String standard_name "mass_concentration_of_chlorophyll_a_in_sea_water";
    String units "mg m^-3";
    Float32 valid_max 100.0;
    Float32 valid_min 0.001;
  }
  NC_GLOBAL {
    String cdm_data_type "Grid";
    String comment "This is science quality data.";
    String Conventions "CF-1.6, COARDS, ACDD-1.3";
    String creator_email "coastwatch.info@noaa.gov";
    String creator_name "NOAA CoastWatch";
    String creator_type "institution";
    String creator_url "https://coastwatch.noaa.gov";
    Float64 Easternmost_Easting 179.98125;
    Float64 geospatial_lat_max 89.75625;
    Float64 geospatial_lat_min -89.75625;
    Float64 geospatial_lat_resolution 0.0375;
    String geospatial_lat_units "degrees_north";
    Float64 geospatial_lon_max 179.98125;
    Float64 geospatial_lon_min -179.98125;
    Float64 geospatial_lon_resolution 0.0375;
    String geospatial_lon_units "degrees_east";
    Float64 geospatial_vertical_max 0.0;
    Float64 geospatial_vertical_min 0.0;
    String geospatial_vertical_positive "up";
    String geospatial_vertical_units "m";
    String grid_mapping_name "latitude_longitude";
    String history "Sun Sep 20 01:55:01 2026
: /data/data652/coastwatch/oc/L3/scripts/bin/nccomposite -M gmean -T Month -m chlor_a /data/data652/coastwatch/oc/L3/scripts/config/chlor_a_comp_config.input /data/aftp/socd1/mecb/coastwatch/viirs/science/L3/global/chlora/monthly/WW00/V2026213_2026243_F31_WW00_chlora.nc
2026-10-09T17:29:37Z (local files)
2026-10-09T17:29:37Z https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPVIIRSSQchlaMonthly.das";
    String id "noaacwNPPVIIRSSQchlaMonthly";
    String identifier_product_doi "https://dx.doi.org";
    String identifier_product_doi_authority "https://dx.doi.org";
    String infoUrl "https://coastwatch.noaa.gov/cw/satellite-data-products/ocean-color/science-quality/viirs-snpp.html";
    String institution "NOAA NESDIS CoastWatch";
    String instrument "VIIRS";
    String keywords "algorithm, altitude, chemistry, chlor_a, chlorophyll, color, concentration, data, default, Earth Science  > Oceans  > Ocean Chemistry  > Chlorophyll, image, imager, imager/radiometer, imaging, infrared, L3, latitude, level, level-3, longitude, mapped, mass, mass_concentration_of_chlorophyll_a_in_sea_water, monthly, national, npp, ocean, ocean color, oceans, Oceans  > Ocean Optics  > Ocean Color, optics, orbiting, partnership, polar, polar-orbiting, radiometer, sea, seawater, smi, standard, star, suite, suite/suomi-npp, suomi, time, VIIRS, viirs, viirs-n, visible, water, ww00";
    String keywords_vocabulary "GCMD Science Keywords";
    String l2_flag_names "ATMFAIL,LAND,HIGLINT,BADLT,HISATZEN,CLOUD,HISOLZEN,CHLFAIL,NAVWARN,CLDSHDSTL,ALGICE,SEAICE,NAVFAIL,NEGLRC";
    String license "https://science.nasa.gov/earth-science/earth-science-data/data-information-policy/
The data may be used and redistributed for free but is not intended
for legal use, since it may contain inaccuracies. Neither the data
Contributor, ERD, NOAA, nor the United States Government, nor any
of their employees or contractors, makes any warranty, express or
implied, including warranties of merchantability and fitness for a
particular purpose, or assumes any legal liability for the accuracy,
completeness, or usefulness, of this information.

Please acknowledge the use of these data with the following statement: \"These data were provided by NOAA's Center for Satellite Applications  and  Research (STAR) and the CoastWatch program.\" To reference these data as a citation in a paper, please follow the instructions in the license and at this link: https://coastwatch.noaa.gov/erddap/information.html#citeDataset";
    String map_projection "geographic";
    String measure "Mean";
    String naming_authority "gov.noaa.coastwatch";
    Float64 Northernmost_Northing 89.75625;
    String platform "Suomi-NPP";
    String processing_level "L3 Mapped";
    String processing_version "Unspecified";
    String product_name "NOAA S-NPP VIIRS ocean color products from CoastWatch";
    String project "Ocean Color Science Team (NOAA/NESDIS/STAR/OCST)";
    String publisher_email "coastwatch.info@noaa.gov";
    String publisher_name "NOAA CoastWatch Central";
    String publisher_type "group";
    String publisher_url "https://coastwatch.noaa.gov/erddap/";
    String references "O and #39;Reilly J. E. et al. (1998), Ocean color chlorophyll algorithms for SeaWiFS, J. Geophys. Res., 103(C11), 2493724953";
    String Satellite "Suomi-NPP";
    String Sensor "VIIRS";
    String source "Satellite observations from VIIRS ocean color sensor";
    String sourceUrl "(local files)";
    Float64 Southernmost_Northing -89.75625;
    String spatialResolution "4.17 km";
    String standard_name_vocabulary "CF Standard Name Table v29";
    String summary "Level-3 Standard Mapped Image (SMI), Global, 4km, Chlorophyll, Monthly composite data from the Visible and Infrared Imager/Radiometer Suite (VIIRS). These are science quality data with a 15-day latency. The data, processed by the NOAA/STAR Ocean Color Team, are produced from MSL12 v1.2 using OC-SDR v04 and were release by CoastWatch as of 2017-08-07. VIIRS is a multi-disciplinary instrument that flies on the Suomi-NPP (National Polar-orbiting Partnership) satellite and is the successor to MODIS. Suomi-NPP is the initial spacecraft in the JPSS (Joint Polar Satellite Systems) series of spacecraft. JPSS is our Nation's next generation polar-orbiting operational environmental satellite system. JPSS is a collaborative program between NOAA and its acquisition agent NASA.";
    String temporal_range "Month";
    String testOutOfDate "now-33days";
    String time_coverage_end "2026-08-01T12:00:00Z";
    String time_coverage_resolution "PM1";
    String time_coverage_start "2012-01-02T12:00:00Z";
    String title "Chlorophyll, NOAA S-NPP VIIRS, Science Quality, Global 4km, Level 3, 2012-present, Monthly";
    Float64 Westernmost_Easting -179.98125;
  }
}
