Attributes {
  latitude {
    String _CoordinateAxisType "Lat";
    Float64 actual_range -90.0, 90.0;
    String axis "Y";
    String ioos_category "Location";
    String long_name "Latitude";
    String point_spacing "even";
    String standard_name "latitude";
    String units "degrees_north";
  }
  longitude {
    String _CoordinateAxisType "Lon";
    Float64 actual_range 0.0, 359.91999999999996;
    String axis "X";
    String ioos_category "Location";
    String long_name "Longitude";
    String point_spacing "even";
    String standard_name "longitude";
    String units "degrees_east";
  }
  ROSE {
    Float32 _FillValue -1.0e+34;
    Float64 colorBarMaximum 5638.0;
    Float64 colorBarMinimum -7009.0;
    String history "From worldbath.nc";
    String ioos_category "Bathymetry";
    String long_name "Relief Of the Surface of the Earth";
    Float32 missing_value -1.0e+34;
    String positive "up";
    String standard_name "height";
    String units "meters";
  }
  NC_GLOBAL {
    String acknowledgement "The Pacific Islands Ocean Observing System (PacIOOS) is funded through the National Oceanic and Atmospheric Administration (NOAA) as a Regional Association within the U.S. Integrated Ocean Observing System (IOOS). PacIOOS is coordinated by the University of Hawaii School of Ocean and Earth Science and Technology (SOEST).";
    String cdm_data_type "Grid";
    String comment "These data are provided by the NOAA National Centers for Environmental Information (NCEI) Marine Geology and Geophysics (MGG) Division.";
    String Conventions "CF-1.6, ACDD-1.3";
    String creator_email "mgg.info@noaa.gov";
    String creator_institution "NOAA Marine Geology and Geophysics (MGG)";
    String creator_name "Peter W. Sloss";
    String creator_type "person";
    String creator_url "https://www.ngdc.noaa.gov/mgg/";
    String date_created "1988-01-01";
    String date_issued "1988-01-01";
    String date_metadata_modified "2021-03-25";
    String date_modified "1988-01-01";
    String drawLandMask "under";
    Float64 Easternmost_Easting 359.91999999999996;
    String geospatial_bounds "POLYGON ((-90.0 -180.0, 90.0 -180.0, 90.0 180.0, -90.0 180.0, -90.0 -180.0))";
    String geospatial_bounds_crs "EPSG:4326";
    Float64 geospatial_lat_max 90.0;
    Float64 geospatial_lat_min -90.0;
    Float64 geospatial_lat_resolution 0.08333333333333333;
    String geospatial_lat_units "degrees_north";
    Float64 geospatial_lon_max 359.91999999999996;
    Float64 geospatial_lon_min 0.0;
    Float64 geospatial_lon_resolution 0.08333410511692521;
    String geospatial_lon_units "degrees_east";
    String history "2012-02-28T00:00:00Z Downloaded from NOAA/NCEI/MMG by J. Potemra.
2026-09-16T20:55:02Z https://pae-paha.pacioos.hawaii.edu/thredds/dodsC/etopo5
2026-09-16T20:55:02Z http://localhost:8080/erddap/griddap/etopo5_EDDGridCopy.das";
    String id "etopo5";
    String infoUrl "https://www.ngdc.noaa.gov/mgg/global/etopo5.HTML";
    String institution "NOAA Marine Geology and Geophysics (MGG)";
    String instrument "Not Applicable > Not Applicable";
    String instrument_vocabulary "GCMD Instrument Keywords";
    String IRI_LDEO_note "updated 27 Feb 1998 from NGDC CD-ROM 29 April 1993";
    String ISO_Topic_Categories "elevation, oceans";
    String keywords "Earth Science > Land Surface > Topography > Terrain Elevation > Digital Elevation/Terrain Model (Dem), Earth Science > Oceans > Bathymetry/Seafloor Topography > Bathymetry";
    String keywords_vocabulary "GCMD Science Keywords";
    String license "The data may be used and redistributed for free but is not intended for legal use, since it may contain inaccuracies. Neither the data Contributor, University of Hawaii, PacIOOS, NOAA, State of Hawaii nor the United States Government, nor any of their employees or contractors, makes any warranty, express or implied, including warranties of merchantability and fitness for a particular purpose, or assumes any legal liability for the accuracy, completeness, or usefulness, of this information.";
    String locations "Geographic Region > Global";
    String locations_vocabulary "GCMD Location Keywords";
    String metadata_link "https://www.pacioos.hawaii.edu/metadata/etopo5.html";
    String naming_authority "org.pacioos";
    Float64 Northernmost_Northing 90.0;
    String platform "Models/Analyses > > DEM > Digital Elevation Model";
    String platform_vocabulary "GCMD Platform Keywords";
    String program "Pacific Islands Ocean Observing System (PacIOOS)";
    String project "Pacific Islands Ocean Observing System (PacIOOS)";
    String publisher_email "info@pacioos.org";
    String publisher_institution "Pacific Islands Ocean Observing System (PacIOOS)";
    String publisher_name "Pacific Islands Ocean Observing System (PacIOOS)";
    String publisher_type "institution";
    String publisher_url "http://www.pacioos.hawaii.edu";
    String references "https://www.ngdc.noaa.gov/mgg/global/etopo5.HTML";
    String source "ETOPO5 Global Surface Relief";
    String sourceUrl "https://pae-paha.pacioos.hawaii.edu/thredds/dodsC/etopo5";
    Float64 Southernmost_Northing -90.0;
    String standard_name_vocabulary "CF Standard Name Table v39";
    String summary "ETOPO5 is a 5 arc-minute global relief model of Earth's surface that integrates land topography and ocean bathymetry. It was built from numerous global and regional data sets. This historical dataset has been deprecated in favor of the newer and higher-resolution ETOPO1 1 arc-minute global relief model.";
    String time_coverage_duration "P0D";
    String time_coverage_resolution "P0D";
    String title "ETOPO5 Global Surface Relief";
    Float64 Westernmost_Easting 0.0;
  }
}
