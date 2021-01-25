IGN Recently opened access to [RGE ALTI 5m](https://geoservices.ign.fr/documentation/diffusion/telechargement-donnees-libres.html#rge-alti-5m) data

This post attempts to play with the data at a basic-level, to reproduce IGN's own slope maps.

# Data overview

For example this archive covers all the Alpes-Maritimes (06): [RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D006_2020-09-15.7z](ftp://RGE_ALTI_ext:Thae5eerohsei8ve@ftp3.ign.fr/RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D006_2020-09-15.7z). I weighs 313 MB / 1.7 GB uncompressed.
The included "LISEZ-MOI.pdf" (=readme) is useless but the (french) documentation is here: RGE_ALTI:

* [DC_RGEALTI_2-0.pdf](https://geoservices.ign.fr/ressources_documentaires/Espace_documentaire/MODELES_3D/RGE_ALTI/DC_RGEALTI_2-0.pdf) - functional
* [DL_RGEALTI_2-0.pdf](https://geoservices.ign.fr/ressources_documentaires/Espace_documentaire/MODELES_3D/RGE_ALTI/DL_RGEALTI_2-0.pdf) - technical

We'll use a tile of Mont Clapier as an example:
* Folder *RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D006_2020-09-15/RGEALTI/1_DONNEES_LIVRAISON_2020-11-00140/RGEALTI_MNT_5M_ASC_LAMB93_IGN69_D006/*
* File *RGEALTI_FXX_0990_6305_MNT_LAMB93_IGN69.asc* ;
  where 0990 / 6305 are the X/Y of the NW corner of this tile in kilometers.

Each tile is encoded using the [ESRI ASCII raster format](https://gis.stackexchange.com/questions/71867/understanding-esris-asc-file) (ASCIIGRID). It look like this:
```python
ncols        1000
nrows        1000
xllcorner    989997.500000000000
yllcorner    6300002.500000000000
cellsize     5.000000000000
NODATA_value  -99999.00
  1079.03 1079.89 ...
```
Where

* ... is a ncols x nrows grid of altitudes
* cellsize is precision (5 meters)
* NODATA_value is used to fill the grid, e.g. beyond borders
* xllcorner/yllcorner is the X/Y of the Lower-Left (SW) corner, and in meters this time.

The projection used for all these coordinates is "[Lambert 93](https://fr.wikipedia.org/wiki/Projection_conique_conforme_de_Lambert#Lambert_93)" (French-specific)

<img src="img/geo/lambert93.jpg" width="400">
<img src="img/geo/lambert93-horizon.jpg" width="400">

There's some metadata in [IGNF.xml](https://librairies.ign.fr/geoportail/resources/IGNF.xml) (there's a copy in each archive) including bounding boxes for this projection: `<gml:ProjectedCRS gml:id="RGF93LAMB93"> ...`

There's also a shape file in folder *3_SUPPLEMENTS_LIVRAISON_2020-11-00140*, which I suppose lets you load the full dataset in QGIS or using [gdal ESRI Shapefile / DBF](https://gdal.org/drivers/vector/shapefile.html) driver, but I haven't tried yet. Starting with a single file allows to iterate faster.

# GDAL setup

We'll use [GDAL](https://gdal.org/) to work with the data.

There are many tutorials out-there ; on Ubuntu 18.04 I could only easily install 3.0.4 from January 2020 (whereas the latest at this time is 3.2.1):

```bash
sudo add-apt-repository ppa:ubuntugis/ubuntugis-unstable
sudo apt install gdal-bin

# python part (not used today)
sudo apt install libgdal-dev
ogrinfo --version  # 3.0.4
pip install GDAL==3.0.4
```

GDAL understands our `.asc` file natively:
```bash
gdalinfo RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc
  Driver: AAIGrid/Arc/Info ASCII Grid
  Files: RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc
  Size is 1000, 1000
  ...
```

The main difference with something like GeoTiff is the absence of built-in SRS (that we'll discuss later).
# Generating slope

We will follow [Creating color relief and slope shading with gdaldem](https://blog.mastermaps.com/2012/06/creating-color-relief-and-slope-shading.html) -

So we first compute the slope:

```bash
gdaldem slope RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc clapier_lamb_slope.tif
```

Then plot it in grey-scale.

```bash
echo "0 255 255 255\n90 0 0 0" > gdaldem-color-slope-greyscale.conf
gdaldem color-relief clapier_lamb_slope.tif gdaldem-color-slope-greyscale.conf clapier_slopeshade_greyscale.tif
```

<img src="img/geo/clapier_slopeshade_greyscale.jpg" width="400">

We can use slope palette from IGN:
```python
gdaldem-color-slope-ign.conf:
0    255 255 255
29.9 255 255 255
30   242 229   0
34.9 242 229   0
35   243 148  25
39.9 243 148  25
40   240   0   0
44.9 232   0   0
45   200 137 187
90   200 137 187
```

```bash
gdaldem color-relief clapier_lamb_slope.tif gdaldem-color-slope-ign.conf clapier_slopeshade_ign.tif```
```

<img src="img/geo/clapier_slopeshade_ign.jpg" width="400">

And we can compare the result with the official IGN slope map on [geoportail.gouv.fr](https://www.geoportail.gouv.fr/carte?c=7.417854230209106,44.102449446150985&z=16&l0=GEOGRAPHICALGRIDSYSTEMS.MAPS:WMTS(1)&l1=GEOGRAPHICALGRIDSYSTEMS.SLOPES.MOUNTAIN::GEOPORTAIL:OGC:WMTS(0.59)&permalink=yes).

<img src="img/geo/ign-vs-gdem.jpg" width="700">

Pretty close! IGN has the benefit of using the RGE ALTI 1m, soon to be opened as well...I am actually surprised it's so close without correcting for the distortion as outlined [here](https://gis.stackexchange.com/questions/14750/using-srtm-global-dem-for-slope-calculation)

We can also use a more precise palette (useful for alpinism/ski-touring), like the one from OpenSlopeMap:
```python
  min   max    R   G   B       HTML
  0 °  -9 °    0   0   0    #FFFFFF
 10 ° -29 °    0 255   0    #00FF00
 30 ° -34 °  240 225   0    #F0E100
 35 ° -39 °  255 155   0    #FF9B00
 40 ° -42 °  255   0   0    #FF0000
 43 ° -45 °  255  38 255    #FF26FF
 46 ° -49 °  167  25 255    #A719FF
 50 ° -54 °  110   0 255    #6E00FF
 55 ° -90 °    0   0 255    #0000FF
```

Which I slightly tweaked in [gdaldem-color-slope-oslo.conf](data_geo/gdaldem-color-slope-oslo.conf)

```bash
gdaldem color-relief clapier_lamb_slope.tif gdaldem-color-slope-oslo.conf clapier_slopeshade_oslo.tif
```

<img src="img/geo/clapier_slopeshade_oslo.jpg" width="400">


# Projection conversion

If we want to put our new overlay online, we are going to need to get it to a more standard projection, WGS84. We'll need to tell gdal that what we've been using all this time is Lambert93, a.k.a EPSG:2154 (as pointed out by [GDAL-OGR](https://gdal.gloobe.org/gdal/presentation.html))

It is possible to do this directly on the raw elevation data (and translate it at the same time to GeoTiff), with:

```bash
gdalwarp -s_srs EPSG:2154 -t_srs WGS84 -of GTiff RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc clapier_wgs.tif
```

but I could not get `gdaldem slopes` to work on it, so it's better to convert our slope file:

```bash
gdalwarp -s_srs EPSG:2154 -t_srs WGS84 clapier_lamb_slope.tif clapier_wgs_slope.tif

gdaldem color-relief clapier_wgs_slope.tif gdaldem-color-slope-oslo.conf clapier_slopeshade_wgs_oslo.tif
```

Our overlay is now web-ready... or not, because of all missing data near corners.

<img src="img/geo/clapier_slopeshade_wgs_oslo.jpg" width="400">
