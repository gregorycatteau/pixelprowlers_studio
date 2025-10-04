import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def extract_chunks_from_zone(zone_path: Path) -> List[Dict]:
    zone = json.loads(zone_path.read_text(encoding="utf-8"))
    content = zone.get("content", {})
    tags = zone.get("tags", [])
    visibility = zone.get("visibility", "internal")

    chunks = []

    # Manifesto
    for idx, principle in enumerate(content.get("manifesto", {}).get("principles", [])):
        chunks.append(
            {
                "chunk_id": f"{zone['zone_id']}__manifesto__{idx}",
                "zone_id": zone["zone_id"],
                "section": "manifesto",
                "title": principle["title"],
                "text": f"{principle['title']}\n{principle['description']}",
                "tags": tags,
                "visibility": visibility,
            }
        )

    # Long Term Vision
    if "long_term_vision" in content:
        ltv = content["long_term_vision"]
        text = f"Vision long terme : {ltv.get('summary','')}"
        if "targets" in ltv:
            for key, val in ltv["targets"].items():
                text += f"\nObjectif [{key}] : {val}"
        chunks.append(
            {
                "chunk_id": f"{zone['zone_id']}__long_term_vision",
                "zone_id": zone["zone_id"],
                "section": "long_term_vision",
                "title": "Vision à long terme",
                "text": text,
                "tags": tags,
                "visibility": visibility,
            }
        )

    # Ethical Guidelines
    if "ethical_guidelines" in content:
        ethics = content["ethical_guidelines"]
        text = "Principes éthiques fondamentaux :\n"
        for key, val in ethics.items():
            label = key.replace("_", " ").capitalize()
            text += f"- {label} : {'oui' if val else 'non'}\n"
        chunks.append(
            {
                "chunk_id": f"{zone['zone_id']}__ethical_guidelines",
                "zone_id": zone["zone_id"],
                "section": "ethical_guidelines",
                "title": "Principes éthiques",
                "text": text.strip(),
                "tags": tags,
                "visibility": visibility,
            }
        )

    return chunks


# Exemple d’usage
if __name__ == "__main__":
    zone_file = Path("cdn_zones/Z1.json")
    chunks = extract_chunks_from_zone(zone_file)
    output = Path("cdn_zones/Z1_chunks.json")
    output.write_text(json.dumps(chunks, indent=2, ensure_ascii=False))
    print(f"✅ {len(chunks)} chunks extraits et enregistrés dans {output}")
