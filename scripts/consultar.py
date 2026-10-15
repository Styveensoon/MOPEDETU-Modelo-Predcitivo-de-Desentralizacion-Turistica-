"""Ejecuta una consulta de solo lectura y muestra el resultado (para verificaciones).

Uso:
    python scripts/consultar.py "SELECT COUNT(*) FROM dw.dim_municipio"
"""
import sys

import pandas as pd

from db import motor

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

with motor().connect() as conn:
    for consulta in sys.argv[1:]:
        print(pd.read_sql_query(consulta, conn).to_string(index=False))
        print()
