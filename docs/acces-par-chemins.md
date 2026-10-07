# Portail et applications sur une route Cloudflare

Le mode `routing_mode: "paths"` sert les applications installées sous
`https://www.pigeonfou.com/<id>/`. Une seule route Cloudflare est nécessaire :
`www.pigeonfou.com` → HTTP `127.0.0.1:18080`, Host Header `www.pigeonfou.com`.
Ne pas supprimer la route du portail. Les autres routes Cloudflare deviennent facultatives.

Accès LAN sans DNS : `https://<lan_ip>:<lan_port>/`, par exemple
`https://192.168.9.132:8443/`. Nginx conserve l'ACL des réseaux locaux.
Le certificat local est autosigné ; les certificats existants sont conservés et peuvent
ne pas inclure l'adresse IP. Le navigateur peut donc demander une exception locale.
Ne pas ouvrir le port LAN au réseau Internet.

## Appliquer sur une installation existante

Mettre à jour le gestionnaire depuis `main` et CablePlan/DocTrad depuis `AllFortOne`
avant d'activer ce mode. Les nouvelles versions restent compatibles avec le mode racine.
Les commandes `update` sauvegardent chaque application et sa base avant le changement.

```bash
cd ~/OneForAll
git pull --ff-only origin main
sudo bash install-oneforall.sh bootstrap
sudo bash install-oneforall.sh update --apps cableplan,doctrad
python3 -c 'import json; from pathlib import Path; p=Path("site.json"); c=json.loads(p.read_text()); c["routing_mode"]="paths"; p.write_text(json.dumps(c, indent=2)+"\n")'
sudo bash install-oneforall.sh configure --config "$PWD/site.json"
sudo bash install-oneforall.sh bootstrap
sudo bash install-oneforall.sh status
```

La configuration met à jour les environnements, les chemins des cookies PHP et Python,
et redémarre les services concernés. Les configurations précédentes sont conservées
sous `/var/backups/oneforall/routing-<date>/` en accès root uniquement.
En cas d'échec d'application, les configurations des services sont rétablies.
Le portail et les contrôles de santé utilisent les préfixes, et le portail LAN fournit
des liens avec l'adresse IP. Une reconnexion aux applications est nécessaire.

CablePlan conserve son contrôle `allow_tunnel_access` : le préfixe public ne le contourne
pas. Utiliser le portail LAN pour ouvrir `/cableplan/`, se connecter et choisir l'accès
Internet dans les paramètres réseau. Le canal est fixé par Nginx, sans faire confiance
au canal fourni par le navigateur. DocTrad reste hors ligne pour ses traductions.

## Retour au mode sous-domaines

Changer `routing_mode` en `subdomains`, réappliquer `configure`, puis `bootstrap`.
Restaurer les routes Cloudflare correspondantes et vérifier `status`.
Le changement de routage seul ne modifie pas les bases. Si l'on revient aussi à une
ancienne version applicative, utiliser les sauvegardes de déploiement avec la commande
`restore` et sa base associée, plutôt qu'un simple changement de code.

## Validation

Tests du gestionnaire et tests web locaux Python exécutés ; contrôles natifs Nginx et
PHP-FPM exécutés sur les exécutables extraits Ubuntu 24.04. Ceci ne constitue pas une
validation serveur Ubuntu 24.04 ou 26.04. La recette sur le serveur et la route Cloudflare
reste nécessaire : connexions, pages, téléchargements, accès LAN et restrictions publiques.
