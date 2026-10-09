# Déploiements DocTrad avec dépendances CPU partagées

DocTrad utilise désormais un ensemble de bibliothèques immuable sous
/opt/oneforall/apps/doctrad/dependencies/<empreinte>.
L'empreinte dépend du verrou CPU dérivé de requirements.lock, de la version de
Python, de son ABI et de l'architecture. Les versions GPU NVIDIA, CUDA et Triton
sont exclues ; PyTorch provient exclusivement de l'index CPU officiel.

Chaque release possède son propre environnement léger et son propre paquet
DocTrad. Un fichier .pth référence les bibliothèques partagées ; aucune mise à
jour du code applicatif ne modifie les bibliothèques des versions précédentes.
Les services uvicorn sont lancés avec le Python de la release.

Le premier déploiement télécharge les dépendances CPU. Les suivants réutilisent
le pool si le verrou et Python sont inchangés. Si la roue CPU demandée est
indisponible ou pip check échoue, le déploiement est arrêté avant activation,
sans bascule automatique sur CUDA.

Les nouvelles sauvegardes excluent .cache pour éviter de recopier les paquets
pip. Documents, modèles, clés et base de données restent sauvegardés.
Les anciens environnements et sauvegardes ne sont pas supprimés automatiquement.

Mise à jour du gestionnaire installé, hors déploiement en cours :

```bash
cd ~/OneForAll
git pull --ff-only origin main
sudo install -o root -g root -m 0644 oneforall/dependencies.py oneforall/deploy.py /opt/oneforall/manager/oneforall/
```

Le gestionnaire applique ces optimisations à la prochaine nouvelle release de
DocTrad. Une release déjà prête est réutilisée telle quelle ; elle n'est jamais
modifiée sous les services actifs.
