#!/bin/bash -ex

#python scripts/overpass-latest.py
python scripts/gas-grass.py
#python scripts/google-places.py
cd data/content-pack 
find . -name ".DS_Store" -delete
rm -f barbless-maps.zip
zip -r barbless-maps barbless-maps
cd -
rclone copy data/content-pack/barbless-maps.zip vue-barbless:vue-barbless/content-packs/
