# OneForAll

Portail et installation native unifiée de CablePlan, DocTrad, OddWorks (`gestion-projet`) et CNCToleQuotation. Les applications restent dans leurs dépôts respectifs. OneForAll fournit un frontal Nginx commun, un menu d’installation à la carte, des services isolés, une chaîne GitHub Actions et des procédures de migration/restauration.

**État : implémentation préparée et contrôlée localement ; déploiement sur votre serveur et recette métier encore requis.** Les vérifications natives ont été exécutées avec Nginx et PHP d’Ubuntu 24.04. Cela ne constitue pas une installation complète validée sur Ubuntu 24.04 ou 26.04.

## Adresses

| Application | Adresse publique prévue | Dépôt |
|---|---|---|
| Portail | `https://www.pigeonfou.com` | `pigeonfou/OneForAll` |
| CablePlan | `https://cableplan.pigeonfou.com` | `pigeonfou/CablePlan` |
| DocTrad | `https://doctrad.pigeonfou.com` | `pigeonfou/DocTrad` |
| OddWorks | `https://oddworks.pigeonfou.com` | `pigeonfou/gestion-projet` |
| CNCToleQuotation | `https://cnctolequotation.pigeonfou.com` | `pigeonfou/CNCToleQuotation` |

Les applications utilisent des routes absolues à la racine. Les sous-domaines évitent de réécrire tous les formulaires, API, téléchargements et cookies. Le portail reste le point de départ commun. En local, utiliser les mêmes noms DNS dirigés vers l’IP LAN, avec le port HTTPS 8443 par défaut. Voir [architecture](docs/architecture.md).

## Premier lancement

Depuis une copie du dépôt :

```bash
cp config/site.example.json site.json
nano site.json
sudo bash install-oneforall.sh configure --config "$PWD/site.json"
sudo bash install-oneforall.sh
```

Adapter au minimum `lan_ip`, `lan_networks` et `domain`. L’exposition Internet reste désactivée tant que `public_enabled` est faux. Le menu propose le diagnostic, le socle, la sélection des applications, les mises à jour, les sauvegardes, la restauration et la désactivation. Les choix complémentaires créent les comptes Python, importent les anciennes données, les modèles DocTrad et configurent OpenCascade.

Pour une procédure complète, suivre [installation Ubuntu](docs/installation-ubuntu.md). Les dépôts privés nécessitent une clé de lecture ou un mécanisme Git authentifié sur le serveur, expliqué dans [GitHub et Cloudflare](docs/github-cloudflare.md).

## Commandes principales

```bash
sudo bash install-oneforall.sh diagnose
sudo bash install-oneforall.sh bootstrap
sudo bash install-oneforall.sh install --apps cableplan,doctrad
sudo bash install-oneforall.sh create-admin --apps cableplan
sudo bash install-oneforall.sh create-admin --apps doctrad
sudo bash install-oneforall.sh status
sudo bash install-oneforall.sh logs --apps cableplan,doctrad
sudo bash install-oneforall.sh backup --apps cableplan,doctrad
sudo bash install-oneforall.sh update --apps cableplan --sha COMMIT_COMPLET_40_CARACTERES
```

Pour les deux applications PHP, fournir un fichier privé contenant le mot de passe administrateur avec `--admin-password-file /chemin/prive`. Le menu le saisit sans affichage et efface son fichier temporaire après l’opération. Choisir des mots de passe distincts en installant les applications séparément.

Les mises à jour acceptent uniquement la tête de la branche `AllFortOne` approuvée. Un verrou système empêche les opérations simultanées. Une sauvegarde précède la migration ; un journal de déploiement conserve la sauvegarde initiale en cas d’interruption. Les services sont arrêtés si le contrôle HTTP de déploiement échoue. La restauration est une opération explicite, documentée dans [sauvegarde et retour arrière](docs/sauvegarde-restauration.md).

## Sécurité et accès hors ligne

- Les authentifications de CablePlan, DocTrad et OddWorks restent actives. Aucun SSO ajouté.
- L’administration CNC est protégée par Nginx Basic Auth ; son API conserve le Bearer token. Le token de démonstration est désactivé.
- CablePlan reçoit `lan` uniquement depuis l’entrée LAN et `tunnel` depuis l’entrée Cloudflare. Sa propre option d’accès distant reste obligatoire.
- Les applications non choisies n’installent pas leurs modèles ni leurs dépendances lourdes.
- Le frontal public écoute uniquement sur `127.0.0.1:18080` ; le frontal LAN écoute l’IP privée choisie en HTTPS.
- Les traitements métier ne nécessitent pas de CDN ou service d’IA distant. Installation, mises à jour, GitHub Actions et Cloudflare nécessitent le réseau.
- Le fonctionnement hors ligne de DocTrad demande des modèles locaux vérifiés. Une application sans modèle reste signalée « Configuration à compléter ».
- CNC ne produit pas de cotation avec la géométrie synthétique de secours dans une instance OneForAll. Configurer OpenCascade avant une cotation réelle.

## Dépendances particulières

DocTrad utilise PostgreSQL, Tesseract et une pile de modèles locaux ; son `requirements.lock` est conservé. Son installation peut être volumineuse et échouer si les roues correspondant au Python du serveur sont absentes. OneForAll laisse alors la version active intacte pendant la préparation.

CNC utilise MariaDB et un environnement Python pour le modèle de cotation. OpenCascade utilise un Python distinct, généralement l’environnement Conda existant, configurable avec le choix 16. Le script historique `install-occ.sh` cible `/opt/cnctolequotation` et ne doit pas être lancé directement pour modifier une instance OneForAll.

## Documentation et vérification

- [Recensement et étapes réalisées](docs/recensement-etapes.md)
- [Architecture et isolation](docs/architecture.md)
- [Installation Ubuntu 24.04 / 26.04](docs/installation-ubuntu.md)
- [Migration des installations existantes](docs/migration.md)
- [GitHub Actions et Cloudflare](docs/github-cloudflare.md)
- [Sauvegarde, restauration et dépannage](docs/sauvegarde-restauration.md)
- [Résultats et limites des tests](docs/verification.md)

Vérifications reproductibles du gestionnaire :

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q oneforall
bash -n install-oneforall.sh
node --check portal/app.js
python3 tests/verify_native.py
```

La dernière commande exige Nginx ; elle valide aussi PHP-FPM lorsqu’il est installé. Elle utilise uniquement des fichiers temporaires et ne démarre pas les services système. `.github/workflows/checks.yml` exécute ces contrôles sur un runner GitHub hébergé Ubuntu 24.04.

### Une route publique et accès direct LAN

Voir [l'accès par chemins](docs/acces-par-chemins.md) pour servir toutes les applications
sous `www.pigeonfou.com/<application>/` et ouvrir le portail directement via l'adresse IP LAN.
