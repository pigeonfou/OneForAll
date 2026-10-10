# Installation Ubuntu 24.04 / 26.04

Cible : serveur x86_64 à jour, sans Docker, accès sudo et suffisamment d’espace pour les applications choisies, leurs modèles et une sauvegarde complète. Ubuntu 26.04 est accepté par le gestionnaire mais reste à valider sur le serveur réel, notamment pour les dépendances Python de DocTrad.

## 0. Partir d’Ubuntu 26 fraîchement installé

Toutes les commandes ci-dessous s’exécutent sur le **serveur central OneForAll**, connecté avec le compte créé pendant l’installation Ubuntu (par exemple `ubuntu`). Les exemples utilisent `192.168.7.10` pour le serveur, `192.168.7.0/24` pour le LAN et `192.168.7.20` pour un serveur distant : remplacer ces valeurs par celles de votre réseau.

### 0.1 Première connexion et mises à jour

Depuis la console du serveur :

```bash
whoami
sudo -v
cat /etc/os-release
uname -m
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y git curl ca-certificates openssl openssh-client openssh-server python3 python3-venv nano iproute2 ufw
sudo systemctl enable --now ssh
sudo reboot
```

Attendre le redémarrage, puis se reconnecter à la console ou depuis un autre poste : `ssh ubuntu@IP_DU_SERVEUR`. La procédure cible Ubuntu 26.04 x86_64 (`uname -m` affiche `x86_64`) ; les paquets Python applicatifs sont installés dans des environnements virtuels par OneForAll, jamais avec un pip global.

### 0.2 Adresse réseau stable et espace disque

```bash
ip -br -4 address
ip -4 route
hostname -I
df -h /
free -h
```

Réserver l’adresse du serveur dans le DHCP de votre routeur ; c’est l’option recommandée pour éviter de modifier Netplan pendant une connexion SSH. Relever le masque réel du LAN (ne pas supposer `/24` si le réseau utilise un autre masque). OneForAll doit garder la même IP après redémarrage.

DocTrad peut occuper plusieurs dizaines de Go : environ 6 Go par version Python/CUDA dans l’installation observée, auxquels s’ajoutent modèles et sauvegardes. Prévoir l’espace pour **deux versions et une sauvegarde complète des données**. Une partition de 100 Go peut se remplir rapidement avec plusieurs modèles et des sauvegardes répétées ; surveiller `df -h /` avant chaque mise à jour.

### 0.3 Récupérer OneForAll, y compris si le dépôt est privé

Pour un dépôt accessible publiquement, utiliser le clone HTTPS de l’étape 1. Si GitHub demande un identifiant/mot de passe ou si le dépôt est privé, préparer une clé de lecture du dépôt OneForAll :

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
test -f ~/.ssh/oneforall-repo.key || ssh-keygen -t ed25519 -N '' -C oneforall-repo -f ~/.ssh/oneforall-repo.key
cat ~/.ssh/oneforall-repo.key.pub
```

Dans GitHub, ouvrir **pigeonfou/OneForAll → Settings → Deploy keys → Add deploy key**, coller la clé **publique**, sans cocher l’accès en écriture. Puis :

```bash
cd ~
git -c core.sshCommand="ssh -i $HOME/.ssh/oneforall-repo.key -o IdentitiesOnly=yes -o StrictHostKeyChecking=ask" clone --branch main ssh://git@ssh.github.com:443/pigeonfou/OneForAll.git
cd OneForAll
```

À la première connexion, vérifier l’empreinte de GitHub avant de saisir **uniquement `yes`**, puis Entrée. Pour ED25519, l’empreinte publiée est `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU` ; la comparer aussi à la [page officielle GitHub](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints). Ne pas coller une nouvelle commande à la place de cette réponse. Le mot de passe de votre compte GitHub ne permet pas d’authentifier les opérations Git HTTPS.

Si vous avez déjà cloné le dépôt, faire `cd ~/OneForAll && git pull --ff-only origin main` ; ne pas le cloner par-dessus le dossier existant. Continuer à l’étape 2 après ces préparatifs.

### 0.4 Donner au gestionnaire l’accès aux dépôts applicatifs

À faire **avant** le choix d’installation locale ou SSH pour chaque application sélectionnée, même si le compte Ubuntu peut déjà accéder à GitHub : le gestionnaire travaille en root et utilise ses propres clés.

```bash
sudo install -d -m 700 /etc/oneforall/git /root/.ssh
sudo bash -c '
set -e
for app in cableplan doctrad oddworks cnctolequotation; do
  test -f "/etc/oneforall/git/$app.key" || ssh-keygen -t ed25519 -N "" -C "oneforall-$app" -f "/etc/oneforall/git/$app.key"
  chmod 600 "/etc/oneforall/git/$app.key"
done
'
```

Afficher séparément les clés publiques avec `sudo cat /etc/oneforall/git/cableplan.key.pub`, puis les autres identifiants. Ajouter chaque clé au bon dépôt dans **Settings → Deploy keys**, en lecture seule :

| Clé | Dépôt GitHub |
| --- | --- |
| `cableplan.key.pub` | `pigeonfou/CablePlan` |
| `doctrad.key.pub` | `pigeonfou/DocTrad` |
| `oddworks.key.pub` | `pigeonfou/gestion-projet` |
| `cnctolequotation.key.pub` | `pigeonfou/CNCToleQuotation` |

Une clé de déploiement distincte est nécessaire pour chaque dépôt. Il suffit d’enregistrer les clés des applications réellement choisies. Tester ensuite chaque dépôt choisi, par exemple :

```bash
sudo git -c core.sshCommand='ssh -i /etc/oneforall/git/doctrad.key -o IdentitiesOnly=yes -o StrictHostKeyChecking=ask -o HostKeyAlgorithms=ssh-ed25519 -o ConnectTimeout=15' ls-remote ssh://git@ssh.github.com:443/pigeonfou/DocTrad.git refs/heads/main
```

Vérifier l’empreinte GitHub comme à l’étape précédente, puis répondre `yes`. Cela crée l’entrée GitHub dans `/root/.ssh/known_hosts`, requise ensuite par le gestionnaire. Le résultat attendu est un SHA suivi de `refs/heads/main`. Adapter la clé et le dépôt selon le tableau pour tester les autres services. `Permission denied (publickey)` signifie qu’il faut corriger l’autorisation GitHub avant de poursuivre.

### 0.5 Préparer le réseau OneForAll

Depuis `~/OneForAll` :

```bash
cp config/site.example.json site.json
nano site.json
```

Pour un premier démarrage LAN sans DNS supplémentaire, utiliser cet exemple en remplaçant IP et réseau :

```json
{
  "domain": "pigeonfou.com",
  "lan_ip": "192.168.7.10",
  "lan_port": 8443,
  "tunnel_port": 18080,
  "public_enabled": false,
  "public_apps": [],
  "lan_networks": ["192.168.7.0/24"],
  "certificate": "/etc/oneforall/tls/server.crt",
  "private_key": "/etc/oneforall/tls/server.key",
  "routing_mode": "paths"
}
```

`domain` sert à la configuration des hôtes et des certificats ; l’accès LAN par IP avec `paths` ne nécessite pas de posséder un domaine public. Choisir votre vrai domaine si un tunnel public est prévu. Dans nano : Ctrl+O, Entrée, puis Ctrl+X.

```bash
python3 -m json.tool site.json >/dev/null
sudo bash install-oneforall.sh configure --config "$PWD/site.json"
```

Si vous activez UFW sur ce serveur frais, autoriser d’abord SSH et le frontal LAN. Adapter le port 22 si SSH utilise un autre port et remplacer le réseau d’exemple :

```bash
sudo ufw allow from 192.168.7.0/24 to any port 22 proto tcp
sudo ufw allow from 192.168.7.0/24 to any port 8443 proto tcp
sudo ufw enable
sudo ufw status verbose
```

Votre poste d’administration doit appartenir au réseau autorisé avant d’activer le pare-feu. Aucun port 18101/18102/18112, PostgreSQL ou MariaDB n’est à ouvrir aux postes clients. Ne pas faire de redirection de port Internet sur le routeur pour l’accès LAN.

### 0.6 Préparer un serveur distant neuf (uniquement pour le choix SSH)

À la console de **chaque serveur distant**, effectuer les mises à jour et installer SSH, Python et tar :

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y openssh-server python3 tar
sudo systemctl enable --now ssh
sudo -v
ip -br -4 address
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Réserver aussi son adresse DHCP. Conserver l’empreinte affichée pour vérifier la connexion depuis le central. Le compte `ubuntu` doit pouvoir utiliser sudo ; son mot de passe sera demandé par l’assistant, sans besoin de configurer NOPASSWD. Si UFW est activé sur le distant, autoriser le port SSH et le port 8443 depuis le LAN avec les règles de l’étape 0.5. Si une mise à jour du noyau demande un redémarrage, le faire avant le transfert de clé.

Revenir sur le **serveur central** et préparer une clé SSH dédiée pour ce serveur distant :

```bash
sudo install -d -m 700 /root/.ssh
sudo test -f /root/.ssh/oneforall-remote-192-168-7-20.key || sudo ssh-keygen -t ed25519 -N '' -C oneforall-remote -f /root/.ssh/oneforall-remote-192-168-7-20.key
sudo ssh-copy-id -i /root/.ssh/oneforall-remote-192-168-7-20.key.pub ubuntu@192.168.7.20
sudo ssh -i /root/.ssh/oneforall-remote-192-168-7-20.key -o IdentitiesOnly=yes ubuntu@192.168.7.20 'id; cat /etc/os-release'
```

Remplacer IP et compte ; avec un port différent, ajouter `-p PORT` à `ssh-copy-id` et `ssh`. La première commande de connexion demande de comparer l’empreinte SSH au résultat relevé sur la console distante, puis le mot de passe du **compte SSH distant** pour déposer la clé. Les connexions suivantes utilisent cette clé. Dans l’assistant, fournir le chemin privé `/root/.ssh/oneforall-remote-192-168-7-20.key`, le compte distant et son mot de passe sudo. Ne pas transmettre la clé privée du serveur central au serveur distant.

### 0.7 Lancer l’installation et créer les comptes

Sur le central :

```bash
cd ~/OneForAll
sudo bash install-oneforall.sh setup
```

Pour chaque service : **1 local**, **2 distant déjà installé**, **3 ignorer**, **4 installer via SSH**. L’assistant installe le socle, demande les mots de passe applicatifs pour les premières installations et vérifie les services. Les comptes initiaux sont `admin` ; choisir des mots de passe distincts par application. L’installation distante copie uniquement la clé GitHub de lecture du service concerné pour ses mises à jour.

Après l’assistant, créer le compte d’administration du portail central :

```bash
sudo bash install-oneforall.sh portal-admin
sudo bash install-oneforall.sh status
df -h /
```

Ouvrir `https://192.168.7.10:8443/` depuis un poste du LAN, puis l’application choisie. Le certificat initial est autosigné : approuver/importer le certificat LAN sur les postes, ou installer un certificat de votre PKI. L’administration du portail est distincte des comptes `admin` applicatifs. Les liens distants utilisent le certificat du serveur distant.

DocTrad : ouvrir `/doctrad/`, se connecter avec `admin`, puis **Système & modèles** pour télécharger un modèle avant une traduction. Le téléchargement nécessite Internet sur le serveur d’application ; les traductions utilisent ensuite les modèles locaux. CNC : préparer OpenCascade selon l’étape 5 avant de traiter des pièces. Un service distant neuf reçoit OneForAll sans runner ni Cloudflare ; ces fonctions restent optionnelles.

### 0.8 Contrôles et entretien

```bash
sudo bash install-oneforall.sh status
sudo systemctl status oneforall-nginx --no-pager
```

Pour les journaux, choisir uniquement les applications installées localement, par exemple `sudo bash install-oneforall.sh logs --apps doctrad`. Pour une application distante, exécuter les commandes de status/logs sur ce serveur via SSH. Tester une connexion applicative et un petit traitement réel avant d’installer des modèles volumineux.

Suivre [sauvegarde et restauration](sauvegarde-restauration.md) et vérifier l’espace avant les mises à jour. Ne pas supprimer automatiquement les versions courantes, modèles ou sauvegardes de retour arrière. Internet/Cloudflare et GitHub Actions ne sont pas nécessaires à cette première installation LAN ; suivre ensuite [GitHub et Cloudflare](github-cloudflare.md) si vous souhaitez les activer.

Les étapes ci-dessus constituent le parcours initial complet. Les sections suivantes détaillent les commandes individuelles et les variantes. Les validations de code ne remplacent pas un test d’installation neuf sur votre matériel.


## 1. Préparer le dépôt

Si l’étape 0.3 n’a pas déjà récupéré le dépôt, utiliser la branche `main` de `pigeonfou/OneForAll` :

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

Une première installation par l’assistant `setup` crée aussi le compte Python `admin` avec le mot de passe choisi. Pour une installation Python via le choix 3 sans mot de passe fourni, créer ensuite le compte avec le choix 14. Pour créer un autre compte, utiliser le choix 14, ou :

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

- Un accès SSH par clé depuis le serveur central, avec root ou un compte autorisé à utiliser `sudo` (avec ou sans mot de passe). La clé privée SSH reste sur le serveur central. Vérifier l’empreinte SSH du serveur distant lors de la première connexion.
- La clé GitHub de lecture du dépôt sélectionné dans `/etc/oneforall/git/<application>.key`, et les clés d’hôte GitHub vérifiées dans `/root/.ssh/known_hosts`. L’assistant copie cette clé de lecture sur le serveur distant par SSH pour son installation et ses mises à jour.
- Un accès Internet du serveur distant aux dépôts Ubuntu, GitHub et Python pendant l’installation, puis un accès LAN au port configuré (8443 par défaut). Les plages LAN de la configuration centrale sont reprises.

L’assistant demande l’IP privée, le compte et le port SSH, le chemin de la clé SSH locale, le mot de passe sudo distant (saisie masquée, vide pour sudo sans mot de passe) et le mot de passe administrateur de l’application. Les secrets sont transmis dans une archive privée via SSH, jamais dans les arguments de commande ; les fichiers temporaires sont supprimés après la tentative. Une installation échouée peut laisser un socle partiellement configuré : examiner ses journaux et reprendre sur ce serveur ; ne pas contourner le refus d’installation existante.

Le portail propose une adresse HTTPS LAN avec certificat autosigné, à approuver sur les postes clients. DocTrad nécessite ensuite ses modèles locaux et CNC son Python OpenCascade. Le choix **2 — distant déjà installé** conserve son rôle d’enregistrement d’adresse uniquement.

Validation : tests automatisés des adresses SSH et de l’enregistrement conditionné à la réussite. Aucun déploiement SSH réel sur serveur frais n’a été exécuté dans cet environnement.

Le mot de passe sudo reste uniquement en mémoire et est transmis sur l’entrée standard du processus SSH chiffré ; il n’est écrit ni dans un fichier ni dans les arguments. L’archive est transférée séparément pour que sudo ne consomme pas les données du transfert. L’authentification SSH reste effectuée par clé.
