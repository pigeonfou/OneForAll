# Vérifications du 7 octobre 2026

## Résultats effectivement obtenus

| Contrôle | Résultat |
|---|---|
| Gestionnaire OneForAll | 19 tests unitaires réussis |
| Config DocTrad | 2 tests réussis (port historique et port isolé) |
| Géométrie CNC | 1 test réussi : refus de la géométrie fictive quand OneForAll exige OCC |
| Initialisation OddWorks | Test PHP réussi : base URL racine, compte SQLite et mot de passe absent de la sortie |
| Syntaxe PHP | 108 fichiers contrôlés avec PHP 8.3.6 d’Ubuntu 24.04 |
| Nginx | 4 configurations vérifiées avec Nginx 1.24.0 d’Ubuntu 24.04 : aucun projet, quatre en LAN, quatre publics, sélection publique |
| PHP-FPM | Configurations OddWorks et CNC vérifiées avec PHP-FPM 8.3.6 |
| Python | Compilation de OneForAll et des applications Python réussie |
| Shell / JavaScript | `bash -n` et `node --check` réussis |
| Workflows | 6 fichiers YAML analysés localement |
| GitHub Actions | Contrôles d’intégration réussis pour les quatre branches ; contrôles existants CablePlan et DocTrad également réussis |

Liens GitHub Actions consultés :

- CablePlan : https://github.com/pigeonfou/CablePlan/actions/runs/37588455972 (intégration), https://github.com/pigeonfou/CablePlan/actions/runs/37588456006 (tests existants).
- DocTrad : https://github.com/pigeonfou/DocTrad/actions/runs/37588538931 (intégration), https://github.com/pigeonfou/DocTrad/actions/runs/37588538868 (contrôles existants).
- OddWorks : https://github.com/pigeonfou/gestion-projet/actions/runs/37588543564.
- CNC : https://github.com/pigeonfou/CNCToleQuotation/actions/runs/37588552659.

Les binaires natifs ont été extraits de paquets Ubuntu dans le workspace. Aucun service de production ni aucune base utilisateur n’a été modifié par ces vérifications. La validation de configuration utilise des chemins et ports temporaires ; elle ne remplace pas un essai complet sur le serveur.

La vérification native a révélé puis permis de corriger une valeur d’environnement vide refusée par PHP-FPM et des permissions de dossier de socket incompatibles avec Nginx. Le journal d’interruption conserve maintenant la sauvegarde initiale pour éviter qu’une reprise ne sauvegarde une base partiellement migrée comme état d’origine.

## Ce qui n’a pas été vérifié

- Installation complète sur un serveur Ubuntu 24.04 neuf.
- Installation complète et dépendances sur Ubuntu 26.04.
- Imports de vraies bases PostgreSQL/MariaDB et vrais documents/modèles.
- Sauvegarde/restauration sur les données de l’utilisateur et redémarrage du serveur.
- Cotation d’une vraie pièce STEP avec OpenCascade et modèle calibré.
- Traduction complète du PDF de référence dans la nouvelle instance.
- Publication DNS/Cloudflare et parcours sur `www.pigeonfou.com`.
- Recette visuelle navigateur du portail : le téléchargement du navigateur headless n’a pas produit une archive utilisable dans cet environnement. Aucun screenshot ou résultat visuel n’est déclaré.

## Recette à exécuter avant production

1. Installer seulement CablePlan, relancer le script, puis ajouter DocTrad et vérifier qu’aucune instance/donnée n’est dupliquée.
2. Installer les quatre projets ; vérifier absence de conflit avec les anciens services et ports.
3. Créer les comptes, importer les anciennes données, contrôler utilisateurs, projets, documents, modèles et permissions.
4. CablePlan : créer un câble, relier des pins, sauvegarder/recharger et exporter SVG/PDF/CSV. Vérifier refus public tant que son option distante est désactivée.
5. DocTrad : importer un modèle vérifié, traduire un document comportant texte/images, télécharger le résultat et contrôler la mise en page.
6. OddWorks : connexion, projet, étapes, tâches, affectations et transfert documentaire vers Nextcloud. Contrôler les liens sur le nouveau sous-domaine.
7. CNC : administration authentifiée, génération d’un token, cotation STEP avec `engine=opencascade`, historique et entraînement. Vérifier qu’une cotation ne s’appuie jamais sur la géométrie fictive.
8. En LAN et depuis Internet : ressources statiques, formulaires, redirects, API, cookies distincts et téléchargements. Tester une application non installée puis un backend arrêté.
9. Sauvegarder, modifier une donnée de test, restaurer et vérifier à la fois code et données. Tester une mise à jour interrompue et sa reprise.
10. Redémarrer le serveur ; vérifier services, tunnel, états du portail et persistence des données.
11. Ouvrir le portail sur ordinateur et mobile : disposition, texte, clavier, absence de défilement horizontal et états réels.

Conserver les résultats de cette recette dans `recensement-etapes.md`, avec le commit, l’OS et les actions réellement exécutées.
