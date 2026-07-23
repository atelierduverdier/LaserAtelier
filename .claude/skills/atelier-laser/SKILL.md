---
name: atelier-laser
description: >-
  Développement du workbench FreeCAD « LaserAtelier ». À utiliser dès qu'on
  modifie le code de l'atelier (laser_core.py, task_panels.py, commands.py,
  InitGui.py, docs, README). Rappelle les règles non négociables (tout en
  français, jamais de G4 faisceau allumé, commit+push direct, pas de trailer
  Co-Authored-By) et impose un garde-fou anti-superflu AVANT d'ajouter une
  fonctionnalité.
---

# Atelier LaserAtelier — cadre de travail

## 1. Avant de coder une fonctionnalité : cuisine l'idée

Ne code pas au premier jet. Christophe déteste le superflu (leçon du « Catalogue »
sur-construit, qu'on a dû élaguer). Avant d'écrire du code pour une *nouvelle*
fonctionnalité, passe en revue ces questions — et pose-les-lui quand le doute est réel,
puis attends sa réponse :

- **En as-tu vraiment besoin ?** Quel geste concret à l'atelier ça facilite/remplace ?
- **Ça existe déjà ?** Est-ce que ça double un mode ou un helper présent (voir
  `CLAUDE.md` → Architecture) ?
- **Le plus simple qui marche ?** Propose d'abord la version minimale, pas la complète.
- **Cas limites ?** Géométrie vide, forme à trou, surface courbe, valeurs extrêmes.
- Si tu penses que ça n'est **pas** utile, dis-le franchement *avant* de le construire.

Élaguer > empiler. Une fonctionnalité en moins à tester est une victoire.

## 2. Règles non négociables

- **Tout en français** : code, commentaires, docstrings, chaînes d'UI, tooltips,
  commentaires du G-code généré, **et messages de commit git**. (Seul `CLAUDE.md`
  fait exception.)
- **Jamais de `G4` (dwell) faisceau allumé.** Le HAL scale la puissance par la vitesse
  réelle → puissance forcée à 0 à l'arrêt → un point fait au dwell ne grave **rien**.
  Tout point / pointillé = **micro-trait** (G1 court dont l'avance reproduit le temps
  d'exposition).
- **Commit + push direct sur `main`, sans demander** (dépôt perso
  `github.com/atelierduverdier/LaserAtelier`).
- **Jamais** de trailer `Co-Authored-By`.

## 3. Après chaque édition : vérifie

- Contrôle de syntaxe (le seul garde-fou automatique) :
  `python -c "import ast; [ast.parse(open(f).read()) for f in ('laser_core.py','task_panels.py','commands.py','InitGui.py')]"`
- Si tu as touché à `laser_core.py`, teste en **headless** (stubs FreeCAD/Part, voir
  `CLAUDE.md` → « Working / verifying changes ») plutôt que d'attendre le redémarrage.
- La validation visuelle finale = Christophe qui relance FreeCAD.

## 4. Si tu changes de version

Bumper `VERSION` (dans `laser_core.py`) **ensemble** avec : `<version>` / `<date>` de
`package.xml`, le badge de `docs/index.html`, et la ligne de version du `README`.
Une modification purement doc ne bumpe pas.
