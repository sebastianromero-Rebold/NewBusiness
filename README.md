# NewBusiness — herramientas internas de Rebold

Repositorio del equipo comercial de Rebold para herramientas de new business.

## Proyectos

### [`nota-a-propuesta/`](./nota-a-propuesta)

App local (Flask) que convierte la nota de una reunión comercial en un
borrador de propuesta `.pptx` con el estilo visual real de Rebold: extrae
señales de negocio de la nota, aplica las reglas comerciales de la Growth
Suite para decidir qué servicio(s) recomendar, arma la narrativa, inserta los
costos desde una tabla de pricing controlada por liderazgo (nunca inventados
por la IA), y ensambla el archivo. Incluye un dashboard con las marcas a las
que el equipo les ha dejado propuestas.

**Antes de correrla**, lee `nota-a-propuesta/README.md` — en particular la
sección sobre configurar tu propio `data/pricing.json` local (los precios
reales de Rebold no están en este repo público, por diseño).
