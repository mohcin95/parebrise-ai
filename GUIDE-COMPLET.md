# V-Glass Auto AI Agent — Guide Complet Pas à Pas

---

## ÉTAPE 1 : Créer le repo GitHub

### 1.1 — Ouvre GitHub dans ton navigateur

Va sur : **https://github.com/new**

### 1.2 — Remplis les champs

- **Repository name** : `parebrise-ai`
- **Description** : `V-Glass Auto — AI Voice Agent`
- **Visibility** : choisis **Private** (c'est ton business)
- **NE COCHE RIEN** d'autre (pas de README, pas de .gitignore, rien)

### 1.3 — Clique sur **Create repository**

GitHub te montre une page avec des instructions. Garde cette page ouverte, on en aura besoin.

---

## ÉTAPE 2 : Télécharger les fichiers depuis Claude

### 2.1 — Télécharge le dossier

Dans cette conversation, tu as reçu le dossier `parebrise-ai` avec tous les fichiers. Télécharge-le sur ton Mac/PC.

### 2.2 — Vérifie que tu as tout

Ouvre le dossier, tu dois voir :

```
parebrise-ai/
├── .gitignore
├── README.md
├── voice_server.py
├── static/
│   └── index.html
├── prompts/
│   ├── inbound.txt
│   ├── outbound.txt
│   └── scheduler.txt
├── data/
│   ├── config.json
│   └── prospects.csv
└── scripts/
    ├── install-test.sh
    └── install-full.sh
```

---

## ÉTAPE 3 : Push les fichiers sur GitHub

### 3.1 — Ouvre le Terminal sur ton Mac

Appuie sur **Cmd + Espace**, tape **Terminal**, et ouvre-le.

### 3.2 — Va dans le dossier téléchargé

```bash
cd ~/Downloads/parebrise-ai
```

> Si le dossier est ailleurs, adapte le chemin.

### 3.3 — Initialise Git et pousse

Tape ces commandes une par une :

```bash
git init
```

```bash
git add .
```

```bash
git commit -m "V-Glass Auto AI Agent v1.0"
```

```bash
git remote add origin https://github.com/mohcin95/parebrise-ai.git
```

```bash
git branch -M main
```

```bash
git push -u origin main
```

> Si Git te demande un mot de passe, utilise un **Personal Access Token** :
> - Va sur https://github.com/settings/tokens
> - Clique **Generate new token (classic)**
> - Coche **repo**
> - Copie le token et utilise-le comme mot de passe

### 3.4 — Vérifie

Va sur **https://github.com/mohcin95/parebrise-ai** — tu dois voir tous tes fichiers.

---

## ÉTAPE 4 : Lancer un Pod RunPod

### 4.1 — Connecte-toi à RunPod

Va sur **https://www.runpod.io** et connecte-toi.

### 4.2 — Crée un nouveau Pod

- Clique sur **+ Deploy** ou **GPU Pods**
- Choisis ton GPU : **NVIDIA A40 48GB**
- Template : **RunPod PyTorch 2.4.0** (`runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`)

### 4.3 — Configure les ports

Avant de lancer le pod :
- Cherche le champ **Expose TCP Ports** ou **TCP Public Services**
- Ajoute : `8880, 5678`
  - `8880` = interface voix V-Glass Auto
  - `5678` = n8n (workflows)

### 4.4 — (Recommandé) Attache un Network Volume

- Clique sur **Network Volume** → **Create**
- Taille : **50 GB** minimum (pour stocker les modèles Ollama)
- Mount path : `/workspace`
- Sans ça, tout est perdu quand tu stop le pod

### 4.5 — Lance le Pod

Clique **Deploy**. Attends que le statut passe à **Running** (1-2 minutes).

---

## ÉTAPE 5 : Se connecter au Pod

### 5.1 — Ouvre le Web Terminal

Dans RunPod, clique sur ton pod → **Connect** → **Web Terminal**

Un terminal s'ouvre dans ton navigateur. Tu es maintenant dans ton serveur.

### 5.2 — Vérifie le GPU

Tape :

```bash
nvidia-smi
```

Tu dois voir :

```
NVIDIA A40    | 48GB
```

---

## ÉTAPE 6 : Installer V-Glass Auto

### 6.1 — Clone le repo

```bash
cd ~
git clone https://github.com/mohcin95/parebrise-ai.git
```

> Si le repo est privé, Git te demandera tes identifiants.
> Username : `mohcin95`
> Password : ton Personal Access Token (pas ton mot de passe GitHub)

### 6.2 — Lance l'installation

```bash
cd parebrise-ai
chmod +x scripts/install-test.sh
./scripts/install-test.sh
```

### 6.3 — Ce qui se passe (attends ~15-20 min)

Le script va :

```
✅ 1/8  Installer curl, nodejs, npm, postgresql, ffmpeg, supervisor
✅ 2/8  Installer Ollama (moteur LLM)
✅ 3/8  Installer n8n (orchestration workflows)
✅ 4/8  Installer les paquets Python (Whisper, Kokoro, FastAPI)
✅ 5/8  Installer Qdrant (base de données vectorielle)
✅ 6/8  Démarrer PostgreSQL + Redis
✅ 7/8  Configurer Supervisor (gère tous les services)
✅ 8/8  Télécharger le modèle Qwen3 8B (~5GB, ~5 min)
```

### 6.4 — Vérifie que tout tourne

```bash
supervisorctl status
```

Tu dois voir :

```
ollama    RUNNING   pid 1234, uptime 0:05:00
n8n       RUNNING   pid 1235, uptime 0:04:00
voice     RUNNING   pid 1236, uptime 0:03:00
qdrant    RUNNING   pid 1237, uptime 0:03:00
```

Si un service montre **FATAL** ou **STOPPED** :

```bash
supervisorctl tail voice stderr
```

Ça te montre l'erreur. Souvent il suffit de relancer :

```bash
supervisorctl restart voice
```

---

## ÉTAPE 7 : Trouver l'URL publique

### 7.1 — Retourne dans RunPod

Va dans le dashboard RunPod → clique sur ton pod.

### 7.2 — Trouve l'URL du port 8880

Tu verras quelque chose comme :

```
TCP Port Mappings:
  8880 → https://xxxxx-8880.proxy.runpod.net
  5678 → https://xxxxx-5678.proxy.runpod.net
```

### 7.3 — Copie le lien du port 8880

C'est ton lien **V-Glass Auto AI**. Par exemple :

```
https://abc123def-8880.proxy.runpod.net
```

---

## ÉTAPE 8 : Tester toi-même

### 8.1 — Ouvre le lien dans ton navigateur

Colle l'URL du port 8880 dans Chrome/Safari sur ton téléphone ou PC.

Tu vas voir l'interface **V-Glass Auto** avec un micro et un champ texte.

### 8.2 — Test avec le texte d'abord

Tape dans le champ texte :

```
Bonjour, j'ai un impact sur mon pare-brise
```

L'agent doit répondre quelque chose comme :

> *"Bonjour, V-Glass Auto ! Chez nous, on fait uniquement du remplacement complet de pare-brise. Quel est votre véhicule ?"*

Et tu entendras la voix en même temps.

### 8.3 — Test avec le micro

- Clique sur le bouton **🎤**
- Il devient **🔴 rouge** = il enregistre
- Dis : *"Bonjour, j'ai besoin de changer mon pare-brise"*
- Clique à nouveau sur le micro pour arrêter
- Attends 5-10 secondes
- L'agent répond vocalement

### 8.4 — Teste une conversation complète

Essaie ce scénario :

```
Toi : "Bonjour, j'ai un éclat sur mon pare-brise"
Agent : (explique qu'on remplace, demande le véhicule)

Toi : "C'est une Peugeot 308 de 2022"
Agent : (demande si assurance bris de glace)

Toi : "Oui j'ai la MAIF"
Agent : (explique la prise en charge, propose un RDV)

Toi : "Oui, jeudi matin si possible"
Agent : (confirme le créneau, demande l'adresse)
```

---

## ÉTAPE 9 : Envoyer le lien à quelqu'un d'autre

### 9.1 — Copie l'URL

```
https://xxxxx-8880.proxy.runpod.net
```

### 9.2 — Envoie par WhatsApp/Telegram/SMS

Envoie un message comme :

> *"Salut, teste notre nouvel agent vocal V-Glass Auto. Ouvre ce lien et parle au micro ou tape un message : https://xxxxx-8880.proxy.runpod.net"*

### 9.3 — Ce que la personne doit faire

1. Ouvrir le lien dans Chrome/Safari
2. Le navigateur va demander l'accès au micro → **Autoriser**
3. Appuyer sur 🎤 et parler
4. Ou taper un message

> **⚠️ Important** : Le micro ne marche que en HTTPS. L'URL RunPod est déjà en HTTPS, donc c'est bon.

---

## ÉTAPE 10 : Commandes utiles

### Voir les logs en temps réel

```bash
# Logs du serveur vocal
supervisorctl tail -f voice

# Logs Ollama (LLM)
supervisorctl tail -f ollama

# Logs n8n
supervisorctl tail -f n8n
```

### Redémarrer un service

```bash
supervisorctl restart voice
supervisorctl restart ollama
supervisorctl restart n8n
```

### Voir la VRAM utilisée

```bash
nvidia-smi
```

### Tester le TTS manuellement

```bash
curl http://localhost:8880/speak \
  -H 'Content-Type: application/json' \
  -d '{"input":"Bonjour, V-Glass Auto à votre service"}' \
  -o test.wav
```

### Tester le LLM manuellement

```bash
curl http://localhost:11434/api/chat \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"Salut, combien coûte un remplacement de pare-brise ?"}]}'
```

### Modifier le comportement de l'agent

```bash
nano ~/parebrise-ai/prompts/inbound.txt
```

Modifie le texte, puis :

```bash
supervisorctl restart voice
```

L'agent utilise le nouveau prompt immédiatement.

### Télécharger le modèle lourd (optionnel)

```bash
ollama pull llama3:70b-instruct-q4_K_M
```

~40GB, prend 30-60 min. Meilleur raisonnement pour les tâches complexes.

---

## ÉTAPE 11 : Arrêter / Reprendre

### Arrêter le pod (économiser de l'argent)

Dans RunPod → **Stop Pod**

> Si tu as un Network Volume, tes données sont sauvegardées.
> Sans Network Volume, TOUT est perdu. Tu devras refaire l'étape 6.

### Relancer après un stop

Si tu as un Network Volume, reconnecte-toi au terminal et :

```bash
cd ~/parebrise-ai
./scripts/install-test.sh
```

Le script détecte ce qui est déjà installé et relance juste les services.

---

## RÉSUMÉ RAPIDE

| Étape | Action | Temps |
|-------|--------|-------|
| 1 | Créer repo GitHub | 2 min |
| 2 | Télécharger les fichiers | 1 min |
| 3 | Push sur GitHub | 3 min |
| 4 | Lancer pod RunPod | 2 min |
| 5 | Ouvrir Web Terminal | 1 min |
| 6 | `git clone` + `install-test.sh` | 15-20 min |
| 7 | Copier l'URL publique | 1 min |
| 8 | Tester | 5 min |
| 9 | Envoyer le lien | 30 sec |
| **Total** | | **~30 min** |

---

## EN CAS DE PROBLÈME

### Le micro ne marche pas
→ Vérifie que l'URL est en **https://** (pas http)
→ Le navigateur doit demander l'accès au micro → clique **Autoriser**
→ Sur iPhone Safari, ça peut être capricieux. Essaie Chrome.

### L'agent ne répond pas
```bash
supervisorctl status          # tout est RUNNING ?
supervisorctl tail voice stderr   # erreur Python ?
curl http://localhost:11434/api/tags   # Ollama tourne ?
```

### "Model not found"
```bash
ollama list                   # vérifie que qwen3:8b est là
ollama pull qwen3:8b          # re-télécharge si besoin
```

### Le service "voice" crash en boucle
```bash
supervisorctl tail voice stderr
```
Souvent c'est un paquet Python manquant :
```bash
pip install [paquet_manquant] --break-system-packages
supervisorctl restart voice
```

### Port 8880 pas accessible
→ Vérifie dans RunPod Settings que le port 8880 est bien dans **TCP Public Services**
→ Parfois il faut attendre 1-2 min après le démarrage
