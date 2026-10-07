# Migration des installations existantes

L’import copie les données vers les instances OneForAll. Il ne supprime ni les anciens dépôts, ni les bases sources, ni leurs tunnels. Il remplace les données de la **nouvelle instance** après une sauvegarde ; le choix 13 demande une confirmation explicite.

## Ordre recommandé

1. Diagnostiquer le serveur, configurer et installer le socle sans accès Internet.
2. Installer une instance séparée pour chaque application voulue. Le menu détecte les installations historiques et demande de confirmer `INSTANCE` ; en CLI, utiliser `--isolated`.
3. Sauvegarder la source par ses procédures habituelles et s’assurer d’avoir l’espace nécessaire pour les modèles.
4. Choix 13 → application → `IMPORTER`, ou commande ci-dessous.
5. Vérifier les utilisateurs, documents, projets, réglages réseau, modèles et exports sur l’adresse OneForAll locale.
6. Préparer la bascule des routes Cloudflare et des déploiements. Ne permettre les écritures que dans une instance après la bascule.
7. Conserver les anciennes données et les sauvegardes jusqu’à validation complète.

```bash
sudo bash install-oneforall.sh import-legacy --apps cableplan --confirm-import
sudo bash install-oneforall.sh import-legacy --apps doctrad --confirm-import
sudo bash install-oneforall.sh import-legacy --apps oddworks --confirm-import
sudo bash install-oneforall.sh import-legacy --apps cnctolequotation --confirm-import
```

Importer une application à la fois et vérifier son résultat. Les comptes métier sont ceux des bases importées. L’administrateur créé dans la nouvelle instance avant import ne remplace pas les utilisateurs historiques.

## Sources reconnues

| Application | Source | Traitement |
|---|---|---|
| CablePlan | `/var/lib/cableplan/database.sqlite` | snapshot SQLite cohérent et copie vers l’instance isolée |
| OddWorks | `/var/lib/projectflow/database.sqlite` | snapshot SQLite cohérent ; réglages et relations inclus dans la base |
| DocTrad | `/etc/docutranslate/docutranslate.env` | lecture des chemins réels, copie des documents/modèles, dump PostgreSQL local |
| CNC | `/opt/cnctolequotation/api/config.php` et `data` | lecture de la config par l’utilisateur historique, dump MariaDB, modèles, uploads et historique |

Les snapshots des sources sont conservés dans `/var/backups/oneforall/legacy-<id>/<date>`. Une sauvegarde standard de la cible est créée avant son remplacement. Les fichiers de configuration sauvegardés peuvent contenir des secrets : ils restent dans des répertoires privés du serveur.

L’import PostgreSQL et MariaDB automatique est réservé aux bases locales sur leurs ports standards. Pour une base distante, un autre moteur ou des chemins historiques non standard, arrêter et adapter l’import plutôt que modifier les données à l’aveugle.

DocTrad et CablePlan historiques sont arrêtés brièvement si leurs services sont actifs, puis redémarrés même en cas d’erreur. PostgreSQL et MariaDB partagés restent actifs.

OddWorks et CNC historiques utilisent potentiellement un Apache partagé : l’import ne stoppe pas Apache. Pour la bascule finale, suspendre les écritures sur le site historique choisi, refaire l’import, puis rediriger les utilisateurs vers OneForAll. Un snapshot SQLite assure une base cohérente à un instant donné, mais ne synchronise pas les écritures ultérieures.

Les modèles DocTrad sont recopiés et leur registre recalcule les chemins à partir du nouveau dossier. L’import CNC peut réutiliser le Python OpenCascade historique sous `/opt` ; il reste une dépendance tant que vous n’avez pas préparé un nouvel environnement. Le token CNC de démonstration est désactivé après l’import, les autres tokens étant conservés.

## Bascule des adresses

DocTrad et CablePlan peuvent conserver leurs sous-domaines si ce sont ceux du manifeste. Modifier leur route Cloudflare vers le frontal OneForAll seulement après la recette. Conserver la configuration précédente du tunnel pour revenir en arrière.

L’ancienne adresse OddWorks `projet.pigeonfou.com/gestion-projet` n’est pas automatiquement réécrite : les routes du nouvel hôte sont à la racine `oddworks.pigeonfou.com`. Garder l’ancienne adresse pendant la transition, puis retirer les écritures ou fournir un lien vers la nouvelle adresse. Ne pas transformer arbitrairement les POST/PUT/API par une redirection 301/302.

Les workflows historiques continuent de cibler leurs anciennes instances. Pour la nouvelle instance, utiliser uniquement le workflow OneForAll. Retirer les anciennes routes applicatives et arrêter les anciens services spécifiques quand leur abandon est décidé ; ne pas arrêter un Apache partagé avec d’autres applications.

## Échec d’import

La source reste conservée. Ne lancer aucune purge. La sortie indique la sauvegarde de la cible, utilisable avec la procédure standard de restauration. Consulter les journaux et corriger les dépendances avant de relancer. L’import est reproductible et peut être refait depuis la source ; les écritures éventuellement créées dans la cible entre deux imports seraient remplacées.
