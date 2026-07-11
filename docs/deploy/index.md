# Deploy — Déploiement en production

Le module `deploy` permet de déployer des plugins, extensions (services), fichiers de configuration (.env, certificats…) et le fichier `integration.yaml` vers des serveurs distants via SSH/SFTP. Il supporte les sources **locales** et les **repos GitHub** (publics et privés), avec un système de hooks pre/post.

## Quickstart

```bash
# 1. Scan automatique du projet (détecte plugins, extensions, integration.yaml)
xcli deploy generate

# 2. Éditer xcore-deploy.yaml (targets, tweaks)

# 3. Simuler sans rien envoyer
xcli deploy run production --dry-run

# 4. Déployer
xcli deploy run production
```

---

## Structure complète de `xcore-deploy.yaml`

```yaml
version: "1"

# ── Serveurs ─────────────────────────────────────────────────────────────────
targets:
  production:
    host: prod.monapp.com
    port: 22
    user: deploy
    ssh_key: ~/.ssh/id_ed25519
    xcore_url: https://api.monapp.com
    xcore_token: "${XCORE_ADMIN_TOKEN}"
    plugins_root: /opt/xcore/app/plugins
    extensions_root: /opt/xcore/app/extensions

  staging:
    host: staging.monapp.com
    user: deploy
    ssh_key: ~/.ssh/id_ed25519
    xcore_url: https://staging.monapp.com
    xcore_token: "${XCORE_STAGING_TOKEN}"
    plugins_root: /opt/xcore/app/plugins

# ── Hooks globaux ─────────────────────────────────────────────────────────────
hooks:
  pre_deploy:
    - cmd: "uv run xcli plugin security validate --save"
    - cmd: "uv run pytest tests/ -x -q"
      ignore_errors: false

  post_deploy:
    - cmd: "uv run xcli deploy status production"
      ignore_errors: true

# ── Config XCore (integration.yaml) ──────────────────────────────────────────
integration:
  source: ./integration.yaml
  remote_path: /opt/xcore/integration.yaml
  restart_xcore: true

# ── Fichiers (config, .env, certificats) ──────────────────────────────────────
# Copiés vers le serveur avant les extensions et plugins.
files:
  - source: ./.env
    dest: /opt/xcore/.env
    # only: [production]

  - source: ./conf/private.pem
    dest: /opt/xcore/conf/private.pem
    only: [production]

  - source: ./conf/public.pem
    dest: /opt/xcore/conf/public.pem

# ── Extensions (services) ─────────────────────────────────────────────────────
extensions:
  - name: mail
    source: ./extensions/mail
    restart: true
    only: [production]

  - name: pubsub
    repo: https://github.com/org/xcore-pubsub
    ref: v1.0.0
    restart: true

# ── Plugins ───────────────────────────────────────────────────────────────────
plugins:
  - name: auth
    source: ./app/auth
    sign: true
    reload: true

  - name: billing
    repo: https://github.com/org/billing-plugin
    ref: main
    sign: true
    reload: true

  - name: pdf-generator
    source: ./app/pdf-generator
    reload: true
    only: [production]
    hooks:
      pre_deploy:
        - cmd: "uv run xcli plugin security validate ./app/pdf-generator"
      post_deploy:
        - cmd: "echo 'pdf-generator déployé'"
          ignore_errors: true
```

---

## Section `files:` — Copie de fichiers

Les fichiers déclarés dans `files:` sont copiés vers le serveur **avant** les extensions et plugins. Utile pour `.env`, certificats, fichiers de config, etc.

```yaml
files:
  - source: ./.env
    dest: /opt/xcore/.env
  - source: ./conf/private.pem
    dest: /opt/xcore/conf/private.pem
    only: [production]
  - source: ./config/prod.yaml
    dest: /opt/xcore/config/prod.yaml
```

| Champ | Description |
|---|---|
| `source` | Chemin local du fichier (relatif à la racine du projet) |
| `dest` | Chemin distant de destination |
| `only` | (optionnel) Restreindre à certains targets |

---

## Sources : local vs GitHub

Chaque plugin et extension accepte soit `source:` (chemin local), soit `repo:` (dépôt Git).

### Source locale

```yaml
plugins:
  - name: mon-plugin
    source: ./app/mon-plugin
```

### GitHub — repo public

```yaml
plugins:
  - name: mon-plugin
    repo: https://github.com/org/mon-plugin
    ref: v2.1.0
```

### GitHub — repo privé via token

```yaml
plugins:
  - name: mon-plugin
    repo: https://github.com/org/mon-plugin-prive
    ref: main
    token: "${GITHUB_TOKEN}"
```

### GitHub — repo privé via SSH

```yaml
plugins:
  - name: mon-plugin
    repo: git@github.com:org/mon-plugin-prive.git
    ref: main
    # utilise ssh_key du target
```

### Plugin dans un sous-dossier du repo

```yaml
plugins:
  - name: mon-plugin
    repo: https://github.com/org/monorepo
    ref: main
    subdirectory: packages/mon-plugin
```

!!! note "Clone automatique"
    xcli fait un `git clone --depth 1 --branch <ref>` dans un dossier temporaire, puis emballe et transfère le code. Le clone est supprimé après le déploiement.

---

## Variables d'environnement

Les valeurs `${VAR}` ou `{VAR}` dans le YAML sont interpolées depuis l'environnement système.

```bash
export XCORE_ADMIN_TOKEN="mon-token-secret"
export XCORE_STAGING_TOKEN="staging-token"
export GITHUB_TOKEN="ghp_..."
export PROD_HOST="prod.monapp.com"
```

---

## Ordre d'exécution complet

```
hooks.pre_deploy (global)
│
├─ integration.yaml (si défini)
│   → sftp integration.yaml
│   → POST /config/reload  (ou restart service)
│
├─ Fichiers (section files:)
│   → sftp chaque fichier
│
├─ Pour chaque extension :
│   extension.hooks.pre_deploy
│   → archive tar.gz
│   → sftp + extraction
│   → POST /services/{name}/restart
│   extension.hooks.post_deploy
│
├─ Pour chaque plugin :
│   plugin.hooks.pre_deploy
│   → signature HMAC       (si sign: true)
│   → archive tar.gz
│   → sftp + extraction
│   → POST /plugins/{name}/reload
│   plugin.hooks.post_deploy
│
hooks.post_deploy (global)
└─ Rapport tableau final
```

---

## Hooks

### Niveau global

Définis sous `hooks:` à la racine.

| Moment | Quand |
|---|---|
| `hooks.pre_deploy` | Avant integration.yaml, fichiers, extensions et plugins |
| `hooks.post_deploy` | Après tous les plugins |

### Niveau plugin / extension

Définis sous `plugins[].hooks` ou `extensions[].hooks`.

| Moment | Quand |
|---|---|
| `pre_deploy` | Avant l'archivage |
| `post_deploy` | Après le hot-reload / restart |

### Options d'un hook

```yaml
hooks:
  pre_deploy:
    - cmd: "ma-commande --option valeur"
      cwd: "./sous-dossier"     # répertoire d'exécution (défaut : racine projet)
      ignore_errors: true       # continue même si exit code != 0 (défaut : false)
```

!!! warning "Hooks bloquants"
    Par défaut (`ignore_errors: false`), un hook qui échoue **annule le déploiement**. Utilise `ignore_errors: true` pour les commandes non-critiques (notifications, rapports...).

---

## Commandes

### `xcli deploy generate`

Scanne le projet et génère `xcore-deploy.yaml` automatiquement.

Détecte les plugins (dossiers avec `plugin.yaml`), les extensions (`__init__.py`) et `integration.yaml`. Si le fichier existe déjà, les **targets et hooks sont conservés**.

```bash
xcli deploy generate
xcli deploy generate --output deploy/prod.yaml
xcli deploy generate --plugins-dir ./custom-plugins --dry-run
```

| Option | Description |
|---|---|
| `--output`, `-o` | Fichier de sortie (défaut: `xcore-deploy.yaml`) |
| `--plugins-dir`, `-p` | Répertoire des plugins (défaut: `./app`) |
| `--extensions-dir`, `-e` | Répertoire des extensions (défaut: `./extensions`) |
| `--dry-run` | Affiche le résultat sans écrire le fichier |

---

### `xcli deploy init`

Génère un fichier `xcore-deploy.yaml` d'exemple complet.

```bash
xcli deploy init
xcli deploy init --output deploy/prod.yaml
```

---

### `xcli deploy list`

Liste les targets, plugins, extensions, fichiers et hooks déclarés.

```bash
xcli deploy list
xcli deploy list --file deploy/prod.yaml
```

---

### `xcli deploy run <target>`

Déploie l'intégralité (integration.yaml + fichiers + extensions + plugins) vers un target.

```bash
xcli deploy run production
xcli deploy run staging
```

**Options :**

| Option | Description |
|---|---|
| `--plugin <nom>` | Déploie **uniquement** ce plugin (skip extensions, fichiers et integration) |
| `--dry-run` | Simule sans envoyer ni exécuter de commandes réelles |
| `--no-reload` | Transfère les fichiers sans déclencher reload/restart |
| `--file <chemin>` | Fichier de configuration alternatif |

```bash
# Déployer un seul plugin (skip extensions + fichiers + integration)
xcli deploy run production --plugin auth

# Simuler le déploiement complet
xcli deploy run production --dry-run

# Transférer sans redémarrer
xcli deploy run production --no-reload

# Fichier alternatif
xcli deploy run production --file deploy/prod.yaml
```

---

### `xcli deploy copy <target> <source> <dest>`

Copie un fichier vers un serveur distant via SFTP (sans passer par le déploiement complet).

```bash
xcli deploy copy production .env /opt/xcore/.env
xcli deploy copy staging config.yaml /opt/xcore/config.yaml --dry-run
xcli deploy copy production docker-compose.yml /opt/xcore/ --file deploy/prod.yaml
```

---

### `xcli deploy status <target>`

Affiche l'état des plugins sur le serveur via l'API XCore.

```bash
xcli deploy status production
xcli deploy status staging --file deploy/prod.yaml
```

---

## Dépendances requises

```bash
pip install paramiko   # SSH/SFTP
pip install httpx      # Appels API XCore (reload/restart)
# git doit être disponible dans le PATH pour les sources repo
```

---

## Exemples de hooks courants

```yaml
hooks:
  pre_deploy:
    - cmd: "uv run xcli plugin security validate --save"
    - cmd: "uv run xcli plugin security validate --check-breaking"
    - cmd: "uv run pytest tests/ -x -q"
      ignore_errors: false

  post_deploy:
    - cmd: "uv run xcli deploy status production"
    - cmd: >
        curl -s -X POST https://hooks.slack.com/services/XXX
        -H 'Content-type: application/json'
        -d '{"text": "✅ Déploiement production terminé"}'
      ignore_errors: true
```
