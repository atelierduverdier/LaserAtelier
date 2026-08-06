# -*- coding: utf-8 -*-
"""La config ne doit JAMAIS pouvoir être tronquée.

Ce fichier est la seule chose irremplaçable du projet : 283 mesures prises
au pied à coulisse sur du bois au 06/08/2026, que rien ne recalcule. Le
reste du dépôt se reclone.

`open(chemin, "w")` VIDE le fichier avant d'écrire. Une coupure à cet
instant — FreeCAD qui segfaute, ce dont ce dépôt garde la trace — et des
heures d'établi disparaissent. Constaté à l'audit du 06/08/2026 : les
seules sauvegardes dataient du 29 juillet, prises à la main, alors que la
config avait grossi de 42 à 78 Ko depuis.

On écrit donc à côté, puis on remplace d'un seul geste : `os.replace` est
atomique. À tout instant le fichier en place est soit l'ancien complet,
soit le nouveau complet.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()
core = h.core

import glob                                                   # noqa: E402
import json                                                   # noqa: E402
import os                                                     # noqa: E402

CHEMIN = core.CONFIG_FILE
print("config d'essai (copie jetable) : %s" % os.path.basename(CHEMIN))

print("=" * 62)
print("§1  L'écriture passe par un fichier temporaire, puis un remplacement")
print("=" * 62)

avant = json.load(open(CHEMIN))
avant["_essai_audit"] = 1
core.save_config(avant)
relu = json.load(open(CHEMIN))
assert relu.get("_essai_audit") == 1, "l'écriture n'a pas eu lieu"
assert not os.path.exists(CHEMIN + ".tmp"), "le fichier temporaire traîne"
print("   écrit et relu, aucun .tmp résiduel : ✓")

print()
print("=" * 62)
print("§2  UNE COUPURE EN PLEINE ÉCRITURE ne détruit rien")
print("=" * 62)

# On simule le segfault : `json.dump` explose au milieu. Avec l'ancienne
# écriture (open "w" direct) le fichier serait déjà tronqué à zéro.
taille_avant = os.path.getsize(CHEMIN)
somme_avant = open(CHEMIN, "rb").read()
_vrai_dump = json.dump


def _dump_qui_meurt(*a, **k):
    a[1].write('{"moitie": ')
    raise IOError("coupure simulée en pleine écriture")


json.dump = _dump_qui_meurt
try:
    core.save_config({"peu importe": True})
finally:
    json.dump = _vrai_dump

taille_apres = os.path.getsize(CHEMIN)
print("   taille avant %d o, après la coupure %d o" % (taille_avant, taille_apres))
assert open(CHEMIN, "rb").read() == somme_avant, (
    "LA CONFIG A ÉTÉ ABÎMÉE par une écriture interrompue")
json.load(open(CHEMIN))          # elle doit rester lisible
print("   octet pour octet identique, et toujours lisible : ✓")

print()
print("=" * 62)
print("§3  Une copie de sûreté existe après chaque enregistrement")
print("=" * 62)

assert os.path.exists(CHEMIN + ".bak"), "aucune sauvegarde .bak"
photos = glob.glob(CHEMIN + ".2*")
print("   .bak présent, %d photographie(s) datée(s)" % len(photos))
assert photos, "aucune photographie du jour"
sauvegarde = json.load(open(CHEMIN + ".bak"))
assert isinstance(sauvegarde, dict), "la sauvegarde n'est pas lisible"

print()
print("=" * 62)
print("§4  Les photographies ne s'accumulent pas sans fin")
print("=" * 62)

for jour in range(1, 20):
    open("%s.202601%02d" % (CHEMIN, jour), "w").write("{}")
core.save_config(json.load(open(CHEMIN)))
restantes = glob.glob(CHEMIN + ".2*")
print("   19 anciennes + celle du jour -> %d gardée(s) (plafond %d)"
      % (len(restantes), core.CONFIG_SAUVEGARDES_JOURS))
assert len(restantes) <= core.CONFIG_SAUVEGARDES_JOURS, (
    "%d photographies : elles s'accumulent" % len(restantes))

print()
print("=" * 62)
print("§5  Une sauvegarde en échec n'empêche PAS l'enregistrement")
print("=" * 62)

# VÉCU pendant l'écriture de ce correctif : un `import time` oublié dans la
# copie de sûreté faisait échouer TOUT `save_config`, en silence -- le
# filet empêchait le devoir. Le test l'aurait attrapé, pas l'usage.
_vraie_sauvegarde = core._sauvegarder_config


def _sauvegarde_qui_casse(_chemin):
    raise OSError("disque plein, par exemple")


core._sauvegarder_config = _sauvegarde_qui_casse
try:
    donnees = json.load(open(CHEMIN))
    donnees["_malgre_tout"] = 42
    core.save_config(donnees)
finally:
    core._sauvegarder_config = _vraie_sauvegarde

relu = json.load(open(CHEMIN))
print("   sauvegarde en échec -> enregistrement %s"
      % ("FAIT" if relu.get("_malgre_tout") == 42 else "PERDU"))
assert relu.get("_malgre_tout") == 42, (
    "le filet a empêché le devoir : une sauvegarde qui échoue fait perdre "
    "l'enregistrement, silencieusement")

print()
print("TOUT EST VERT")
