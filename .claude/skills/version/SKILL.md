---
name: version
description: >-
  Changer de version dans LaserAtelier : les SIX estampilles à bumper ensemble en un
  seul commit (laser_core.py, package.xml version+date, docs/index.html, README.md,
  docs/manuel.html ×3, PDF régénéré), le tag, et les chiffres d'effort recalculés aux
  versions mineures. À charger dès qu'une modification de code appelle une nouvelle
  version, ou qu'on cite un numéro de version dans un document.
---

# Changer de version

Source unique : `VERSION` dans `laser_core.py`. Elle est restée **44 versions**
en retard dans un fichier qui la recopiait : c'est l'origine de tout le
rituel, et `tests/test_versions_docs.py` le **contrôle** au lieu d'y croire.

## 1. Faut-il bumper ?

Une modification de code, oui. **Une modification purement documentaire, non.**
Le nombre : correctif → patch, fonctionnalité → mineure.

## 2. Les six estampilles, en UN commit

| fichier | quoi |
|---|---|
| `laser_core.py` | `VERSION = "x.y.z"` |
| `package.xml` | `<version>` **et** `<date>` |
| `docs/index.html` | badge du héros |
| `README.md` | ligne sous le logo |
| `docs/manuel.html` | **3 occurrences** : couverture, frise, signature de fin. Une 4ᵉ mention dans « Thème clair, thème sombre » est une DATE D'ARRIVÉE, elle ne bouge pas |
| `docs/Manuel-LaserAtelier.pdf` | `weasyprint docs/manuel.html docs/Manuel-LaserAtelier.pdf` |

Puis `python3 tests/lancer.py versions` : le test vérifie que les six
s'accordent, que le site annonce autant de modes qu'il montre de cartes, et
que les deux chiffres du journal cités par le README (numéro de chapitre, total
d'entrées) sont ceux du manuel.

## 3. Aux versions mineures : l'effort

```bash
python3 outils/chiffrer_effort.py --html   # héros de docs/index.html
python3 outils/chiffrer_effort.py --md     # README.md et couverture du manuel
```

« ≈ N heures pour en arriver là » se **recalcule**, jamais ne se retape : le
générique du film (223 h) et le site le lisent aussi. L'outil imprime ses
hypothèses avec le chiffre.

## 4. Le tag

`git tag v<version>` sur `main`, poussé avec le commit. Message de commit en
français préfixé par la version (`v2.99.51 — …`), trailer du harnais accepté
(skill `commit-atelier`).

## 5. Ce qui va avec un changement de code

Le skill `atelier-laser` (cadre de travail : cuisiner l'idée, règles non
négociables, contrôle `ast`) et le `CLAUDE.md`, qui restent la référence. Si
ce skill et le `CLAUDE.md` divergent un jour, c'est le `CLAUDE.md` qui a raison
et ce fichier qu'on corrige.
