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

- **Flujogramas:** las guías suelen incluir flujogramas como imágenes; el parser solo extrae texto y tablas, así que su contenido se pierde. Normalmente esa información también aparece en el texto de la guía.
