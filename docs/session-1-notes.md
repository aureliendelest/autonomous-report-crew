# Session 1 — Notes

## Ce qui a été construit
Pipeline CLI à 3 agents (Chercheur → Critique → Rédacteur) pour le domaine football,
avec boucle de retour plafonnée entre Critique et Chercheur.

## Décisions techniques
- **LLM** : Groq (`openai/gpt-oss-120b`), API compatible OpenAI, function calling
  classique (contrairement à l'outil serveur natif d'Anthropic, c'est notre code qui
  exécute l'appel de recherche et renvoie le résultat au modèle).
- **Recherche web** : Tavily (`topic="news"`, `time_range="month"` pour privilégier
  des résultats récents).
- **Limite de tokens** : l'offre gratuite Groq plafonne à 8000 tokens/minute. Le
  `max_tokens` par appel a été réduit (800) et le contenu Tavily tronqué pour rester
  sous cette limite.
- **Date du jour** injectée dans les messages envoyés aux agents (Chercheur et
  Critique), sans quoi le Critique ne peut pas juger si une information est périmée.
- **Boucle de recherche plafonnée** (`MAX_RESEARCH_LOOPS = 2`) pour éviter qu'un bug
  dans la détection du marqueur `STATUT: OK` ne consomme tout le quota Tavily.

## Limites connues
- La qualité des sources dépend entièrement de ce que Tavily retourne : le Critique
  peut détecter une info manquante ou périmée, mais ne peut pas vérifier l'exactitude
  factuelle d'une source qu'il juge correcte.
- Modèle `openai/gpt-oss-120b` : à surveiller si Groq fait évoluer son catalogue de
  modèles (l'ancien choix `llama-3.3-70b-versatile` n'était déjà plus disponible).
