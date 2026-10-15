"""Carga el catálogo de rutas existentes, Pueblos Mágicos, anclas y regiones (Rol C · Styveen).

Escribe solo las tablas del rol C:
  dw.dim_fuente (filas 7 y 8 + guías y regionalización), dw.dim_ruta (origen = 'existente'),
  dw.fact_ruta_parada y las columnas es_pueblo_magico, es_ancla y region de dw.dim_municipio.

Las llaves *_sk son identity (GENERATED ALWAYS), así que todo se sincroniza por clave natural:
fuentes por nombre, rutas por (nombre, origen) y municipios por cve_geo.
Si dw.dim_municipio aún está vacía, carga fuentes y rutas, y deja las paradas y los UPDATE pendientes:
basta con volver a ejecutar el script cuando el ETL termine. Es idempotente.

Uso:
    python scripts/cargar_rutas_existentes.py            # genera CSV/SQL y carga en Supabase
    python scripts/cargar_rutas_existentes.py --sin-bd   # solo genera CSV y SQL
"""
import csv
import json
import math
import sys
import unicodedata
from collections import OrderedDict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "dashboard"))

CATALOGO = RAIZ / "data" / "catalogos" / "rutas_existentes.csv"
MUNICIPIOS_CSV = RAIZ / "data" / "catalogos" / "municipios_turismo.csv"
GEO = RAIZ / "data" / "geo" / "puebla_municipios.geojson"
SQL = RAIZ / "sql" / "04_catalogo_rutas_styveen.sql"
FECHA_CONSULTA = "2026-10-14"

# Pueblos Mágicos de Puebla y año de nombramiento (SECTUR). Cholula cuenta como uno solo, con dos municipios.
PUEBLOS_MAGICOS = {
    "Cuetzalan del Progreso": 2002, "Zacatlán": 2011, "Chignahuapan": 2012, "Pahuatlán": 2012,
    "Tlatlauquitepec": 2012, "Xicotepec": 2012, "San Pedro Cholula": 2012, "San Andrés Cholula": 2012,
    "Atlixco": 2015, "Huauchinango": 2015, "Tetela de Ocampo": 2020, "Huejotzingo": 2023, "Teziutlán": 2023,
}

# Criterio de ancla: destino consolidado reconocido en un catálogo oficial (ver docs/catalogo_rutas_y_anclas.md).
ANIOS_CONSOLIDACION = 10
ANCLAS_EXTRA = {
    "Puebla": "Capital; Centro Histórico Patrimonio de la Humanidad (UNESCO, 1987)",
    "Tehuacán": "Segunda ciudad del estado; acceso a la Reserva de la Biosfera Tehuacán-Cuicatlán (UNESCO, 2018)",
}

# Regionalización socioeconómica oficial en 7 regiones (Congreso del Estado de Puebla, 2015).
REGIONES = {
    "Sierra Norte": "Ahuacatlán, Ahuazotepec, Amixtlán, Aquixtla, Camocuautla, Coatepec, Cuautempan, Chiconcuautla, "
                    "Chignahuapan, Honey, Francisco Z. Mena, Hermenegildo Galeana, Huauchinango, Ixtacamaxtitlán, Jalpan, "
                    "Jopala, Juan Galindo, Naupan, Olintla, Pahuatlán, Pantepec, San Felipe Tepatlán, Tepango de Rodríguez, "
                    "Tepetzintla, Tetela de Ocampo, Tlacuilotepec, Tlaola, Tlapacoya, Tlaxco, Venustiano Carranza, Xicotepec, "
                    "Xochiapulco, Zacatlán, Zihuateutla, Zongozotla",
    "Sierra Nororiental": "Acateno, Atempan, Ayotoxco de Guerrero, Caxhuacan, Cuetzalan del Progreso, Chignautla, Huehuetla, "
                          "Hueyapan, Hueytamalco, Hueytlalpan, Huitzilan de Serdán, Atlequizayan, Ixtepec, Jonotla, Nauzontla, "
                          "Tenampulco, Teteles de Ávila Castillo, Teziutlán, Tlatlauquitepec, Tuzamapan de Galeana, Xiutetelco, "
                          "Xochitlán de Vicente Suárez, Yaonáhuac, Zacapoaxtla, Zapotitlán de Méndez, Zaragoza, Zautla, Zoquiapan",
    "Valle de Serdán": "Acatzingo, Aljojuca, Atzitzintla, Cuapiaxtla de Madero, Cuyoaco, Chalchicomula de Sesma, Chichiquila, "
                       "Chilchotla, Esperanza, General Felipe Ángeles, Guadalupe Victoria, Lafragua, Libres, "
                       "Mazapiltepec de Juárez, Cañada Morelos, Ocotepec, Oriental, Palmar de Bravo, Quecholac, Quimixtlán, "
                       "Rafael Lara Grajales, Los Reyes de Juárez, San José Chiapa, San Juan Atenco, San Nicolás Buenos Aires, "
                       "San Salvador el Seco, San Salvador Huixcolotla, Soltepec, Tecamachalco, Tepeyahualco, Tlachichuca",
    "Angelópolis": "Acajete, Amozoc, Atoyatempan, Calpan, Coronango, Cuautinchán, Cuautlancingo, Chiautzingo, Domingo Arenas, "
                   "Huejotzingo, Juan C. Bonilla, Mixtla, Nealtican, Nopalucan, Ocoyucan, Puebla, San Andrés Cholula, "
                   "San Felipe Teotlalcingo, San Martín Texmelucan, San Matías Tlalancaleca, San Miguel Xoxtla, "
                   "San Nicolás de los Ranchos, San Pedro Cholula, San Salvador el Verde, Santo Tomás Hueyotlipan, "
                   "Tecali de Herrera, Tepatlaxco de Hidalgo, Tepeaca, Tepeyahualco de Cuauhtémoc, Tlahuapan, Tlaltenango, "
                   "Tlanepantla, Tochtepec",
    "Valle de Atlixco y Matamoros": "Acteopan, Ahuatlán, Atlixco, Atzala, Atzitzihuacán, Cohuecan, Chietla, Epatlán, Huaquechula, "
                                    "Izúcar de Matamoros, San Diego la Mesa Tochimiltzingo, San Gregorio Atzompa, "
                                    "San Jerónimo Tecuanipan, San Martín Totoltepec, Santa Isabel Cholula, Teopantlán, "
                                    "Tepemaxalco, Tepeojuma, Tepexco, Tianguismanalco, Tilapa, Tlapanalá, Tochimilco, Xochiltepec",
    "Mixteca": "Acatlán, Ahuehuetitla, Albino Zertuche, Atexcal, Axutla, Coatzingo, Cohetzala, Coyotepec, Cuayuca de Andrade, "
               "Chiautla, Chigmecatitlán, Chila, Chila de la Sal, Chinantla, Guadalupe, Huatlatlauca, Huehuetlán el Chico, "
               "Huitziltepec, Ixcamilpa de Guerrero, Ixcaquixtla, Jolalpan, Juan N. Méndez, La Magdalena Tlatlauquitepec, "
               "Molcaxac, Petlalcingo, Piaxtla, San Jerónimo Xayacatlán, San Juan Atzompa, San Miguel Ixitlán, "
               "San Pablo Anicano, San Pedro Yeloixtlahuaca, Santa Catarina Tlaltempan, Santa Inés Ahuatempan, "
               "Huehuetlán el Grande, Tecomatlán, Tehuitzingo, Teotlalco, Tepexi de Rodríguez, Totoltepec de Guerrero, "
               "Tulcingo, Tzicatlacoyan, Xayacatlán de Bravo, Xicotlán, Xochitlán Todos Santos, Zacapala",
    "Tehuacán y Sierra Negra": "Ajalpan, Altepexi, Caltepec, Coxcatlán, Coyomeapan, Chapulco, Eloxochitlán, Nicolás Bravo, "
                               "San Antonio Cañada, San Gabriel Chilac, San José Miahuatlán, San Sebastián Tlacotepec, "
                               "Santiago Miahuatlán, Tehuacán, Tepanco de López, Tlacotepec de Benito Juárez, Vicente Guerrero, "
                               "Yehualtepec, Zapotitlán, Zinacatepec, Zoquitlán",
}

# "clave" enlaza con la columna fuente del CSV; fuente_sk solo se fija en las filas que ya existían (7 y 8).
FUENTES = [
    dict(clave="pueblos_magicos", fuente_sk=7, nombre="Catálogo de destinos y Pueblos Mágicos",
         institucion="Secretaría de Turismo federal (SECTUR), programa Pueblos Mágicos",
         tipo="Catálogo manual",
         url="https://www.nmas.com.mx/puebla/nuevos-pueblos-magicos-en-puebla-huejotzingo-y-teziutlan/",
         version_corte="12 Pueblos Mágicos de Puebla, nombramientos 2002-2023",
         fecha_descarga=FECHA_CONSULTA, licencia_terminos="Información pública",
         cobertura="13 municipios (Cholula = San Pedro Cholula + San Andrés Cholula)",
         calidad_notas="Lista y años cruzados entre notas de prensa sobre los nombramientos de SECTUR (N+ 2023, "
                       "Milenio 2025) y gopueblos.com; no se localizó el decreto en gob.mx. Anclas: criterio en "
                       "docs/catalogo_rutas_y_anclas.md",
         uso_en_modelo="Anclas y flags de visibilidad aproximada"),
    dict(clave="catalogo", fuente_sk=8, nombre="Catálogo de rutas turísticas existentes",
         institucion="Secretaría de Desarrollo Turístico del Estado de Puebla (visitpuebla.mx)",
         tipo="Catálogo manual",
         url="https://visitpuebla.mx/documents/CATALOGO%20DE%20RUTAS.pdf",
         version_corte="Catálogo de Rutas Turísticas del Estado de Puebla: 22 rutas en 4 circuitos",
         fecha_descarga=FECHA_CONSULTA, licencia_terminos="Información pública gubernamental",
         cobertura=None,
         calidad_notas="El catálogo no numera las paradas: se usa el orden de aparición. Localidades asignadas a su "
                       "municipio (Chipilo -> San Gregorio Atzompa, Santa María Tonantzintla -> San Andrés Cholula, "
                       "Ciudad Serdán -> Chalchicomula de Sesma, San Miguel Tenextatiloyan -> Zautla). "
                       "Bioruta del Café y Ruta del Mezcal se toman de sus guías oficiales (ver sus filas).",
         uso_en_modelo="Medir la novedad de las rutas propuestas (y, opcionalmente, etiquetas para el modelo de enlaces)"),
    dict(clave="bioruta_cafe", fuente_sk=None, nombre="Guía Bioruta del Café Puebla",
         institucion="Secretaría de Desarrollo Turístico del Estado de Puebla (visitpuebla.mx)",
         tipo="Catálogo manual",
         url="https://visitpuebla.mx/documents/BIORUTA%20DEL%20CAFE.pdf",
         version_corte="4 circuitos: Sierra Norte, Sierra Nororiental, Sierra Nevada y Sierra Negra",
         fecha_descarga=FECHA_CONSULTA, licencia_terminos="Información pública gubernamental",
         cobertura="29 municipios numerados en orden",
         calidad_notas="Orden de paradas según la numeración de la guía (1-29).",
         uso_en_modelo="Rutas existentes del café (novedad de rutas)"),
    dict(clave="ruta_mezcal", fuente_sk=None, nombre="Guía Ruta del Mezcal Poblano",
         institucion="Secretaría de Desarrollo Turístico del Estado de Puebla (visitpuebla.mx)",
         tipo="Catálogo manual",
         url="https://visitpuebla.mx/documents/RUTA%20DEL%20MEZCAL.pdf",
         version_corte="3 circuitos: Reserva de la Biosfera, Popocatépetl y Mixteca Poblana",
         fecha_descarga=FECHA_CONSULTA, licencia_terminos="Información pública gubernamental",
         cobertura="11 municipios con orden A-E por circuito",
         calidad_notas="Molcaxac aparece en el catálogo general (Legado de la Mixteca) pero no en la guía; se incluye "
                       "antes de Tepexi de Rodríguez.",
         uso_en_modelo="Rutas existentes del mezcal (novedad de rutas)"),
    dict(clave="regiones", fuente_sk=None, nombre="Regionalización socioeconómica del estado de Puebla (7 regiones)",
         institucion="Congreso del Estado de Puebla, Ley de Desarrollo Económico Sustentable (2015)",
         tipo="Oficial",
         url="https://es.wikipedia.org/wiki/Regiones_de_Puebla",
         version_corte="7 regiones, 2015",
         fecha_descarga=FECHA_CONSULTA, licencia_terminos="CC BY-SA (transcripción)",
         cobertura="217 municipios",
         calidad_notas="Transcrita de Wikipedia; existen regionalizaciones posteriores (22 regiones 2022-2024, "
                       "macrorregiones 2025) sin lista completa publicada.",
         uso_en_modelo="Columna region de dim_municipio (agregación y filtros del mapa)"),
]


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower().strip())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).replace(".", " ").split())


def haversine_km(a, b) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def cargar_municipios():
    geo = json.loads(GEO.read_text(encoding="utf-8"))
    props = [f["properties"] for f in geo["features"]]
    por_nombre = {normalizar(p["nombre"]): p for p in props}
    assert len(por_nombre) == 217, "Nombres de municipio duplicados en el GeoJSON"

    def buscar(nombre):
        p = por_nombre.get(normalizar(nombre))
        if p is None:
            raise KeyError(f"Municipio no encontrado en el Marco Geoestadístico: {nombre!r}")
        return p

    region = {}
    for reg, lista in REGIONES.items():
        for n in lista.split(","):
            cve = buscar(n)["cve_geo"]
            assert cve not in region, f"{n} aparece en dos regiones"
            region[cve] = reg
    assert len(region) == 217, f"La regionalización cubre {len(region)} de 217 municipios"

    pm = {buscar(n)["cve_geo"]: anio for n, anio in PUEBLOS_MAGICOS.items()}
    anclas = {buscar(n)["cve_geo"]: c for n, c in ANCLAS_EXTRA.items()}
    for cve, anio in pm.items():
        if 2026 - anio >= ANIOS_CONSOLIDACION:
            anclas[cve] = f"Pueblo Mágico desde {anio} (≥ {ANIOS_CONSOLIDACION} años de nombramiento)"

    filas = []
    for p in sorted(props, key=lambda p: p["cve_geo"]):
        c = p["cve_geo"]
        filas.append(dict(cve_geo=c, nombre=p["nombre"], region=region[c], es_pueblo_magico=c in pm,
                          anio_pueblo_magico=pm.get(c, ""), es_ancla=c in anclas, criterio_ancla=anclas.get(c, ""),
                          lon=p["lon"], lat=p["lat"]))
    return filas, buscar


def construir_rutas(buscar, anclas: set):
    rutas = OrderedDict()
    with CATALOGO.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p = buscar(r["municipio"])
            ruta = rutas.setdefault(int(r["ruta_id"]), dict(
                nombre=r["ruta"], tipo=r["tipo"], tema=r["tema"], es_monotematica=r["es_monotematica"] == "true",
                circuito=r["circuito"], fuente=r["fuente"], paradas=[], localidades=[]))
            ruta["paradas"].append(dict(orden_parada=int(r["orden"]), cve_geo=p["cve_geo"], nombre=p["nombre"],
                                        lonlat=(p["lon"], p["lat"])))
            if r["localidad_mencionada"]:
                ruta["localidades"].append(f"{r['localidad_mencionada']} ({p['nombre']})")

    claves = {f["clave"] for f in FUENTES}
    dim, paradas = [], []
    for ruta in rutas.values():
        assert ruta["fuente"] in claves, f"Fuente desconocida: {ruta['fuente']}"
        ps = sorted(ruta["paradas"], key=lambda x: x["orden_parada"])
        assert [x["orden_parada"] for x in ps] == list(range(1, len(ps) + 1)), f"Orden roto en {ruta['nombre']}"
        desc = (f"Ruta oficial del circuito {ruta['circuito']} (Secretaría de Desarrollo Turístico de Puebla). "
                f"Recorrido: {' → '.join(x['nombre'] for x in ps)}.")
        if ruta["localidades"]:
            desc += " Localidades mencionadas: " + "; ".join(ruta["localidades"]) + "."
        dim.append(dict(nombre=ruta["nombre"], tipo=ruta["tipo"], tema=ruta["tema"],
                        es_monotematica=ruta["es_monotematica"], origen="existente", version_sk=None,
                        num_municipios=len({x["cve_geo"] for x in ps}), duracion_estimada_h=None,
                        descripcion=desc, fuente=ruta["fuente"]))
        for i, x in enumerate(ps):
            dist = round(haversine_km(ps[i - 1]["lonlat"], x["lonlat"]), 2) if i else None
            paradas.append(dict(ruta=ruta["nombre"], orden_parada=x["orden_parada"], cve_geo=x["cve_geo"],
                                eje_sk=None, distancia_desde_anterior_km=dist, tiempo_desde_anterior_min=None,
                                es_ancla=x["cve_geo"] in anclas, es_emergente=False, estancia_sugerida_h=None))
    return dim, paradas


def _sql_valor(v):
    if v is None or v == "":
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def _columnas_fuente(f):
    return {k: v for k, v in f.items() if k not in ("clave", "fuente_sk")}


def generar_sql(fuentes, dim, paradas, municipios):
    """SQL equivalente a cargar_bd(), para correrlo en el SQL Editor de Supabase."""
    q = _sql_valor
    lineas = ["-- Generado por scripts/cargar_rutas_existentes.py (Rol C · Styveen). Idempotente.",
              "-- Las llaves *_sk son identity: todo se cruza por nombre (fuentes, rutas) y cve_geo (municipios).",
              "BEGIN;", "", "-- 1. Fuentes"]
    nombre_fuente = {f["clave"]: f["nombre"] for f in fuentes}
    for f in fuentes:
        cols = _columnas_fuente(f)
        sets = ", ".join(f"{c} = {q(v)}" for c, v in cols.items())
        if f["fuente_sk"]:
            lineas.append(f"UPDATE dw.dim_fuente SET {sets} WHERE fuente_sk = {f['fuente_sk']};")
        else:
            lineas.append(f"INSERT INTO dw.dim_fuente ({', '.join(cols)}) SELECT {', '.join(q(v) for v in cols.values())} "
                          f"WHERE NOT EXISTS (SELECT 1 FROM dw.dim_fuente WHERE nombre = {q(f['nombre'])});")
            lineas.append(f"UPDATE dw.dim_fuente SET {sets} WHERE nombre = {q(f['nombre'])};")

    lineas += ["", "-- 2. Rutas existentes"]
    for d in dim:
        fsk = f"(SELECT fuente_sk FROM dw.dim_fuente WHERE nombre = {q(nombre_fuente[d['fuente']])} LIMIT 1)"
        cols = {k: v for k, v in d.items() if k != "fuente"}
        valores = ", ".join(q(v) for v in cols.values())
        sets = ", ".join(f"{c} = {q(v)}" for c, v in cols.items()) + f", fuente_sk = {fsk}"
        lineas.append(f"INSERT INTO dw.dim_ruta ({', '.join(cols)}, fuente_sk) SELECT {valores}, {fsk} "
                      f"WHERE NOT EXISTS (SELECT 1 FROM dw.dim_ruta WHERE nombre = {q(d['nombre'])} AND origen = 'existente');")
        lineas.append(f"UPDATE dw.dim_ruta SET {sets} WHERE nombre = {q(d['nombre'])} AND origen = 'existente';")
    nombres = ", ".join(q(d["nombre"]) for d in dim)
    lineas.append("DELETE FROM dw.fact_ruta_parada WHERE ruta_sk IN (SELECT ruta_sk FROM dw.dim_ruta "
                  f"WHERE origen = 'existente' AND nombre NOT IN ({nombres}));")
    lineas.append(f"DELETE FROM dw.dim_ruta WHERE origen = 'existente' AND nombre NOT IN ({nombres});")

    lineas += ["", "-- 3. Paradas (requiere dw.dim_municipio cargada)",
               "DELETE FROM dw.fact_ruta_parada WHERE ruta_sk IN (SELECT ruta_sk FROM dw.dim_ruta WHERE origen = 'existente');",
               "INSERT INTO dw.fact_ruta_parada (ruta_sk, orden_parada, municipio_sk, distancia_desde_anterior_km, "
               "es_ancla, es_emergente)",
               "SELECT r.ruta_sk, v.orden_parada, m.municipio_sk, v.dist, v.es_ancla, false FROM (VALUES"]
    lineas.append(",\n".join(f"  ({q(p['ruta'])}, {p['orden_parada']}, '{p['cve_geo']}', "
                             f"{q(p['distancia_desde_anterior_km'])}::numeric, {q(p['es_ancla'])})" for p in paradas))
    lineas += [") AS v(ruta, orden_parada, cve_geo, dist, es_ancla)",
               "JOIN dw.dim_ruta r ON r.nombre = v.ruta AND r.origen = 'existente'",
               "JOIN dw.dim_municipio m ON m.cve_geo = v.cve_geo;", "", "-- 4. Pueblos Mágicos, anclas y regiones"]

    pm = ", ".join(f"'{m['cve_geo']}'" for m in municipios if m["es_pueblo_magico"])
    an = ", ".join(f"'{m['cve_geo']}'" for m in municipios if m["es_ancla"])
    lineas.append(f"UPDATE dw.dim_municipio SET es_pueblo_magico = (cve_geo IN ({pm})),")
    lineas.append(f"                            es_ancla         = (cve_geo IN ({an}));")
    for reg in REGIONES:
        cves = ", ".join(f"'{m['cve_geo']}'" for m in municipios if m["region"] == reg)
        lineas.append(f"UPDATE dw.dim_municipio SET region = {q(reg)} WHERE cve_geo IN ({cves});")
    lineas += ["", "COMMIT;", ""]
    SQL.parent.mkdir(parents=True, exist_ok=True)
    SQL.write_text("\n".join(lineas), encoding="utf-8")


def cargar_bd(fuentes, dim, paradas, municipios):
    import supabase_cliente as sb

    def patch(tabla, filtro, cambios):
        sb._peticion(f"{tabla}?{filtro}", True, "dw", "PATCH", cambios, {"Prefer": "return=minimal"})

    def crear(tabla, fila):
        return sb._peticion(tabla, True, "dw", "POST", fila, {"Prefer": "return=representation"})[0]

    # 1. Fuentes: 7 y 8 ya existen; las demás se crean una sola vez y se identifican por nombre.
    existentes = sb.leer("dim_fuente", "dw", "fuente_sk,nombre", secreta=True)
    por_nombre = dict(zip(existentes.nombre, existentes.fuente_sk))
    fuente_sk = {}
    for f in fuentes:
        cols = _columnas_fuente(f)
        sk = f["fuente_sk"] or por_nombre.get(f["nombre"])
        if sk:
            patch("dim_fuente", f"fuente_sk=eq.{sk}", cols)
        else:
            sk = crear("dim_fuente", cols)["fuente_sk"]
        fuente_sk[f["clave"]] = int(sk)
    print(f"✓ dim_fuente: {len(fuentes)} fuentes → " + ", ".join(f"{k}={v}" for k, v in fuente_sk.items()))

    # 2. Rutas existentes, identificadas por nombre.
    actuales = sb._peticion("dim_ruta?select=ruta_sk,nombre&origen=eq.existente", True, "dw")
    ruta_sk = {r["nombre"]: r["ruta_sk"] for r in actuales}
    sobran = [sk for n, sk in ruta_sk.items() if n not in {d["nombre"] for d in dim}]
    if sobran:
        ids = ",".join(map(str, sobran))
        sb._peticion(f"fact_ruta_parada?ruta_sk=in.({ids})", True, "dw", "DELETE")
        sb._peticion(f"dim_ruta?ruta_sk=in.({ids})", True, "dw", "DELETE")
    for d in dim:
        fila = {**{k: v for k, v in d.items() if k != "fuente"}, "fuente_sk": fuente_sk[d["fuente"]]}
        if d["nombre"] in ruta_sk:
            patch("dim_ruta", f"ruta_sk=eq.{ruta_sk[d['nombre']]}", fila)
        else:
            ruta_sk[d["nombre"]] = crear("dim_ruta", fila)["ruta_sk"]
    print(f"✓ dim_ruta: {len(dim)} rutas existentes (ruta_sk {min(ruta_sk.values())}-{max(ruta_sk.values())})")

    # 3. Paradas y columnas de dim_municipio: necesitan la dimensión de municipios.
    mun = sb.leer("dim_municipio", "dw", "municipio_sk,cve_geo", secreta=True)
    if mun.empty:
        print("… dw.dim_municipio está vacía: paradas y UPDATE de municipios quedan pendientes. "
              "Vuelve a ejecutar el script cuando el ETL la cargue (o corre sql/04_catalogo_rutas_styveen.sql).")
        return
    sk = dict(zip(mun.cve_geo.str.strip(), mun.municipio_sk))
    faltan = sorted({p["cve_geo"] for p in paradas} - set(sk))
    if faltan:
        raise SystemExit(f"cve_geo sin municipio_sk en dim_municipio: {faltan}")

    ids = ",".join(str(ruta_sk[d["nombre"]]) for d in dim)
    sb._peticion(f"fact_ruta_parada?ruta_sk=in.({ids})", True, "dw", "DELETE")
    filas = [{**{k: v for k, v in p.items() if k not in ("ruta", "cve_geo")},
              "ruta_sk": ruta_sk[p["ruta"]], "municipio_sk": int(sk[p["cve_geo"]])} for p in paradas]
    sb.insertar("fact_ruta_parada", filas, "dw")
    print(f"✓ fact_ruta_parada: {len(filas)} paradas")

    lista = lambda campo: ",".join(m["cve_geo"] for m in municipios if m[campo])
    patch("dim_municipio", "cve_geo=not.is.null", {"es_pueblo_magico": False, "es_ancla": False})
    patch("dim_municipio", f"cve_geo=in.({lista('es_pueblo_magico')})", {"es_pueblo_magico": True})
    patch("dim_municipio", f"cve_geo=in.({lista('es_ancla')})", {"es_ancla": True})
    for reg in REGIONES:
        cves = ",".join(m["cve_geo"] for m in municipios if m["region"] == reg)
        patch("dim_municipio", f"cve_geo=in.({cves})", {"region": reg})
    print("✓ dim_municipio: es_pueblo_magico, es_ancla y region actualizados")


def main():
    municipios, buscar = cargar_municipios()
    anclas = {m["cve_geo"] for m in municipios if m["es_ancla"]}
    dim, paradas = construir_rutas(buscar, anclas)
    for f in FUENTES:
        if f["clave"] == "catalogo":
            f["cobertura"] = (f"{sum(d['fuente'] == 'catalogo' for d in dim)} rutas tomadas del catálogo general "
                              f"({len({p['cve_geo'] for p in paradas})} municipios en todas las rutas existentes)")

    with MUNICIPIOS_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(municipios[0]))
        w.writeheader()
        w.writerows(municipios)
    generar_sql(FUENTES, dim, paradas, municipios)

    print(f"Rutas existentes: {len(dim)} · paradas: {len(paradas)} · municipios en rutas: "
          f"{len({p['cve_geo'] for p in paradas})}")
    print(f"Pueblos Mágicos: {sum(m['es_pueblo_magico'] for m in municipios)} municipios · "
          f"anclas: {len(anclas)} · regiones: {len(REGIONES)}")
    print(f"Archivos: {MUNICIPIOS_CSV.relative_to(RAIZ)}, {SQL.relative_to(RAIZ)}")
    if "--sin-bd" not in sys.argv:
        cargar_bd(FUENTES, dim, paradas, municipios)


if __name__ == "__main__":
    main()


