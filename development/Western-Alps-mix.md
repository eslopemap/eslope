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

The projection used for all these coordinates is the French-specific [Lambert 93](https://fr.wikipedia.org/wiki/Projection_conique_conforme_de_Lambert#Lambert_93).

<img src="img/geo/lambert93.jpg" width="400">
<img src="img/geo/lambert93-horizon.jpg" width="400">

There's some metadata in [IGNF.xml](https://librairies.ign.fr/geoportail/resources/IGNF.xml) (there's a copy in each archive) including bounding boxes for this projection: `<gml:ProjectedCRS gml:id="RGF93LAMB93"> ...`

There's also a shape, listing every tile's extent and source which should let you load the full dataset, e.g. in QGIS or using [gdal ESRI Shapefile / DBF](https://gdal.org/drivers/vector/shapefile.html) driver.

```bash
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
gdaldem color-relief clapier_lamb_slope.tif gdaldem-slope-ign.clr clapier_slopeshade_ign.tif
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
<img src="img/geo/oslo-colormap-gradient.png" width="400">

Which I slightly tweaked above to make it continuous, in [gdaldem-slope-oslo.clr](geo/data/gdaldem-slope-oslo.clr). Let's use it:


```bash
gdaldem color-relief clapier_lamb_slope.tif gdaldem-slope-oslo.clr clapier_slopeshade_oslo.tif
```

<img src="img/geo/clapier_slopeshade_oslo.jpg" width="400">

It can be useful to differentiate missing data from "flat" slope (white), for example by making it transparent. This can help to merge multiple DEM together as we'll do later.
To do so, the `clr` files I ended up using have a 4th column for transparency (255 for opaque) and an additional `nv 0 0 0 0` line to be used with the `gdaldem color-relief -alpha` option.

Note that transparency is not necessary to make a slope overlay, as one can use the "multiply" blending option (available for example on mobile [AlpineQuest](https://www.alpinequest.net/forum/viewtopic.php?t=3991), [LocusMaps](https://docs.locusmap.eu/doku.php?id=manual:user_guide:maps_tools:overlays)) or OruxMaps, to avoid the loss of contrast of a classic translucent overlay.


Reprojection
===============

If we want to put our new overlay online, we are going to need to get it to a more standard projection, WGS84 Pseudo-Mercator ([EPSG:3857](https://epsg.io/3857)) aka WebMercator -- not to be [confused](https://gis.stackexchange.com/a/48952/176462) with WGS84 / EPSG 4326.

 Since `asc` files are not georeferenced, we'll need to tell gdal that what we've been using all this time is *Lambert93*, a.k.a *EPSG:2154* (as pointed out by [GDAL-OGR](https://gdal.gloobe.org/gdal/presentation.html))

It is possible to do this directly on the raw elevation data (and translate it at the same time to GeoTiff), with:

```bash
gdalwarp -s_srs EPSG:2154 -t_srs EPSG:3857 -of GTiff RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc clapier_wgs.tif
```

... but doing so will prevent us from using `gdaldem slopes` effectively (it needs meter units for x/y/z, and result would be biased anyway) so we will instead convert the result of our slope computation:

```bash
gdalwarp -s_srs EPSG:2154 -t_srs EPSG:3857 clapier_lamb_slope.tif clapier_slope.tif

gdaldem color-relief clapier_wgs_slope.tif gdaldem-slope-oslo.clr clapier_slopeshade_oslo.tif
```

<img src="img/geo/clapier_slopeshade_wgs_oslo.jpg" width="400">


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

We will also use
* the Aosta Valley 2005/2008 DEM, which has an even higher 2m resolution and is hosted [here](https://geoportale.regione.vda.it/download/dtm/) and uses *UTM ED50 32N* aka *EPSG:23032*.
* the swissALTI3D dataset hosted [here](https://www.swisstopo.admin.ch/de/geodata/height/alti3d.html)

Clapier sample
--------------

Let's start with the Italian side of Mont Clapier, in tile 243.

<details>
<summary>(How we got clapier-slopeshade-sorbet.tif previously)</summary>

```bash
gdal_translate -a_srs EPSG:2154 -a_nodata -99999 ../RGEALTI_FXX_1050_6345_MNT_LAMB93_IGN69.asc clapier-lamb.tif
gdaldem slope clapier-lamb.tif clapier-lamb-slope.tif
gdaldem color-relief -alpha clapier-lamb-slope.tif ../gdaldem-slope-sorbet.clr clapier-lamb-slopeshade-sorbet.tif
gdalwarp -t_srs EPSG:3857 clapier-lamb-slopeshade-sorbet.tif clapier-slopeshade-sorbet.tif
```
</details>

```bash
wget 'http://www.datigeo-piem-download.it/static/regp01/DTM5_ICE/RIPRESA_AEREA_ICE_2009_2011_DTM-SDO_CTR_FOGLI50-243-EPSG32632-TIF.zip'
unzip *243*.zip
gdaldem slope DTM5_243.tif DTM5_243-utm32n-slope.tif
gdaldem color-relief -alpha DTM5_243-utm32n-slope.tif ../gdaldem-slope-sorbet.clr DTM5_243-utm32n-slopeshade-sorbet.tif
gdalwarp -t_srs EPSG:3857 DTM5_243-utm32n-slopeshade-sorbet.tif DTM5_243-slopeshade-sorbet.tif
gdal_merge.py -a_nodata=0 clapier-wgs-slopeshade-sorbet.tif DTM5_243-slopeshade-sorbet.tif -o clapier_sorbet_frit.tif
```

This is the same workflow we've used with the IGN data, and when we merge the 2 files we make sure the italian one is last.

It is important that the 2 source files have an alpha layer, otherwise `gdal_merge` will not "blend" the layers, and/or produce black borders (unless tricked with `-a_nodata 0`).
This is done by the `nv` line in our `.clr` file catching the *nodata=-9999* in the *...-slope.tif* files.

<img src="img/geo/clapier_sorbet_frit.webp" width="300">


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

*__Note: Tiling:__* without the `-co TILED` option, gdal will generate a striped file, which in this case takes 2 minutes to create, is 2% bigger, and might be less efficient to use.

*__Note: Memory:__* `gdal_merge.py` needs to put all datat in memory, instead you [can](https://gis.stackexchange.com/questions/230553/merging-all-tiles-from-one-directory-using-gdal) use `gdalbuildvrt mosaic.vrt *.tif` then `gdal_translate` it.

From there we can generate the slope model and shade with `gdaldem` as above.

*__Note: Compression:__* You can use GeoTIFF Jpeg compression with `-co COMPRESS=JPEG -co PHOTOMETRIC=YCBCR`, at the expense of transparency. <br/>
After some tests and reading this awesome [Guide to GeoTIFF compression and optimization with GDAL](https://kokoalberti.com/articles/geotiff-compression-optimization-guide/), I went instead with fast ZSTD compression for all the intermediate data-sets, with `-co compress=zstd -co predictor=2 -co zstd_level=1` .

*__Note: Sparse files:__* We can also use `-co SPARSE_OK=TRUE` to reduce file size for our non-rectangular dataset.


Putting it all together
--------------

**Tips to work with big datasets:**

  * To test commands on smaller version of the files, use `gdalwarp -r average -ts 800 0 <in> <out>` to downsample to 800px width. To downsample `WGS84` files, use `gdalwarp -tr 0.003 -0.003 <in> <out>` to set pixel size to *1 px = 0.003°*. For WebMercator it can be `-tr 200 -200` for a *1 px = 200 meters*.

  * To inpect a small chunk, either **(a)** design a geojson file drawing a square, eg *clapier.geojson*, then use `gdalwarp -crop_to_cutline -cutline clapier.geojson <in> <out>`
  ...
  or better **(b)** specify a *target extent* with `-te_srs WGS84 -te 7.38 44 7.44 44.15` . <details><summary>(a) Geojson...</summary>
    ```json
    {"type":"Feature","geometry":{"type":"Polygon","coordinates":[[[7.38,44.15],[7.38,44.1],[7.44,44.1],[7.44,44.15],[7.38,44.15]]]},"properties":{}}
    ``` </details>
  * `gdalinfo -stat` or `gdalinfo -hist` are also handy. For example this shows size, min/max altitudes and missing data in the Aoste DEM: `gdalinfo -stats aoste-dem.vrt`:

    > Size is 44186, 22846
    > <br/> Band 1 Block=128x128 Type=Float32, ColorInterp=Undefined
    > <br/> NoData Value=-9999
    > <br/> Metadata:
    > <br/>    STATISTICS_MAXIMUM=3813.3359375
    > <br/>    STATISTICS_MEAN=1996.4601879555
    > <br/>    STATISTICS_MINIMUM=333.18200683594
    > <br/>    STATISTICS_STDDEV=723.69831082825
    > <br/>    STATISTICS_VALID_PERCENT=72.04

**Common**

Some common variables, to work with tiled geotiff and use ZSTD compression as discussed above:
  ```bash
  download=$HOME/Downloads/dwnmaps/elevationdata
  mkdir -p $download
  workdir=$download
  g_tile='-co num_threads=all_cpus -co tiled=yes -co blockXsize=1024 -co blockYsize=1024'
  g_zstd='-co bigtiff=yes -co compress=zstd -co predictor=2 -co zstd_level=1 -co sparse_ok=true'
  ```

**Download datasets**

The URLs of the files we need to download are here - if they haven't changed in the meantime:

* <a href="geo/src/ign-rge-alti-5m-urls.txt">ign-rge-alti-5m-urls.txt</a>
* <a href="geo/src/piemonte-alpi-dtm5-urls.txt">piemonte-alpi-dtm5-urls.txt</a>
* <a href="geo/src/aosta-dtm0508-urls.txt">aosta-dtm0508-urls.txt</a>

```bash
cd $download
wget -i ign-rge-alti-5m-urls.txt
wget --wait=20 --random-wait --no-http-keep-alive --limit-rate=300k -nc -i piemonte-alpi-dtm5-urls.txt
wget --wait=20 --random-wait --no-http-keep-alive --limit-rate=300k -nc -i aosta-dtm0508-urls.txt

for f in RGE*29.7z; do 7z x $f; done
cd $workdir
```


**French alps** - dept 04 05 06 38 73 74 *(slope 8 minutes → 5GB ; color 5 minutes → 2GB)*:
```bash
gdalbuildvrt -a_srs EPSG:2154 -srcnodata -99999 -vrtnodata -99999 ignalps_dem.vrt \
  $download/RGEALTI_2-0_5M_ASC_LAMB93-IGN69_*/RGEALTI/1_DONNEES_LIVRAISON_*/RGEALTI_MNT_5M_ASC_LAMB93_IGN69_*/RGEALTI_FXX_*
time gdaldem slope $=g_zstd $=g_tile ignalps_dem.vrt ignalps-lamb-slope.tif
time gdaldem color-relief $=g_zstd $=g_tile -alpha ignalps-lamb-slope.tif ~/code/eddy-geek/TIL/geo/data/gdaldem-slope-oslo.clr ignalps-lamb-oslo.tif

```

*I'm using zsh `$=VAR` syntax, use `$VAR` in bash.*

**Piemont** *(slope: 3 min → 1.6GB instead of 7GB uncompressed ; color 2 min → 1 GB)*:

```bash
cd $download ; unzip RIPRESA*TIF.zip ; cd $workdir
gdalbuildvrt piemont_dem.vrt $download/DTM5_*.tif
time gdaldem slope $=g_zstd $=g_tile piemont_dem.vrt piemont-utm32n-slope-tile.tif
time gdaldem color-relief $=g_zstd $=g_tile -alpha piemont-utm32n-slope.tif ../../gdaldem-slope-oslo.clr piemont-utm32n-oslo.tif
```

**Aoste**:

We use gdal's "[virtual file system](https://gdal.org/user/virtual_file_systems.html)" syntax to access inside zip files directly (aoste).

(!) For some reason trying to use `tiled=yes` for slopes does not work.

```bash
ln -s $download aoste_dtm_zips
rm -f aoste_dtm_zips.txt ; touch aoste_dtm_zips.txt ; for f in DTM0508_002_000{001..914} ; do echo "/vsizip/{aoste_dtm_zips/$f.zip}/$f.ASC" >> aoste_dtm_zips.txt ; done

gdalbuildvrt -a_srs EPSG:23032 -srcnodata -9999 -vrtnodata -9999 aoste-dem.vrt -input_file_list aoste_dtm_zips.txt
time gdaldem slope $=g_zstd aoste-dem.vrt aoste-utm32n-slope.tif
time gdaldem color-relief $=g_zstd -alpha aoste-utm32n-slope.tif gdaldem-slope-oslo.clr aoste-utm32n-oslo.tif
```

**Switzerland**:
```bash
mkdir ch_downloads
cd ch_downloads
wget --no-http-keep-alive -nc -i ../ch.swisstopo.swissalti3d-valais-w2550-e2623-s1075-n1130.csv
cat ../ch.swisstopo.swissalti3d-z9valais-w2484-e2623-s1075-n1157.csv | rev | cut -d / -f1 | rev > _vrt_input.txt
gdalbuildvrt -input_file_list _vrt_input.txt z9valais-dem.vrt
cd ..
time gdaldem slope $=g_zstd ch_downloads/z9valais-dem.vrt valais-lv95-slope.tif
```


**Merge**:

Then we merge it all, reproject to WebMercator, and resample all-together.

*__Note: Resolution:__* `gdalwarp` thinks the 2m resolution of the UTM-32N Aoste dataset translates roughly to 2.8 WGS "meters". But our final zlevel=16 file will have a slightly more precise resolution of 2.3 meters (see [OSM Zoom levels](https://wiki.openstreetmap.org/wiki/Zoom_levels) and this article's *Mobile* section). To avoid the loss of precision from resampling twice, we use `-tr` option to force the resolution.

*__Note: Resampling:__* gdal uses *nearest* resampling by default. A insightful comparison can be found in [What is Lanczos resampling useful for in a spatial context?](https://gis.stackexchange.com/a/14361/176462). *nearest* actually seemed best for this slope overlay given that we are upsampling, and that accuracy is paramount. However stuff like hillshading will have artifacts, in that case it's better to shade before reprojection.

<img src="https://i.stack.imgur.com/Lw6ei.png" width="626">


*__Note: Extent:__* To somewhat limit file size, I have cropped the data to the area roughly defined by Aigle-Jouques-Sanremo-Zermatt, aligned on the TMS tiles as shown [here](https://www.maptiler.com/google-maps-coordinates-tile-bounds-projection/).

<img src="img/geo/Aigle-Jouques-SanRemo-Zermatt.jpg" width="100">

*__Note: nodata:__* gdal can identify nodata [from a specific *nodata value*](https://gdal.org/development/rfc/rfc58_removing_dataset_nodata_value.html) **or** [with a mask](https://gdal.org/development/rfc/rfc15_nodatabitmask.html) like the alpha band. <br/>
By default gdalwarp will blend the inputs with the alpha band (we rely on this here!) but "forget" the *nodata value* saying that our `nv 0 0 0 0` pixels are nodata, and write them as black transparent, which causes jpegs with a black frame down the line. <br/>
By setting `-dstnodata 255` we make them **white transparent** instead, and unfortunately set each band *nodata value* -- that we then remove with `gdal_edit`. <br/>
The alpha band (4) still allows to differentiate "flat white" and "no data white". gdal_translate uses it as a mask **even if there is a _nodata value_**, so a later translation to jpg will still end-up black unless `-b 1 -b 2 -b 3` are provided to explicitly ignore that band.

<details><summary>A gdal_calc alternative...</summary>
It's a bit of a trick in that we'd need to discard the metadat nodata value to further process the data. One alternative is to not use `-dstnodata 255` and instead use gdal_calc as follows:

We need a recent version of gdal_calc with the `hideNoData` flag.

```bash
wget https://github.com/OSGeo/gdal/raw/d9e9e827d85c9581a81d93409ea88943497e174f/gdal/swig/python/osgeo/utils/gdal_calc.py

inf=oslo-Aigle-Jouques-Sanremo-Zermatt.tif
/usr/bin/python3 ../gdal_calc.py \
 --co num_threads=all_cpus --co tiled=yes --co blockXsize=1024 --co blockYsize=1024  --co bigtiff=yes \
 --co compress=zstd --co predictor=2 --co zstd_level=1  --hideNoData \
 -R $inf --R_band=1 -G $inf --G_band=2 -B $inf --B_band=3 \
 --calc="where(R+G+B,R,255)" --calc="where(R+G+B,G,255)" --calc="where(R+G+B,B,255)" \
 --overwrite --outfile=${inf/.tif/}-result.tif
 ```
</details>

(A possible improvement is to use a built-in palette keep one band through the merge, and defer the RGB encoding until the mbtiles conversion. If needed palette can be [edited](https://gis.stackexchange.com/questions/272847/how-to-change-raster-palette))

Finally, free 7 GB, grab a coffee (15 minutes)  and here we go:

```bash
time gdalwarp $=g_zstd $=g_tile -dstnodata 255 \
  -t_srs EPSG:3857 -tr 2.388657133911758 -2.388657133911758 \
  -te_srs WGS84 -te 5.6250 43.5804 7.7343 46.316 \
  fr/ignalps-lamb-oslo.tif it/piemont-utm32n-oslo.tif aoste/aoste-utm32n-oslo.tif \
  alps/oslo-Aigle-Jouques-Sanremo-Zermatt.tif

gdal_edit.py -unsetnodata oslo-Aigle-Jouques-Sanremo-Zermatt.tif
```

As an alternative workflow here is what I ended up using, to build a merged, reprojected 20GB slope model that I can directly convert to mbtiles (next section):

```bash
resolution=2.388657133911758
extent='5.6250 43.5804 7.7343 46.558'
time gdalwarp $=g_tile \
  -co bigtiff=yes -co compress=zstd -co zstd_level=3 -co sparse_ok=true \
  -dstnodata 255 \
  -t_srs EPSG:3857 -tr $=resolution -$=resolution \
  -te_srs WGS84 -te $=extent \
  fr/ignalps-lamb-slope.tif it/piemont-utm32n-slope.tif aoste/aoste-utm32n-slope.tif \
  alex/ignalex-lamb-slope.tif ch/valais-lv95-slope.tif \
  alps/slopes-Lausanne-Jouques-Sanremo-Zermatt.tif
```

20 GB is quite big but:
* increasing compression is very slow
* using integer (bytes) instead of floats is possible but the rounding introduces a "quantization" effect after the shading step as seen on the right below:

<img src="img/geo/comparison-slope-as-byte-or-float32.png" width="300">

This is only an issue if you intend to use continuous gradient palettes, or discrete palettes with integer cutoffs.

Mobile use
===============

To convert the above to mbtiles (~30 minutes):

```bash
time gdal_translate -b 1 -b 2 -b 3 -co tile_format=jpeg -co quality=75 \
  alps/oslo-Aigle-Jouques-Sanremo-Zermatt.{tif,mbtiles}
```

*__Note: Zoom level__:* gdal's [MBTiles raster driver](https://gdal.org/drivers/raster/mbtiles.html) says:

> ZOOM_LEVEL_STRATEGY=AUTO/LOWER/UPPER. Strategy to determine zoom level. LOWER will select the zoom level immediately below the theoretical computed non-integral zoom level, leading to subsampling. On the contrary, UPPER will select the immediately above zoom level, leading to oversampling. Defaults to AUTO which selects the closest zoom level.

Good maps like [Sorbetto](https://tartamillo.wordpress.com/sorbetto/) only include slope shade starting at level 15.

For us, when using the automatic resolution of the 5m DEMs (ign or piemont), *AUTO = LOWER is 14*, and *UPPER is 15*. For the 2m aoste DEM, *LOWER is 15* and *AUTO = UPPER is 16*. Finally, with the `-tr` trick, and we shoud avoid the resampling (Bilinear by default).

*__Note: Tile format__:*
> TILE_FORMAT=PNG/PNG8/JPEG: Format used to store tiles. See Tile formats section. Defaults to PNG.

`JPEG` with the default 75% quality will cut size by at least 50%. It is possible to go down to 40%, with some quality loss.

Right now I'm using `PNG` instead to get the best quality, and used an external recompression of every PNG tile with an external tool, pngnq, to reduce PNG size by 50% without visible quality loss (with better results than the built-in `PNG8 `format). This is implemented in <a href="geo/src/mbtidime/mbtcompress.py">mbtcompress.py</a>, and takes *forever* (500 Kb/s on 8 cores so 10 hours total).

It would probably be far quicker to use a single PNG palette for all images rather than recomputing it a million times.

----

Quantized PNG version, directly from the merged slope model:

```bash
sed 's/nv    0   0   0   0/nv  255 255 255 255/g' ../gdaldem-slope-oslo.clr >! /tmp/gdaldem-slope-oslow.clr

time gdaldem color-relief alps/slopes-Lausanne-Jouques-Sanremo-Zermatt.tif /tmp/gdaldem-slope-oslow.clr alps/oslos-Lausanne-Jouques-Sanremo-Zermatt-raw.mbtiles

time mbtcompress.py alps/oslos-Lausanne-Jouques-Sanremo-Zermatt{-raw,}.mbtiles
```
The whole 06/Alpes-Maritimes county in this format will weigh 150 MB in "normal" PNG / zoom level 14 ; or 450 MB at level 15.

<img src="img/geo/06_slopeshade_oslo.jpg" width="400">

The Western alps as defined in the previous section weigh around 4 GB in quantized png / zoom 16.

<img src="img/geo/oslos-Lausanne-Jouques-Sanremo-Zermatt-ovr.png" width="400">


Use with AlpineQuest
---------------

Alpine will up & downsample up to 3 levels. beyond that however, it will display a transparent-blue "warning layer". To avoid it we can add some white tiles at zoom level 12 (enough to cover 10-14 range, then only level 16 will display the slopes):

We take the `-a_ullr` coordinates directly from our Z16 tif above, and compute the size by dividing its width/height (98301, 180454) by 2**5 for 5 levels.

```bash
gdal_create $=g_zstd -outsize 3071 5639 -a_srs EPSG:3857 -a_ullr 626172 5831778 860979 5400735 -bands 3 -burn 255 white11.tif
# JPG z11
gdal_translate -co tile_format=jpeg -co quality=10 white11.tif white11jpg.mbtiles
# PNG z12 & z9
gdal_translate -co tile_format=png8 -co zoom_level_strategy=upper white11.tif white12.mbtiles
time gdal_translate -co tile_format=png8 -tr 305 305 white12.mbtiles white9.mbtiles
```

PNG8 white mbtiles are 10 times smaller than JPG ones, but mbtiles does not support mixing formats, so make sure to use the correct one ;-)

```sql
mbt_append()  # mbt_append $source $dest
{
  echo "ATTACH \"$1\" AS low; INSERT INTO main.tiles SELECT * FROM low.tiles;" | sqlite3 $2
}

mbt_append alps/white12.mbtiles alps/oslos-Lausanne-Jouques-Sanremo-Zermatt.mbtiles
```


Use with OruxMaps
---------------

OruxMaps will not downsample automatically. So you would need to add the other layers with `gdaladdo`.

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
