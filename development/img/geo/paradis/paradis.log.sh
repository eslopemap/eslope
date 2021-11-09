##
## Needs the big slopes tif as input.
## Takes from it a sample of size 2*z11 tiles covering fr & it,
## and run color-relief -> mbtiles on it
##


source ~/code/eddy-geek/TIL/geo/src/useful_extents.sh

extent=$=paradis_z11

resolution=2.388657133911758
gdalwarp \
  -co compress=zstd \
  -dstnodata 255 \
  -t_srs EPSG:3857 -tr $=resolution -$=resolution \
  -te_srs WGS84 -te $=extent \
  ~/code/eddy-geek/slope-ign-alti/alps/slopes-Lausanne-Jouques-Sanremo-Zermatt.tif \
  ./slopes-paradis.tif

sed 's/nv    0   0   0   0/nv  255 255 255 255/g' ../../../geo/data/gdaldem-slope-oslo14near.clr >! /tmp/gdaldem-slope-oslo14w.clr

time gdaldem color-relief ./slopes-paradis.tif \
  /tmp/gdaldem-slope-oslo14w.clr ./slopes-paradis.mbtiles \
  -nearest_color_entry -co TILE_FORMAT=png8


# Check for 4-bit palette
source ~/code/eddy-geek/TIL/geo/src/mbtidime/mbtshell.sh
mbt_first_tile slopes-paradis.mbtiles
file slopes-paradis-firsttile.png                                                                                                                     master ✚ ✱ ◼
# PNG image data, 256 x 256, 8-bit colormap, non-interlaced
identify -verbose slopes-paradis-firsttile.png | grep png:                                                                                            master ✚ ✱ ◼
#     png:IHDR.bit-depth-orig: 8
#     png:IHDR.bit_depth: 8
#     png:PLTE.number_colors: 12

# why do I only gain 1.5 % by moving to 4-bit?
# https://www.nayuki.io/page/png-file-chunk-inspector

# full thing

