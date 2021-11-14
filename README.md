# eslope

Enhanced slope overlays for the alps, to use for hiking, ski-touring, alpinism, ...

This is a sister project to openslopemap.org, with more focus on model precision for the western alps, different techincal and aesthetical choices, and detailed documentation. Kudos to the OpenSlopeMap team for the inspiring work!

For now deployment is ongoing.

# How to use the maps online?

* Online
  * Head to [WTracks](https://opoto.github.io/wtracks/) and in the layer control (top-right), tick *EU: E.Slopes* (pending [wtracks#21](https://github.com/opoto/wtracks/pull/21))
  * Configure your tool with the correct URL. The Leaflet URL is curl http://www.montagne.top/tile/eslo14_walps/{z}/{x}/{y}.png

# How to use the maps offline?

* You need an app supporting mbtiles:
  * For Android, options include **[AlpineQuest](https://alpinequest.net/)** *(~10€ on [play store](https://play.google.com/store/apps/details?id=psyberia.alpinequest.full))*  ; **OruxMaps** *(free [online](https://www.oruxmaps.com/cs/en/more/downloads) ; 4€ on [play store](https://play.google.com/store/apps/details?id=com.orux.oruxmapsDonate&hl=en&gl=US))* ; [Locus](https://www.locusmap.app/) ; and more.
  * For iphone, [MBTiles GPS](https://apps.apple.com/us/app/mbtiles-gps/id592703465) (untested)
  * On the PC, I haven't found simple viewers that support layers. [QGIS](https://qgis.org/) is way too complex for this task. [GPXSee](http://gpxsee.org/) is an excellent viewer, but single-layer. Maybe [ape@map](https://lic.apemap.at/cms/index.php?page=productdownload) (German, untested)
* Download the latest mbtiles file, currently [oslos-Lausanne-Jouques-Sanremo-Zermatt.mbtiles](https://drive.google.com/file/d/1c8HcLZ1Cc-I0w53eDh6hN1K31yHVWvb9/view?usp=sharing)
* Configure the app to use it:
  * For AlpineQuest, [import as file-based map](https://alpinequest.net/en/help/v2/maps/file-based-select), use "Add as Layer". [Then set opacity](https://alpinequest.net/en/help/v2/maps/change-opacity#how_to_modify_the_opacity_of_a_map_or_layer) to ~50% and *Layer Blending Mode* (💧icon) to "Multiply".
  * For OruxMap, place it in the correct folder, something like /sdcard/oruxmaps/mapfiles and follow [manual](https://www.oruxmaps.com/cs/en/manual)

# How to web-host the tiles

Check the upcoming dedicated [Hosting.md].
I use go-pmtiles, but many alternatives exist including [MapTiler tileserver](https://github.com/maptiler/tileserver-gl)

# Coverage & Data

The area covered currently is *a part of* the western alps, in GPS terms from lower-left [43.580 N 5.625 E](https://www.openstreetmap.org/?lat=43.580&lon=5.625&zoom=15) to upper-right [46.558 N 7.734E](https://www.openstreetmap.org/?lat=46.558&lon=7.734&zoom=15), or as a mnemonic, Lausanne-Jouques-Sanremo-Zermatt. Some (lower elevation) areas are not covered.

Outside of this area, you can use SRTM data.

Zoom-levels:
* Only [zoom-level]() 16 is provided so far (other levels are filled white to avoid artifacts). It means an actual pixel resolution of around 3m at 45°

Data sources:
* France: [RGE ALTI 5m](https://geoservices.ign.fr/documentation/diffusion/telechargement-donnees-libres.html#rge-alti-5m). Mostly based on Radar, with a "real" resolution closer to 30m. ⚠️ Only *departement*s n° 04 05 06 38 73 74
* Italy>Piemonte: *RIPRESA AEREA ICE 2009-2011 - DTM 5*, hosted [here](http://www.geoportale.piemonte.it/geonetworkrp/srv/ita/metadata.show?id=2552&currTab=rndt)
* Italy>Aosta: [DTM 2005 / 2008 aggregato](https://geoportale.regione.vda.it/download/dtm/)
* Switzerland: [SwissAlti3D](https://www.swisstopo.admin.ch/en/geodata/height/alti3d.html)

Future work:
* Missing french areas: 39,01,84,13 (Jura,Ain,Vaucluse,Bouches-du-Rhone)
* Easten alps. See [openslopemap data-sources](https://www-openslopemap-org.translate.goog/projekt/hintergrundinformationen/?_x_tr_sl=de&_x_tr_tl=en&_x_tr_hl=en-GB&_x_tr_pto=nui)

For details on the process: [IGN-data-gdaldem](https://github.com/eddy-geek/TIL/blob/master/202101-IGN-data-gdaldem.md)

# Links
* A tutorial for Austrian elevation data: [terrain-rgb](https://github.com/syncpoint/terrain-rgb)
* Hosting [tiling-notes](https://gist.github.com/smnorris/4866ac1c17a37cab907d11d20de491dc)

# License

The code in this repository is under [CC 1.0](LICENSE). The elevation data behind may have additional restrictions.
