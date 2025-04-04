#!/usr/bin/env python3

import argparse
import geopandas as gpd
from pathlib import Path

def filter_and_convert(input_geojson: str, output_kml: str):
    """
    Filter GeoJSON features by OHV designation and convert to KML
    
    Args:
        input_geojson: Path to input GeoJSON file
        output_kml: Path to output KML file
    """
    # Read the GeoJSON file
    gdf = gpd.read_file(input_geojson)
    
    # Filter for Open or Limited OHV designation
    filtered = gdf[
        (gdf["LUP_OHV_DSGNTN"] == "Open") | 
        (gdf["LUP_OHV_DSGNTN"] == "Limited")
    ]
    
    # Create output directory if it doesn't exist
    Path(output_kml).parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to KML
    filtered.to_file(output_kml, driver='KML')

def main():
    parser = argparse.ArgumentParser(
        description="Filter GeoJSON by OHV designation and convert to KML"
    )
    parser.add_argument(
        "input", 
        help="Input GeoJSON file path"
    )
    parser.add_argument(
        "output",
        help="Output KML file path"
    )
    
    args = parser.parse_args()
    filter_and_convert(args.input, args.output)

if __name__ == "__main__":
    main()
