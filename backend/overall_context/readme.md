# overall_context (PixelProwlers)

App Django pour gouverner le CDN contextuel souverain (taxonomie, validation, migration, audit).

## Dossiers
- `data/` : schémas, changelog, registry, policy
- `validators/` : scripts de validation
- `backup/` : outils de backup/cryptage
- `utils/` : loaders et synchro DB
- `../cdn_zones/` : instances des blocs (Z1..Z10...)

## Scripts
- `validators/validate_zone.py` : valide un bloc contre le schéma
- `test_cdn_integrity.py` : audit global (zones ↔ schéma ↔ registre)
- `cdn_schema_migrator.py` : migration v1.0 → v1.1

## Sécurité
- Rétention contextuelle, contrôle d’accès granulaire
- Backups locaux chiffrés (cf. backup_encryptor.py)
- Zéro appel réseau dans les scripts
