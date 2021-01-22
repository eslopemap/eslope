IGN Recently opened access to [RGE ALTI 5m](https://geoservices.ign.fr/documentation/diffusion/telechargement-donnees-libres.html#rge-alti-5m) data

This post attempts to play with the data at a basic-level, to reproduce IGN's own slope maps.

# Data overview

For example this archive covers all the Alpes-Maritimes (06): [RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D006_2020-09-15.7z](ftp://RGE_ALTI_ext:Thae5eerohsei8ve@ftp3.ign.fr/RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D006_2020-09-15.7z)

The included "LISEZ-MOI.pdf" (=readme) is useless but the (french) documentation is here: RGE_ALTI:

* [DC_RGEALTI_2-0.pdf](https://geoservices.ign.fr/ressources_documentaires/Espace_documentaire/MODELES_3D/RGE_ALTI/DC_RGEALTI_2-0.pdf) - functional
* [DL_RGEALTI_2-0.pdf](https://geoservices.ign.fr/ressources_documentaires/Espace_documentaire/MODELES_3D/RGE_ALTI/DL_RGEALTI_2-0.pdf) - technical

We'll use a tile of Mont Clapier as an example:
* Folder *RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D006_2020-09-15/RGEALTI/1_DONNEES_LIVRAISON_2020-11-00140/RGEALTI_MNT_5M_ASC_LAMB93_IGN69_D006/*
* File *RGEALTI_FXX_0990_6305_MNT_LAMB93_IGN69.asc*
Where 0990 / 6305 are the X/Y of the NW corner of this tile.

It look like this:
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
* NODATA_value is self-explanatory
* xllcorner/yllcorner against X/Y in the projection

The projection used for all these coordinates is "[Lambert 93](https://fr.wikipedia.org/wiki/Projection_conique_conforme_de_Lambert#Lambert_93)" (French-specific)

There's some metadata in [IGNF.xml](https://librairies.ign.fr/geoportail/resources/IGNF.xml) (there's a copy in each archive) including bounding boxes for this projection: `<gml:ProjectedCRS gml:id="RGF93LAMB93"> ...`

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

# Generating slope

We will follow [Creating color relief and slope shading with gdaldem](https://blog.mastermaps.com/2012/06/creating-color-relief-and-slope-shading.html) - GDAL understands
our `.asc` (ASCII) file natively, the main difference with GeoTiff is the absence of built-in SRS (that we'll discuss later).

So we first compute the slope:

```bash
gdaldem slope RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc clapier_lamb_slope.tif
```

Then plot it in grey-scale.

```bash
echo "0 255 255 255\n90 0 0 0" > gdaldem-color-slope-greyscale.conf
gdaldem color-relief clapier_lamb_slope.tif gdaldem-color-slope-greyscale.conf clapier_slopeshade_greyscale.tif
```

[!img/geo/clapier_slopeshade_greyscale.jpg]

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
[!img/geo/clapier_slopeshade_ign.jpg]

And we can compare the result with the official IGN slope map on [geoportail.gouv.fr](https://www.geoportail.gouv.fr/carte?c=7.417854230209106,44.102449446150985&z=16&l0=GEOGRAPHICALGRIDSYSTEMS.MAPS:WMTS(1)&l1=GEOGRAPHICALGRIDSYSTEMS.SLOPES.MOUNTAIN::GEOPORTAIL:OGC:WMTS(0.59)&permalink=yes).

[!img/geo/ign-vs-gdem.jpg]

Pretty close! IGN has the benefit of using the RGE ALTI 1m, soon to be opened as well...

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

[!img/geo/clapier_slopeshade_oslo.jpg]

