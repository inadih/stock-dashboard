# 📈 Stock Research Dashboard

Un dashboard de recherche boursière, construit avec **Claude Code**, pour analyser :

- les **503 entreprises du S&P 500** ;
- les **semi-conducteurs dans le monde** (38 sociétés aux États-Unis, en Europe et en Asie, sur toute la chaîne de valeur) ;
- les entreprises du **calcul quantique** (acteurs spécialisés et grands groupes ayant un programme quantique).

Il combine les données de marché de **Yahoo Finance** avec les **chiffres officiels déposés à la SEC** (EDGAR), et permet de vérifier chaque chiffre dans le rapport d'origine.

> ⚠️ **Outil d'analyse, pas un conseil en investissement.** Les données peuvent être en retard, incomplètes ou fausses : vérifiez toujours dans les rapports officiels avant de tirer une conclusion.

---

## Sommaire

1. [Installation et lancement](#installation-et-lancement)
2. [Comment ça marche](#comment-ça-marche)
3. [Les onglets](#les-onglets)
4. [Sources de données et limites](#sources-de-données-et-limites)
5. [Étapes de développement](#étapes-de-développement)
6. [Pistes d'amélioration](#pistes-damélioration)

---

## Installation et lancement

**Prérequis :** Python 3.11 ou plus récent, et une connexion internet.

```bash
git clone <url-du-depot>
cd stock-dashboard
python -m venv .venv
```

Activez l'environnement puis installez les dépendances :

```bash
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Lancez l'application :

```bash
streamlit run app.py
```

Elle s'ouvre dans le navigateur à l'adresse <http://localhost:8501>. Sous Windows, un double-clic sur `lancer.bat` fait la même chose une fois l'installation faite.

Le premier chargement du S&P 500 prend environ 30 secondes (503 entreprises). Les données sont ensuite gardées en cache.

### Optionnel : identifiant SEC

La SEC demande aux utilisateurs de ses API de s'identifier. Le dashboard utilise un identifiant générique par défaut. Si la SEC refuse les requêtes, définissez votre propre identifiant :

```bash
# Windows (PowerShell)
$env:SEC_USER_AGENT = "Prénom Nom votre@email.com"
# macOS / Linux
export SEC_USER_AGENT="Prénom Nom votre@email.com"
```

---

## Comment ça marche

### Organisation du code

| Fichier | Rôle |
|---|---|
| `app.py` | L'interface Streamlit : barre latérale, onglets, graphiques et tableaux. |
| `universes.py` | La liste des entreprises de chaque univers. Le S&P 500 est lu sur Wikipedia ; les semi-conducteurs et le quantique sont des listes choisies à la main. |
| `data.py` | Les données Yahoo Finance : fiches entreprises, cours, performances, comptes, conversion en dollars. |
| `sec.py` | Les données SEC EDGAR : recherche de l'identifiant SEC, lecture des faits XBRL, reconstitution des trimestres, liens vers les rapports. |
| `lancer.bat` | Raccourci de lancement sous Windows. |

### Le chemin des données

```
Wikipedia ─┐
           ├─► universes.py ─► liste des tickers
Listes     ┘                         │
manuelles                            ▼
                    Yahoo Finance ─► data.py ──► tableau comparatif (onglets 1 et 2)
                                       │
                    SEC EDGAR ──────► sec.py ──► comptes officiels (onglet 3)
                                       │
                                       ▼
                                    app.py (Streamlit)
```

1. **Choix de l'univers.** `universes.py` renvoie la liste des tickers. Pour les sociétés étrangères, on utilise le ticker de la place de cotation principale (`ASML.AS`, `2330.TW`, `8035.T`…).
2. **Fiches entreprises.** `data.py` récupère pour chaque ticker la capitalisation, le chiffre d'affaires, les marges, les multiples (P/E, VE/EBITDA), le free cash flow, la trésorerie et la dette. Les requêtes partent en parallèle (4 à la fois).
3. **Conversion en dollars.** Chaque montant est converti avec le taux de change du jour (`EURUSD=X`, `TWDUSD=X`…), pour comparer TSMC à NVIDIA ou ASML à Applied Materials.
4. **Performances.** Les cours des deux dernières années sont téléchargés en une seule requête, puis on calcule les performances à 1 mois, depuis le 1er janvier et à 1 an.
5. **Comptes officiels.** Pour la fiche entreprise, `sec.py` lit les données XBRL déposées à la SEC et les remet en forme (détails dans l'onglet 3 ci-dessous).

### Les caches

Pour aller vite et ne pas surcharger les serveurs :

| Donnée | Où | Durée |
|---|---|---|
| Composition du S&P 500 | `data/sp500.csv` | 7 jours |
| Fiches Yahoo | `data/cache/` | 24 heures |
| Données SEC | `data/sec/` | 24 heures |
| Tableau d'un univers | mémoire de la session | 1 heure |

Le bouton **🔄 Rafraîchir les données** vide le cache de la session. Pour tout recharger, supprimez le dossier `data/`.

---

## Les onglets

La **barre latérale** sert à choisir l'univers (S&P 500, semi-conducteurs ou quantique) et à filtrer par secteur ou par segment. Le filtre s'applique aux trois onglets.

### 1. Vue d'ensemble

Une photo de l'univers en un coup d'œil.

- **Chiffres clés :** nombre d'entreprises avec des données, capitalisation totale, P/E prévisionnel médian et croissance médiane du chiffre d'affaires.
- **Carte des capitalisations :** chaque case est une entreprise, regroupée par secteur. La **taille** correspond à la capitalisation en dollars et la **couleur** à la performance depuis le 1er janvier (rouge = baisse, vert = hausse). On voit tout de suite qui pèse lourd et qui a monté ou baissé.
- **Tableau comparatif :** toutes les entreprises avec capitalisation, chiffre d'affaires sur 12 mois, croissance, marge brute et marge opérationnelle, P/E, P/E prévisionnel, VE/EBITDA, rendement du free cash flow, trésorerie nette et performances. Cliquez sur une colonne pour trier.
- **Export CSV** du tableau, pour le reprendre dans Excel ou Power BI.

### 2. Comparer

Pour positionner les entreprises les unes par rapport aux autres.

- **Graphique à bulles :** vous choisissez l'indicateur de chaque axe, par exemple croissance du chiffre d'affaires contre P/E prévisionnel. La taille des bulles correspond à la capitalisation et la couleur au segment. C'est utile pour repérer une entreprise chère et peu dynamique, ou l'inverse.
- **Classement :** les 30 premières entreprises selon l'indicateur choisi.

Bon à savoir : un **P/E négatif** veut dire que l'entreprise perd de l'argent (c'est le cas de la plupart des spécialistes du quantique). Les valeurs extrêmes peuvent écraser le graphique : zoomez à la souris.

### 3. Fiche entreprise

L'analyse détaillée d'une entreprise.

- **Indicateurs clés :** capitalisation, chiffre d'affaires sur 12 mois et sa croissance, marge opérationnelle, P/E prévisionnel, free cash flow et trésorerie nette.
- **Cours de bourse** sur 6 mois, 1 an, 2 ans, 5 ans ou depuis l'introduction, avec les **moyennes mobiles 50 et 200 jours**.
- **Comptes trimestriels ou annuels**, au choix entre deux sources :
  - **SEC EDGAR (officiel)**, proposé par défaut quand l'entreprise dépose à la SEC ;
  - **Yahoo Finance** dans les autres cas, ou au choix.
- **Ratios de qualité des résultats :**
  - *Capex / amortissements* : environ 1 pour une entreprise mature, nettement au-dessus en phase d'investissement lourd ;
  - *Part du capex financée par l'activité* : sous 100 %, l'entreprise doit trouver de l'argent ailleurs (dette, augmentation de capital) ;
  - *Rémunération en actions / chiffre d'affaires* : quand elle est élevée et augmente, elle gonfle les résultats « ajustés » ;
  - *R&D / chiffre d'affaires*.
- **Comptes détaillés**, en millions dans la devise de publication.
- **🔗 Rapport SEC d'origine de chaque période :** un lien vers le 10-Q ou le 10-K d'où vient le chiffre.
- **🔍 Contrôle croisé Yahoo / SEC :** compare les deux sources sur le dernier trimestre et signale tout écart de plus de 2 %. En cas de désaccord, c'est la SEC qui fait foi.
- **📄 Derniers rapports déposés à la SEC**, avec un lien de lecture.
- **Description de l'activité** de l'entreprise.

#### Comment les trimestres SEC sont reconstitués

Les rapports trimestriels (10-Q) donnent souvent les flux de trésorerie **en cumul depuis le début de l'exercice** (3, 6 puis 9 mois), et le 4e trimestre n'existe que dans le rapport annuel (10-K). `sec.py` reconstitue donc chaque trimestre seul :

- T2 = cumul 6 mois − cumul 3 mois ;
- T3 = cumul 9 mois − cumul 6 mois ;
- T4 = année complète − cumul 9 mois.

Quand une même période apparaît dans plusieurs rapports (chiffres retraités), c'est le rapport le plus récent qui l'emporte.

---

## Sources de données et limites

| Source | Ce qu'elle apporte | Limites |
|---|---|---|
| **Yahoo Finance** (bibliothèque `yfinance`) | Cours, capitalisations, multiples, comptes de toutes les places boursières | Données non officielles, parfois en retard ou fausses ; les définitions varient (le free cash flow, par exemple) ; Yahoo peut limiter le nombre de requêtes |
| **SEC EDGAR** (API XBRL) | Chiffres officiels déposés par les entreprises, avec lien vers le rapport | Uniquement les sociétés qui déposent à la SEC |
| **Wikipedia** | Composition à jour du S&P 500 | Dépend de la mise à jour de la page |

**Couverture SEC selon les entreprises :**

| Entreprises | Couverture |
|---|---|
| S&P 500 et sociétés américaines (dont le quantique) | ✅ Trimestriel et annuel |
| TSMC, ASML, UMC, ASE, STMicro (via leurs ADR) | ⚠️ Annuel seulement (rapport 20-F), parfois en retard |
| Samsung, SK hynix, Tokyo Electron, Infineon… | ❌ Pas de rapports SEC : données Yahoo uniquement |

---

## Étapes de développement

Le projet a été construit pas à pas avec **Claude Code**, dans le cadre d'une formation.

1. **Inspiration.** Une vidéo de Wall Street Prep (*How to Build INSANE Stock Research Dashboards with Claude*) montre un dashboard sur SpaceX construit en une heure à partir des données gratuites de SEC EDGAR. Les auteurs soulignent trois limites : chiffres non vérifiés, pas de cours de bourse, pas de lien vers les sources. Ce projet part de là et cherche à les corriger.
2. **Choix techniques.**
   - **Python + Streamlit** pour une application locale qui récupère les données en direct, plutôt qu'une page statique figée.
   - **yfinance** comme source gratuite couvrant toutes les places boursières.
   - **Plotly** pour des graphiques interactifs (zoom, survol).
3. **Univers d'entreprises** (`universes.py`).
   - S&P 500 lu sur Wikipedia et mis en cache ; les tickers sont adaptés au format Yahoo (`BRK.B` → `BRK-B`).
   - Semi-conducteurs : liste manuelle sur toute la chaîne de valeur (conception, fonderie, mémoire, équipements, logiciels de conception), avec les tickers des places locales.
   - Quantique : acteurs spécialisés et grands groupes.
4. **Couche de données** (`data.py`).
   - Requêtes en parallèle avec nouvelles tentatives en cas d'échec.
   - Cache disque de 24 heures.
   - Conversion en dollars : taux de change du jour, en distinguant la devise de cotation de la devise des comptes, et en gérant les cotations en pence de Londres.
   - Calcul des performances.
5. **Interface** (`app.py`).
   - Barre latérale (univers, filtres) et trois onglets.
   - Ratios de qualité des résultats inspirés de la vidéo (capex / amortissements, rémunération en actions, etc.).
6. **Tests dans le navigateur.** Chargement des trois univers, vérification de chaque onglet, remplacement d'un paramètre Streamlit obsolète (`use_container_width` → `width`), indicateurs de la fiche répartis sur deux lignes pour rester lisibles.
7. **Intégration de SEC EDGAR** (`sec.py`).
   - **Identifiant SEC :** la liste officielle des tickers exige un email de contact ; on passe donc par le moteur de recherche d'EDGAR pour trouver l'identifiant (CIK) d'une entreprise.
   - **Sociétés étrangères :** correspondance avec leurs ADR (TSMC → TSM, ASML…).
   - **Faits XBRL :** lecture des normes US GAAP et IFRS, devise principale de publication détectée automatiquement.
   - **Trimestres :** reconstitution des trimestres seuls à partir des cumuls.
   - **Traçabilité :** lien vers le rapport source de chaque période, contrôle croisé avec Yahoo et liste des derniers rapports.
8. **Correction d'un bug.** La barre de progression affichée pendant le chargement d'un univers empêchait Streamlit de mettre ce chargement en cache, ce qui bloquait le changement d'univers. Le cache est désormais géré dans la session.

---

## Pistes d'amélioration

- **Cours annoté** : publications de résultats, introduction en bourse, fins de période de blocage, entrée dans un indice.
- **Graphiques cliquables** qui expliquent chaque barre.
- **Données de marché complémentaires** : volumes, grosses transactions, consensus des analystes.
- **Sources officielles hors États-Unis** pour les sociétés européennes et asiatiques.
- **Alertes** quand de nouveaux résultats sont publiés.

---

*Construit avec [Claude Code](https://claude.com/claude-code).*
