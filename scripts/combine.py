from lon_lat_lookup_gen import lon_lat_lookup, get_all_gdfs
import geopandas as gpd
import pandas as pd
import h3pandas
from sklearn.cluster import DBSCAN
import numpy as np

gdfs = get_all_gdfs()
for file in gdfs:
    # filter out closed airports and heliports
    g = gdfs[file]
    airports = g[g['_is_airport'] == True]
    active = airports[airports['_is_active'] == True]
    gdfs[file] = active

    gdfs[file].set_crs(epsg=4326, inplace=True)


gdfs = gdfs.values()
combined_gdf = pd.concat(gdfs, keys=range(len(gdfs)))
combined_gdf = combined_gdf.reset_index(level=1, drop=True).reset_index()
combined_gdf = gpd.GeoDataFrame(combined_gdf, geometry='geometry')
#combined_gdf.rename(columns={'index': '_source'}, inplace=True)

gdf = combined_gdf
coords = gdf.geometry.apply(lambda geom: (geom.centroid.x, geom.centroid.y)).tolist()
dbscan = DBSCAN(eps=.005, min_samples=2)
labels = dbscan.fit_predict(coords)

gdf['cluster'] = labels
gdf = gdf.reindex()
clustered_gdf = gdf[gdf['cluster'] != -1]

singles = gdf[gdf['cluster'] == -1]

grouped_clusters = clustered_gdf.groupby('cluster')
unique_clusters_list = []
duplicate_clusters_list = []
print("checking for dupes, # clusters: ", clustered_gdf['cluster'].unique())

i = 0
for cluster_label, cluster_points in grouped_clusters:
    i += 1
    if (i % 10000) == 0:
        print('at, ', i)
    if cluster_points['index'].duplicated().any():
        duplicate_clusters_list.append(cluster_points)
    else:
        unique_clusters_list.append(cluster_points)


print("concating uniques")
unique_clusters = pd.concat(unique_clusters_list, ignore_index=True)
print("dissolving uniques")
unique_clusters = unique_clusters.dissolve(by='cluster')
print("appending singles")
unique_clusters = pd.concat([unique_clusters, singles], ignore_index=True)
print("concating dupes")
duplicate_clusters = pd.concat(duplicate_clusters_list, ignore_index=True)

# Save the result to a new layer called "clusters"
print("duplicates: ", len(duplicate_clusters))
print("uniques: ", len(unique_clusters))
#duplicate_clusters.set_geometry('geometry')
#duplicate_clusters.to_file("package.gpkg", layer='duplicate_clusters', driver="GPKG")
#unique_clusters.set_geometry('geometry')
#unique_clusters.to_file("package.gpkg", layer='unique_clusters', driver="GPKG")

