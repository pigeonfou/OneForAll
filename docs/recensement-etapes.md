# Recensement et étapes — OneForAll

Date : 7 octobre 2026. État : adaptations publiées, implémentation OneForAll disponible ; dépôt OneForAll à créer et installation serveur à réaliser.

## État initial observé dans les dépôts

| Projet | Dépôt / branche auditée | Technologie et persistance | Installation / exposition |
|---|---|---|---|
| CablePlan | `pigeonfou/CablePlan`, main | Python 3.12+, FastAPI, SQLite, SVG/ReportLab, Argon2id | Nginx LAN + entrée tunnel localhost:8081, socket Unix, service cableplan, releases /opt/cableplan |
| DocTrad | `pigeonfou/DocTrad`, main | FastAPI, PostgreSQL/SQLAlchemy, traduction locale, worker, OCR et registre de modèles | Nginx, web localhost:8090, runtime:8091, trois services, releases /opt/docutranslate |
| OddWorks | `pigeonfou/gestion-projet`, main | PHP, SQLite, authentification locale, intégration Nextcloud | Apache historique, base d’URL /gestion-projet, DB /var/lib/projectflow/database.sqlite |
| CNC | `pigeonfou/CNCToleQuotation`, main | PHP, MariaDB, Python ML et OpenCascade optionnel | Apache historique sur :80, /opt/cnctolequotation, API Bearer, administration sans authentification repérée |

Les commits audités et ceux des adaptations sont enregistrés dans `config/audited-revisions.json`. Les branches main sont restées identiques entre l’audit et la publication des adaptations.

Les scripts historiques ne sont pas tous idempotents et peuvent reconfigurer un site Apache/Nginx global, réimporter un schéma ou écrire des identifiants de démonstration. Ils ne sont donc pas exécutés en chaîne par OneForAll. Le gestionnaire prépare des instances isolées à partir du code de chaque dépôt.

## Décisions appliquées

- Nginx commun dans un service dédié, sans conflit volontaire avec les anciens ports 80/443.
- Sous-domaines pour conserver les routes absolues des applications et séparer les cookies.
- Utilisateurs, bases, données, sockets et environnements distincts ; aucune copie complète des applications dans OneForAll.
- Adaptations uniquement dans les branches `OneForAll` ; aucune fusion automatique.
- Conservation du canal tunnel CablePlan et de son option d’accès distant.
- Protection Basic Auth de l’administration CNC, API Bearer préservée, token démo désactivé et refus de géométrie fictive dans OneForAll.
- Préparation des versions avant arrêt de l’instance active, sauvegarde avant migration, journal de reprise, restauration explicite code + données.

## Travail réalisé

| Étape | Résultat |
|---|---|
| Inventaire dépôts / branches / scripts | Terminé sur les quatre dépôts |
| Portail français responsive et état réel | Code préparé ; données de statut contrôlées côté serveur et expiration côté navigateur |
| Menu et CLI | Socle, sélection, mise à jour, diagnostic, logs, sauvegarde, restauration, désactivation, runner et tunnel |
| Imports complémentaires | Import historique, modèles locaux vérifiés DocTrad et configuration OpenCascade |
| Configurations natives | Nginx et pools PHP-FPM contrôlés avec les outils Ubuntu 24.04 |
| Branches et PR | Quatre branches OneForAll et quatre PR en brouillon publiées |
| Contrôles GitHub Actions | Intégration des quatre projets réussie ; tests existants CablePlan/DocTrad réussis |
| Documentation | Architecture, Ubuntu, migration, Cloudflare/GitHub, sauvegarde et recette |
| OneForAll GitHub | Dépôt absent ; création non disponible dans le connecteur courant |
| Déploiement et domaine | Non effectués : le code n’est pas déclaré en production |

## Branches publiées

| Projet | SHA OneForAll | Pull request |
|---|---|---|
| CablePlan | `c5b26ca42f457b42eed18be54482aff4ee5d03d9` | https://github.com/pigeonfou/CablePlan/pull/1 |
| DocTrad | `4759f60a50f1e0c4d723eaabf2ed3357c09d8d7c` | https://github.com/pigeonfou/DocTrad/pull/1 |
| OddWorks | `c1ecd4f775ee399d0766dd81ffddfa127c91c8f7` | https://github.com/pigeonfou/gestion-projet/pull/3 |
| CNC | `448d3faf083ce4d1fc6b67a55154db5049735622` | https://github.com/pigeonfou/CNCToleQuotation/pull/1 |

Les workflows historiques de production n’ont pas été déclenchés par ces branches. Les PR restent à examiner avant toute fusion.

## Vérifications et commandes reproductibles

Voir `verification.md` pour le détail, les liens GitHub Actions et les limites. Les commandes locales réussies :

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q oneforall
bash -n install-oneforall.sh
node --check portal/app.js
python3 tests/verify_native.py
```

`verify_native.py` accepte aussi `--native-root /chemin/paquets-extraits` pour les paquets Nginx/PHP-FPM extraits sans installation de services. Les tests applicatifs supplémentaires figurent dans leurs branches.

## Prochaines étapes nécessaires

1. Créer `pigeonfou/OneForAll`, privé de préférence, avec une branche main initialisée (README) et accessible au connecteur GitHub ; publier les fichiers préparés.
2. Exécuter les contrôles OneForAll dans ce dépôt.
3. Sur le serveur, configurer IP LAN/DNS local, les accès Git de lecture, installer le socle et sélectionner les applications.
4. Importer les données et vérifier les parcours sur les nouvelles instances.
5. Enregistrer le runner dédié OneForAll et configurer les routes du tunnel vers le frontal.
6. Activer l’exposition publique choisie et, séparément, celle de CablePlan.
7. Tester le workflow exact SHA → serveur → portail et compléter la recette avant bascule finale.
8. Documenter le résultat réel et conserver les sauvegardes des anciennes installations.

Aucun token, mot de passe, clé privée ou dump de données utilisateur n’est présent dans ce recensement.

## 2026-10-08 — Routage par préfixes et accès IP LAN

- Demande utilisateur : réduire les routes Cloudflare et fournir l'accès IP LAN.
- Ajout du mode `routing_mode=paths`, optionnel pour préserver les configurations existantes.
- Portail, liens LAN/publics et santé sous les préfixes ; IP LAN admise sur le portail TLS.
- CablePlan et DocTrad : préfixes natifs pour HTML, JavaScript, redirections et cookies.
- PHP : chemins de cookies séparés, protections des sources et authentification CNC préservées.
- Configuration sauvegardée, restauration sur erreur ; gros téléchargements pip dans `/var/tmp`.
- Validation : 21 tests gestionnaire, 7 tests CablePlan et 10 tests web DocTrad réussis.
- Sept configurations Nginx et deux PHP-FPM passent les parseurs natifs Ubuntu 24.04.
- Test HTTP Nginx dans le conteneur impossible : création de socket refusée par l'environnement.
- Le serveur utilisateur Ubuntu 26.04 doit appliquer `docs/acces-par-chemins.md` puis effectuer la recette.

## 2026-10-08 — Rétablissement des comptes administrateurs

- Diagnostic : l'installateur initial demandait un mot de passe mais ne créait aucun compte Python.
- Première installation Python : création du compte `admin` avec le mot de passe choisi, après activation de la version.
- Ajout de `reset-admin --apps oddworks,cableplan,doctrad` : création ou réinitialisation, confirmation masquée, sauvegarde préalable de chaque application.
- Le secret est transmis sur stdin, jamais dans les arguments des processus ou des fichiers temporaires.
- CablePlan invalide les sessions du compte réinitialisé ; ses limites de connexion sont réinitialisées.
- Vérification : 23 tests du gestionnaire réussis ; création et remplacement des mots de passe vérifiés sur bases de test CablePlan et DocTrad.

## 2026-10-08 — Correction CSS DocTrad derrière le préfixe

- Constat navigateur réel : feuille `/doctrad/static/style.css` non chargée, styles par défaut.
- Reproduction locale StaticFiles : chemin conservé → HTTP 200 ; préfixe retiré → HTTP 404.
- Nginx transmet désormais le chemin complet aux applications ASGI configurées avec `root_path`.
- Le canal CablePlan reste fixé par le frontal ; les contrôles de disponibilité restent préfixés.
- Correction du frontal uniquement : `git pull`, `bootstrap`, `status`, sans réinstaller DocTrad.
- Validation : 24 tests gestionnaire et parseurs natifs Nginx/PHP-FPM réussis ; recette CSS serveur après application.

## 2026-10-08 — Téléchargement des modèles depuis DocTrad

- Ajout dans DocTrad OneForAll d'un catalogue de trois modèles locaux et d'un formulaire administrateur.
- Téléchargement explicite dans un processus isolé des secrets et des documents ; services de traduction inchangés en mode hors ligne.
- Suivi des octets, contrôle de licence/révision/SHA-256, verrou, reprise et publication atomique.
- Poids Safetensors uniquement ; aucune suppression ou substitution de modèle existant.
- 24 tests locaux ciblés réussis (Hub simulé) ; téléchargement réel et traduction à valider sur le serveur.
- Installation : `sudo bash install-oneforall.sh update --apps doctrad`, puis Système & modèles → OPUS.

## 2026-10-08 — Correction du nom des branches

- Création de `OneForAll` depuis la tête actuelle de chaque branche applicative, sans réécriture d’historique.
- Catalogue, messages du gestionnaire, workflows et documentation utilisent le nom corrigé.
- Anciennes branches conservées pendant la transition ; développement désormais sur `OneForAll`.
- Mise à jour du gestionnaire par `git pull` puis `bootstrap` avant le prochain déploiement applicatif.
