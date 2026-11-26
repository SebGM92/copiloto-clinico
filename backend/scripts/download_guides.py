"""Descarga las guías clínicas en PDF a backend/data/guides."""
from pathlib import Path

import httpx

GUIDES: dict[str, str] = {
    "dm2_minsal.pdf": "https://diprece.minsal.cl/wrdprss_minsal/wp-content/uploads/2018/01/DIABETES-MELLITUS-TIPO-2-1.pdf",
}

OUT = Path(__file__).resolve().parent.parent / "data" / "guides"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, url in GUIDES.items():
        dest = OUT / name
        if dest.exists():
            print(f"ya existe: {name}")
            continue
        r = httpx.get(url, follow_redirects=True, timeout=60)
        r.raise_for_status()
        dest.write_bytes(r.content)
        print(f"descargado: {name}")


if __name__ == "__main__":
    main()
