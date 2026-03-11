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

1. Dans OpenWebUI, sélectionner le modèle "Doc Extractor" (ou le pipeline ajouté)
2. Coller une URL de documentation :
   ```
   https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.notion/
   ```
3. Recevoir le document Markdown structuré

## Fonctionnalités

- ✅ Validation URL (HTTP/HTTPS)
- ✅ Extraction de la structure (H1-H4)
- ✅ Extraction du contenu principal (trafilatura)
- ✅ Conversion automatique en Markdown
- ✅ Métadonnées (titre, URL source, date)
- ✅ Gestion des erreurs (timeout, 404, etc.)
- ✅ Préservation des blocs de code
- ✅ Tableaux Markdown

## Format de Sortie

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

## Dépannage

- **Timeout** : Augmenter `REQUEST_TIMEOUT` dans les Valves
- **Contenu vide** : Le site peut utiliser du JavaScript côté client (non supporté)
- **Erreur 403** : Le site bloque le scraping - try utiliser un autre user-agent
