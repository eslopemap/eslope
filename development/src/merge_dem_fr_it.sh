#!/bin/bash
set -euo pipefail # bash strict mode

# bottom = FR / IGN
# top = IT / Piemont

#gdal_translate -a_srs EPSG:2154 -a_nodata -99999 ../RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc clapier-lamb.tif
#gdaldem slope clapier-lamb.tif clapier-lamb-slope.tif
dem_bottom=clapier-lamb-slope.tif


#gdaldem slope DTM5_243.tif DTM5_243-utm32n-slope.tif
dem_top=DTM5_243-utm32n-slope.tif


cat > black.clr <<EOF
0        255 255 255 255
29.99999 255 255 255 255
30       244 204   0 255
33       244 204   0 255
45       255  17  17 255
49.99999 255  17  17 255
50        77  77  77 255
90        77  77  77 255
nv         0   0   0   0
EOF


cat > white.clr <<EOF
0        255 255 255 255
29.99999 255 255 255 255
30       244 204   0 255
33       244 204   0 255
45       255  17  17 255
49.99999 255  17  17 255
50        77  77  77 255
90        77  77  77 255
nv       255 255 255   0
EOF

cat > oblack.clr <<EOF
0        255 255 255 255
29.99999 255 255 255 255
30       244 204   0 255
33       244 204   0 255
45       255  17  17 255
49.99999 255  17  17 255
50        77  77  77 255
90        77  77  77 255
nv         0   0   0 255
EOF


cat > owhite.clr <<EOF
0        255 255 255 255
29.99999 255 255 255 255
30       244 204   0 255
33       244 204   0 255
45       255  17  17 255
49.99999 255  17  17 255
50        77  77  77 255
90        77  77  77 255
nv       255 255 255 255
EOF

function doit() {
  alpha=$3

  gdaldem color-relief $alpha $dem_bottom $1 tmp-slopeshade-bottom-proj.tif
  gdalwarp -t_srs WGS84 tmp-slopeshade-bottom-proj.tif tmp-slopeshade-bottom-$1.tif -overwrite

  gdaldem color-relief $alpha $dem_top $1 tmp-slopeshade-top-proj.tif
  gdalwarp -t_srs WGS84 tmp-slopeshade-top-proj.tif tmp-slopeshade-top-$2.tif -overwrite

  [ -n "$4" ] && a_nodata=-a_nodata || a_nodata=''
  gdal_merge.py $a_nodata $4 tmp-slopeshade-bottom-$1.tif tmp-slopeshade-top-$2.tif -o merge-$1.$2.$3.$4.tif
}

set -x

# doit owhite.clr oblack.clr '' 0
doit black.clr black.clr -alpha ''

# doit white.clr black.clr -alpha 0
# doit black.clr white.clr -alpha 0
# doit white.clr white.clr -alpha 0
# doit black.clr black.clr -alpha 0


# doit white.clr black.clr -alpha 255
# doit black.clr white.clr -alpha 255
# doit white.clr white.clr -alpha 255
# doit black.clr black.clr -alpha 255

set +x
