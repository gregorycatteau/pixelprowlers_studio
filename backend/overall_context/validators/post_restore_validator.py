import json
from pathlib import Path


def validate_json_structure(data: dict, required_fields: list) -> tuple:
    """
    Vérifie la présence des champs obligatoires dans un JSON donné.
    """
    messages = []
    missing = [field for field in required_fields if field not in data]

    if missing:
        messages.append(f"❌ Champs manquants dans le fichier : {', '.join(missing)}")
        return False, messages

    messages.append("✅ Tous les champs obligatoires sont présents.")
    return True, messages


def validate_against_schema(data: dict, schema: dict) -> tuple:
    """
    Valide la structure du JSON contre le schéma défini (champs requis + types).
    """
    messages = []
    required = schema.get("required_fields", [])
    optional = schema.get("optional_fields", [])
    expected_keys = set(required + optional)
    actual_keys = set(data.keys())

    missing = set(required) - actual_keys
    extra = actual_keys - expected_keys

    if missing:
        messages.append(f"⚠️ Clés manquantes vs schéma : {', '.join(missing)}")
    if extra:
        messages.append(f"⚠️ Clés supplémentaires vs schéma : {', '.join(extra)}")
    if not missing:
        messages.append("✅ Conformité au schéma validée.")

    return len(missing) == 0, messages


def load_schema(schema_path: Path) -> dict:
    try:
        with open(schema_path, "r") as f:
            return json.load(f)
    except Exception as e:
        return {}


def validate_file(filepath: Path, schema_path: Path) -> tuple:
    """
    Valide un fichier JSON restauré selon un schéma défini.
    """
    messages = []
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"❌ JSON invalide : {e}"]

    schema = load_schema(schema_path)
    if not schema:
        return False, ["❌ Impossible de charger le schéma."]

    is_structurally_valid, struct_msgs = validate_json_structure(
        data, schema.get("required_fields", [])
    )
    is_schema_valid, schema_msgs = validate_against_schema(data, schema)

    messages.extend(struct_msgs + schema_msgs)
    return is_structurally_valid and is_schema_valid, messages
