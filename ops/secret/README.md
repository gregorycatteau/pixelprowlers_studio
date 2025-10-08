# Secrets Management — sops/age

**PixelProwlers Studio** — Sprint 0

Ce dossier contient la configuration et les conventions pour la gestion sécurisée des secrets via **sops** (Secrets OPerationS) et **age** (encryption tool).

## 📋 Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Installation](#installation)
- [Configuration initiale](#configuration-initiale)
- [Utilisation](#utilisation)
- [Conventions du projet](#conventions-du-projet)
- [Exemples](#exemples)
- [Sécurité & Bonnes pratiques](#sécurité--bonnes-pratiques)
- [Troubleshooting](#troubleshooting)

---

## Vue d'ensemble

### Pourquoi sops/age ?

- **sops** : outil de chiffrement de fichiers qui préserve la structure (YAML/JSON/ENV)
- **age** : algorithme de chiffrement moderne, simple et sécurisé
- **Deny-by-default** : aucun secret ne doit être committé en clair dans Git

### Architecture

```
ops/secret/
├── README.md              (ce fichier)
├── .gitignore             (protège les clés et fichiers décryptés)
├── .sops.yaml             (configuration sops pour le projet)
├── keys/                  (clés age — JAMAIS commité)
│   └── .gitkeep
├── dev/                   (secrets dev/local chiffrés)
│   └── app.env.enc
├── staging/               (secrets staging chiffrés)
│   └── app.env.enc
└── prod/                  (secrets production chiffrés)
    └── app.env.enc
```

---

## Installation

### macOS (Homebrew)

```bash
brew install sops age
```

### Linux (binaires)

```bash
# age
curl -LO https://github.com/FiloSottile/age/releases/latest/download/age-v1.1.1-linux-amd64.tar.gz
tar xzf age-v1.1.1-linux-amd64.tar.gz
sudo mv age/age age/age-keygen /usr/local/bin/

# sops
curl -LO https://github.com/getsops/sops/releases/latest/download/sops-v3.8.1.linux.amd64
sudo mv sops-v3.8.1.linux.amd64 /usr/local/bin/sops
sudo chmod +x /usr/local/bin/sops
```

### Vérification

```bash
age --version
sops --version
```

---

## Configuration initiale

### 1. Générer votre clé age locale

**⚠️ À faire une seule fois par développeur/machine**

```bash
# Créer le dossier keys si nécessaire
mkdir -p ops/secret/keys

# Générer une paire de clés age
age-keygen -o ops/secret/keys/local.key

# Afficher la clé publique (à partager avec l'équipe si nécessaire)
grep 'public key:' ops/secret/keys/local.key
```

**Sortie attendue :**

```
Public key: age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 2. Protéger votre clé privée

```bash
chmod 600 ops/secret/keys/local.key
```

**🚨 JAMAIS commiter `ops/secret/keys/` dans Git !**

### 3. Configurer sops

Créez `.sops.yaml` à la racine du projet (déjà fait si existant) :

```yaml
creation_rules:
  # Dev/local — votre clé publique locale
  - path_regex: ops/secret/dev/.*\.enc$
    age: age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  # VOTRE clé publique

  # Staging — clé publique staging (à définir plus tard)
  - path_regex: ops/secret/staging/.*\.enc$
    age: age1yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy

  # Production — clé publique production (à définir plus tard)
  - path_regex: ops/secret/prod/.*\.enc$
    age: age1zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz
```

**📝 Remplacez les clés publiques par les vôtres.**

---

## Utilisation

### Chiffrer un fichier

```bash
# Créer un fichier secret en clair (temporaire)
cat > ops/secret/dev/app.env <<EOF
DATABASE_URL=postgresql://user:pass@localhost/db
SECRET_KEY=super-secret-key-change-me
API_TOKEN=token_abc123xyz
EOF

# Chiffrer avec sops
sops --encrypt ops/secret/dev/app.env > ops/secret/dev/app.env.enc

# Supprimer l'original en clair
rm ops/secret/dev/app.env

# Commit du fichier chiffré (safe)
git add ops/secret/dev/app.env.enc
git commit -m "chore(secrets): add dev app secrets"
```

### Déchiffrer un fichier

```bash
# Déchiffrer dans stdout
sops --decrypt ops/secret/dev/app.env.enc

# Déchiffrer dans un fichier
sops --decrypt ops/secret/dev/app.env.enc > .env

# Éditer en place (déchiffre → éditeur → rechiffre)
sops ops/secret/dev/app.env.enc
```

### Éditer un secret existant

```bash
# sops déchiffre automatiquement, ouvre votre éditeur, puis rechiffre
export EDITOR=vim  # ou nano, code, etc.
sops ops/secret/dev/app.env.enc
```

### Intégrer dans un script

```bash
#!/bin/bash
# Charger les secrets dans l'environnement
export $(sops --decrypt ops/secret/dev/app.env.enc | xargs)

# Utiliser les variables
echo "Database: $DATABASE_URL"
```

---

## Conventions du projet

### Nommage des fichiers

| Type             | Nom de fichier          | Exemple                          |
|------------------|-------------------------|----------------------------------|
| Env vars         | `<app>.env.enc`         | `app.env.enc`, `backend.env.enc` |
| JSON config      | `<service>.json.enc`    | `n8n-creds.json.enc`             |
| YAML config      | `<service>.yaml.enc`    | `caddy-tls.yaml.enc`             |
| Clés SSH/API     | `<name>.key.enc`        | `deploy.key.enc`                 |

### Règles strictes

✅ **DOIT (SHALL)**

- Tous les secrets **doivent** être chiffrés avec sops/age avant commit
- Les clés privées **doivent** rester sur la machine locale (jamais Git)
- Les clés publiques **peuvent** être partagées/committées
- Utiliser `.enc` comme suffixe pour les fichiers chiffrés

❌ **NE DOIT PAS**

- Jamais committer un fichier `.env`, `.key`, `*.pem` en clair
- Jamais partager une clé privée age par email/Slack/etc.
- Jamais logger les secrets décryptés (stdout OK pour usage immédiat)

### Rotation des secrets

1. Générer un nouveau secret
2. Chiffrer avec sops
3. Déployer la nouvelle version
4. Révoquer l'ancien secret
5. Supprimer l'ancien du fichier chiffré

---

## Exemples

### Exemple 1 : Secrets Django dev

```bash
# Créer le fichier
cat > /tmp/backend.env <<EOF
DJANGO_SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
DATABASE_URL=postgresql://pxp_app_user:pxp_app_pass@localhost:5432/pxp_app
ALLOWED_HOSTS=localhost,127.0.0.1,api.dev.localhost
CSRF_TRUSTED_ORIGINS=http://dev.localhost,http://api.dev.localhost
EOF

# Chiffrer
sops --encrypt /tmp/backend.env > ops/secret/dev/backend.env.enc

# Nettoyer
rm /tmp/backend.env

# Utiliser
sops --decrypt ops/secret/dev/backend.env.enc > backend/.env
```

### Exemple 2 : Credentials JSON (n8n, API keys)

```bash
# Créer le fichier JSON
cat > /tmp/n8n-creds.json <<EOF
{
  "smtp": {
    "host": "smtp.example.com",
    "user": "noreply@pixelprowlers.io",
    "password": "smtp_secret_password"
  },
  "nats": {
    "url": "nats://localhost:4222",
    "user": "dojo_user",
    "password": "dojo_pass"
  }
}
EOF

# Chiffrer
sops --encrypt /tmp/n8n-creds.json > ops/secret/dev/n8n-creds.json.enc

# Nettoyer
rm /tmp/n8n-creds.json

# Déchiffrer et utiliser dans n8n
sops --decrypt ops/secret/dev/n8n-creds.json.enc | jq .
```

### Exemple 3 : Clé SSH de déploiement

```bash
# Générer une clé SSH dédiée
ssh-keygen -t ed25519 -f /tmp/deploy_key -C "deploy@pixelprowlers.io" -N ""

# Chiffrer la clé privée
sops --encrypt /tmp/deploy_key > ops/secret/prod/deploy.key.enc

# La clé publique peut être committée en clair (si nécessaire)
cp /tmp/deploy_key.pub ops/secret/prod/deploy.key.pub

# Nettoyer
rm /tmp/deploy_key /tmp/deploy_key.pub

# Utiliser en CI/CD
sops --decrypt ops/secret/prod/deploy.key.enc > /tmp/deploy_key
chmod 600 /tmp/deploy_key
ssh -i /tmp/deploy_key user@server "deploy command"
rm /tmp/deploy_key
```

---

## Sécurité & Bonnes pratiques

### 🔐 Stockage des clés privées

| Environnement | Où stocker la clé privée age                          |
|---------------|-------------------------------------------------------|
| **Dev local** | `ops/secret/keys/local.key` (gitignored)              |
| **CI/CD**     | GitHub Secrets, GitLab CI Variables, etc.             |
| **Prod VPS**  | `/etc/secrets/age.key` (chmod 600, root only)         |

### 🛡️ Défense en profondeur

1. **Chiffrement au repos** : sops/age
2. **Chiffrement en transit** : TLS/mTLS (Caddy, NATS)
3. **Chiffrement en mémoire** : à venir (Vault HSM pour secrets ultra-sensibles)
4. **Rotation régulière** : tous les 90 jours minimum
5. **Audit logs** : logger les accès aux secrets (prod)

### 🚨 Incident : clé privée exposée

**Si une clé privée age est compromise :**

1. **Révoquer immédiatement** : ne peut pas être "révoquée" directement avec age
2. **Rotation** : générer une nouvelle paire de clés
3. **Rechiffrer tous les secrets** avec la nouvelle clé publique :

```bash
# Déchiffrer avec l'ancienne clé
sops --decrypt --age <OLD_KEY> ops/secret/prod/app.env.enc > /tmp/app.env

# Rechiffrer avec la nouvelle clé
sops --encrypt --age <NEW_PUBLIC_KEY> /tmp/app.env > ops/secret/prod/app.env.enc

# Nettoyer
shred -u /tmp/app.env
```

4. **Post-mortem** : documenter l'incident, améliorer les process

---

## Troubleshooting

### Erreur : `no age identity found`

**Cause** : sops ne trouve pas votre clé privée age.

**Solution** :

```bash
# Définir la variable d'environnement SOPS_AGE_KEY_FILE
export SOPS_AGE_KEY_FILE=ops/secret/keys/local.key

# Ou directement :
sops --age $(cat ops/secret/keys/local.key | grep 'AGE-SECRET-KEY') --decrypt file.enc
```

### Erreur : `failed to decrypt`

**Cause** : votre clé publique n'est pas dans `.sops.yaml` ou mauvaise clé.

**Solution** :

1. Vérifier `.sops.yaml` contient votre clé publique
2. Vérifier le chemin du fichier match le `path_regex`
3. Demander à un collègue de rechiffrer avec votre clé publique

### Erreur : `MAC verification failed`

**Cause** : fichier corrompu ou modifié manuellement.

**Solution** : restaurer depuis Git ou redemander le fichier original.

### Partager un secret avec un nouveau membre

1. Récupérer sa **clé publique age** (ex : `age1abc...`)
2. Ajouter sa clé à `.sops.yaml` :

```yaml
creation_rules:
  - path_regex: ops/secret/dev/.*\.enc$
    age: >-
      age1xxxxxxxxxx,  # Clé existante
      age1yyyyyyyyyy   # Nouvelle clé membre
```

3. Rechiffrer le fichier avec les 2 clés :

```bash
sops updatekeys ops/secret/dev/app.env.enc
```

4. Commit et push

---

## Ressources

- [sops GitHub](https://github.com/getsops/sops)
- [age GitHub](https://github.com/FiloSottile/age)
- [age Specification](https://age-encryption.org/)
- [SOPS with age Tutorial](https://github.com/getsops/sops#encrypting-using-age)

---

## Next Steps (après Sprint 0)

- [ ] Intégrer HashiCorp Vault pour secrets dynamiques (prod)
- [ ] Automatiser la rotation des secrets (Shali)
- [ ] Configurer alertes sur accès secrets (observabilité)
- [ ] mTLS pour NATS avec certificats chiffrés via sops

---

**Bon chiffrement et bonne chasse aux pixels 🐾🔐**

— PixelProwlers Studio, Sprint 0
