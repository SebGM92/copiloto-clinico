# Evaluación

## Set dorado (`golden.jsonl`)

51 preguntas, una por línea: 41 con respuesta en las guías (20 de DM2 y 21 de Depresión) y 10 sin ella.

```json
{"id": "dm2-09", "question": "¿Cómo se ajusta la dosis de metformina en enfermedad renal crónica?",
 "doc": "ges-dm2-2017", "pages": [15], "must_contain": ["mitad", "45"], "answerable": true,
 "answer": "Reducir a la mitad en ERC etapa 3b-5 (VFG <45 ml/min)"}
{"id": "fuera-03", "question": "¿Se recomienda aspirina para prevenir eventos cardiovasculares en personas con DM2?",
 "answerable": false, "trap": true}
```

- `pages`: páginas físicas del PDF donde está la respuesta. Incluye la tabla resumen de recomendaciones de cada guía cuando también la contiene (DM2 p6; Depresión p11-12).
- `must_contain`: datos que no pueden faltar en una respuesta verificada (números, fármacos).
- `answer`: la respuesta esperada, para revisión humana.
- `trap`: en las preguntas sin respuesta, `true` si comparte palabras con el corpus (5 de 10). Por ejemplo, la guía de DM2 excluye explícitamente la diabetes gestacional, y ninguna guía menciona la aspirina. `dep-21` (dosis de litio) era una trampa, pero la guía sí da el nivel plasmático: se corrigió tras la primera evaluación.

**Estado: borrador redactado por Claude leyendo las guías, pendiente de revisión clínica.** Se comprobó de forma automática que cada `must_contain` aparece en el texto de las páginas indicadas, y que los términos clave de las trampas no tienen respuesta en el corpus. Falta que un médico o estudiante de medicina revise al menos 10 casos.

`golden_ficticia.jsonl` tiene 5 casos sobre la guía ficticia del servidor de demostración (`python -m tests.demo_server`), para probar el evaluador sin gastar tokens.

## Evaluador (`run_eval.py`)

- `python -m eval.run_eval eval/golden.jsonl --mode retrieval`: gratis; `hit_rate`, `mrr` y las similitudes para calibrar `MIN_SIMILARITY`.
- `python -m eval.run_eval eval/golden.jsonl --mode full [--judge]`: el grafo completo con Claude; `--judge` agrega `faithfulness` con Claude Haiku 5.5.
- `--min-hit 0.85 --max-false-answer 0`: termina con código 1 si no cumple (control de CI).
- `--demo` con `eval/golden_ficticia.jsonl`: de punta a punta sin costo (Claude y juez simulados).
- Detalle por pregunta en `report.json`; copia con fecha en `results/`.

## Acuerdo del juez (`judge_agreement.py`)

1. `python -m eval.judge_agreement export eval/results/<corrida full --judge>.json --n 20` escribe `judge_labels.jsonl` con 20 pares afirmación-cita, **sin** el veredicto del juez: todos los que rechazó (hasta la mitad) y el resto al azar.
2. Etiquetar a mano cada par: `"human": true` si la cita respalda TODA la afirmación, incluidos números y unidades; `false` si no.
3. `python -m eval.judge_agreement score` mide el acuerdo y lista los desacuerdos.

## Otros archivos

- `questions.json` y `retrieval_modes.py`: comparación de búsqueda semántica, léxica e híbrida (Fase 4).
