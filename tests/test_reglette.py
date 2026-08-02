#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""La planche se vérifie elle-même : le contrôle par la réglette gravée.

Ce que ce test protège, et qui est arrivé le 01/08/2026 : « 256-86 » (la
taille de l'IMAGE redressée) saisi à la place de « 240-70 » (les cotes de
la MIRE). L'image sortait 6 % trop large et 23 % trop haute, sans le
moindre avertissement -- le contrôle des diagonales (0,03 %) comme celui
du rapport des cotes étaient tous les deux passés, parce que tous les deux
se calculent sur les MÊMES quatre points que le redressement. Un contrôle
qui relit ses propres données ne contrôle rien.

La réglette, elle, n'entre pas dans l'homographie. Son pas est donc une
mesure indépendante, et c'est la seule qui pouvait attraper le coup.

Ce test tourne à part : `mesurer_reglette` a besoin d'OpenCV, absent du
python embarqué de FreeCAD. On délègue donc au python SYSTÈME, comme le
bouton du panneau le fait lui-même. Sans OpenCV nulle part, on ne fait pas
échouer la suite -- on le DIT, ce qui est différent de passer en silence.
"""
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Le sous-programme est écrit ici plutôt que dans un fichier à part : ce
# qu'il vérifie n'a de sens qu'avec le commentaire ci-dessus sous les yeux.
SOUS_PROGRAMME = r'''
import importlib.util, os, sys
import numpy as np

spec = importlib.util.spec_from_file_location(
    "redresser_photo", os.path.join(sys.argv[1], "outils", "redresser_photo.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

PXMM, L, H, MARGE = 50.0, 240.0, 70.0, 8.0


def planche(pas_px):
    """Fausse planche redressee : fond clair, reglette de traits noirs au
    pas donne, plus un peu de grain pour que la detection ait quelque
    chose a ecarter."""
    w = int((L + 2 * MARGE) * PXMM)
    h = int((H + 2 * MARGE) * PXMM)
    img = np.full((h, w, 3), 220, dtype=np.uint8)
    rng = np.random.default_rng(1234)
    img = np.clip(img.astype(np.int16)
                  + rng.integers(-25, 25, img.shape), 0, 255).astype(np.uint8)
    y0 = int((MARGE + 12.0) * PXMM)
    for i in range(int(L) + 1):
        x = int(round(MARGE * PXMM + i * pas_px))
        if x >= w - 2:
            break
        haut = 3.0 if i % 10 == 0 else (2.0 if i % 5 == 0 else 1.0)
        img[y0:y0 + int(haut * PXMM), x:x + 3] = 20
    return img


# 1. Echelle juste : la reglette doit CONFIRMER.
r = mod.mesurer_reglette(planche(PXMM), PXMM, L, MARGE)
assert r is not None, "reglette non detectee sur une planche pourtant nette"
pas, n, disp, y = r
assert abs(100 * (pas / PXMM - 1)) < 0.2, "ecart {:+.3f} %".format(
    100 * (pas / PXMM - 1))
assert n >= 0.9 * L, "seulement {} traits detectes".format(n)
print("1. echelle juste : {} traits, pas {:.3f} px/mm, ecart {:+.3f} % OK".format(
    n, pas, 100 * (pas / PXMM - 1)))

# 2. L'erreur du 01/08/2026 : cotes 256 declarees pour une mire de 240,
#    donc une reglette etiree de 256/240. Le controle DOIT la voir.
etire = PXMM * 256.0 / 240.0
r2 = mod.mesurer_reglette(planche(etire), PXMM, L, MARGE)
assert r2 is not None
err2 = 100 * (r2[0] / PXMM - 1)
assert err2 > 1.5, (
    "le controle laisse passer une echelle fausse de {:+.2f} % -- c'est "
    "exactement le defaut qu'il existe pour attraper".format(err2))
print("2. echelle fausse (256 pour 240) : ecart {:+.2f} % -> refusee OK".format(err2))

# 3. Le controle DISCRIMINE : les deux cas ci-dessus doivent tomber de part
#    et d'autre du seuil. Un controle qui refuse tout vaut celui qui accepte
#    tout ; c'est l'ecart entre les deux verdicts qui prouve qu'il mesure.
assert abs(100 * (pas / PXMM - 1)) < 1.5 < err2
print("3. les deux verdicts encadrent le seuil de 1,5 % OK")

# 4. Du bois SANS reglette ne doit pas inventer un pas. Mieux vaut
#    « non verifiee » qu'une confirmation tiree du grain.
rng = np.random.default_rng(7)
bois = np.clip(np.full((4300, 12800, 3), 200, dtype=np.int16)
               + rng.integers(-40, 40, (4300, 12800, 3)), 0, 255).astype(np.uint8)
r4 = mod.mesurer_reglette(bois, PXMM, L, MARGE)
if r4 is not None:
    assert abs(100 * (r4[0] / PXMM - 1)) > 1.5, (
        "du grain de bois seul a produit un pas de {:.2f} px/mm, pris pour "
        "une reglette juste".format(r4[0]))
    print("4. bois nu : pas {:.2f} px/mm -> ecart {:+.1f} %, refuse OK".format(
        r4[0], 100 * (r4[0] / PXMM - 1)))
else:
    print("4. bois nu : aucune reglette detectee OK")

# 5. Une ligne de graduation ne croise que les traits de SA hauteur : au
#    dessus de 1 mm on ne voit qu'un trait sur 5, puis sur 10. La detection
#    doit tomber sur la bande du millimetre, pas lire un pas x5 ou x10.
assert abs(pas - PXMM) < 2.0, (
    "pas de {:.1f} px pour {:.0f} attendus : la ligne retenue croise les "
    "traits de 5 ou 10 mm, pas ceux du millimetre".format(pas, PXMM))
print("5. bande du millimetre bien retenue (pas x5 ni x10) OK")

# --- 6. Une GRILLE hachuree ne doit pas voler la reglette --------------
# Le 02/08/2026, la planche de tons est sortie REFUSEE : « 29,01 px/mm au
# lieu de 50 », « largeur probable 190 mm » -- croix bien placees, cotes
# justes. Les rangees de cases donnaient 111 transitions a 30 px, la
# reglette 112 a 50 px : UNE VOIX d'ecart, et le depart se faisait au seul
# NOMBRE de traits. Selon le clic des croix, c'etait tantot l'une tantot
# l'autre qui gagnait.
#
# Les hachures sont FOURNIES (elles gagneraient au nombre) mais IRREGULIERES
# (leur remplissage bave et se recouvre : 0,6-0,8 sur le bois reel), la
# reglette est moins fournie mais parfaite (0,99-1,00). C'est ce contraste
# que le test reproduit -- sans le jitter il ne discriminerait rien, les
# deux etant a 1,00, et il passerait pour une mauvaise raison.
rng6 = np.random.default_rng(3)
PXMM6, L6, M6 = 50.0, 110.0, 5.0
W6 = H6 = int((L6 + 2 * M6) * PXMM6)
img6 = np.full((H6, W6, 3), 200, dtype=np.uint8)
for by in range(int(20 * PXMM6), int(85 * PXMM6), int(13 * PXMM6)):
    x = int(M6 * PXMM6)
    while x < int((M6 + L6) * PXMM6) - 20:
        img6[by:by + int(10 * PXMM6), x:x + 14] = 70
        x += 30 + int(rng6.integers(-9, 10))      # la bavure du remplissage
yr6 = int((M6 + 101.5) * PXMM6)
for k in range(int(L6) + 1):
    x = int((M6 + k) * PXMM6)
    img6[yr6:yr6 + int(1.0 * PXMM6), x:x + 4] = 30

res6 = mod.mesurer_reglette(img6, PXMM6, L6, M6)
assert res6 is not None, "reglette non detectee alors qu'elle est la"
pas6, n6, disp6, y6 = res6
assert abs(pas6 - PXMM6) < 0.5, (
    "une rangee de cases a vole la reglette : pas {:.2f} au lieu de {:.2f} "
    "-- la planche serait refusee avec des croix pourtant bonnes"
    .format(pas6, PXMM6))
assert abs(y6 - yr6) < 2 * PXMM6, (
    "detectee ailleurs que sur la reglette", y6, yr6)
print("6. une grille hachuree ne vole plus la reglette ({:.2f} px/mm) OK"
      .format(pas6))

print("\nreglette : 6 verifications OK")
'''


def python_systeme():
    for c in ("/usr/bin/python3", "/usr/local/bin/python3"):
        if os.path.exists(c):
            return c
    return None


py = python_systeme()
if py is None:
    print("python système introuvable : contrôle de la réglette non testé.")
    sys.exit(0)

# Même assainissement que le panneau : lancé depuis l'AppImage FreeCAD, un
# python système hérite de PYTHONHOME et meurt avant la première ligne.
VARS_APPIMAGE = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE",
                 "LD_LIBRARY_PATH", "LD_PRELOAD", "QT_PLUGIN_PATH",
                 "QML2_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH")
env = {k: v for k, v in os.environ.items() if k not in VARS_APPIMAGE}

dispo = subprocess.run([py, "-c", "import cv2, numpy"], env=env,
                       capture_output=True, text=True)
if dispo.returncode != 0:
    print("OpenCV absent du python système : contrôle de la réglette non testé.\n"
          "  sudo pacman -S python-opencv python-numpy")
    sys.exit(0)

r = subprocess.run([py, "-c", SOUS_PROGRAMME, RACINE], env=env,
                   capture_output=True, text=True, timeout=600)
print(r.stdout.strip())
if r.returncode != 0:
    print(r.stderr.strip()[-2000:])
sys.exit(r.returncode)

