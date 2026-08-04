# -*- coding: utf-8 -*-
"""Les 44 polices MONO-TRAIT de l'atelier, une par module.

Ce sont des DONNÉES, pas du code : chaque module y expose `GLYPHES`
(caractère → (avance, [traits])), `CAP_HEIGHT` et `ADV_DEFAULT`, produits
par `outils/generer_police_monotrait.py` depuis un SVG mono-trait libre.
Provenances et licences : `licences/POLICES.md`.

POURQUOI UN DOSSIER. Elles étaient à la racine, où elles noyaient les sept
modules du workbench sous quarante-quatre fichiers de données -- « j'ai vu
que dans le dépôt toutes les hershey_font étaient à la racine » (Christophe,
04/08/2026). Le rangement a un second effet, moins visible et plus utile :
FreeCAD met CHAQUE dossier de `Mod/` sur `sys.path`, si bien que tout module
à la racine d'un workbench occupe un nom GLOBAL, partagé avec tous les
autres ateliers installés. On passe donc de quarante-quatre noms exposés à
un seul, et il est assez spécifique pour n'être disputé à personne.

Le chargement reste PARESSEUX (`laser_core._hershey_module`) : 2,6 Mo sur le
disque ne coûtent rien tant qu'on n'a pas choisi une police.
"""
