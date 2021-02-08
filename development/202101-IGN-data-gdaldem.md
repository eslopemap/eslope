IGN Recently opened access to the French DEM (Digital Elevation model): [RGE ALTI 5m](https://geoservices.ign.fr/documentation/diffusion/telechargement-donnees-libres.html#rge-alti-5m).

This post attempts to play with the data at a basic-level, to reproduce and improve upon IGN's own slope maps.

Table of contents
===============

* [Data overview](#data-overview)
* [GDAL setup](#gdal-setup)
* [Generating slope](#generating-slope)
* [Reprojection](#reprojection)
* [Handling the whole dataset](#handling-the-whole-dataset)
* [Mobile use](#mobile-use)
* [Possible integrations](#possible-integrations)

Data overview
===============

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

* ... is a ncols x nrows grid of elevations
* cellsize is precision (5 meters)
* NODATA_value is used to fill the grid, e.g. beyond borders
* xllcorner/yllcorner is the X/Y of the Lower-Left (SW) corner, and in meters this time.

The projection used for all these coordinates is "[Lambert 93](https://fr.wikipedia.org/wiki/Projection_conique_conforme_de_Lambert#Lambert_93)" (French-specific)

<img src="img/geo/lambert93.jpg" width="400">
<img src="img/geo/lambert93-horizon.jpg" width="400">

There's some metadata in [IGNF.xml](https://librairies.ign.fr/geoportail/resources/IGNF.xml) (there's a copy in each archive) including bounding boxes for this projection: `<gml:ProjectedCRS gml:id="RGF93LAMB93"> ...`

There's also a shape, listing every tile's extent and source which should let you load the full dataset, e.g. in QGIS or using [gdal ESRI Shapefile / DBF](https://gdal.org/drivers/vector/shapefile.html) driver.

``` bash
ogrinfo  3_SUPPLEMENTS_LIVRAISON_2020-11-00140/RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D006_2020-09-15/source.shp
INFO: Open of `source.shp'
      using driver `ESRI Shapefile' successful.
Layer name: source
Metadata:
  DBF_DATE_LAST_UPDATE=2020-11-10
Geometry: Polygon
Feature Count: 1324
Extent: (989997.500000, 6270002.500000) - (1079997.500000, 6375002.500000)
Layer SRS WKT:
PROJCRS["RGF93_Lambert_93",
     ...
Data axis to CRS axis mapping: 1,2
CODE: Integer (9.0)
RESOLUTION: String (80.0)
ORIGINE: String (80.0)
PRECISION: String (80.0)

OGRFeature(source):0
  CODE (Integer) = 7
  RESOLUTION (String) = 5 m
  ORIGINE (String) = Radar
  PRECISION (String) = 1 m < Emq < 7 m
  POLYGON ((1014997.5 6315002.5,1019997.5 6315002.5,1019997.5 6310002.5,1014997.5 6310002.5,1014997.5 6315002.5))

...
```

GDAL setup
===============

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

We'll start with a single file to iterate faster.

GDAL understands our `.asc` file natively:
```bash
gdalinfo RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc
  Driver: AAIGrid/Arc/Info ASCII Grid
  Files: RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc
  Size is 1000, 1000
  ...
```

The main difference with something like GeoTiff is the absence of built-in SRS (that we'll discuss later).

Generating slope
===============

We will follow [Creating color relief and slope shading with gdaldem](https://blog.mastermaps.com/2012/06/creating-color-relief-and-slope-shading.html) -

So we first compute the slope:

```bash
gdaldem slope RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc clapier_lamb_slope.tif
```

Then plot it in grey-scale.

```bash
echo "0 255 255 255\n90 0 0 0" > gdaldem-slope-greyscale.clr
gdaldem color-relief clapier_lamb_slope.tif gdaldem-slope-greyscale.clr clapier_slopeshade_greyscale.tif
```

<img src="img/geo/clapier_slopeshade_greyscale.jpg" width="400">

We can use slope palette from IGN:
```python
gdaldem-slope-ign.clr:
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
gdaldem color-relief clapier_lamb_slope.tif gdaldem-slope-ign.clr clapier_slopeshade_ign.tif```
```

<img src="img/geo/clapier_slopeshade_ign.jpg" width="400">

And we can compare the result with the official IGN slope map on [geoportail.gouv.fr](https://www.geoportail.gouv.fr/carte?c=7.417854230209106,44.102449446150985&z=16&l0=GEOGRAPHICALGRIDSYSTEMS.MAPS:WMTS(1)&l1=GEOGRAPHICALGRIDSYSTEMS.SLOPES.MOUNTAIN::GEOPORTAIL:OGC:WMTS(0.59)&permalink=yes).

<img src="img/geo/ign-vs-gdem.jpg" width="700">

Pretty close! IGN has the benefit of using the RGE ALTI 1m, soon to be opened as well...I am actually surprised it's so close without correcting for the distortion as outlined [here](https://gis.stackexchange.com/questions/14750/using-srtm-global-dem-for-slope-calculation)

We can also use a more precise palette (useful for alpinism/ski-touring), like the one from OpenSlopeMap:
```python
  min   max    R   G   B       HTML  color
  0 °  -9 °    0   0   0    #FFFFFF  white
 10 ° -29 °    0 255   0    #00FF00  green
 30 ° -34 °  240 225   0    #F0E100  yellow
 35 ° -39 °  255 155   0    #FF9B00  orange
 40 ° -42 °  255   0   0    #FF0000  red
 43 ° -45 °  255  38 255    #FF26FF  magenta
 46 ° -49 °  167  25 255    #A719FF  violet
 50 ° -54 °  110   0 255    #6E00FF  purple
 55 ° -90 °    0   0 255    #0000FF  blue
```
<img src="img/geo/oslo-colormap-palette.jpg" width="50">
<img src="img/geo/oslo-colormap-gradient.jpg" width="400">

Which I slightly tweaked above to make it continuous, in [gdaldem-slope-oslo.clr](geo/data/gdaldem-slope-oslo.clr). Let's use it:


```bash
gdaldem color-relief clapier_lamb_slope.tif gdaldem-slope-oslo.clr clapier_slopeshade_oslo.tif
```

<img src="img/geo/clapier_slopeshade_oslo.jpg" width="400">


Reprojection
===============

If we want to put our new overlay online, we are going to need to get it to a more standard projection, WGS84 (EPSG:3857) aka WebMercator or Pseudo-Mercator. Since `asc` files are not georeferenced, we'll need to tell gdal that what we've been using all this time is *Lambert93*, a.k.a *EPSG:2154* (as pointed out by [GDAL-OGR](https://gdal.gloobe.org/gdal/presentation.html))

It is possible to do this directly on the raw elevation data (and translate it at the same time to GeoTiff), with:

```bash
gdalwarp -s_srs EPSG:2154 -t_srs WGS84 -of GTiff RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc clapier_wgs.tif
```

... but doing so will prevent us from using `gdaldem slopes` effectively (it needs meter units for x/y/z, and result would be biased anyway) so we will instead convert the result of our slope computation:

```bash
gdalwarp -s_srs EPSG:2154 -t_srs WGS84 clapier_lamb_slope.tif clapier_wgs_slope.tif

gdaldem color-relief clapier_wgs_slope.tif gdaldem-slope-oslo.clr clapier_slopeshade_wgs_oslo.tif
```

<img src="img/geo/clapier_slopeshade_wgs_oslo.jpg" width="400">

Handling the whole dataset
===============

So far we've worked on only one tile, but we can instead start by merging all the tiles in a big GeoTIFF. We just need to specify the Lambert projection as `.asc` doesn't provide it.

```bash
cd RGEALTI_*D006_*/RGEALTI/1_DONNEES_LIVRAISON_*/RGEALTI_*/

for ascfile in *.asc; do
    gdal_translate -a_srs EPSG:2154 -a_nodata -99999 $ascfile ${ascfile/.asc/-lambert.tif}
done

gdal_merge.py *.tif -o data-lamb-tiled.tif -a_nodata -99999 -co TILED=YES
```

I am not sure of the best way to handle nodata, the translate doc says:

> Assign a specified nodata value to output bands *[...]* if the input dataset has a nodata value, this does not cause pixel values that are equal to that nodata value to be changed to the value specified with this option.

The last command took 30 seconds and generated a 1.5GB file.

*Note 1:* without the `-co TILED` option, gdal will generate a striped file, which in this case takes 2 minutes to create, is 2% bigger, and might be less efficient to use.

*Note 2:* If you don't have `gdal_merge.py`, you [can](https://gis.stackexchange.com/questions/230553/merging-all-tiles-from-one-directory-using-gdal) instead use `gdalbuildvrt mosaic.vrt *.tif` then `gdal_translate` it.

From there we can generate the slope model and shade with `gdaldem` as above.

```bash
gdaldem color-relief clapier_lamb_slope.tif gdaldem-slope-oslo.clr clapier_slopeshade_oslo.tif
```

Note that you can use GeoTIFF Jpeg compression with `-co "COMPRESS=JPEG" -co "PHOTOMETRIC=YCBCR"`, at the expense of transparency.

What about the italian border?
===============

Our Italian neighbours in Piemont have an even more impressive DEM, called *RIPRESA AEREA ICE 2009-2011 - DTM 5*, hosted [here](http://www.geoportale.piemonte.it/geonetworkrp/srv/ita/metadata.show?id=2552&currTab=rndt). Unlike the current IGN *RGE ALTI*, partially based on RADAR, it uses LiDAR *even in the mountains*. Here's how much better it is in the *Monte Oronaye / Tête de Moïse* area:

<img src="img/geo/oronaye-sample-it.png" width="300">
<img src="img/geo/oronaye-sample-fr.png" width="300">

So we are going to use it for the italian side and on the border overlap.

Some differences in this dataset:
* It comes already in georeferenced TIF
* It uses yet another projection, *UTM 32N* aka *EPSG:32632*. Again we'll compute slopes **before** reprojecting.
* While the French use `-a_nodata -99999`, the Italian use `-a_nodata -99` (and gdal uses `-9999` - no, it's not confusing).

Clapier sample
--------------

Let's start with the Italian side of Mont Clapier, in tile 243.

<details>
<summary>(How we got clapier_slopeshade_wgs_oslo.tif previously)</summary>

```bash
gdal_translate -a_srs EPSG:2154 -a_nodata -99999 ../RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc clapier-lamb.tif
gdaldem slope clapier-lamb.tif clapier-lamb-slope.tif
gdaldem color-relief -alpha clapier-lamb-slope.tif ../gdaldem-slope-sorbet-nvwhite.clr clapier-lamb-slopeshade-sorbet.tif
gdalwarp -t_srs WGS84 clapier-lamb-slopeshade-sorbet.tif clapier-wgs-slopeshade-sorbet.tif
```
</details>

```bash
wget 'http://www.datigeo-piem-download.it/static/regp01/DTM5_ICE/RIPRESA_AEREA_ICE_2009_2011_DTM-SDO_CTR_FOGLI50-243-EPSG32632-TIF.zip'
unzip *243*.zip
gdaldem slope DTM5_243.tif DTM5_243-utm32n-slope.tif
gdaldem color-relief -alpha DTM5_243-utm32n-slope.tif ../gdaldem-slope-sorbet.clr DTM5_243-utm32n-slopeshade-sorbet.tif
gdalwarp -t_srs WGS84 DTM5_243-utm32n-slopeshade-sorbet.tif DTM5_243-slopeshade-sorbet.tif
gdal_merge.py clapier-wgs-slopeshade-sorbet.tif DTM5_243-slopeshade-sorbet.tif -o clapier_sorbet_frit.tif
```

This is the same workflow we've used with the IGN data, and when we merge the 2 files we make sure the italian one is last.

No need to add `gdalwarp -srcnodata -99 -dstnodata -99999`, the `gdaldem slope` output has a no_data of `-9999` for both datasets.

This is then transformed by the "nv" line in our `.clr` file.

France has a nodata that is white transparent: `nv 255 255 255 0`,<br/>
while Italy has a nodata that is black transparent: `nv 0 0 0 0`.

Then, since

Mobile use
===============

To convert to mbtiles (which will automatically reproject to EPSG:3857 WebMercator as needed):

```bash
gdal_translate -of MBTiles clapier_slopeshade_oslo.tif clapier_slopeshade_oslo.mbtiles
```

The whole 06/Alpes-Maritimes county in this format will weigh 150 MB, contain only zoom level 14 as evidenced by `gdalinfo`, and crash regular desktop image viewers.

<img src="img/geo/06_slopeshade_oslo.jpg" width="400">

Good maps like [Sorbetto](https://tartamillo.wordpress.com/sorbetto/) only include slope shade starting at level 15, which can be achieved thus:

```bash
gdal_translate -of MBTiles -co ZOOM_LEVEL_STRATEGY=UPPER input.tif output.mbtiles
```

In this case the file will weigh 450 MB and took 5 minutes to generate on my recent laptop.

Contours
===============


```bash
mkdir contour ; cd contour
# Just to add the projection
gdal_translate -a_srs EPSG:2154 ../RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc clapier_lamb.tif
gdaldem slope clapier_lamb.tif clapier_lamb_slope.tif
# Compute contour
# gdal_contour -a elev -i 10 clapier_lamb_slope.tif clapier_lamb_contour.shp
# gdalwarp -s_srs EPSG:2154 -t_srs WGS84 clapier_lamb_contour.shp clapier_wgs_contour.shp
# 'not recognized as a supported file format.' So wwe reproject before :-/
gdalwarp -s_srs EPSG:2154 -t_srs WGS84 clapier_lamb_slope.tif clapier_wgs_slope.tif
gdal_contour -a elev -i 10 clapier_wgs_slope.tif clapier_wgs_contour.shp

# nik2img.py jotunheimen_contours.xml jotunheimen_contours.png -d 4096 4096 --projected-extent 460000 6810000 470000 6820000

```

Now we have a Shapefile that we need to turn into image pixels, aka rasterize.

I'll start with gdal_rasterize following [this](https://gis.stackexchange.com/questions/144920/problem-with-contour-lines-thickness-in-bigger-zoom-levels) and especially [raster tiles from vector data with GDAL](https://gis.stackexchange.com/questions/160030/raster-tiles-from-vector-data-with-gdal-how-to-avoid-aliasing-artefacts). Rendering is not as polished as alternatives.

```bash
sudo apt install -y apcalc
z=14
gdal_rasterize \
        --config GDAL_CACHEMAX 1024 \
        -ts $(calc "2851 << (${z} - 12)") \
            $(calc "4220 << (${z} - 12)") \
        -ot byte -of GTiff -co COMPRESS=DEFLATE -co PREDICTOR=2 -co ZLEVEL=9 \
        -ot Byte -burn 0 -a_nodata 255 \
        -l clapier_wgs_contour.shp clapier_wgs_contour_z${z}.tif
```

Alternatives to investigate:

* Mapnik
<details> <summary>Aborted mapnik-render tentative</summary>
First, setup: on ubuntu, `sudo apt install libmapnik-dev mapnik-utils` (using 3.0.22)

```xml
cat mapnik_contour_conf.xml
<Map srs="+proj=utm +zone=32 +ellps=WGS84 +datum=WGS84 +units=m +no_defs">

  <Style name="contours 10m style">
    <Rule>
      <LineSymbolizer stroke="#747b90" stroke-width="0.7" />
    </Rule>
  </Style>

  <Layer name="contours 10m">
    <StyleName>contours 10m style</StyleName>
    <Datasource>
      <Parameter name="type">shape</Parameter>
      <Parameter name="file">clapier_wgs_contour.shp</Parameter>
    </Datasource>
  </Layer>

</Map
```

```bash
mapnik-render --xml mapnik_contour_conf.xml --img clapier_wgs_contour.img
```

Unfortunately mapnik-render is unusable this way ([issue](https://github.com/mapnik/mapnik/issues/3373))

Maybe I should try [docker-mapnik3 / renderd](https://github.com/jawg/docker-mapnik3) ans [conf to use](https://github.com/jawg/docker-mapnik3/issues/2) instead. Or using the mapnik [python bindings](https://github.com/mapnik/python-mapnik/blob/master/docs/getting-started.md)

</details>

* [contour-tiles](
https://github.com/joe-akeem/contour-tiles/blob/master/Makefile)
... which uses postgis then tippecanoe to create vector contour (but that would only work on OruxMaps).

* [Creating a custom cycling map from open data](https://dev.to/hiddewie/creating-a-custom-cycling-map-3g2a) -> [map-it](https://github.com/hiddewie/map-it/)

Possible integrations
===============

This maps could benefit from the more precise contour lines/relief:

* [OpenSlopeMap](https://www.openslopemap.org/projekt/hintergrundinformationen/)
* OpenAndroMaps [Elevate](https://www.openandromaps.org/en/legend/elevate-mountain-hike-theme) based on [MapsForge](https://wiki.openstreetmap.org/wiki/Mapsforge)
* OpenTopoMap (on [github](https://github.com/der-stefan/OpenTopoMap/tree/master/mapnik))
* OpenHikingMap / [maps.refuges.info](https://wiki.openstreetmap.org/wiki/Hiking/mri)
* ThunderForest Topo / OpenCycleMap / my.viewranger.com (private)
* [MapTiler Topo](https://www.maptiler.com/maps/#topo) (based on OpenTilesMap but Topo is private)

On mobile
----------

We could convert the raw DEM (Digital Elevation Model) to use it directly in [OruxMaps](https://www.oruxmaps.com/cs/en/blog/25-dem-files) or [AlpineQuest](https://www.alpinequest.net/en/help/v2/elevations), or [Locus Map Pro](https://docs.locusmap.eu/doku.php?id=manual:faq:how_to_add_map_shading). These apps are able to display relief or slope shade and more based on the DEM.

However at this time they only support lower-precision formats, like the SRTM `hgt` format which has maximum precision of 1 arc-second (≈30 meters), so we are unlikely to see much improved quality after downsampling. If you want to try, *Sonnyy* already made the downsampled 1" DEM [here](https://data.opendataportal.at/dataset/dtm-france).

> *[Orux]* Supported SRTM-DTED and GTOPO30/SRTM30 files. You have to copy the .HGT or the .DEM + .HDR files in the oruxmaps/dem/ folder.

> *[Alpine]* You must use DEM files in the “.HGT” format (either 1201 or 3601 values per lines)


So I will be using the MBTiles above as overlay instead.
