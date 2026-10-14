"""Catálogo de actividades turísticas temáticas (anillo A1) y reglas para asignarlas.

Cada actividad se detecta con hasta tres señales:
  - scian:    códigos SCIAN 2023 del DENUE (prefijo o código completo).
  - nombre:   expresión regular sobre nom_estab + raz_social (sin acentos, en minúsculas),
              restringida a los códigos de `nombre_en` para no confundir, p. ej., un "Café Internet".
  - catalogo: temas de las rutas oficiales existentes (dim_ruta.tema) y lugares de catálogo (INAH).

Los códigos se verificaron contra el DENUE 05/2026 de Puebla.
"""

ACTIVIDADES = [
    # clave, nombre, icono, eje (dim_eje.codigo), descripción
    ("cafe", "Café", "☕", "turismo", "Fincas, beneficios y tostadores de café de altura"),
    ("mezcal", "Mezcal y destilados", "🥃", "turismo", "Palenques y elaboración de mezcal y otros destilados de agave"),
    ("bebidas_tradicionales", "Pulque y sidra", "🍎", "alimentos", "Pulquerías, sidra y bebidas fermentadas tradicionales"),
    ("artesanias", "Talavera y artesanías", "🏺", "comercio_turistico", "Talavera, alfarería, ónix y tiendas de artesanías"),
    ("gastronomia", "Gastronomía tradicional", "🍲", "alimentos", "Moles, antojitos, barbacoa y cocina tradicional"),
    ("museos", "Museos y cultura", "🏛️", "turismo", "Museos públicos y privados"),
    ("arqueologia", "Zonas arqueológicas", "🗿", "turismo", "Zonas arqueológicas abiertas al público (INAH)"),
    ("religioso", "Turismo religioso y conventos", "⛪", "turismo", "Conventos, santuarios y rutas religiosas"),
    ("ecoturismo", "Ecoturismo y aventura", "🌲", "turismo", "Cabañas, campamentos, parques ecoturísticos, senderismo"),
    ("volcanes", "Volcanes y alta montaña", "🌋", "turismo", "Izta-Popo, Citlaltépetl y montañismo"),
    ("balnearios", "Balnearios y aguas termales", "♨️", "turismo", "Parques acuáticos, balnearios y aguas termales"),
    ("flores_viveros", "Flores y viveros", "🌸", "comercio_turistico", "Viveros y producción de flores y plantas"),
    ("comunitario", "Turismo comunitario", "🤝", "turismo", "Cooperativas y sociedades de producción con servicios turísticos"),
    ("operadores", "Agencias y operadores turísticos", "🧭", "turismo", "Agencias de viajes, excursiones y transporte turístico"),
]

# Códigos SCIAN donde tiene sentido buscar palabras clave de turismo.
SCIAN_TURISTICO = ("7211", "7212", "7213", "7224", "7225", "7121", "7131", "7139", "5615", "4871", "4872", "4879",
                   "3119", "3121", "3271", "4659", "4612", "3114", "4663")
# Hospedaje, recreación y operadores: evita falsos positivos como "Pulquería La Cabaña" o "Carnitas El Volcán".
SCIAN_HOSPEDAJE_RECREACION = ("7211", "7212", "7213", "7121", "7131", "7139", "5615", "4871", "4872", "4879")

REGLAS = {
    "cafe": dict(scian=("311921", "311922"),
                 nombre=r"\bfinca\b|cafetal|beneficio de cafe|cafe de altura|cafe organico|tostador",
                 nombre_en=SCIAN_TURISTICO, catalogo=("cafe",)),
    "mezcal": dict(scian=("312145", "312149"), nombre=r"mezcal|mexcal|palenque",
                   nombre_en=("3121", "4612", "7224", "7225", "4659"), catalogo=("mezcal",)),
    "bebidas_tradicionales": dict(scian=("312132", "312139"), nombre=r"pulque|sidra|tlachiquer",
                                  nombre_en=SCIAN_TURISTICO, catalogo=()),
    "artesanias": dict(scian=("327111", "465915"), nombre=r"talavera|artesania|alfarer|\bonix\b|barro brunido",
                       nombre_en=SCIAN_TURISTICO, catalogo=()),
    "gastronomia": dict(scian=(),
                        nombre=r"\bmoles?\b|antojit|barbacoa|mixiote|cocina tradicional|chiles? en nogada|cemita|mole de caderas",
                        nombre_en=("7225", "3114", "4612"), catalogo=("gastronomia",)),
    "museos": dict(scian=("712111", "712112"), nombre=None, nombre_en=(), catalogo=()),
    "arqueologia": dict(scian=(), nombre=None, nombre_en=(), catalogo=("arqueologia",)),
    "religioso": dict(scian=(), nombre=None, nombre_en=(), catalogo=("religioso", "conventos")),
    "ecoturismo": dict(scian=("721190", "721210", "712190", "713998"),
                       nombre=r"ecotur|cabanas?|campamento|tirolesa|rappel|parque ecologico|senderismo|canopy",
                       nombre_en=SCIAN_HOSPEDAJE_RECREACION,
                       catalogo=("senderismo", "naturaleza", "ciclismo", "naturaleza_cultura", "arqueologia_naturaleza")),
    "volcanes": dict(scian=(), nombre=r"volcan|popocatepetl|iztaccihuatl|citlaltepetl|pico de orizaba|alta montana",
                     nombre_en=SCIAN_HOSPEDAJE_RECREACION, catalogo=("naturaleza_cultura",)),
    "balnearios": dict(scian=("713113", "713114"), nombre=r"balneario|aguas termales|termal\b|spa termal",
                       nombre_en=SCIAN_TURISTICO, catalogo=()),
    # Solo viveros y productores: la florería de barrio (466312) existe en casi todos los municipios.
    "flores_viveros": dict(scian=(), nombre=r"vivero|floricult|invernadero", nombre_en=("4663", "1114"),
                           catalogo=()),
    "comunitario": dict(scian=(),
                        nombre=r"cooperativa(?! escolar)|\bs\.? ?p\.? ?r\.?\b|sociedad de produccion rural|ejido|comunitari",
                        nombre_en=("7211", "7213", "7225", "7139", "7121", "5615", "4659"), catalogo=()),
    "operadores": dict(scian=("561510", "561520", "487110", "487210", "487990"), nombre=None, nombre_en=(),
                       catalogo=()),
}

# Zonas arqueológicas del INAH abiertas al público con respaldo en fuentes (cve_geo del municipio).
ZONAS_ARQUEOLOGICAS = {
    "21140": "Zona Arqueológica de Cholula",
    "21170": "Cantona",
    "21043": "Yohualichan",
    "21169": "Tepexi el Viejo",
}

# Punto medio del estrato de personal ocupado (dw.dim_estrato_personal).
PUNTO_MEDIO = {"0 a 5 personas": 2.5, "6 a 10 personas": 8, "11 a 30 personas": 20.5, "31 a 50 personas": 40.5,
               "51 a 100 personas": 75.5, "101 a 250 personas": 175.5, "251 y más personas": 300}


def nivel_predominancia(cl: float, unidades: float, catalogo: bool) -> str:
    if unidades == 0:
        return "reconocida_sin_registro" if catalogo else "sin_oferta"
    if cl >= 2 and unidades >= 3:
        return "muy_alta"
    if cl >= 1.25:
        return "alta"
    if cl >= 0.75:
        return "media"
    return "baja"
