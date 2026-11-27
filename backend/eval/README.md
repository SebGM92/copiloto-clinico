# Evaluación

## Set dorado (`golden.jsonl`)

50 preguntas, una por línea: 40 con respuesta en las guías (20 de DM2 y 20 de Depresión) y 10 sin ella.

```json
{"id": "dm2-09", "question": "¿Cómo se ajusta la dosis de metformina en enfermedad renal crónica?",
 "doc": "ges-dm2-2017", "pages": [15], "must_contain": ["mitad", "45"], "answerable": true,
 "answer": "Reducir a la mitad en ERC etapa 3b-5 (VFG <45 ml/min)"}
{"id": "fuera-03", "question": "¿Qué dosis de litio se usa para potenciar un antidepresivo en una depresión refractaria?",
 "answerable": false, "trap": true}
```

- `pages`: páginas físicas del PDF donde está la respuesta. Incluye la tabla resumen de recomendaciones de cada guía cuando también la contiene (DM2 p6; Depresión p11-12).
- `must_contain`: datos que no pueden faltar en una respuesta verificada (números, fármacos).
- `answer`: la respuesta esperada, para revisión humana.
- `trap`: en las preguntas sin respuesta, `true` si comparte palabras con el corpus (5 de 10). Por ejemplo, la guía recomienda potenciar con litio, pero no da su dosis; y la guía de DM2 excluye explícitamente la diabetes gestacional.

**Estado: borrador redactado por Claude leyendo las guías, pendiente de revisión clínica.** Se comprobó de forma automática que cada `must_contain` aparece en el texto de las páginas indicadas, y que los términos clave de las trampas no tienen respuesta en el corpus. Falta que un médico o estudiante de medicina revise al menos 10 casos.

`golden_ficticia.jsonl` tiene 5 casos sobre la guía ficticia del servidor de demostración (`python -m tests.demo_server`), para probar el evaluador sin gastar tokens.

## Otros archivos

- `questions.json` y `retrieval_modes.py`: comparación de búsqueda semántica, léxica e híbrida (Fase 4).
