# De Nota de Reunión a Propuesta Comercial — Rebold

App interna que convierte la nota de una reunión comercial en un borrador de
propuesta `.pptx` con el estilo visual real de Rebold, siguiendo el pipeline
de 7 pasos: ingesta → señales → diagnóstico por reglas → narrativa → pricing
controlado → ensamble → revisión humana obligatoria. Incluye un dashboard con
las marcas a las que el equipo les ha dejado propuestas.

## Regla de oro (no negociable)

**La IA nunca genera montos de inversión, revenue-share ni cifras de proof
cases.** Todo costo sale de `data/pricing.json` (tu copia local, ver más
abajo). Lo que no tiene cifra cerrada se marca
`"Monto pendiente de definir con liderazgo Rebold"` — nunca se estima,
redondea ni infiere. El archivo final siempre sale marcado
**BORRADOR — PENDIENTE DE REVISIÓN** y nunca se envía automáticamente a nadie.

## ⚠️ Este repo es público — configura tu pricing localmente

`data/pricing.json` (los precios reales de Rebold) y `data/propuestas.json`
(nombre/correo reales de contactos de clientes) están en `.gitignore` a
propósito y **no existen en este repo**. La primera vez que lo clones:

```bash
cp data/pricing.example.json data/pricing.json
```

y reemplaza cada `"REEMPLAZAR"` con el número real que te dé Sofía/liderazgo.
Sin este paso, todas las líneas de inversión saldrán como "pendiente de
definir" — lo cual es el comportamiento seguro por defecto, no un error.
`data/propuestas.json` se crea solo, vacío, la primera vez que generes una
propuesta — nunca lo subas a git si algún día decides quitarlo del
`.gitignore`.

## Instalación

```bash
cd nota-a-propuesta
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp data/pricing.example.json data/pricing.json   # y edítalo con precios reales
python app.py
```

Abre `http://127.0.0.1:5000` — arranca en el dashboard.

## Desplegar para que otros equipos entren a una sola URL (Google Cloud Run)

Correr `python app.py` en tu máquina sirve para probar, pero cada quien vería
solo lo que generó en su propia computadora — no hay histórico compartido. Para
que varios equipos usen una sola URL con un dashboard compartido de verdad, la
app se despliega en Cloud Run y el histórico de propuestas se guarda en
Firestore en vez de en un archivo local (la app detecta sola en qué entorno
está corriendo, vía las variables `K_SERVICE`/`GOOGLE_CLOUD_PROJECT` que Cloud
Run define automáticamente — no hay que tocar código para esto).

**Se decidió explícitamente que esta URL queda abierta a cualquiera que la
tenga (sin login).** La app muestra contactos reales de clientes y cifras de
pricing de Rebold — solo compártela dentro del equipo, no la publiques en
ningún canal externo. Si más adelante quieres restringirla a
`@letsrebold.com`, Cloud Run soporta Identity-Aware Proxy (IAP); pide ayuda
para configurarlo cuando lo necesites.

Pasos (requieren una cuenta/proyecto de Google Cloud y el SDK `gcloud`
instalado — no vienen configurados en este repo):

```bash
# 1. Una sola vez: crea o elige tu proyecto de GCP y habilita Firestore.
gcloud config set project TU_PROYECTO_DE_GCP
gcloud services enable firestore.googleapis.com run.googleapis.com
gcloud firestore databases create --location=us-central1   # o la región que prefieras

# 2. Sube tus precios reales a Firestore (nunca al repo — ver el script para más detalle).
cd nota-a-propuesta
cp data/pricing.example.json data/pricing.json   # si no lo tenías ya, y complétalo
pip install google-cloud-firestore
gcloud auth application-default login
python scripts/upload_pricing_to_firestore.py

# 3. Despliega. --source . construye el contenedor desde el Dockerfile de esta carpeta.
gcloud run deploy nota-a-propuesta \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances=1 --max-instances=1 \
  --set-env-vars FLASK_SECRET_KEY=$(openssl rand -hex 16)
```

El comando termina imprimiendo la URL pública (algo como
`https://nota-a-propuesta-xxxxx.a.run.app`) — esa es la que compartes con los
otros equipos.

`--min-instances=1 --max-instances=1` es intencional, no un descuido: mientras
alguien está a mitad de revisar un borrador (entre "Procesar nota" y
"Confirmar y descargar"), ese estado vive en memoria del proceso, no en
Firestore. Con una sola instancia siempre corriendo, esa revisión no se pierde
a media revisión. El dashboard con el histórico completo sí vive en Firestore
y sobrevive sin problema a que la instancia se reinicie o se vuelva a
desplegar.

Si más adelante quieres usar Claude API en vez del modo heurístico, agrega
`--update-env-vars ANTHROPIC_API_KEY=tu_key` a un `gcloud run deploy` (o
`gcloud run services update`) posterior — nunca la pongas en el Dockerfile ni
en el repo.

Para actualizar la app después de cambios de código, corre el mismo
`gcloud run deploy` de nuevo desde `nota-a-propuesta/`.

## Qué hay en la app

- **Dashboard (`/`)**: todas las marcas a las que se les ha generado una
  propuesta en esta instancia, con su contacto (nombre/correo capturados al
  crear la nota) y el estado de cada propuesta (borrador / descargada).
- **Nueva propuesta (`/nueva`)**: el formulario de siempre — pega la nota o
  sube un `.docx`, indica si es cliente actual o prospecto nuevo (obligatorio,
  nunca se asume), y ahora también el nombre/correo del contacto del cliente
  (solo para identificar la propuesta en el dashboard, no se envía a ningún
  lado).
- **Revisión (`/revisar/<id>`)**: señales extraídas, diagnóstico, narrativa e
  inversión, editable antes de generar el archivo final.

Local (`python app.py`), el dashboard se guarda en `data/propuestas.json`, un
JSON simple en disco. Desplegado en Cloud Run, el mismo código guarda y lee
ese histórico desde Firestore automáticamente (ver la sección de despliegue
arriba) — así el dashboard es de verdad compartido entre todos los equipos
que usen la URL pública, no algo por-instancia.

## Diseño del `.pptx`

El estilo visual (fondo casi negro, tarjetas oscuras redondeadas, kicker rosa
en mayúsculas, titulares en Arial Black, tarjetas de inversión con precio
grande) está calcado de una propuesta real de Rebold
(`Plaza_Mayor_Propuesta_Rebold.pptx`) para que el borrador se sienta como un
documento de Rebold desde el primer momento, no como una plantilla genérica.
Todo el ensamble vive en `deck/builder.py`.

## Modo de extracción (con o sin API key de Claude)

- **Sin `ANTHROPIC_API_KEY`**: la app usa un extractor heurístico por keywords
  (`pipeline/llm.py: MockLLMProvider`). Es 100% funcional — solo puede citar
  substrings textuales de la nota, así que es imposible que alucine un dolor
  que el cliente no dijo. Es la opción segura por defecto.
- **Con `ANTHROPIC_API_KEY`** (copia `.env.example` a `.env` y complétala, o
  expórtala como variable de entorno): la app cambia automáticamente a Claude
  API para una extracción y narrativa más matizadas. Aun así, cada cita se
  valida después contra el texto original (guardarraíl anti-alucinación en
  `pipeline/signals.py`) y a la narrativa nunca se le pasa la tabla de pricing.

## Pricing: de dónde salen los números

`data/pricing.example.json` es la plantilla versionada (sin cifras reales).
Tu copia local `data/pricing.json` sigue estas reglas de mapeo, tomadas de la
hoja real "Productos y pricing Rebold" al momento de construir esta app:

- Si la hoja trae una **cifra cerrada** (ej: Pieza IA Video = $320.000 COP) →
  se inserta tal cual.
- Si la hoja trae un **rango** (ej: Rebold Optimization Audit
  $5.000.000–$18.000.000 según indicadores) → se marca `pendiente` en la app
  y el rango solo aparece como referencia interna en las notas del orador,
  nunca como cifra cerrada en la slide visible al cliente.
- **Activation Hub** usa una regla fija (fee de $2.000.000 COP si la inversión
  digital mensual es menor a $20.000.000 COP, o 10% sobre inversión digital +
  3% sobre ATL si es igual o mayor), calculada en código en
  `pricing/provider.py` — si esa regla cambia, hay que editar ese archivo,
  no solo el JSON.
- **Audience Nexus** (revenue-share) no tenía ninguna fila en la hoja original
  → siempre queda `pendiente` hasta que liderazgo la defina.

Para refrescar `data/pricing.json` cuando liderazgo actualice la hoja real,
ver las instrucciones dentro de `pricing/sync_from_drive.py` (requiere
credenciales de Google Sheets API — hay que crearlas una vez en Google Cloud
Console, no vienen configuradas en este proyecto).

## Casos de prueba

`data/casos_prueba.json` trae únicamente los casos con cifras reales que ya
existen en la skill `rebold-servicios-suite` (Jägermeister, Falabella, Páramo
Presenta, Keralty México, Ferias Colombia, 4Patas, Colsubsidio, Henkel, MSD,
PTESA). Si no hay un caso de la industria exacta del cliente, la app muestra
el caso más cercano igual, etiquetado como "Caso de referencia" con su
industria real visible — nunca fabrica uno nuevo. Este archivo sí es público
porque son cifras que Rebold ya usa en pitches reales.

## Estructura

```
app.py                     Flask: rutas, dashboard y orquestación del pipeline
pipeline/ingest.py         Paso 1 — normalización de la nota (texto/.docx)
pipeline/llm.py            Capa de LLM intercambiable (heurística ↔ Claude API)
pipeline/signals.py        Paso 2 — señales estructuradas + guardarraíl anti-alucinación
pipeline/diagnostic_engine.py  Paso 3 — reglas duras (máx. 2 servicios, Growth Engine,
                            Agent Lab gateado, cross-sell, default Rebold Audit)
pipeline/narrative.py      Paso 4 — narrativa (nunca recibe pricing)
pipeline/store.py          Persistencia del dashboard: JSON local o Firestore según entorno
pricing/provider.py        Paso 5 — resolución de costos, SIEMPRE desde datos
                            estructurados, nunca desde texto generado (JSON local o Firestore)
pricing/sync_from_drive.py Script manual para refrescar pricing.json desde Drive
scripts/upload_pricing_to_firestore.py  Sube tu pricing.json real a Firestore para Cloud Run
deck/builder.py            Paso 6 — ensamble del .pptx con el estilo visual de Rebold
Dockerfile, .dockerignore  Imagen para desplegar en Cloud Run
data/pricing.example.json  Plantilla de pricing SIN cifras reales (versionada)
data/pricing.json          Tu copia local con cifras reales (gitignored)
data/casos_prueba.json     Proof cases oficiales (público)
data/propuestas.json       Dashboard en modo local (gitignored — tiene contactos reales;
                            en Cloud Run esto vive en Firestore, no en este archivo)
data/audit_log.jsonl       Métricas de éxito (Paso 7 / Sección 7 del brief, gitignored)
templates/, static/        UI (dashboard, formulario, pantalla de revisión)
```

## Casos ambiguos (por diseño, nunca se fuerza un diagnóstico)

- **Sin dolor explícito**: la app no inventa uno — pide agregar la frase
  textual que falta y no deja avanzar.
- **Tipo de relación no indicado**: es un campo obligatorio del formulario sin
  valor por defecto — nunca se asume "prospecto nuevo" ni "cliente actual".
- **Más de 2 dolores**: el motor prioriza 2 según la matriz de la skill y deja
  el resto como "oportunidades futuras" (solo visibles internamente, nunca en
  la slide del cliente).
- **Agent Lab**: solo aparece si hay señal explícita de CRM/base dormida —
  nunca por defecto, ni siquiera si el cliente es "cliente actual".

## Métricas (`data/audit_log.jsonl`)

Cada vez que se genera un `.pptx` se registra: si las citas de dolor son
substrings verbatim de la nota original (control de alucinación), qué
servicios se recomendaron, y qué líneas de inversión quedaron "pendiente" vs.
"definido". Esto es lo que permite medir, con el tiempo, la métrica que más
importa: **cero incidentes de montos inventados llegando a un cliente**.
