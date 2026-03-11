# Smart Doc-to-Markdown Extractor

Pipeline OpenWebUI pour transformer une URL de documentation en document Markdown structuré.

## Installation

1. Installer les dépendances :
```bash
pip install -r requirements.txt
```

2. Copier le fichier `doc_extractor.py` dans le dossier des pipelines OpenWebUI :
   - Chemin typique : `open-webui/src/openwebui/pipelines/valves/` ou via l'interface dans "Pipelines > Add Pipeline"

## Utilisation

### Extraction simple (une page)

1. Dans OpenWebUI, sélectionner le modèle "Doc Extractor"
2. Coller une URL de documentation :
   ```
   https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.notion/
   ```
3. Recevoir le document Markdown structuré

### Crawl complet (site entier)

Pour scraper tout un site de documentation, utiliser le préfixe `crawl:` :

```
crawl: https://docs.example.com/
```

### Configuration inline

Vous pouvez configurer le crawl directement dans le message :

```
crawl: https://docs.example.com/ max:50 delay:1.0 exclude:/blog/ include:/docs/ depth:2
```

| Paramètre | Description | Exemple |
|-----------|-------------|---------|
| `max:N` | Nombre max de pages | `max:100` |
| `delay:N` | Délai entre requêtes (secondes) | `delay:2` |
| `exclude:PATTERN` | Exclure URLs correspondant au pattern | `exclude:/blog/` |
| `include:PATTERN` | Inclure seulement ces URLs | `include:/docs/` |
| `depth:N` | Profondeur max du crawl | `depth:3` |

### Aide de configuration

Tapez `config?` pour voir les options de configuration interactives.

## Fonctionnalités

- ✅ Extraction URL unique → Markdown
- ✅ Arborescence H1-H4 (sommaire)
- ✅ Métadonnées (Title, Source, Date)
- ✅ Nettoyage des `#` de fin
- ✅ **Crawl de site complet**
- ✅ **Tree view ASCII** (vue arborescente)
- ✅ **Filtrage par patterns** (regex)
- ✅ **Rate limiting** (évite le ban)
- ✅ **Export ZIP** avec structure
- ✅ **SUMMARY.md** généré automatiquement
- ✅ **Métadonnées JSON** pour suivi
- ✅ **Support des redirections** (308, 301, etc.)
- ✅ **Historique versionné** (optionnel)

## Configuration (Valves)

| Paramètre | Description | Défaut |
|-----------|-------------|--------|
| `REQUEST_TIMEOUT` | Timeout en secondes | 10 |
| `USER_AGENT` | User-Agent pour les requêtes | DocExtractor/1.0 |
| `CRAWL_ENABLED` | Activer le crawl par défaut | false |
| `MAX_PAGES` | Nombre max de pages à crawler | 50 |
| `DELAY_SECONDS` | Délai entre requêtes | 1.0 |
| `INCLUDE_PATTERN` | Regex pour inclure des URLs | (vide) |
| `EXCLUDE_PATTERN` | Regex pour exclure des URLs | (vide) |

### Exemples de patterns

- `INCLUDE_PATTERN`: `/docs/|/api/` - ne crawler que /docs/ et /api/
- `EXCLUDE_PATTERN`: `/blog/|/changelog/` - exclure /blog/ et /changelog/

## Format de Sortie

### Page unique

```markdown
---
**Title**: [Titre de la page]
**Source**: [URL]
**Extracted**: [Date]

## 📑 Sommaire / Arborescence
- Titre H1
  - Titre H2
    - Titre H3

## 📄 Contenu
[Contenu extrait en Markdown]
```

### Crawl complet

```markdown
---
**Site**: https://docs.example.com
**Pages**: 42
**Crawled**: 2024-01-15

## 📑 Pages Crawled
1. [Getting Started](https://docs.example.com/getting-started)
2. [API Reference](https://docs.example.com/api/reference)
...

## 📦 Export
To download all pages as Markdown files, use the Files API.
```

## Dépannage

- **Timeout** : Augmenter `REQUEST_TIMEOUT` dans les Valves
- **Contenu vide** : Le site peut utiliser du JavaScript côté client (non supporté)
- **Erreur 403** : Le site bloque le scraping - essayer un autre user-agent
- **Trop de pages** : Réduire `MAX_PAGES` ou ajouter `EXCLUDE_PATTERN`

