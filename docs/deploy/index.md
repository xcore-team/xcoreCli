# Deploy — Déploiement en production

Le module `deploy` permet de déployer des plugins, extensions (services) et la configuration `integration.yaml` vers des serveurs distants via SSH/SFTP. Il supporte les sources **locales** et les **repos GitHub** (publics et privés), avec un système de hooks pre/post.

## Quickstart

```bash
# 1. Générer le fichier de configuration
xcli deploy init

# 2. Éditer xcore-deploy.yaml (targets, plugins, extensions, integration)

# 3. Simuler sans rien envoyer
xcli deploy production --dry-run

# 4. Déployer
xcli deploy production
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
    extensions_root: /opt/xcore/app/extensions  # défaut: ../extensions relatif à plugins_root

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
      cwd: "."
      ignore_errors: false

  post_deploy:
    - cmd: "uv run xcli deploy status production"
      ignore_errors: true

# ── Config XCore (integration.yaml) ──────────────────────────────────────────
integration:
  source: ./integration.yaml        # chemin local
  remote_path: /opt/xcore/integration.yaml
  restart_xcore: true               # hot-reload via API, sinon restart service
  # only: [production]              # restreindre à certains targets

# ── Extensions (services) ─────────────────────────────────────────────────────
extensions:
  - name: mail
    source: ./extensions/mail       # source locale
    restart: true                   # POST /services/mail/restart après transfert
    only: [production]

  - name: pubsub
    repo: https://github.com/org/xcore-pubsub   # GitHub public
    ref: v1.0.0
    restart: true

# ── Plugins ───────────────────────────────────────────────────────────────────
plugins:
  - name: auth
    source: ./app/auth              # source locale
    sign: true
    reload: true

  - name: billing
    repo: https://github.com/org/billing-plugin  # GitHub public
    ref: main
    sign: true
    reload: true

  - name: pdf-generator
    source: ./app/pdf-generator
    sign: false
    reload: true
    only: [production]              # uniquement en production
    hooks:
      pre_deploy:
        - cmd: "uv run xcli plugin security validate ./app/pdf-generator"
      post_deploy:
        - cmd: "echo 'pdf-generator déployé'"
          ignore_errors: true
```

---

## Sources : local vs GitHub

Chaque plugin et extension accepte soit `source:` (chemin local), soit `repo:` (dépôt Git).

### Source locale

```yaml
plugins:
  - name: mon-plugin
    source: ./app/mon-plugin        # relatif à la racine du projet
```

### GitHub — repo public

```yaml
plugins:
  - name: mon-plugin
    repo: https://github.com/org/mon-plugin
    ref: v2.1.0                     # branche, tag ou commit
```

### GitHub — repo privé via token

```yaml
plugins:
  - name: mon-plugin
    repo: https://github.com/org/mon-plugin-prive
    ref: main
    token: "${GITHUB_TOKEN}"        # injecté depuis l'env
```

### GitHub — repo privé via SSH

```yaml
plugins:
  - name: mon-plugin
    repo: git@github.com:org/mon-plugin-prive.git
    ref: main
    # utilise automatiquement ssh_key du target
```

### Plugin dans un sous-dossier du repo

```yaml
plugins:
  - name: mon-plugin
    repo: https://github.com/org/monorepo
    ref: main
    subdirectory: packages/mon-plugin   # chemin relatif dans le repo
```

!!! note "Clone automatique"
    xcli fait un `git clone --depth 1 --branch <ref>` dans un dossier temporaire, puis emballe et transfère le code. Le clone est supprimé après le déploiement.

---

## Variables d'environnement

Les valeurs `${VAR}` dans le YAML sont interpolées depuis l'environnement système.

```bash
export XCORE_ADMIN_TOKEN="mon-token-secret"
export XCORE_STAGING_TOKEN="staging-token"
export GITHUB_TOKEN="ghp_..."          # pour les repos privés
export PROD_HOST="prod.monapp.com"
```

---

## Déploiement de `integration.yaml`

Si la section `integration:` est présente, xcli synchronise le fichier de configuration vers le serveur **avant** les extensions et les plugins.

```yaml
integration:
  source: ./integration.yaml
  remote_path: /opt/xcore/integration.yaml
  restart_xcore: true
```

**Séquence de rechargement :**

1. Transfert SFTP vers `remote_path`
2. Appel `POST /config/reload` (hot-reload sans coupure)
3. Si l'API échoue → fallback `systemctl restart xcore` (ou `supervisorctl`)

---

## Hooks — pre & post deploy

### Niveau global

Définis sous `hooks:` à la racine. Exécutés **une fois** pour tout le déploiement.

| Moment | Quand |
|---|---|
| `hooks.pre_deploy` | Avant integration.yaml, extensions et plugins |
| `hooks.post_deploy` | Après tous les plugins |

### Niveau plugin / extension

Définis sous `plugins[].hooks` ou `extensions[].hooks`.

| Moment | Quand |
|---|---|
| `pre_deploy` | Avant l'archivage |
| `post_deploy` | Après le hot-reload / restart |

### Ordre d'exécution complet

```
hooks.pre_deploy (global)
│
├─ integration.yaml (si défini)
│   → sftp integration.yaml
│   → POST /config/reload  (ou restart service)
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

### `xcli deploy init`

Génère un fichier `xcore-deploy.yaml` d'exemple.

```bash
xcli deploy init
xcli deploy init --output deploy/prod.yaml
```

---

### `xcli deploy list`

Liste les targets, plugins, extensions et hooks.

```bash
xcli deploy list
xcli deploy list --file deploy/prod.yaml
```

---

### `xcli deploy <target>`

Déploie l'intégralité (integration.yaml + extensions + plugins) vers un target.

```bash
xcli deploy production
xcli deploy staging
```

**Options :**

| Option | Description |
|---|---|
| `--plugin <nom>` | Déploie uniquement ce plugin (skip extensions + integration) |
| `--dry-run` | Simule sans envoyer ni exécuter de commandes réelles |
| `--no-reload` | Transfère les fichiers sans déclencher reload/restart |
| `--file <chemin>` | Fichier de configuration alternatif |

```bash
# Déployer un seul plugin
xcli deploy production --plugin billing

# Simuler le déploiement complet
xcli deploy production --dry-run

# Transférer sans redémarrer
xcli deploy production --no-reload

# Fichier alternatif
xcli deploy production --file deploy/prod.yaml
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
# git doit être disponible dans le PATH pour les sources repo:
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
