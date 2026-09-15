# NewBusiness — herramientas internas de Rebold

Repositorio del equipo comercial de Rebold para herramientas de new business.

## Proyectos

### 🌐 [`docs/`](./docs) — versión web, para compartir con todos los equipos (empieza aquí)

Un único archivo `index.html` con el pipeline completo (nota de reunión →
señales → diagnóstico → narrativa → pricing → `.pptx`) corriendo 100% en el
navegador — sin backend, sin servidor, sin ninguna cuenta de servicio en la
nube. Es la versión pensada para compartir un solo link con otros equipos vía
**GitHub Pages**.

**Cómo compartirla**: activa GitHub Pages en este repo apuntando a la carpeta
`docs/` de la rama `main` (Settings → Pages → Source: Deploy from a branch →
`main` → `/docs`), y comparte la URL que GitHub te da
(`https://sebastianromero-rebold.github.io/NewBusiness/`). Lee
[`docs/README.md`](./docs/README.md) antes de compartirla — en particular la
parte de cómo cada persona configura su propio pricing sin exponer cifras
reales de Rebold en el código público.

**Limitación por diseño** (no un bug): al no tener servidor ni base de datos,
cada persona que abre el link tiene su propio historial de propuestas y su
propia configuración de pricing guardados solo en su navegador — no hay un
dashboard verdaderamente compartido entre distintas personas. Si en algún
momento la empresa permite crear una cuenta de un servicio en la nube, se
puede agregar un histórico compartido de verdad (ver la sección de Cloud Run
en `nota-a-propuesta/README.md`, hecha para ese escenario).

### 🖥️ [`nota-a-propuesta/`](./nota-a-propuesta) — versión con backend (Flask)

La misma lógica que `docs/`, pero como app Python con servidor propio. Tiene
un dashboard de verdad compartido (vía Firestore) cuando se despliega en
Google Cloud Run. **No es la opción activa hoy** porque la empresa no permite
crear cuentas de Google Cloud — queda documentada por si esa restricción
cambia más adelante, o para correrla localmente tú solo con mejor calidad de
extracción (puede usar la API de Claude en vez del modo heurístico).
