"""Sube tu data/pricing.json real (con cifras) a Firestore, para que la app
desplegada en Cloud Run lo lea sin que esas cifras hayan pasado nunca por el
repo público de GitHub.

Corre esto UNA VEZ (y de nuevo cada vez que actualices precios) desde tu
máquina, nunca desde CI/CD ni desde un lugar donde el archivo real podría
terminar versionado.

Uso:
    1. gcloud auth application-default login
       (una vez, para que este script pueda escribir en tu proyecto de GCP)
    2. gcloud config set project TU_PROYECTO_DE_GCP
    3. Asegúrate de tener data/pricing.json local con las cifras reales
       (copia data/pricing.example.json si no lo tienes y complétalo).
    4. python scripts/upload_pricing_to_firestore.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRICING_PATH = HERE.parent / "data" / "pricing.json"


def main() -> None:
    if not PRICING_PATH.exists():
        raise SystemExit(
            f"No existe {PRICING_PATH}. Copia data/pricing.example.json a "
            "data/pricing.json y complétalo con las cifras reales antes de subirlo."
        )

    from google.cloud import firestore

    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    db = firestore.Client()
    db.collection("config").document("pricing").set(pricing)
    print(f"Listo. {PRICING_PATH.name} subido a Firestore (config/pricing) en el proyecto {db.project}.")
    print("Verifica en la consola de Firestore que las cifras sean las correctas antes de anunciar la URL al equipo.")


if __name__ == "__main__":
    main()
