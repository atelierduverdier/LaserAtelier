# -*- coding: utf-8 -*-
"""Un panneau doit tenir dans la vue des tâches de FreeCAD.

Christophe, 06/08/2026, capture à l'appui : « dans gravure remplie j'ai un
problème d'affichage ». Les boutons « Corriger » et « Alléger » des deux
verdicts étaient rognés, et le texte du verdict énergie s'arrêtait au
milieu.

Rien à voir avec ces rangées. Le panneau exigeait **693 px** de large
alors que la vue des tâches en fait ~570 : tout ce qui dépassait à droite
était coupé. La cause : `_appliquer_priorite_nuancier` écrivait le nom du
matériau DANS LE TITRE du QGroupBox -- « Puissance vs défocus -- inutile :
Hêtre a des tons mesurés ». Un titre de QGroupBox ne revient jamais à la
ligne : sa largeur devient la largeur minimale du groupe, donc du panneau.

Ce qui a démasqué la vraie cause, c'est d'avoir mesuré chaque piste
séparément : raccourcir la case à cocher ne changeait RIEN (693 px avant
comme après), déplacer le bouton sous l'étiquette non plus. Seul le titre
comptait.

Le défaut n'apparaît qu'au-delà de ~11 pt : à la police par défaut de
cette machine tout tenait, et c'est pourquoi personne ne l'avait vu.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer, sans_dialogues                  # noqa: E402

h = preparer()
tp = h.tp
sans_dialogues()

import inspect                                                # noqa: E402
from PySide6 import QtWidgets, QtGui                          # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

# La vue des tâches de FreeCAD, mesurée sur la capture de Christophe.
LARGEUR_VUE = 573
# Police d'épreuve : le défaut n'existe pas en dessous de 11 pt.
POINTS = 13

_police = QtGui.QFont(app.font())
_police.setPointSize(POINTS)
app.setFont(_police)


def largeur_mini(panneau):
    """Largeur minimale exigée par le contenu du panneau."""
    form = getattr(panneau, "form", None)
    if form is None:
        return None
    inner = form.widget() if hasattr(form, "widget") and form.widget() else form
    return inner.minimumSizeHint().width()


def construire(nom):
    cls = getattr(tp, nom)
    sig = inspect.signature(cls.__init__)
    return cls(*([[]] if len(sig.parameters) > 1 else []))


print("=" * 62)
print("§1  Gravure remplie tient dans la vue des tâches")
print("=" * 62)

p = construire("TaskPanelFilledEngraving")
larg = largeur_mini(p)
print("   police %d pt : le panneau exige %d px, la vue en fait %d"
      % (POINTS, larg, LARGEUR_VUE))
assert larg <= LARGEUR_VUE, (
    "le panneau exige %d px pour une vue de %d : tout ce qui dépasse à "
    "droite est rogné (c'était 693 px avant le correctif)" % (larg, LARGEUR_VUE))

print()
print("=" * 62)
print("§2  Le titre du groupe ne porte JAMAIS le nom du matériau")
print("=" * 62)

# La propriété, et non le symptôme : un titre qui grandit avec une donnée
# variable est une largeur minimale qui grandit sans limite. Le nom d'un
# matériau peut être bien plus long que « Hêtre ».
boites = [b for b in p.form.findChildren(QtWidgets.QGroupBox)
          if b.title().startswith("Puissance vs")]
assert boites, "le groupe « Puissance vs défocus » est introuvable"
boite = boites[0]
picker = p._shade_picker["mat"]
materiaux = [picker.itemData(i) for i in range(picker.count())
             if picker.itemData(i)]
print("   matériaux proposés : %s" % (materiaux or "aucun"))

if materiaux:
    # LE TITRE PAR DÉFAUT, PAS CELUI AFFICHÉ. Le panneau s'ouvre déjà sur un
    # matériau, donc `boite.title()` porte DÉJÀ la mention « inutile ici » :
    # comparer à lui ferait passer §3 quoi qu'il arrive. Première version de
    # ce test, et elle passait pour cette raison-là.
    tp._appliquer_priorite_nuancier(p._shade_picker, p._fluence)
    defaut_titre = boite._titre_defaut_priorite_nuancier
    defaut_texte = boite._texte_defaut_priorite_nuancier
    avant_titre = defaut_titre
    avant_texte = defaut_texte
    print("   titre par défaut : %r" % defaut_titre)
    picker.setCurrentIndex([picker.itemData(i) for i in range(picker.count())]
                           .index(materiaux[0]))
    app.processEvents()
    tp._appliquer_priorite_nuancier(p._shade_picker, p._fluence)
    titre_grise = boite.title()
    print("   avec « %s » : titre = %r" % (materiaux[0], titre_grise))
    assert materiaux[0] not in titre_grise, (
        "le nom du matériau est reparti dans le titre : la largeur du "
        "panneau redeviendra celle du nom le plus long")
    assert len(titre_grise) < len(defaut_titre) + 20, (
        "titre trop long : %r" % titre_grise)
    # La raison doit rester VISIBLE, simplement ailleurs -- dans une
    # étiquette qui, elle, revient à la ligne.
    assert materiaux[0] in p._fluence["lbl"].text(), (
        "la raison a disparu du panneau : elle doit passer dans "
        "l'étiquette, pas être perdue")
    print("   la raison est passée dans l'étiquette : ✓")

    print()
    print("=" * 62)
    print("§3  Et le texte d'origine revient si le matériau est retiré")
    print("=" * 62)

    # La liste « Nuancier matériau » de cet atelier n'a PAS d'entrée neutre
    # (ses trois items sont des matériaux), donc le chemin « aucun matériau »
    # ne s'atteint pas en cliquant. On appelle donc la fonction avec un faux
    # sélecteur : c'est ce chemin-là qui doit restaurer la notice, et sans
    # lui le message « inutile ici » resterait collé pour de bon.
    class _SansMateriau:
        def currentData(self):
            return None

    tp._appliquer_priorite_nuancier({"mat": _SansMateriau()}, p._fluence)
    print("   titre restauré  : %r" % boite.title())
    assert boite.title() == defaut_titre, (
        "titre non restauré : %r au lieu de %r"
        % (boite.title(), defaut_titre))
    assert p._fluence["lbl"].text() == defaut_texte, (
        "la notice d'origine a été perdue : l'étiquette garde %r"
        % p._fluence["lbl"].text()[:60])
    assert boite.isEnabled(), "le bloc est resté grisé sans matériau"
    print("   notice restaurée : ✓")

else:
    print("   (aucun matériau mesuré : §2 et §3 sans objet ici)")

print()
print("=" * 62)
print("§4  Aucun AUTRE panneau ne doit se mettre à déborder")
print("=" * 62)

# CETTE LISTE EST VIDE DEPUIS LE 06/08/2026, et elle ne peut que le
# rester : y ajouter un nom doit être un geste conscient, jamais la façon
# de faire passer un panneau.
#
# Les quatre qui y figuraient (Calligraphie 861, Assistant 781, Texte 712,
# Texte contour 670) sont tombés à 538 / 568 / 333 / 504 pour trois causes
# mesurées, aucune de celles qu'on aurait devinées :
#
#   - une QComboBox exige son entrée la plus longue comme largeur MINIMALE
#     (588 px pour le sélecteur de police) et `setSizeAdjustPolicy` n'y
#     change rien -- elle ne touche que `sizeHint` (`_combo_compact`) ;
#   - une QCheckBox ne se replie pas : deux libellés-phrases valaient 565
#     et 595 px à eux seuls, raccourcis, l'explication passée en bulle ;
#   - sept colonnes de QDoubleSpinBox à 91 px faisaient 749 px de grille
#     de mesures dans l'Assistant.
DEJA_TROP_LARGES = set()

trop_larges = set()
mesures = []
for nom in sorted(x for x in dir(tp) if x.startswith("TaskPanel")):
    cls = getattr(tp, nom)
    if not inspect.isclass(cls):
        continue
    try:
        panneau = construire(nom)
    except Exception:
        continue
    larg = largeur_mini(panneau)
    if larg is None:
        continue
    mesures.append((larg, nom))
    if larg > LARGEUR_VUE:
        trop_larges.add(nom)

mesures.sort(reverse=True)
for larg, nom in mesures[:6]:
    print("   %4d px | %-26s %s" % (larg, nom,
                                    "trop large" if larg > LARGEUR_VUE else "tient"))
print("   %d panneaux mesurés, %d trop larges" % (len(mesures), len(trop_larges)))

nouveaux = trop_larges - DEJA_TROP_LARGES
assert not nouveaux, (
    "ces panneaux se sont mis à déborder de la vue des tâches : %s"
    % ", ".join(sorted(nouveaux)))
gueris = DEJA_TROP_LARGES - trop_larges
if gueris:
    print("   (guéris depuis, à retirer de la liste : %s)"
          % ", ".join(sorted(gueris)))

print()
print("=" * 62)
print("§5  Une liste déroulante n'impose plus son entrée la plus longue")
print("=" * 62)

# LA PROPRIÉTÉ, PAS LE PANNEAU. §4 mesure des totaux, qui peuvent tomber
# juste pour une autre raison ; ici on vérifie le mécanisme. Le sélecteur
# de police porte 45 entrées dont « Verdier -- la police de l'atelier
# (chapeau sur ¤) », 588 px à 13 pt.
pt = construire("TaskPanelText")
combo = pt.combo_font
naturel = combo.minimumSizeHint().width()
print("   %d entrées, la plus longue vaut %d px" % (combo.count(), naturel))
assert naturel > LARGEUR_VUE / 2, (
    "la liste des polices n'est plus assez longue pour que ce test prouve "
    "quoi que ce soit (%d px) : lui trouver un autre cas" % naturel)
assert (combo.sizePolicy().horizontalPolicy()
        == QtWidgets.QSizePolicy.Ignored), (
    "la liste dicte à nouveau la largeur du panneau : _combo_compact ne "
    "l'a pas traitée")
print("   plafonnée à %d px, politique %s"
      % (combo.minimumWidth(), combo.sizePolicy().horizontalPolicy().name))
assert combo.minimumWidth() < naturel, (
    "le plafond (%d) ne réduit rien face au naturel (%d)"
    % (combo.minimumWidth(), naturel))

# ET LA LISTE DÉROULÉE GARDE SA LARGEUR : on rogne la boîte fermée, qui
# n'affiche que la sélection courante, jamais le choix lui-même.
assert combo.view().minimumWidth() >= naturel, (
    "la popup a été rognée elle aussi (%d < %d) : les noms de police "
    "deviendraient illisibles au moment de choisir"
    % (combo.view().minimumWidth(), naturel))
print("   la liste déroulée garde ses %d px : ✓" % combo.view().minimumWidth())

print()
print("=" * 62)
print("§6  Une case de mesure reste lisible en entier")
print("=" * 62)

# Le revers du resserrage : la grille de l'Assistant est passée de 749 à
# ~530 px en réduisant ses cases de 91 à 66. Un cran de plus et « 10.00 »
# serait tronqué à l'écran -- une mesure au pied à coulisse qu'on ne peut
# plus relire est pire qu'un panneau trop large.
pa = construire("TaskPanelAssistant")
grilles = pa.form.widget().findChildren(tp._GrilleResultats)
assert grilles, "aucune grille de mesures dans l'Assistant"
grille = grilles[0]
case = grille.findChildren(QtWidgets.QDoubleSpinBox)[0]
case.setValue(case.maximum())
metrique = QtGui.QFontMetrics(case.font())
texte = metrique.horizontalAdvance(case.text())
# ~12 px de cadre et de marges internes, mesurés sur ce style.
utile = case.minimumWidth() - 12
print("   case de %d px, valeur maxi %r large de %d px (utile %d)"
      % (case.minimumWidth(), case.text(), texte, utile))
assert texte <= utile, (
    "la valeur maximale (%s) ne tient pas dans la case (%d px de texte "
    "pour %d utiles) : une mesure serait tronquée à l'écran"
    % (case.text(), texte, utile))
print("   la grille entière fait %d px" % grille.minimumSizeHint().width())

print()
print("TOUT EST VERT")

# SORTIE EXPLICITE, pour la même raison que `test_panneaux.py`. Ce fichier
# construit VINGT-DEUX panneaux, chacun avec ses grilles, ses filtres
# d'événements et ses minuteurs. La destruction de tout cela par Qt rend
# parfois un code non nul -- tous les contrôles ayant pourtant affiché OK,
# et sans la moindre trace d'erreur.
#
# Constaté le 06/08/2026 : vert en solitaire (9,7 s), rouge environ une
# exécution sur trois EN PARALLÈLE (25 s, message vide). La pression
# mémoire des seize fronts rallonge la destruction, c'est tout. Une suite
# qui rougit au hasard apprend à ignorer le rouge -- pire que pas de suite.
#
# Chaque assertion s'exécute AU-DESSUS de cette ligne : un vrai échec lève
# et sort toujours non nul. (Vérifié en insérant `assert False` juste
# avant ce bloc -- placé APRÈS, il ne s'exécuterait jamais et ne prouverait
# rien.)
import os as _os
_Qt = QtWidgets
for _nom_w, _w in list(globals().items()):
    if _nom_w.startswith("p") and isinstance(_w, _Qt.QWidget):
        try:
            _w.setParent(None)
            _w.deleteLater()
        except Exception:
            pass
_Qt.QApplication.processEvents()
sys.stdout.flush()
sys.stderr.flush()
_os._exit(0)
