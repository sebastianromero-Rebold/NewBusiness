# Rebold NewBusiness

Plataforma del equipo comercial de Rebold para convertir **lo que pasó en la reunión con el cliente**
(apuntes, notas, menciones, archivos y audios) en una **propuesta comercial lista en Google Slides**.
Las propuestas siguen el estilo visual de Rebold y usan el conocimiento de la Growth Suite y la
metodología de storytelling de la agencia.

**App:** https://sebastianromero-rebold.github.io/NewBusiness/

```
index.html              ← la aplicación completa (un solo archivo, corre en el navegador)
apps-script/Code.gs     ← backend en Google Apps Script (Drive, Sheets, Slack, correo, IA)
apps-script/appsscript.json
```

---

## Qué hace

1. **Datos de la propuesta**: marca, presupuesto (moneda y periodicidad), comercial que contactó al
   cliente, uno o más contactos del cliente con teléfono y correo, y los directores de área que la
   revisan: Natalia Patiño, Javier Lozano, Jennifer Carvajal, Sebastian Romero y Alejandro Muller.
2. **Material de la reunión**: notas de texto, archivos (PDF, Word, PowerPoint, Excel, imágenes,
   texto) y audios. También se puede **grabar la reunión** desde el navegador y se transcribe en vivo
   (Chrome/Edge).
3. **Generación con IA (Claude)** en dos pasos:
   - *Diagnóstico y estrategia* con la lógica de **rebold-servicios-suite**: qué servicio(s)
     ofrecer (máx. 2 protagonistas), dolores detectados y siguiente paso de la cuenta.
   - *Narrativa y slides* con **strategic-planning-360**: problema real → oportunidad → insight →
     hipótesis → frentes → ecosistema → métricas → inversión → próximos pasos.
4. **Pre-visualización editable**: se ve igual que el archivo final. Puedes editar cualquier texto
   con un clic, reordenar, duplicar o eliminar slides, y pedirle ajustes a la IA por slide o para
   toda la presentación.
5. **Salida**: descarga en `.pptx` o **Guardar en Drive** como Google Slides (carpeta por marca, una
   versión nueva cada vez: v1, v2…).
6. **Revisión**: *Enviar a revisión* notifica por **Slack** a los directores seleccionados con el
   link de revisión y el link de Drive. Cada director **aprueba** o **pide ajustes** con
   comentarios (el comercial recibe los comentarios por Slack y correo).
7. **Aprobado final**: cuando todos los directores seleccionados aprueban la versión vigente, se
   envía un **correo** a los directivos implicados para que aprueben y validen la propuesta.
8. **Dashboard**: número de propuestas, valor en pipeline, valor ganado, tasa de cierre, valor por
   estado y por comercial, y la tabla con el estado de cada propuesta: *Borrador, En revisión,
   Ajustes solicitados, Aprobada interna, Enviada, Presentada, Aprobada, Rechazada, Eliminada*.
9. **Registro (log)**: cada acción queda en Google Sheets (quién, qué, cuándo). Cada cambio guarda
   una copia completa del registro anterior, así que nada se pierde aunque se elimine. Eliminar una
   propuesta la marca como *Eliminada* (se puede restaurar), nunca se borra.

### Reglas que protegen la propuesta
- La IA **nunca escribe montos de inversión**: el valor de la slide de inversión sale del presupuesto
  que ingresó el comercial.
- Solo usa cifras que estén en el material de la reunión o las cifras oficiales de los casos de
  Rebold. Si detecta una cifra de dinero que no viene de ninguna de esas fuentes, el editor la marca
  en amarillo para que se revise.
- Agent Lab solo aparece con una señal explícita de CRM/base dormida, y Audience Nexus nunca lleva
  cifras de revenue-share (se definen con liderazgo).

---

## Instalación del backend (una sola vez, ~15 minutos)

El backend corre en **Google Apps Script** con una cuenta de Google Workspace de Rebold. No
necesita una cuenta de Google Cloud. La persona que lo despliega es la "dueña" de la carpeta de
Drive y de la hoja de Google Sheets que se crean.

1. Entra a <https://script.google.com> → **Nuevo proyecto**. Nómbralo `Rebold NewBusiness`.
2. Copia el contenido de [`apps-script/Code.gs`](apps-script/Code.gs) en el archivo `Código.gs`.
3. En **Configuración del proyecto** (ícono de engranaje) activa *Mostrar el archivo de manifiesto
   "appsscript.json"*, y reemplaza su contenido por [`apps-script/appsscript.json`](apps-script/appsscript.json).
4. En **Configuración del proyecto → Propiedades del script** agrega:

   | Propiedad | Obligatoria | Valor |
   |---|---|---|
   | `TEAM_CODE` | sí | Un código que compartirás con el equipo (ej. una frase larga) |
   | `ANTHROPIC_API_KEY` | sí | API key de Claude (console.anthropic.com) |
   | `SLACK_BOT_TOKEN` | recomendada | Token `xoxb-…` de una app de Slack con el permiso `chat:write` → mensaje directo a cada director |
   | `SLACK_WEBHOOK_URL` | opcional | Webhook de un canal (ej. `#propuestas`) con menciones a los directores |
   | `OPENAI_API_KEY` | opcional | Para transcribir audios **subidos** (la grabación en vivo no lo necesita) |
   | `DIRECTIVOS_CC` | opcional | Correos adicionales (separados por coma) para el correo de aprobación final |
   | `CLAUDE_MODEL` | opcional | Por defecto `claude-opus-5` |
   | `APP_URL` | opcional | Por defecto `https://sebastianromero-rebold.github.io/NewBusiness/` |

5. Selecciona la función `setup` y pulsa **Ejecutar**. Acepta los permisos. Esto crea la carpeta
   **"Rebold · Propuestas NewBusiness"** en Drive y la hoja **"Rebold NewBusiness · Base de
   propuestas y log"** (pestañas *Propuestas* y *Log*).
6. **Implementar → Nueva implementación → Aplicación web**. En *Ejecutar como* elige **Yo** y en
   *Quién tiene acceso* elige **Cualquier persona**. Copia la URL que termina en `/exec`.
   (El acceso queda protegido por el `TEAM_CODE`: sin el código, el backend no responde.)
7. Abre la app → **Configuración** → pega la URL y el código de equipo → *Probar conexión*.
   Para que nadie más tenga que pegar la URL, puedes ponerla en `DEFAULT_BACKEND_URL` dentro de
   `index.html` y subir el cambio. Cada persona solo necesita el código de equipo.

> Cuando cambies `Code.gs`, publica otra vez desde **Implementar → Gestionar implementaciones →
> Editar → Nueva versión** para que la URL use el código nuevo.

**Directores**: sus nombres, correos e IDs de Slack están al inicio de `Code.gs` (`DIRECTORES`).
Se tomaron del Slack de Rebold. Verifica los correos antes de salir a producción. El correo de
Sebastian Romero se asumió como `sebastian.romero@letsrebold.com`.

## Publicación en GitHub Pages
Settings → Pages → *Deploy from a branch* → `main` / `(root)`. La app queda en
`https://sebastianromero-rebold.github.io/NewBusiness/`.

## Modo local (para probar sin backend)
Si no hay URL de backend, la app funciona en **modo local**: los datos quedan solo en ese
navegador y la IA se llama con una API key de Claude propia (Configuración → Modo local). En este
modo no hay Drive, Slack ni correo, pero sí se puede generar, editar y descargar el `.pptx`. El
Dashboard tiene un botón para ver una **propuesta de ejemplo** sin gastar IA.

## Notas técnicas
- Las slides se diseñan una sola vez como primitivas (rectángulos, textos, imágenes e iconos) sobre
  un lienzo de 13.33 × 7.5 in. De ahí salen la pre-visualización HTML y el `.pptx`
  ([PptxGenJS](https://gitbrent.github.io/PptxGenJS/)). Los textos se reducen automáticamente para
  caber en su caja.
- Google Slides se crea subiendo el `.pptx` a Drive con conversión (servicio avanzado de Drive v3).
- La API key de Claude vive solo en las propiedades del script. El HTML público no contiene
  credenciales.
- Límites de Apps Script: 6 min por ejecución, ~1.500 correos/día en Workspace. Por eso la
  generación se hace en llamadas cortas (estrategia y luego dos bloques de slides en paralelo).
