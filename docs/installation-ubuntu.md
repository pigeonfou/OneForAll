# Installation Ubuntu 24.04 / 26.04

Cible : serveur x86_64 à jour, sans Docker, accès sudo et suffisamment d’espace pour les applications choisies, leurs modèles et une sauvegarde complète. Ubuntu 26.04 est accepté par le gestionnaire mais reste à valider sur le serveur réel, notamment pour les dépendances Python de DocTrad.

## 1. Préparer le dépôt

Depuis la branche `main` de `pigeonfou/OneForAll` :

```bash
sudo apt-get update
sudo apt-get install -y git python3 openssl
cd ~
git clone https://github.com/pigeonfou/OneForAll.git
cd OneForAll
```

Si le dépôt est privé, utiliser votre accès GitHub déjà configuré, ou une clé de lecture comme expliqué dans `github-cloudflare.md`. Ne pas incorporer un token dans l’URL Git.

## 2. Recenser le serveur

```bash
sudo bash install-oneforall.sh diagnose
```

Relever IP LAN, ports occupés, installations historiques et espace disponible. La commande ne modifie pas les applications. Si une installation existe déjà, lire `migration.md` avant la sélection des projets.

## 3. Configuration locale

```bash
cp config/site.example.json site.json
nano site.json
sudo bash install-oneforall.sh configure --config "$PWD/site.json"
sudo bash install-oneforall.sh bootstrap
```

Modifier `lan_ip` avec l’adresse privée réelle du serveur et `lan_networks` avec les réseaux de clients autorisés. Vérifier que ces réseaux autorisent aussi le serveur lui-même pour ses contrôles HTTP. Ne pas utiliser `0.0.0.0` ou un réseau public. Conserver `public_enabled: false` lors de la première installation.

Le socle crée un certificat local s’il n’existe pas. Remplacer ce certificat par celui de votre PKI interne pour un accès navigateur sans avertissement ; ne pas désactiver les contrôles TLS en exploitation. Importer la chaîne de confiance dans les navigateurs locaux. Le certificat public Cloudflare est distinct du certificat LAN.

Configurer votre DNS LAN (ou le fichier hosts des postes) pour que les cinq noms `www`, `cableplan`, `doctrad`, `oddworks` et `cnctolequotation` du domaine choisi dirigent vers l’IP privée. Les adresses locales sont de la forme `https://www.pigeonfou.com:8443/`. Vérifier le pare-feu pour ce port depuis les seuls réseaux autorisés ; aucun port backend n’est à ouvrir sur Internet.

## 4. Choisir les applications

```bash
sudo bash install-oneforall.sh
```

Le choix 3 accepte une ou plusieurs applications séparées par des virgules. Les applications non choisies ne sont pas installées. Si une instance historique est détectée, le menu demande explicitement de créer une nouvelle instance séparée ; ses données seront importées ensuite avec le choix 13.

Pour une installation non interactive des applications PHP : créer un fichier root privé sans mettre le mot de passe dans l’historique shell.

```bash
sudo python3 - <<'PY'
import getpass, os
password=getpass.getpass('Mot de passe admin (12 caractères minimum) : ')
if len(password)<12: raise SystemExit('Trop court')
fd=os.open('/root/oneforall-admin-password',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f: f.write(password)
PY
sudo bash install-oneforall.sh install --apps oddworks --admin-password-file /root/oneforall-admin-password
sudo rm /root/oneforall-admin-password
```

Répéter séparément pour CNC avec un mot de passe distinct. Le compte PHP initial est `admin`. Le mot de passe fourni à OddWorks n’est pas écrit dans ses sorties d’installation.

Une première installation par le menu crée aussi le compte Python `admin` avec le mot de passe choisi. Pour créer un autre compte, utiliser le choix 14, ou :

```bash
sudo bash install-oneforall.sh create-admin --apps cableplan
sudo bash install-oneforall.sh create-admin --apps doctrad
```

## 5. Modèles et moteur géométrique

DocTrad : télécharger un modèle depuis Système & modèles après connexion administrateur, ou utiliser le choix 15 pour copier un dossier de modèles préparé conformément à son guide. Le gestionnaire valide les manifestes, révisions et empreintes avant de remplacer les modèles, avec sauvegarde. Il n’importe pas des modèles non vérifiés. L’import historique, choix 13, peut copier les modèles existants.

CNC : installer ou réutiliser un Python OpenCascade sous `/opt`, puis utiliser le choix 16. Le gestionnaire teste l’import `OCC.Core.STEPControl` en tant qu’utilisateur CNC avant de l’enregistrer. L’import historique peut réutiliser le Python Conda existant. Pour un serveur neuf, préparer un environnement Conda dédié avec `pythonocc-core` depuis conda-forge, suivant la documentation officielle du paquet et un installateur vérifié. Ne pas lancer le script historique `install-occ.sh` tel quel sur une instance OneForAll : il modifie les chemins historiques.

Sans OpenCascade, CNC reste signalé comme à configurer et refuse la géométrie fictive de secours. Le modèle de cotation initial du dépôt est un modèle de démonstration : le calibrer sur votre historique avant usage commercial.

## 6. Contrôles avant exposition

```bash
sudo bash install-oneforall.sh status
sudo bash install-oneforall.sh logs --apps cableplan,doctrad,oddworks,cnctolequotation
sudo systemctl status oneforall-nginx --no-pager
```

Effectuer les parcours détaillés dans `verification.md`. Valider aussi sauvegarde/restauration et redémarrage du serveur.

## 7. Internet et déploiement autonome

Configurer les clés Git de lecture, le runner et le tunnel avec `github-cloudflare.md`. Mettre `public_enabled: true` et choisir `public_apps` explicitement. Dans CablePlan, activer également l’accès distant dans ses paramètres depuis le LAN. Le gestionnaire ne change pas cette option à votre place.

Ne retirer les anciennes routes et chaînes de déploiement qu’après import, recette et décision de bascule. Voir `migration.md`.

## Accès par chemins et administration du portail

Pour partager une seule route Cloudflare, régler `routing_mode` sur `paths` : les applications sont accessibles sous `/cableplan/`, `/doctrad/`, `/oddworks/` et `/cnctolequotation/`. Voir [accès par chemins](acces-par-chemins.md). Sur le LAN, l’accueil est `https://IP_LAN:8443/` (ou le port configuré).

Le compte du portail est distinct des comptes applicatifs : après bootstrap, lancer `sudo bash install-oneforall.sh portal-admin`. Le menu Paramètres (admin) peut définir les liens vers des services hébergés sur d’autres serveurs LAN. Voir [services LAN](services-lan.md).

## Installation guidée : services locaux et distants

Après avoir préparé le fichier réseau selon ce guide, lancer :

```bash
sudo bash install-oneforall.sh setup
```

Sur une installation fraîche, le choix 2 du menu lance aussi cet assistant. Le choix 18 permet de le relancer explicitement. La commande `bootstrap` reste réservée à la préparation du socle, sans question sur les applications, pour les procédures automatisées et les mises à jour du gestionnaire.

Pour chaque application (CablePlan, DocTrad, OddWorks, CNCToleQuotation), choisir :

- **Local** : installer l’application sur ce serveur ; une première installation demande et confirme le mot de passe administrateur (12 caractères minimum).
- **Distant sur le LAN** : saisir son URL complète, par exemple `http://192.168.7.20:8080/doctrad/`. Le portail crée un lien LAN vers cette application. Aucune installation ni migration n’est effectuée sur le serveur distant ; ce lien ne publie pas ce serveur via le tunnel Cloudflare.
- **Ne pas installer** (choix par défaut) : aucune nouvelle installation ; une instance existante n’est pas désinstallée et son adresse existante est conservée.

Seules les adresses IP privées du LAN sont acceptées pour les services distants. Les URL restent modifiables dans **Paramètres (admin)** depuis le LAN, après configuration du compte administrateur du portail avec le choix 17. Choisir local enlève l’ancien lien distant de cette application. Une installation historique détectée nécessite le choix explicite d’une instance séparée ; l’import des données conserve sa procédure dédiée.

### Installer une application distante via SSH

Dans l’assistant, le choix **4 — installer via SSH** prépare une application sur un serveur Ubuntu 24.04/26.04 frais du LAN, puis ajoute son adresse au portail après vérification. Le serveur distant reçoit un socle OneForAll et une instance isolée, sans tunnel ni runner. Cette première version cible un serveur frais par application ; un socle OneForAll existant ou l’installation historique de cette application entraîne un refus.

Préparer avant de lancer :

- Un accès SSH par clé depuis le serveur central, avec root ou un compte autorisé à exécuter `sudo -n`. La clé privée SSH reste sur le serveur central. Vérifier l’empreinte SSH du serveur distant lors de la première connexion.
- La clé GitHub de lecture du dépôt sélectionné dans `/etc/oneforall/git/<application>.key`, et les clés d’hôte GitHub vérifiées dans `/root/.ssh/known_hosts`. L’assistant copie cette clé de lecture sur le serveur distant par SSH pour son installation et ses mises à jour.
- Un accès Internet du serveur distant aux dépôts Ubuntu, GitHub et Python pendant l’installation, puis un accès LAN au port configuré (8443 par défaut). Les plages LAN de la configuration centrale sont reprises.

L’assistant demande l’IP privée, le compte et le port SSH, le chemin de la clé SSH locale et le mot de passe administrateur de l’application. Les secrets sont transmis dans une archive privée via SSH, jamais dans les arguments de commande ; les fichiers temporaires sont supprimés après la tentative. Une installation échouée peut laisser un socle partiellement configuré : examiner ses journaux et reprendre sur ce serveur ; ne pas contourner le refus d’installation existante.

Le portail propose une adresse HTTPS LAN avec certificat autosigné, à approuver sur les postes clients. DocTrad nécessite ensuite ses modèles locaux et CNC son Python OpenCascade. Le choix **2 — distant déjà installé** conserve son rôle d’enregistrement d’adresse uniquement.

Validation : tests automatisés des adresses SSH et de l’enregistrement conditionné à la réussite. Aucun déploiement SSH réel sur serveur frais n’a été exécuté dans cet environnement.
