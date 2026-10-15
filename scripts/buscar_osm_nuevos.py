"""Busca en OpenStreetMap establecimientos turísticos de Puebla que NO están en el DENUE.

Uso:
    python scripts/buscar_osm_nuevos.py                 # usa la descarga en caché si existe
    python scripts/buscar_osm_nuevos.py --descargar     # vuelve a consultar Overpass

Salidas (en data/processed/):
- osm_nuevos.csv         establecimientos nuevos, listos para scripts/cargar_osm.py
- osm_dudosos.csv        parecidos a un registro del DENUE cercano; revisar a mano, no se cargan
- osm_ya_en_denue.csv    descartados por estar en el DENUE (con el id_denue que hizo match)

Criterios:
- Solo POIs con nombre (sin nombre no se puede verificar que no estén en el DENUE).
- Cada etiqueta OSM se asigna a un SCIAN de la tipología que ya usa la BD (los mismos códigos
  que vienen en el DENUE, ver CLASIFICACION). Lo que no encaja (parques, jardines, oficinas de
  información) se descarta.
- Se compara contra el DENUE COMPLETO de Puebla (todos los sectores, no solo los turísticos):
  un restaurante que el DENUE clasificó en otro SCIAN ya existe y no debe duplicarse.
  Match = nombre casi igual (>= 0.85) a menos de 1 km (las coordenadas de OSM y del DENUE
  pueden diferir varios cientos de metros), parecido (>= 0.75) a menos de 300 m, o algo
  parecido (>= 0.6) a menos de 40 m. Lo que no hace match pero se parece (>= 0.5) a algo a
  menos de 150 m queda como dudoso.
- Nombres genéricos ("Taquería", "Motel", "Nieves"): no se pueden verificar por nombre; si hay
  un establecimiento del mismo subsector a menos de 75 m se da por existente, si no, dudoso.
- Datos sin equivalente en OSM (personal ocupado, calificación) quedan vacíos (NULL).
"""
import argparse
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import geopandas as gpd
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / "data" / "raw" / "osm"
SALIDA = RAIZ / "data" / "processed"
DENUE_CSV = RAIZ / "data" / "raw" / "denue" / "conjunto_de_datos" / "denue_inegi_21_.csv"
MUN_SHP = RAIZ / "data" / "raw" / "mg" / "21_puebla" / "conjunto_de_datos" / "21mun.shp"
CRS_METROS = 6372  # Lambert Conformal Conic de México (INEGI)

SERVIDORES = ["https://overpass.private.coffee/api/interpreter",
              "https://overpass-api.de/api/interpreter",
              "https://overpass.kumi.systems/api/interpreter"]

AREA = 'area["ISO3166-2"="MX-PUE"][admin_level=4]->.pue;'
CONSULTAS = {
    "servicios": AREA + """(
  nwr["tourism"~"^(hotel|motel|hostel|guest_house|apartment|chalet|camp_site|caravan_site|alpine_hut|wilderness_hut|museum|gallery|theme_park|zoo|aquarium)$"]["name"](area.pue);
  nwr["amenity"~"^(restaurant|cafe|fast_food|bar|pub|ice_cream|food_court|biergarten|nightclub|theatre|arts_centre)$"]["name"](area.pue);
  nwr["leisure"~"^(water_park|golf_course|bowling_alley)$"]["name"](area.pue);
  nwr["shop"~"^(travel_agency|craft|art)$"]["name"](area.pue);
  nwr["office"="travel_agent"]["name"](area.pue);
  nwr["craft"~"^(pottery|handicraft|weaver|basket_maker|glassblower|woodcarver)$"]["name"](area.pue);
);""",
    # Balnearios, ecoparques y similares: en OSM casi nunca tienen una etiqueta propia, se
    # filtran después por nombre (filtrar por nombre en Overpass agota el tiempo).
    "recreativos": AREA + """(
  nwr["leisure"~"^(resort|water_park|swimming_area|swimming_pool|park|sports_centre|nature_reserve)$"]["name"](area.pue);
  nwr["tourism"~"^(attraction|camp_site|picnic_site)$"]["name"](area.pue);
  nwr["garden:type"="botanical"]["name"](area.pue);
);""",
}

RX_BALNEARIO = re.compile(r"balneario|parque acu[aá]tico|aguas termales|albercas", re.I)
RX_ECOPARQUE = re.compile(r"eco ?parque|ecotur|tirolesa|parque recreativo|centro recreativo|aventura", re.I)
RX_CABANAS = re.compile(r"caba[nñ]as?\b", re.I)
RX_BOTANICO = re.compile(r"jard[ií]n bot[aá]nico", re.I)


def _cocina(t: dict) -> str:
    return t.get("cuisine", "").lower()


def clasificar(t: dict) -> str | None:
    """Devuelve el SCIAN (6 dígitos, mismos códigos del DENUE) o None si no es de la tipología."""
    tur, ame, lei, nombre = t.get("tourism"), t.get("amenity"), t.get("leisure"), t.get("name", "")
    cocina = _cocina(t)
    if tur == "hotel":
        # 721111 = hotel con otros servicios integrados (restaurante, alberca, etc.)
        con_servicios = (_entero(t.get("stars")) or 0) >= 4 or any(t.get(k) == "yes" for k in ("restaurant", "swimming_pool", "bar"))
        return "721111" if con_servicios else "721112"
    if tur == "motel":
        return "721113"
    if tur == "chalet" or (tur == "camp_site" and RX_CABANAS.search(nombre)):
        return "721190"
    if tur in ("hostel", "guest_house"):
        return "721311"
    if tur == "apartment":
        return "721312"
    if RX_BOTANICO.search(nombre) or t.get("garden:type") == "botanical" or tur in ("zoo", "aquarium"):
        return "712131"
    if tur in ("camp_site", "caravan_site", "alpine_hut", "wilderness_hut"):
        return "713998" if RX_ECOPARQUE.search(nombre) else "721210"
    if tur == "museum":
        return "712112"  # supuesto: en Puebla la mayoría de los museos son públicos
    if tur == "gallery":
        return "712111"
    if tur == "theme_park":
        return "713111"
    if lei == "water_park" or RX_BALNEARIO.search(nombre):
        return "713113"
    if lei == "golf_course":
        return "713910"
    if lei == "bowling_alley":
        return "713950"
    if RX_ECOPARQUE.search(nombre) and (lei or tur):
        return "713998"
    if ame == "restaurant":
        if re.search(r"seafood|fish|mariscos", cocina) or re.search(r"marisc", nombre, re.I):
            return "722512"
        if re.search(r"pizza|burger|chicken|hot_dog", cocina):
            return "722517"
        if re.search(r"taco|torta", cocina):
            return "722514"
        if re.search(r"antojit|quesadilla|tamal|pozole|cemita|chalupa", cocina):
            return "722513"
        return "722511"
    if ame == "fast_food":
        if re.search(r"taco|torta|cemita", cocina):
            return "722514"
        if re.search(r"pizza|burger|chicken|hot_dog", cocina):
            return "722517"
        return "722518"
    if ame in ("cafe", "ice_cream"):
        return "722515"
    if ame == "food_court":
        return "722519"
    if ame in ("bar", "pub", "biergarten"):
        return "722412"
    if ame == "nightclub":
        return "722411"
    if ame == "theatre":
        return "711311"
    if ame == "arts_centre":
        return "711312"  # casas de cultura, mayoritariamente públicas
    if t.get("shop") == "travel_agency" or t.get("office") == "travel_agent":
        return "561510"
    if t.get("shop") in ("craft", "art") or t.get("craft"):
        return "465915"
    return None


def descargar(nombre: str, consulta: str) -> dict:
    q = f"[out:json][timeout:300];\n{consulta}\nout center meta;"
    for url in SERVIDORES:
        try:
            req = urllib.request.Request(
                url, data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": "MOPEDETU-hackathon/1.0 (uso educativo)"})
            with urllib.request.urlopen(req, timeout=600) as r:
                texto = r.read().decode("utf-8")
            if texto.lstrip().startswith("{"):
                datos = json.loads(texto)
                if not datos.get("remark"):
                    print(f"  {nombre}: {len(datos['elements'])} elementos de {url}")
                    return datos
                print(f"  {url}: {datos['remark'][:100]}")
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  {url}: {e}")
        time.sleep(5)
    raise SystemExit(f"No se pudo descargar '{nombre}' de ningún servidor Overpass")


def leer_osm(forzar: bool) -> tuple[pd.DataFrame, str]:
    CACHE.mkdir(parents=True, exist_ok=True)
    filas, corte = [], None
    for nombre, consulta in CONSULTAS.items():
        ruta = CACHE / f"osm_{nombre}.json"
        if forzar or not ruta.exists():
            ruta.write_text(json.dumps(descargar(nombre, consulta), ensure_ascii=False), encoding="utf-8")
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        corte = corte or datos["osm3s"]["timestamp_osm_base"][:10]
        for e in datos["elements"]:
            t = e.get("tags", {})
            lat = e.get("lat", e.get("center", {}).get("lat"))
            lon = e.get("lon", e.get("center", {}).get("lon"))
            if not t.get("name") or lat is None:
                continue
            filas.append({"osm_tipo": e["type"], "osm_id": e["id"], "tags": t, "lat": lat, "lon": lon,
                          "ultima_edicion_osm": (e.get("timestamp") or "")[:10] or None})
    df = pd.DataFrame(filas).drop_duplicates(["osm_tipo", "osm_id"])
    return df, corte


def _primero(t: dict, *claves) -> str | None:
    for k in claves:
        if t.get(k):
            return t[k].strip()
    return None


def _entero(v: str | None) -> int | None:
    m = re.match(r"\s*(\d+)", v or "")
    return int(m.group(1)) if m else None


def atributos(t: dict) -> dict:
    calle = " ".join(x for x in (t.get("addr:street"), t.get("addr:housenumber")) if x)
    direccion = ", ".join(x for x in (calle, t.get("addr:suburb") or t.get("addr:neighbourhood"),
                                      t.get("addr:city"), t.get("addr:postcode")) if x)
    redes = "; ".join(t[k] for k in ("contact:facebook", "facebook", "contact:instagram",
                                     "instagram", "contact:tiktok") if t.get(k))
    accesible = {"yes": True, "no": False, "limited": True}.get(t.get("wheelchair", ""))
    return {
        "nombre": t["name"].strip()[:120],
        "marca": _primero(t, "brand", "operator"),
        "etiqueta_osm": next((f"{k}={t[k]}" for k in ("tourism", "amenity", "leisure", "shop",
                                                        "office", "craft") if k in t), None),
        "direccion": direccion or None,
        "codigo_postal": t.get("addr:postcode"),
        "telefono": _primero(t, "phone", "contact:phone", "contact:mobile", "mobile"),
        "correo": _primero(t, "email", "contact:email"),
        "sitio_web": _primero(t, "website", "contact:website", "url"),
        "redes_sociales": redes or None,
        "horario": t.get("opening_hours"),
        "cocina": t.get("cuisine"),
        "estrellas": _entero(t.get("stars")),
        "habitaciones": _entero(t.get("rooms") or t.get("beds")),
        "capacidad": _entero(t.get("capacity")),
        "accesible_silla_ruedas": accesible,
        "internet": {"wlan": "wifi", "yes": "sí", "no": "no"}.get(t.get("internet_access", ""),
                                                                 t.get("internet_access")),
        "acepta_tarjeta": True if t.get("payment:credit_cards") == "yes" or t.get("payment:cards") == "yes"
        else (False if t.get("payment:cards") == "no" else None),
        "cuota_entrada": {"yes": True, "no": False}.get(t.get("fee", "")),
        "descripcion": _primero(t, "description", "description:es"),
        "wikidata": t.get("wikidata"),
        "personal_ocupado": None,  # OSM no lo registra
    }


STOP = {"hotel", "motel", "hostal", "hostel", "posada", "restaurante", "restaurant", "rest", "cafe",
        "cafeteria", "coffee", "bar", "cantina", "la", "el", "los", "las", "de", "del", "y", "en",
        "the", "and", "s", "a", "sa", "cv", "de cv", "fonda", "taqueria", "tacos", "pizzeria",
        "museo", "balneario", "suites", "inn", "boutique"}


def normalizar(s: str | float) -> str:
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


# Palabras que no distinguen un negocio de otro: no bastan para decir que dos nombres coinciden.
GENERICAS = {"puebla", "poblano", "poblana", "cholula", "atlixco", "mexico", "mexicana", "mexicano",
             "centro", "express", "plaza", "real", "san", "santa", "sin", "nombre", "comida", "cocina",
             "antojitos", "gorditas", "nieves", "helados", "paleteria", "mariscos", "pizzas", "tortas",
             "economica", "grill", "city", "parque", "cabanas", "campamento", "galeria", "artesanias",
             "agencia", "viajes", "teatro", "casa", "cultura", "jardin", "carnitas", "barbacoa",
             "pollos", "burgers", "hamburguesas", "sushi", "tienda", "snack", "botanero"}
ALIAS = {"kfc": "kentucky fried chicken", "mcdonald s": "mcdonalds", "mc donalds": "mcdonalds",
         "mc donald s": "mcdonalds", "samborns": "sanborns", "7 eleven": "seven eleven"}


def nucleo(s: str) -> str:
    n = normalizar(s)
    for a, b in ALIAS.items():
        n = re.sub(rf"{a}", b, n)
    tokens = [w for w in n.split() if w not in STOP]
    return " ".join(tokens) or n


def es_generico(n: str) -> bool:
    return not n or all(w in GENERICAS or w in STOP for w in n.split())


def similitud(a: str, b: str) -> float:
    """Parecido entre núcleos de nombre: ratio de difflib, o 0.9 si uno contiene al otro."""
    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    corto = ta if len(ta) <= len(tb) else tb
    contenido = (ta <= tb or tb <= ta) and len(" ".join(corto)) >= 4         and any(w not in GENERICAS for w in corto)
    return max(SequenceMatcher(None, a, b).ratio(), 0.9 if contenido else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--descargar", action="store_true", help="Ignora la caché y consulta Overpass")
    args = ap.parse_args()

    osm, corte = leer_osm(args.descargar)
    osm["codigo_act"] = osm["tags"].map(clasificar)
    print(f"OSM con nombre: {len(osm):,}; de la tipología: {osm['codigo_act'].notna().sum():,}")
    osm = osm[osm["codigo_act"].notna()].copy()
    osm = pd.concat([osm.drop(columns="tags"), pd.DataFrame(osm["tags"].map(atributos).tolist(),
                                                            index=osm.index)], axis=1)

    g = gpd.GeoDataFrame(osm, geometry=gpd.points_from_xy(osm["lon"], osm["lat"]), crs=4326)
    mun = gpd.read_file(MUN_SHP).to_crs(4326)
    mun["cve_geo"] = mun["CVE_ENT"] + mun["CVE_MUN"]
    g = gpd.sjoin(g, mun[["cve_geo", "NOMGEO", "geometry"]], predicate="within", how="inner")
    g = g.rename(columns={"NOMGEO": "municipio"}).drop(columns="index_right").to_crs(CRS_METROS)

    # 1) Duplicados dentro de OSM (mismo lugar como nodo y como polígono, etc.): mismo núcleo de
    #    nombre a menos de 150 m -> se queda el que tiene más atributos llenos.
    g["nucleo"] = g["nombre"].map(nucleo)
    g["n_atributos"] = g.drop(columns="geometry").notna().sum(axis=1)
    g = g.sort_values("n_atributos", ascending=False)
    pares = gpd.sjoin(g[["nucleo", "geometry"]], g[["nucleo", "geometry"]],
                      predicate="dwithin", distance=150)
    pares = pares[(pares.index != pares["index_right"]) & (pares["nucleo_left"] == pares["nucleo_right"])]
    orden = {ix: i for i, ix in enumerate(g.index)}
    quitar = {ix for ix, r in pares.iterrows() if orden[ix] > orden[r["index_right"]]}
    g = g.drop(index=list(quitar))
    print(f"Duplicados internos de OSM eliminados: {len(quitar)}")

    # 2) Cruce contra el DENUE completo
    denue = pd.read_csv(DENUE_CSV, encoding="latin-1", dtype=str,
                        usecols=["id", "nom_estab", "raz_social", "codigo_act", "latitud", "longitud"])
    denue["latitud"] = pd.to_numeric(denue["latitud"], errors="coerce")
    denue["longitud"] = pd.to_numeric(denue["longitud"], errors="coerce")
    denue = denue.dropna(subset=["latitud", "longitud"])
    d = gpd.GeoDataFrame(denue, geometry=gpd.points_from_xy(denue["longitud"], denue["latitud"]),
                         crs=4326).to_crs(CRS_METROS)
    d["n_nom"] = d["nom_estab"].map(nucleo)
    d["n_raz"] = d["raz_social"].map(nucleo)

    g["generico"] = g["nucleo"].map(es_generico)
    cerca = gpd.sjoin(g[["nucleo", "codigo_act", "generico", "geometry"]],
                      d[["id", "n_nom", "n_raz", "codigo_act", "geometry"]],
                      predicate="dwithin", distance=1000, how="inner")
    gx = g.geometry
    cerca["dist_m"] = [gx.loc[i].distance(d.geometry.iloc[j]) for i, j in
                       zip(cerca.index, d.index.get_indexer(cerca["index_right"]))]
    cerca["sim"] = [max(similitud(a, b), similitud(a, c)) for a, b, c in
                    zip(cerca["nucleo"], cerca["n_nom"], cerca["n_raz"])]
    mismo_subsector = cerca["codigo_act_left"].str[:3] == cerca["codigo_act_right"].str[:3]
    cerca["match"] = (((cerca["sim"] >= 0.85))
                      | ((cerca["sim"] >= 0.75) & (cerca["dist_m"] <= 300))
                      | ((cerca["sim"] >= 0.6) & (cerca["dist_m"] <= 40))
                      | (cerca["generico"] & mismo_subsector & (cerca["dist_m"] <= 75)))
    cerca["dudoso"] = (cerca["sim"] >= 0.5) & (cerca["dist_m"] <= 150)
    cerca["prioridad"] = cerca["match"] * 2 + cerca["dudoso"] + cerca["sim"] / 10
    mejor = cerca.sort_values("prioridad", ascending=False).groupby(level=0).first()

    g = g.join(mejor[["id", "sim", "dist_m", "match", "dudoso"]].rename(
        columns={"id": "id_denue_parecido", "sim": "similitud_nombre", "dist_m": "distancia_m"}))
    g["match"] = g["match"].astype("boolean").fillna(False)
    g["dudoso"] = (g["dudoso"].astype("boolean").fillna(False) | g["generico"]) & ~g["match"]

    g["id_externo"] = "OSM:" + g["osm_tipo"].str[0] + g["osm_id"].astype(str)
    g["url_osm"] = "https://www.openstreetmap.org/" + g["osm_tipo"] + "/" + g["osm_id"].astype(str)
    g["fuente"] = "OpenStreetMap"
    g["corte"] = corte
    g["fecha_consulta"] = date.today().isoformat()
    columnas = ["id_externo", "fuente", "nombre", "codigo_act", "etiqueta_osm", "cve_geo", "municipio",
                "lat", "lon", "direccion", "codigo_postal", "telefono", "correo", "sitio_web",
                "redes_sociales", "horario", "cocina", "estrellas", "habitaciones", "capacidad",
                "accesible_silla_ruedas", "internet", "acepta_tarjeta", "cuota_entrada", "marca",
                "descripcion", "wikidata", "personal_ocupado", "ultima_edicion_osm", "url_osm",
                "corte", "fecha_consulta"]
    revision = ["id_denue_parecido", "similitud_nombre", "distancia_m"]
    g = g.sort_values(["cve_geo", "codigo_act", "nombre"])
    for c in ("estrellas", "habitaciones", "capacidad"):
        g[c] = g[c].astype("Int64")
    g["distancia_m"] = g["distancia_m"].round(0)
    g["similitud_nombre"] = g["similitud_nombre"].round(2)

    SALIDA.mkdir(parents=True, exist_ok=True)
    nuevos = g[~g["match"] & ~g["dudoso"]]
    nuevos[columnas].to_csv(SALIDA / "osm_nuevos.csv", index=False, encoding="utf-8")
    g[g["dudoso"]][columnas + revision].to_csv(SALIDA / "osm_dudosos.csv", index=False, encoding="utf-8")
    g[g["match"]][columnas + revision].to_csv(SALIDA / "osm_ya_en_denue.csv", index=False, encoding="utf-8")

    print(f"Ya en el DENUE: {int(g['match'].sum()):,} · dudosos: {int(g['dudoso'].sum()):,} · "
          f"NUEVOS: {len(nuevos):,} (corte OSM {corte})")
    print(nuevos.groupby(nuevos["codigo_act"]).size().to_string())


if __name__ == "__main__":
    main()
