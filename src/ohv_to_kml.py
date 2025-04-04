#!/usr/bin/env python3

import argparse
import geopandas as gpd
import fiona
from pathlib import Path

def filter_and_convert(input_geojson: str, output_gpx: str):
    """
    Filter GeoJSON features by OHV designation and convert to GPX
    
    Args:
        input_geojson: Path to input GeoJSON file
        output_gpx: Path to output GPX file
    """
    # List available drivers
    print("Available drivers:", fiona.supported_drivers)
    
    # Read the GeoJSON file
    gdf = gpd.read_file(input_geojson)
    
    # Filter for Open or Limited OHV designation
    filtered = gdf[
        (gdf["LUP_OHV_DSGNTN"] == "Open") | 
        (gdf["LUP_OHV_DSGNTN"] == "Limited")
    ]
    
    # Create output directory if it doesn't exist
    Path(output_gpx).parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Convert to GPX
        filtered.to_file(output_gpx, driver='GPX')
    except Exception as e:
        print(f"Error converting file: {e}")
        print("Available drivers:", fiona.supported_drivers)
        raise

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
        help="Output GPX file path"
    )
    
    args = parser.parse_args()
    
    # Change file extension to .gpx
    output_path = str(Path(args.output).with_suffix('.gpx'))
    filter_and_convert(args.input, output_path)

if __name__ == "__main__":
    main()
