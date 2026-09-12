# Projet : Autonomous Report Crew

## Contexte
Projet portfolio personnel : un système multi-agents (chercheur → critique → rédacteur)
qui automatise la production de rapports de veille sur un sujet donné.

Objectif : démontrer une compétence "agentique" (orchestration LLM, tool-calling,
boucle raisonnement/action) en complément d'un premier projet Kaggle (ML classique
sur données géospatiales).

## Architecture générale
Le système repose sur 3 agents qui collaborent en séquence :

1. **Agent Chercheur** : reçoit un sujet, effectue des recherches web ciblées,
   ramène des extraits de sources pertinentes.
2. **Agent Critique** : relit les résultats du chercheur, vérifie la cohérence
   et la fiabilité des sources, signale les contradictions ou informations
   manquantes, peut redemander une recherche complémentaire.
3. **Agent Rédacteur** : synthétise le tout dans un rapport final structuré
   (résumé, points clés, sources citées).

Le code de l'architecture (appels API, boucle des agents) est générique.
Ce qui différencie un "domaine" d'un autre, ce sont uniquement les prompts
système de chaque agent (voir `/prompts`).

## Domaines couverts

### Domaine de test : football
Fiche hebdomadaire sur un club de football (résultats, actualité, prochaine
échéance). Utilisé pour valider que le pipeline fonctionne sur un sujet où
la qualité du résultat est facile à juger soi-même.

### Domaine sérieux : adoption de l'IA en entreprise
Synthèse sectorielle sur l'adoption de l'IA générative en entreprise
(cas d'usage, ROI observé, freins). Domaine présentable en entretien,
avec du contenu de fond réutilisable.

## Roadmap (sessions de développement)

- **Session 1** : agent multi-étapes en ligne de commande, un seul domaine
  (football), sans interface.
- **Session 2** : ajout d'un front simple (Streamlit) avec sélection de
  domaine parmi une liste pré-configurée (football, IA en entreprise).
- **Session 3** (optionnelle) : création dynamique de nouveaux domaines
  depuis l'interface (génération automatique des prompts système).

## Stack technique
- Python 3.x
- API Anthropic (`anthropic` SDK, modèle Claude)
- Recherche web : [à préciser selon l'implémentation retenue en session 1]
- Interface (session 2+) : Streamlit
- Gestion des secrets : fichier `.env` (jamais commité), voir `.env.example`

## Structure du projet
/src → code source (agents, orchestration, appels API)
/prompts → prompts système par domaine et par agent
/docs → rapport de projet, notes de conception
/outputs → rapports générés par les agents (exemples de sortie)
.env.example → structure attendue du fichier .env (sans les vraies clés)
requirements.txt
README.md


## Conventions de travail avec Claude Code

- Toujours lire ce fichier en début de session pour retrouver le contexte.
- Commit après chaque fonctionnalité qui fonctionne (pas de gros commits fourre-tout).
- Messages de commit clairs et en anglais, format court
  (ex: "add the critical agent", "research loop corrected").
- Toujours vérifier `git status` avant de committer pour éviter d'inclure
  des fichiers indésirables (`.env`, fichiers temporaires).
- Push sur `main` uniquement quand une fonctionnalité est testée et fonctionnelle.
- Ne jamais committer de clé API ou de secret — toujours passer par `.env`.

## Niveau de l'utilisateur
Niveau de code plutôt débutant/intermédiaire. Privilégier des explications
claires à chaque étape, éviter les abstractions inutiles, et proposer des
solutions simples avant des solutions "élégantes" mais complexes.
Pas d'overengineering.