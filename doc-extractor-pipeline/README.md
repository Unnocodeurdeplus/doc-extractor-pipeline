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

Cela va :
- Découvrir toutes les pages liées
- Extraire chaque page en Markdown
- Générer une liste des pages trouvées

## Fonctionnalités

- ✅ Validation URL (HTTP/HTTPS)
- ✅ Extraction de la structure (H1-H4)
- ✅ Extraction du contenu principal (trafilatura)
- ✅ Conversion automatique en Markdown
- ✅ Métadonnées (titre, URL source, date)
- ✅ Gestion des erreurs (timeout, 404, etc.)
- ✅ Préservation des blocs de code
- ✅ Tableaux Markdown
- ✅ **Crawl de site complet**
- ✅ **Filtrage par patterns (include/exclude)**

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

