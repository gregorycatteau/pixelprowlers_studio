# Spécification CDN PixelProwlers

## Schéma
- Version actuelle: `cdn_schema_v1.1.json`
- Voir `cdn_schema_changelog.json` pour l'historique

## Règles
- Toute zone (`Zx.json`) doit contenir `schema_version`, `access_policy`, `versioning_policy`, `metrics_template`
- Rétention: `retention_policy = contextual` avec `retention_rules` définies

## Processus (CI)
1. Création/édition d'une zone → PR Git
2. `validate_zone.py --strict` passe
3. `test_cdn_integrity.py` passe
4. Merge → `cdn_registry.json` mis à jour (manuel ou via job)
5. Backup auto chiffré lancé
