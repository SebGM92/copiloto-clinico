# Copiloto Clínico

Monorepo: `backend/` (FastAPI + LangGraph + pgvector) y `frontend/` (Next.js).

```bash
# Base de datos (Postgres + pgvector en el puerto 5433)
docker compose up -d

# Backend
cd backend
cp .env.example .env
pip install -r requirements-dev.txt
set -a && source .env && set +a
python -m scripts.download_guides    # descarga las guías de corpus.json a guias/ y las ingesta
uvicorn app.main:app --reload        # API en http://localhost:8000 (POST /api/chat, GET /api/documents)

# Frontend
cd frontend
npm install && npm run dev           # http://localhost:3000
```

## Corpus

`backend/corpus.json` lista las guías con sus URL oficiales de DIPRECE. `python -m scripts.download_guides` (desde `backend/`) descarga cada PDF a `backend/guias/` (fuera de Git) y lo ingesta. Reingestar es seguro: si el PDF no cambió (mismo SHA-256) se omite. Para sumar una guía, agrega una entrada con el enlace directo al PDF; algunas filas de la tabla de DIPRECE enlazan a una página HTML y el script lo rechaza.

Hay que correrlo con `-m`: `python scripts/download_guides.py` falla con `No module named 'app'`, porque Python agrega al path la carpeta del script y no la del proyecto.

## Esquema de la base de datos

Cada fragmento se guarda una vez con dos índices: un vector (`embedding`) para buscar por significado y un `tsvector` (`tsv`) para buscar por palabras. Los párrafos viajan como JSONB, así una cita (página y párrafo) se resuelve sin volver a leer el PDF.

La configuración de texto `es_med` es la de español más `unaccent`: "hipertensión" e "hipertension" generan el mismo lexema, y siglas como "HbA1c" o "DM2" se conservan como términos buscables.

Decisiones:

- **El título de la sección pesa más (`A`) que el contenido (`B`).** Si la pregunta menciona "tratamiento farmacológico", gana el fragmento de esa sección y no uno que solo nombra el término de pasada.
- **La columna `tsv` es generada.** PostgreSQL la recalcula sola al cambiar `section` o `content`, así que nunca queda desfasada del texto.
- **HNSW con distancia coseno.** No necesita entrenarse con los datos, a diferencia de IVFFlat, y con unos miles de fragmentos responde en milisegundos.

## Evaluación de la búsqueda

`backend/eval/questions.json` tiene 20 preguntas (10 por guía) con las páginas donde está la respuesta. `python -m eval.retrieval_modes` (desde `backend/`) las corre con búsqueda solo semántica, solo léxica e híbrida, y cuenta en cuántas aparece una página correcta entre los 8 fragmentos que llegarían a Claude.

| Búsqueda | Página correcta en top 8 | En top 20 pero no en top 8 |
|---|---|---|
| Solo semántica (bge-m3) | 20/20 (100 %) | 0 |
| Solo léxica (tsvector, OR) | 18/20 (90 %) | 1 |
| Híbrida (RRF), primera versión | 19/20 (95 %) | 1 |
| Híbrida (RRF) + siglas `iDPP4`/`iSGLT2` | 20/20 (100 %) | 0 |

Lo que muestran:

- **La híbrida perdía una pregunta por una sigla.** En `dm2-04` ("¿iDPP4 o iSGLT2…?") la semántica ponía la página correcta primera, pero la léxica no la encontraba: la pregunta dice "iDPP4" y la guía "Inhibidores de DPP4", lexemas distintos. Con RRF, un fragmento que aparece en una sola lista suma 1/61 y lo superan fragmentos mediocres que aparecen en las dos: quedaba en el puesto 18. Agregar `IDPP4` e `ISGLT2` a las siglas la subió al puesto 1, sin cambiar las demás.
- **La léxica sola falla donde la pregunta no usa las palabras de la guía** (`dm2-10`, `dep-08`).
- **Reranking: por ahora no hace falta.** Ninguna respuesta queda entre los 20 primeros pero fuera de los 8.

Advertencias sobre estos números:

- **Las preguntas las redactó Claude** leyendo las guías, así que tienden a usar su vocabulario. Esto favorece a ambas búsquedas, sobre todo a la semántica, y hay que validarlas con un médico y sumar preguntas reales.
- Con solo dos guías hay pocos distractores; con más guías la búsqueda léxica debería aportar más (dosis exactas, nombres de fármacos).
- La Fase 8 debe repetir esto con más preguntas antes de decidir el reranking.

## Verificación de respuestas

`backend/app/verify.py` revisa cada respuesta de Claude antes de mostrarla, con reglas deterministas:

| Regla | Qué atrapa | Estado |
|---|---|---|
| Sin ninguna cita, o con la frase de abstención | El modelo no encontró sustento | `abstained` |
| Bloque con números y sin cita | Una dosis o meta inventada, o traída de memoria | `retracted` |
| Número que no aparece en el texto citado | Una dosis mal copiada ("100 mg" citando "50 mg") | `retracted` |
| Cita a un índice inexistente o con texto distinto | Un error de integración | `retracted` |

En clínica casi todo error grave es un número. La regla tiene falsos positivos conocidos ("cada 3 meses" citando "trimestral"): preferimos retirar una respuesta correcta a dejar pasar una dosis inventada.

**Ajuste medido:** con la regla tal cual, las 3 respuestas correctas de la prueba se retiraron. Claude abre con frases como "La guía GES de Diabetes Mellitus tipo 2 (2017) indica:" o "(Anexo 6)", sin cita y con números que no son datos clínicos. Ahora se ignoran el año de la guía entregada, las frases numéricas de su título junto a su palabra ("tipo 2", "15 años", no un "2" suelto) y las referencias a partes de la guía ("Anexo 6", "Tabla Nº 1", "Recomendación 3"). Después del ajuste, las 3 quedaron `verified` y la pregunta sin cobertura `abstained`. Una dosis sin cita o mal copiada se sigue retirando.

**Segundo ajuste, al probar el grafo completo:** una respuesta correcta sobre segunda línea en DM2 se retiró porque "metformina con iDPP4" contaba el 4 como dato. Ahora no cuentan los números pegados a una letra o unidos con guion, que son parte de un nombre: iDPP4, DM2, SGLT2, HbA1c, GLP-1, PHQ-9, CIE-10. Con este cambio, la respuesta quedó `verified` y sus 10 citas aparecen en las páginas indicadas del PDF (p29-p31). Las dosis y metas siguen contando ("50 mg", "<8%", "IMC >30").

## API con streaming

`POST /api/chat` recorre el grafo y reenvía cada evento como Server-Sent Events (`status`, `sources`, `token`, `citation`, `references` y, al final, `final` con el veredicto). `GET /api/documents` lista las guías cargadas. Cada pregunta queda en la tabla `queries` con su estado, los fragmentos usados y la latencia; si la pregunta se bloqueó por contener un RUN, se guarda como `[bloqueada: contenía datos de paciente]`, nunca el texto original.

### Decisión: la respuesta se muestra solo después del veredicto

El backend emite el texto en vivo, pero el frontend no lo muestra hasta recibir `final`. Mientras tanto muestra la etapa en curso ("buscando", "generando", "verificando").

| Opción | A favor | En contra |
|---|---|---|
| Texto en vivo en gris, "sin verificar", y retirarlo si falla | Se siente rápido: el primer texto llega en menos de 1 s | Un médico puede leer y actuar antes del veredicto |
| **Generar completo, verificar y recién mostrar** (elegida) | Nunca se ve una respuesta que después se retira | Espera de 3 a 6 s (medido con preguntas reales) |

Por qué:

- **En clínica, leer es actuar.** Un texto en gris con "sin verificar" no evita que alguien lea "50 mg" y lo use, sobre todo con prisa. Retirarlo después no deshace lo leído.
- **El error que importa es justo el que la verificación atrapa.** Un número mal copiado o sin cita se ve igual de convincente que uno correcto mientras se genera.
- **La espera es acotada y visible.** 3 a 6 s con etapas en pantalla es aceptable para una consulta de apoyo, no de urgencia vital.
- **No cuesta nada en el backend.** El streaming sigue igual; si en el futuro se quiere la otra opción, solo cambia el frontend.

## Limitaciones conocidas

- **Flujogramas:** si son imágenes, su contenido se pierde. Si están dibujados con texto vectorial (como el algoritmo de la guía de DM2), la página se detecta y se descarta, porque sus etiquetas sueltas ("Sí", "No", "¿Cumple meta?") solo meten ruido. En ambos casos, la información suele estar también en el texto de la guía.
- **Bloqueo de datos de pacientes (`guard.py`):** solo detecta RUNs con dígito verificador válido y preguntas de más de 2000 caracteres. No detecta un RUN escrito sin dígito verificador ("RUN 12.345.678"), nombres, fechas de nacimiento ni direcciones. Además, un celular de 9 dígitos escrito todo junto ("912345678") se bloquea por error cerca del 9 % de las veces, porque su último dígito calza por azar como dígito verificador (con espacios o "+56" no pasa).
- **Reingesta tras cambiar el parser:** la ingesta decide por el SHA-256 del PDF, así que un cambio en el parser o el chunker no reingesta nada por sí solo. Hay que borrar el documento (`DELETE FROM documents WHERE slug = ...`) y volver a correr el script.
- **Etiquetas de flujograma alineadas:** si varias cajas comparten exactamente la misma línea base, PyMuPDF las une en una sola línea y la página puede no detectarse como flujograma.

## Casos encontrados en guías reales

Al procesar la guía de DM2 del MINSAL (2016-2017) aparecieron casos que el parser no cubría. Cada uno tiene su test en `backend/tests/test_real_guide_cases.py`, con un PDF ficticio que lo reproduce.

| # | Caso | Efecto | Corrección |
|---|---|---|---|
| 1 | Encabezado de página en vertical en el margen lateral | Se colaba como párrafo 1 en cada página, desplazando la numeración de las citas | Los márgenes laterales también cuentan como zona de encabezados |
| 2 | "Certeza/Calidad de la evidencia" en negrita | Se tomaba como título: la fuerza desaparecía del texto del fragmento | Una línea de fuerza de recomendación nunca es título |
| 3 | Párrafo (y palabra: "Inhibi-" / "dores") que sigue en la página siguiente | Quedaba un fragmento suelto sin sentido al inicio de la página | Se une al párrafo anterior; en la nueva página cuenta como bloque 1 |
| 4 | Cambio a negrita a mitad de párrafo | El párrafo se partía en dos ("com-" / "parado") | Un bloque que empieza en minúscula tras uno sin cerrar se une al anterior |
| 5 | Flujograma dibujado con texto vectorial | ~40 párrafos basura ("Sí", "No") | Página con muchas etiquetas cortas y muchos trazos se descarta |
| 6 | Guion de corte dentro de celdas de tabla | "ESTU- DIOS", "hipoglice- miantes" | Las celdas se unen con la misma regla de guiones (también en mayúsculas) |
| 7 | "Recomendación N" y su pregunta, del mismo tamaño que "3.1 …" | La sección perdía "3.1 PRIMERA LÍNEA" y el número de recomendación | Títulos seguidos del mismo nivel se unen; un título numerado manda sobre uno sin número del mismo tamaño |
| 8 | Ítems de lista en negrita ("• Debut inestable:") | Se tomaban como títulos y sacaban la lista del fragmento de la recomendación | Un ítem con viñeta nunca es título |
| 9 | Viñeta sola en su propia línea ("−−") | Párrafos que eran solo un símbolo | La viñeta se pega al ítem que sigue |

Al sumar la guía de Depresión (MINSAL 2013) aparecieron cinco casos más:

| # | Caso | Efecto | Corrección |
|---|---|---|---|
| 10 | Títulos de portada ("Depresión", "en personas de 15 años y más") con letra más grande que los capítulos | Encabezaban la ruta de sección de los 316 fragmentos; con peso `A`, "depresión" puntuaba alto en todos | Un título sin número más grande que los capítulos numerados es de portada y no entra en la ruta |
| 11 | Índice de la guía (líneas con puntos guía en Depresión, tabla en DM2) | Fragmentos con el nombre de todas las secciones, que aparecían en cualquier búsqueda | Se descartan las líneas con puntos guía, las tablas cuya última columna son números de página crecientes y el título "ÍNDICE" |
| 12 | Rótulo de tabla ("Tabla Nº 1: …") en negrita, a veces en dos líneas | Se tomaba como título y quedaba en la ruta de sección del texto que seguía a la tabla | El rótulo es de tipo `caption`, se une si sigue en otra línea y viaja en el fragmento de su tabla |
| 13 | Llamada a nota al pie en superíndice ("Presentación clínica¹") | El título quedaba como "Presentación clínica1" | En los títulos se quitan los superíndices; en el texto se conservan ("kg/m²") |
| 14 | Tamaños de letra inconsistentes (9 niveles; "Epidemiología" más grande que "1.1.") | La jerarquía de secciones salía desordenada | La numeración manda: 5.1.2 cuelga de 5.1 y de 5. Una numeración que retrocede ("1. Fármaco versus Placebo" dentro de 5.3.2) es una lista; los anexos y "REFERENCIAS" reinician la ruta |
