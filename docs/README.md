# De Nota de Reunión a Propuesta Comercial — versión web (sin servidor)

Un único archivo (`index.html`) que corre el pipeline completo — nota de
reunión → señales de negocio → diagnóstico por reglas de la Growth Suite →
narrativa → pricing controlado → `.pptx` con el estilo visual real de
Rebold — **100% en el navegador de quien lo abre**. No hay backend, no hay
base de datos, no hay ninguna cuenta de ningún servicio en la nube.

## Cómo compartirlo con el equipo

1. En este repo de GitHub: **Settings → Pages → Source: Deploy from a
   branch → Branch: `main` / `/docs` → Save**.
2. GitHub publica la página en `https://sebastianromero-rebold.github.io/NewBusiness/`
   (tarda 1-2 minutos la primera vez). Esa es la URL que compartes.
3. Listo — cualquiera con el link puede usarla, sin instalar nada.

## ⚠️ Lo que cada persona debe saber antes de usarla

**El pricing real de Rebold NO viene incluido**, a propósito: el código de
esta página es público (cualquiera puede ver "Ver código fuente" del
navegador), así que ninguna cifra real de Rebold puede vivir aquí sin quedar
expuesta a cualquiera con el link.

La primera vez que uses la página, entra a **"⚙ Configurar precios"** y pega
tu propia tabla de precios (mismo formato que
`nota-a-propuesta/data/pricing.example.json` del repo). Se guarda solo en
`localStorage` de tu navegador — nunca se sube a GitHub, nunca sale de tu
computador. Sin este paso, todas las líneas de inversión saldrán como
"pendiente de definir con liderazgo Rebold", que es el comportamiento seguro
por defecto, no un error.

## Limitaciones por diseño (no son bugs)

- **El historial del dashboard es por navegador/computador, no compartido
  entre personas.** Sin servidor, no hay dónde guardar "lo que generó todo el
  equipo" en un solo lugar. Cada quien ve solo lo que generó desde su propio
  equipo (`localStorage`). Si se necesita un histórico de verdad compartido
  entre todos, hace falta un servidor — ver `nota-a-propuesta/` y su sección
  de despliegue en Cloud Run, para el día que la empresa lo permita.
- **La configuración de pricing también es por navegador.** Si cambias de
  computador o borras datos de navegación, tienes que volver a pegarla.
- **Extracción heurística, no un LLM real.** Igual que el modo por defecto de
  `nota-a-propuesta/`, esta versión extrae señales por palabras clave, nunca
  por una llamada a un modelo de IA — es la opción segura porque solo puede
  citar frases que literalmente están en la nota, nunca puede inventar un
  dolor que el cliente no dijo. No se agregó un modo con API de Claude aquí a
  propósito, porque desde una página estática cualquier llave de API quedaría
  visible en el navegador de quien la use.

## Qué hay en el archivo

Todo vive en `index.html` (datos, lógica de diagnóstico, generación del
`.pptx` con [PptxGenJS](https://gitbrent.github.io/PptxGenJS/), e interfaz),
organizado en bloques `<script>` que replican 1 a 1 los módulos de la versión
Python (`pipeline/llm.py`, `pipeline/diagnostic_engine.py`,
`pricing/provider.py`, `deck/builder.py`) — si cambias una regla de negocio
en un lado, cámbiala también en el otro para que no se desalineen.

Lectura de `.docx` vía [Mammoth.js](https://github.com/mwilliamson/mammoth.js);
ambas librerías (Mammoth y PptxGenJS) se cargan desde jsDelivr, son las únicas
dependencias externas de la página.
