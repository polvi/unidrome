#!/usr/bin/env python3

import argparse
import geopandas as gpd
import simplekml
from pathlib import Path

def filter_and_convert(input_geojson: str, output_file: str):
    """
    Filter GeoJSON features by OHV designation and convert to output format
    
    Args:
        input_geojson: Path to input GeoJSON file
        output_file: Path to output file
    """
    # Read the GeoJSON file
    gdf = gpd.read_file(input_geojson)
    
    # Filter for Open or Limited OHV designation
    filtered = gdf[
        (gdf["LUP_OHV_DSGNTN"] == "Open") | 
        (gdf["LUP_OHV_DSGNTN"] == "Limited")
    ]
    
    # Create output directory if it doesn't exist
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Create KML file
    kml = simplekml.Kml()
    
    # Add each polygon to KML
    for idx, row in filtered.iterrows():
        pol = kml.newpolygon(name=row["OHV_AREA_NM"])
        
        # Add description if available
        if "OHV_LMTN_TX" in row and not pd.isna(row["OHV_LMTN_TX"]):
            pol.description = row["OHV_LMTN_TX"]
        
        # Get coordinates from the geometry
        if row.geometry.geom_type == 'MultiPolygon':
            # Handle multipolygons by using the first polygon
            coords = row.geometry.geoms[0].exterior.coords
        else:
            coords = row.geometry.exterior.coords
            
        pol.outerboundaryis = list(coords)
        
        # Set style
        if row["LUP_OHV_DSGNTN"] == "Open":
            pol.style.polystyle.color = simplekml.Color.green
        else:  # Limited
            pol.style.polystyle.color = simplekml.Color.yellow
        pol.style.polystyle.fill = 1
        pol.style.polystyle.outline = 1
    
    # Save the KML file
    kml.save(output_file)

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
        help="Output file path"
    )
    
    args = parser.parse_args()
    filter_and_convert(args.input, args.output)

if __name__ == "__main__":
    main()
