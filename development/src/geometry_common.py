import json
import mercantile as T

LLBb = T.LngLatBbox



def tms2southwest(z, x, y) -> T.LngLat:
    """Return south_west corner of given TMS tile"""
    # Mercantile uses TXYZ but MBTiles use TMS -> flip
    y = (1 << z) - y - 1
    bb = T.xy_bounds(x, y, z)
    return T.lnglat(bb.left, bb.bottom)

z9longitudes = [round(tms2southwest(9, x=x, y=1).lng, 5) for x in range(263, 279)]
z9latitudes = [round(tms2southwest(9, x=1, y=y).lat, 5) for y in reversed(range(320, 335))]

z10longitudes = [round(tms2southwest(10, x=x, y=1).lng, 5) for x in range(526, 557)]

( # the 2nd number indicates the lowest TMS zoom to be a tile boundary
lng49z9_valence , # 4.92
lng52z10_aix, # 5.2734 # ign2/3.W
lng56z6_grenoble_auriol , # 5.62 # eslope walps.W
lng59z10_chambery_toulon, #5.97656 # ign5.W
lng63z9_digne_thones_pontarlier , # 6.33  # ign 1<>2
lng66z10,
lng70z8_aigle_cannes, # 7.03
lng73z10_monaco_aosta_bern, # 7.38 alps3.E
lng77z9_sanremo_zermatt, # 7.73  # eslope walps.E
lng80z10_imperia_biella,  # 8.08 alps1.E
lng84z7_zurich_savona, # 8.44
lng87z10,
lng91z9_milano_como , # 9.14
lng94z10,
lng98z8_sondrio_smoritz, # 9.84  # bernina slightly east
lng101z10,
lng105z9_pfunds, # 10.55
lng108z10,
lng112z5_bolzano_innsbruck, # 11.25
lng116z10,
lng119z9_bruneck, # 11.95  # eslope calps.E ; Kompass.z15.E
lng123z10,
lng126z8_lienz, # 12.66
lng130z10,
lng133z9_udine_pocking, # 13.36
lng137z10,
lng140z7_klagenfurt_murau, # 14.06
lng144z10,
lng147z9_277, # 14.77
lng151z10,
lng154z8_graz, # 15.47
) = z10longitudes


# W->E
# lng52z10_aix = (lng49z9_valence + lng56z6_grenoble_auriol)/2 # 5.27 # ign2/3.W
# lng10zchambery_toulon = (lng56z6_grenoble_auriol + lng63z9_digne_thones_pontarlier)/2  #5.97656 # ign5.W
# lng73z10_monaco_aosta_bern = (lng70z8_aigle_cannes + lng77z9_sanremo_zermatt)/2 # 7.38
lng71z11_nice = (lng70z8_aigle_cannes+lng73z10_monaco_aosta_bern)/2  # 7.207
lng79z11_ivrea_visp = (3*lng77z9_sanremo_zermatt+ lng84z7_zurich_savona)/4 # 7.9102 frit4.E
# lng80z10_imperia_biella = (lng77z9_sanremo_zermatt + lng84z7_zurich_savona)/2  # 8.08 frit1.E
lng81z12_albenga = 8.1738  # bugianen_liguria.E
lng124z11_mittersill = (lng119z9_bruneck+ 3*lng126z8_lienz)/4  # 12.48 kompasseast.E

# N->S
(
lat80z8_freiburg,
lat75z9_basel_budapest, # 47.52  # eslope calps.N
lat70z7_morteau_luzern_graz, # 47.04
lat65z9_lausanne_smoritz_bolzano, # 46.56  # eslope walps.N ; ign5
lat60z8_cluses_trento, # 46.07
lat55z9_chambery_biella_trieste, # 45.58  # eslope calps.S ; ign 4<>5
lat50z6_grenoble_torino, # 45.09  # ign 3<>4
lat45z9_gap, # 44.59  # ign 1<>3
lat40z8_digne_tende, # 44.09
lat35z9_antibes, # 43.5804  # ign 1&2
lat30z7_toulon, # 43.0689
lat25_perpignan_calvi, # 42.55
lat20_girone, # 42.03
lat15_barcelone_chera,  # 41.50
lat09_salamanque_olbia_latina,  # 40.98
) = z9latitudes


def bb2json(bb: T.LngLatBbox):
    return [
        [bb.west, bb.north],
        [bb.west, bb.south],
        [bb.east, bb.south],
        [bb.east, bb.north],
        [bb.west, bb.north]
    ]

def etopo2geojson(path, bb_dict, name_dict):
    """Duplicated in *etopo/src/geometry.py*"""

    content = \
    {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry":
            {
                "type":"Polygon",
                "coordinates": [bb2json(bb)]
            },
            "properties":
            {
                "name": name_dict.get(i, ''),
                "stroke": "#ff00ff", "stroke-width": 5, "fill-opacity": 0.1
            }
        }
        for i, bb in bb_dict.items()
    ]
    }
    with open(path, 'w') as f:
        f.write(json.dumps(content, indent=2))
