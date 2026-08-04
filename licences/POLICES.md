# Polices mono-trait embarquées

Les modules `polices_monotrait/hershey_font*.py` sont des DONNÉES dérivées de polices libres,
régénérables par `outils/generer_police_monotrait.py`.

| Famille | Source | Licence |
|---|---|---|
| EMS (29 polices) | https://gitlab.com/oskay/svg-fonts | SIL Open Font License 1.1 |
| Hershey (13 polices) | https://gitlab.com/oskay/svg-fonts | Hershey Fonts — domaine public |
| Twin Sans | https://gitlab.com/oskay/svg-fonts | SIL Open Font License 1.1 |
| Relief SingleLine | https://github.com/isdat-type/Relief-SingleLine | SIL Open Font License 1.1 |

Conversions SVG : Windell H. Oskay (Evil Mad Scientist). Les EMS sont de
Sheldon B. Michaels, dérivées de polices Google Fonts. Relief SingleLine est
un projet de l'isdat, conçu pour la CNC.

Le texte complet de l'OFL accompagnant Relief SingleLine est dans
`Relief-SingleLine-OFL.txt` ; les EMS portent leur licence dans les
métadonnées de chaque SVG d'origine, reprise dans l'en-tête de chaque module.

**Écartées, et pourquoi** — deux des quatre sources proposées le 03/08/2026 :

* `github.com/Shriinivas/inkscapestrokefont` : dépôt en **GPL-2**, donc
  incompatible avec la LGPL-2.1-or-later de cet atelier. Les polices qu'il
  contient sont dérivées de fontes OFL, mais la licence des données dérivées
  n'est pas déclarée séparément — ambiguïté qu'on ne lève pas soi-même.
* `cutlings.datafil.no` : polices **commerciales**. À acheter puis convertir
  soi-même avec l'outil, si besoin.
