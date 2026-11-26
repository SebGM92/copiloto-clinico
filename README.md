# Copiloto Clínico

Monorepo: `backend/` (FastAPI + LangGraph + pgvector) y `frontend/` (Next.js).

```bash
# Base de datos (Postgres + pgvector en el puerto 5433)
docker compose up -d

# Backend
cd backend
cp .env.example .env
pip install -r requirements-dev.txt
uvicorn app.main:app --reload        # http://localhost:8000/docs

# Frontend
cd frontend
npm install && npm run dev           # http://localhost:3000
```

## Limitaciones conocidas

- **Flujogramas:** si son imágenes, su contenido se pierde. Si están dibujados con texto vectorial (como el algoritmo de la guía de DM2), la página se detecta y se descarta, porque sus etiquetas sueltas ("Sí", "No", "¿Cumple meta?") solo meten ruido. En ambos casos, la información suele estar también en el texto de la guía.
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
