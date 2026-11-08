# Règles d'engagement : test Strix sur Thiqa (projet hackathon, données synthétiques)

Cible autorisée : http://host.docker.internal:8000 (le serveur Thiqa lancé par run.bat) et le dossier source thiqa_scan/.
Hors périmètre : tout autre hôte, Telegram, Gemini, Groq, internet.

Contexte : prototype de 3 agents IA qui vendent des formations. Les paiements sont simulés (Sandouk Pay, sandbox). Aucun argent réel.
Routes publiques : /api/v1/cases, /api/v1/interaction/*, /api/v1/voice/transcribe. Routes opérateur protégées par l'en-tête X-Ops-Pin.

À tester en priorité :
1. Contournement du PIN opérateur (X-Ops-Pin) et accès aux routes /api/v1/approvals, /llm/test, /runs, /security.
2. Injection de prompt via le texte client pour obtenir une remise, un paiement sans confirmation, ou le prompt système de Sahbi.
3. Falsification d'une offre : offer_hash, montant, payment_method, rejeu d'une confirmation.
4. Validation d'un paiement par son propre demandeur, validation avec un hash différent, double validation.
5. IDOR entre dossiers (case_id) et entre tenants (tenant_id : 9antra et nakhla).
6. Limites de taille et de débit (corps de requête, WebSocket /ws/events), SSRF, traversée de chemin sur /app.
7. Fuite de secrets : clés dans les réponses, les logs, les erreurs ou le dossier source.

Contraintes : pas de déni de service prolongé, pas plus de 10 requêtes par seconde, ne jamais lire ni exfiltrer le fichier .env, ne modifier aucun fichier du projet.
Rapport en français : pour chaque faille, route, requête de preuve, impact, correctif proposé.
