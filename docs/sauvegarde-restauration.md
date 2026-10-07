# Sauvegarde, restauration et dépannage

## Sauvegarder

```bash
sudo bash install-oneforall.sh backup --apps cableplan,doctrad,oddworks,cnctolequotation
```

Chaque application reçoit un dossier privé daté. Il contient les fichiers persistants (modèles inclus), son état de version, sa configuration et le dump PostgreSQL/MariaDB s’il existe. Les services de l’application sont arrêtés pendant la capture et les services précédemment actifs sont relancés ensuite. Les sommes SHA-256 permettent de détecter une modification des fichiers sauvegardés.

Conserver aussi une copie hors du serveur, avec les mêmes restrictions d’accès : ces sauvegardes contiennent des secrets et des documents. Prévoir la capacité nécessaire aux modèles. Aucun effacement automatique n’est effectué par OneForAll.

La configuration commune du portail, les certificats LAN, les clés Git et le token Cloudflare sont distincts des sauvegardes applicatives. Les sauvegarder séparément par un mécanisme sécurisé, par exemple une archive root privée de `/etc/oneforall` et la version du dépôt OneForAll installée. Ne pas envoyer cette archive dans GitHub.

## Restaurer ou revenir à la version précédente

Le retour arrière remet **ensemble** le code et les données du snapshot. Il ne consiste pas à faire un checkout d’un ancien commit sur une base migrée.

```bash
sudo bash install-oneforall.sh restore --apps cableplan --snapshot /var/backups/oneforall/cableplan/DATE_DU_SNAPSHOT --confirm-restore
```

Le menu propose la même action au choix 10 et demande `RESTAURER`. Les écritures postérieures à la sauvegarde sont remplacées ; une sauvegarde de sécurité de l’état courant est créée avant restauration. Les données précédentes sont aussi conservées dans un dossier `before-restore` en cas d’échec de l’extraction.

Les fichiers de la release SHA sauvegardée doivent être encore présents. OneForAll ne purge pas les anciennes versions. La restauration vérifie les empreintes et l’appartenance de l’archive à l’application avant de réactiver sa version.

En cas d’échec, les services restent arrêtés et les anciennes données sont conservées. Examiner l’erreur avant toute nouvelle tentative ; ne pas supprimer les sauvegardes ou dossiers conservés pour libérer de la place tant que la restauration n’est pas validée.

## Déploiement interrompu

Le journal `/var/lib/oneforall/pending/<id>.json` retient le SHA visé et la sauvegarde initiale. Relancer la même version reprend la préparation sans remplacer cette sauvegarde par une capture d’une base déjà partiellement migrée. Si un autre commit est désormais en tête de `AllFortOne`, restaurer d’abord le snapshot prévu ou examiner la reprise avec l’administrateur.

Un contrôle HTTP de déploiement échoué arrête les services de l’application. La restauration demeure explicite pour éviter de remplacer sans examen les données écrites entre-temps. Le portail distingue cet état d’une application disponible.

## Désinstallation

Le choix 11 crée une sauvegarde, désactive les services et retire les routes applicatives du frontal. Données, secrets, releases et sauvegardes sont conservés. Le script ne propose aucune suppression automatique des bases ou modèles ; une purge ultérieure est une opération séparée à décider après validation des sauvegardes.

Pour réactiver une application conservée, relancer son installation. Si le commit courant est inchangé, les services sont simplement réactivés sans nouvelle migration.

## Diagnostics fréquents

| Symptôme | Contrôle |
|---|---|
| Portail public 403 | `public_enabled`, route Cloudflare, nom d’hôte |
| CablePlan public 403 | `public_apps` puis option d’accès distant dans CablePlan |
| Application 502 | état du backend, permissions de la socket, configuration PHP-FPM |
| DocTrad à configurer | présence/empreintes des modèles, heartbeat worker, runtime et OCR |
| CNC à configurer | modèle actif, import OpenCascade, Python géométrique configuré |
| Clone privé impossible | deploy key du bon dépôt, remote Git et `known_hosts` de root |
| Nginx ne démarre pas | `nginx -t -c /etc/oneforall/nginx.conf`, IP LAN réelle, ports et certificat |
| Statut inconnu sur le portail | timer, journaux, certificat utilisé par les contrôles, données de plus de 180 s |
| Restauration refusée | empreintes, chemin du snapshot, release SHA conservée |

```bash
sudo bash install-oneforall.sh diagnose
sudo bash install-oneforall.sh status
sudo bash install-oneforall.sh logs --apps doctrad
sudo journalctl -u oneforall-nginx -u oneforall-status --no-pager -n 100
sudo nginx -t -c /etc/oneforall/nginx.conf
```

Ne pas désactiver l’authentification ou les restrictions CablePlan pour contourner une erreur de proxy.
