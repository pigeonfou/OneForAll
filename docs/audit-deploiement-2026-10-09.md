# Audit des deux modes de déploiement — 9 octobre 2026

## Périmètre

OneForAll et les versions intégrées de CablePlan, DocTrad, CNCToleQuotation et gestion-projet/OddWorks. Comparaison GitHub : les branches applicatives `OneForAll` étaient en avance sur `main` sans divergence ; la branche de qualité DocTrad était déjà incluse dans `OneForAll`. Les paramètres LAN OneForAll étaient déjà dans `main`.

## Corrections

- Guides OneForAll des quatre applications : commandes, chemins, comptes, liens par préfixe, séparation des runners et instances autonomes/gérées.
- Toutes les adaptations intégrées dans les branches `main` ; catalogue OneForAll désormais configuré sur `main`, avec messages du helper alignés sur la branche réellement choisie.
- OddWorks : Ubuntu 26 admis, extensions PHP cURL/XML/ZIP installées, mot de passe administrateur confirmé et obligatoire dans l’installateur.
- DocTrad : guides Ubuntu 26 alignés avec le flag expérimental ; installations pip sur disque dans `/var/tmp` ; droits de lecture des releases lors d’une mise à jour offline corrigés.
- CNC autonome : dépendance rsync installée, création explicite des répertoires, secret DB aléatoire, admin protégé par Basic Auth, token démo désactivé, refus de réimport sur installation existante, vérification Apache et challenge HTTP avant annonce de réussite.
- CNC : Python OpenCascade effectivement configuré dans `geometry_python`, refus de géométrie synthétique par défaut pour l’API ; origine IP LAN admise pour les formulaires derrière OneForAll.
- Workflows d’intégration déclenchés sur `main` et `OneForAll`.

## Limites de la validation

Les vérifications sont des tests applicatifs, contrôles de syntaxe et parseurs natifs ; aucune installation neuve des cinq projets dans cinq VM Ubuntu 24/26 n’a été exécutée. La suite DocTrad locale utilise SQLite et Torch CPU ; les checks GitHub prévoient PostgreSQL et le lock complet. L’inférence locale synthétique démontre le chargement et l’absence de réseau, pas la qualité d’un modèle entraîné. La génération des modèles de traduction réels, OpenCascade/Conda et les secrets/tunnels dépendent du serveur cible. Le modèle ML initial CNC reste une démonstration à calibrer.

Les workflows de déploiement autonomes ne remplacent pas le déploiement OneForAll et requièrent leurs runners/helpers propres. Les mises à jour du gestionnaire root OneForAll exigent un `git pull` administrateur suivi de `bootstrap`. La fusion GitHub ne constitue pas une validation d’installation serveur, de restauration ou de cotation réelle.

## Résultats locaux

- OneForAll : 34 tests, sept configurations Nginx et deux pools PHP-FPM validés avec les binaires Ubuntu 24.04.
- CablePlan : 16 tests et contrôle Ruff sans erreur.
- DocTrad : 111 tests réussis, un test conditionnel ignoré ; PDF de référence vérifié par SHA256 et inférence CPU locale sans réseau.
- OddWorks : 22 scénarios PHP réussis, avec PDO SQLite, mbstring et ctype.
- CNC : test de refus de géométrie fictive réussi.
- 27 scripts shell contrôlés, ainsi que les deux helpers DocTrad sans extension ; syntaxe de 108 fichiers PHP contrôlée.

L’installation Apache CNC et la création MariaDB n’ont pas été exécutées dans cet environnement. Les résultats ci-dessus ne sont pas des tests d’installation fraîche ou de restauration sur Ubuntu 26.
