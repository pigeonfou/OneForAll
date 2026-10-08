# Paramètres administrateur et services sur un autre serveur LAN

Le menu **Paramètres (admin)** de l’accueil LAN permet de choisir, pour chacune des quatre applications, **Serveur OneForAll** ou **Autre serveur LAN**. Renseigner l’URL complète : protocole, IP privée, port éventuel et chemin, par exemple `https://192.168.9.150:8443/doctrad/`.

## Activer l’administration

Sur le serveur OneForAll :

```bash
cd ~/OneForAll
git pull --ff-only origin main &&
sudo bash install-oneforall.sh bootstrap &&
sudo bash install-oneforall.sh portal-admin
```

La dernière commande crée ou réinitialise le compte `admin` du portail, avec une saisie masquée et confirmation (12 caractères minimum). Le menu serveur propose aussi le choix 17. Ce compte est distinct des comptes des applications.

Ouvrir l’accueil HTTPS LAN, puis **Paramètres (admin)**. Le navigateur demande l’identifiant `admin` et le mot de passe choisi. Enregistrer les adresses ; les cartes seront actualisées au prochain contrôle, environ 30 secondes plus tard. En sélectionnant de nouveau **Serveur OneForAll**, le lien local habituel est rétabli.

## Comportement

- Les liens distants fonctionnent même si l’application n’est pas installée sur le serveur OneForAll.
- Le badge **Autre serveur LAN** indique un lien configuré ; il ne garantit pas la disponibilité du serveur distant.
- Le navigateur ouvre directement le service. Aucun proxy, déplacement de données ou installation distante n’est effectué. L’authentification de chaque application reste requise.
- Seules les IP privées IPv4 et IPv6 sont admises. Les noms DNS, IP publiques, identifiants dans l’URL et paramètres sont refusés. HTTP et HTTPS sont possibles ; préférer HTTPS lorsque le service le permet.
- Les adresses distantes et l’administration sont réservées au portail LAN. Les liens du portail public et sa sélection d’applications restent régis par `site.json`.
- Le service `oneforall-portal-admin` n’a aucun droit root et n’écoute que sur un socket Unix. Nginx assure l’authentification et l’ACL LAN ; les écritures vérifient l’origine et un jeton CSRF.
- Les réglages sont enregistrés atomiquement dans `/var/lib/oneforall/portal-admin/services.json` et conservés lors de `bootstrap`. Les sauvegardes applicatives ne les incluent pas : sauvegarder séparément ce fichier et `/etc/oneforall/portal.htpasswd` pour restaurer le portail.

Diagnostic : `sudo systemctl status oneforall-portal-admin --no-pager` et `sudo journalctl -u oneforall-portal-admin -n 50 --no-pager`.
