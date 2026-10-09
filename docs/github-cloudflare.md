# GitHub Actions et Cloudflare

## Dépôts et branches

Les applications sont récupérées depuis leur branche `main`. Le fichier `config/apps.json` est la source commune des dépôts et services. Les changements proposés ne doivent pas être fusionnés automatiquement dans les branches principales.

Créer `pigeonfou/OneForAll`, idéalement privé puisque les autres applications ne sont pas toutes publiques. Initialiser `main`, publier les fichiers, puis donner accès au connecteur GitHub utilisé pour le travail. Le dépôt contient deux workflows : contrôles sur runner hébergé Ubuntu 24.04 et déploiement manuel sur runner du serveur.

## Lecture des dépôts privés depuis le serveur

Le serveur utilise des clés de déploiement **en lecture seule**, une par dépôt privé. Les clés ne sont pas celles du runner GitHub Actions.

```bash
sudo install -d -m 0700 /etc/oneforall/git
sudo ssh-keygen -t ed25519 -N '' -C oneforall-cableplan -f /etc/oneforall/git/cableplan.key
sudo ssh-keygen -t ed25519 -N '' -C oneforall-doctrad -f /etc/oneforall/git/doctrad.key
sudo cat /etc/oneforall/git/cableplan.key.pub
sudo cat /etc/oneforall/git/doctrad.key.pub
```

Ajouter chaque clé **publique** dans le dépôt correspondant, Settings → Deploy keys → Add deploy key, sans autoriser l’écriture. Une clé doit être distincte pour chaque dépôt. Ne pas copier les clés privées dans GitHub, dans une conversation ou dans OneForAll. Si des clés de lecture existent déjà, les réutiliser en les installant sous les chemins attendus, sans les régénérer.

L’installateur utilise SSH sur `ssh.github.com:443` si `/etc/oneforall/git/<id>.key` existe ; sinon il utilise HTTPS. Si un miroir a déjà été créé avec un autre accès, ajuster explicitement son remote/config Git au lieu d’introduire des secrets dans l’URL.

Vérifier la clé de l’hôte SSH GitHub avant de l’ajouter au `known_hosts` de root. Les empreintes officielles sont publiées ici :

https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints

```bash
ssh-keyscan -p 443 ssh.github.com > /tmp/oneforall-github-hosts
ssh-keygen -lf /tmp/oneforall-github-hosts
# Après comparaison des empreintes avec la documentation officielle :
sudo install -d -m 0700 /root/.ssh
sudo sh -c 'cat /tmp/oneforall-github-hosts >> /root/.ssh/known_hosts'
sudo chmod 0600 /root/.ssh/known_hosts
rm /tmp/oneforall-github-hosts
```

Tester la lecture avec la clé correspondante. Le message SSH « authenticated, but GitHub does not provide shell access » est normal ; `git ls-remote` est le contrôle utile.

## Installer le runner OneForAll

Après installation du socle :

```bash
sudo bash install-oneforall.sh setup-runner
sudo install -d -o oneforall-runner -g oneforall-runner -m 0750 /opt/oneforall-runner
```

Dans `pigeonfou/OneForAll` : Settings → Actions → Runners → New self-hosted runner → Linux x64. Utiliser l’archive et l’empreinte fournies par GitHub à ce moment-là. Télécharger et vérifier cette archive, puis la décompresser dans `/opt/oneforall-runner` sous l’utilisateur `oneforall-runner`. Ne pas utiliser un numéro de version de runner copié d’un ancien guide.

Ouvrir un shell sous ce compte pour l’enregistrement :

```bash
sudo -u oneforall-runner -H bash
cd /opt/oneforall-runner
read -rsp 'Token temporaire du runner : ' OFA_RUNNER_TOKEN
printf '\n'
./config.sh --url https://github.com/pigeonfou/OneForAll --token "$OFA_RUNNER_TOKEN" --name oneforall-ubuntu --labels oneforall --unattended
unset OFA_RUNNER_TOKEN
exit
cd /opt/oneforall-runner
sudo ./svc.sh install oneforall-runner
sudo ./svc.sh start
sudo ./svc.sh status
```

Enregistrer le runner au niveau du **dépôt OneForAll**, pour que les workflows des autres dépôts ne lui soient pas attribués. Les autres runners peuvent rester en place pendant la migration.

Le runner ne reçoit qu’une commande sudo : `/usr/local/sbin/oneforall-deploy APP SHA`. Le helper, installé sous root, valide l’application et le SHA, puis vérifie que ce SHA est la tête de la branche `main` configurée. Il ne reçoit pas de chemin de script ni de fichier de configuration fourni par le runner. Le workflow ne fait pas de checkout d’une pull request sur le serveur.

Créer l’environnement GitHub `production` avec les restrictions adaptées à vos habitudes d’approbation. Le workflow de déploiement accepte uniquement `main` et doit être déclenché avec un commit dont les contrôles sont réussis et dont les adaptations ont été examinées. Une pull request externe ne déclenche aucun déploiement de production.

## Déployer une mise à jour

1. Pousser le changement applicatif dans `main` et vérifier les contrôles de cette branche.
2. Dans OneForAll → Actions → Deploy selected OneForAll application → Run workflow.
3. Choisir l’application et le SHA complet de 40 caractères approuvé.
4. Le helper prépare la version, sauvegarde, migre, redémarre, contrôle HTTP et publie les états du portail.
5. Vérifier les parcours métier après le déploiement. Consulter les journaux ou restaurer la sauvegarde si une régression apparaît.

La première installation des dépendances, comptes et modèles passe par le menu serveur. Le runner sert ensuite à mettre à jour les applications déjà installées.

Le gestionnaire privilégié OneForAll lui-même se met à jour depuis une copie contrôlée du dépôt par un administrateur : pull de `main`, revue du changement, puis choix 2 / commande `bootstrap`. Le runner applicatif n’est pas autorisé à remplacer son propre programme root.

## Tunnel Cloudflare

Ne pas exécuter `cloudflared service install` sur un serveur dont le service global est déjà utilisé par un autre projet. OneForAll crée son propre service `oneforall-cloudflared` et conserve les tunnels existants.

Installer `cloudflared` depuis la distribution officielle si absent. `--token-file` exige une version compatible (Cloudflare documente cette option à partir de 2025.4.0) :

https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/

Créer un tunnel dédié dans Cloudflare, puis une route publiée pour chaque nom voulu :

| Hostname | Service local | HTTP Host Header |
|---|---|---|
| `www.pigeonfou.com` | `http://127.0.0.1:18080` | `www.pigeonfou.com` |
| `cableplan.pigeonfou.com` | même service | `cableplan.pigeonfou.com` |
| `doctrad.pigeonfou.com` | même service | `doctrad.pigeonfou.com` |
| `oddworks.pigeonfou.com` | même service | `oddworks.pigeonfou.com` |
| `cnctolequotation.pigeonfou.com` | même service | `cnctolequotation.pigeonfou.com` |

Si le port tunnel est modifié dans `site.json`, adapter le service des routes. Appliquer HTTPS à l’entrée publique. Les CNAME sont ceux du tunnel créé ; ne pas réutiliser un UUID inventé. Éviter une route wildcard qui exposerait des noms non prévus.

Activer le frontal public dans le JSON et sélectionner explicitement les applications :

```json
"public_enabled": true,
"public_apps": ["cableplan", "doctrad", "oddworks", "cnctolequotation"]
```

Puis réappliquer la configuration :

```bash
sudo bash install-oneforall.sh configure --config "$PWD/site.json"
```

Enregistrer le token dans un fichier root privé via une saisie masquée et démarrer le tunnel :

```bash
sudo python3 - <<'PY'
import getpass, os
value=getpass.getpass('Token du tunnel OneForAll : ')
fd=os.open('/root/oneforall-tunnel-token',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f: f.write(value)
PY
sudo bash install-oneforall.sh cloudflare --token-file /root/oneforall-tunnel-token
sudo rm /root/oneforall-tunnel-token
sudo systemctl status oneforall-cloudflared --no-pager
```

Activer également l’autorisation distante dans les paramètres CablePlan depuis le LAN. Si elle reste désactivée, CablePlan retourne 403 sur l’entrée tunnel même si Nginx et Cloudflare sont configurés.

Ouvrir ensuite `https://www.pigeonfou.com`, se connecter à chaque application et effectuer la recette. L’existence d’un service systemd ou d’un CNAME ne suffit pas à déclarer la publication fonctionnelle.

## Branches après intégration dans main

Les adaptations OneForAll sont fusionnées dans `main` des quatre applications. Le catalogue récupère désormais `refs/heads/main`, pour les deux modes d’installation. Les branches `OneForAll` et les anciennes branches sont conservées comme historique ; les nouveaux développements de la version intégrée visent `main`.

Avant le prochain déploiement applicatif, mettre à jour le gestionnaire privilégié et son catalogue :

```bash
cd ~/OneForAll
git pull --ff-only origin main &&
sudo bash install-oneforall.sh bootstrap &&
sudo bash install-oneforall.sh status
```

Cette opération ne réinstalle pas les applications. Les sauvegardes et versions restent identifiées par SHA et restent restaurables. Un déploiement OneForAll exige le SHA exact de la tête `main`, après contrôles. Les runners historiques ciblent uniquement leurs instances autonomes.
