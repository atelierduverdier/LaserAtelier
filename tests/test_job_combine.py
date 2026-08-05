# -*- coding: utf-8 -*-
"""Job combiné : OK ferme, un bouton génère.

Christophe, 04/08/2026 : « j'ai créé plusieurs jobs, je veux en effacer un
puis revenir travailler afin d'en mettre un autre, mais si je clique sur OK
après l'effacement du job il veut me créer le fichier ; un bouton afin de
créer le G-code serait mieux, et le bouton OK sert à valider ».

La génération était accrochée à `accept()`, donc la SEULE façon de fermer le
panneau après avoir remanié la liste était d'écrire un fichier dont on ne
voulait pas. C'est la convention déjà appliquée aux quatre panneaux de test
en v2.20 : le travail se fait par un bouton, OK ferme.

On teste le CÂBLAGE du panneau, pas le générateur : `generate_gcode_combined`
est bouchonné. Ce qui a changé est l'endroit d'où part l'écriture, et c'est
cela qu'il faut prendre.
"""
import inspect as _insp
import sys

from harness import preparer, sans_dialogues

h = preparer()
core = h.core
tp = h.tp
import FreeCAD                                            # noqa: E402

_doc = FreeCAD.newDocument("EssaiJobCombine")
_ecrits = []
_vrai_write = tp._write_gcode_with_dialog
_vrai_gen = core.generate_gcode_combined
tp._write_gcode_with_dialog = (
    lambda form, gcode, defaut: (_ecrits.append(defaut), "/tmp/essai.ngc")[1])
core.generate_gcode_combined = lambda ops, **kw: "G21\nG90\nM2\n"
sans_dialogues()
try:
    _p = tp.TaskPanelCombined()
    _p.operations.clear()
    _p.operations.append({"type": "flat", "label": "essai 1", "params": {}})
    _p.operations.append({"type": "flat", "label": "essai 2", "params": {}})
    # Le widget de liste ne se peuple pas tout seul : empiler dans
    # `operations` sans le dire à la vue laisse `currentRow()` à -1, et la
    # suppression ne trouve rien à supprimer.
    _p._refresh_list()

    # (a) OK NE DOIT RIEN ÉCRIRE. C'est tout le défaut : supprimer une
    #     opération puis fermer écrivait un fichier.
    assert _p.accept() is True, "OK doit fermer le panneau"
    assert not _ecrits, (
        "OK a écrit un fichier : remanier la liste puis fermer grave un job "
        "dont on ne veut pas", _ecrits)

    # (b) ET IL NE DOIT RIEN PERDRE : la liste survit, sinon on ne peut pas
    #     revenir la compléter.
    assert len(_p.operations) == 2, (
        "OK a vidé la liste des opérations", len(_p.operations))

    # (c) LE BOUTON, LUI, ÉCRIT -- et le panneau reste ouvert.
    assert hasattr(_p, "btn_generer"), "pas de bouton de génération"
    _p.btn_generer.click()
    assert len(_ecrits) == 1, (
        "le bouton n'a pas écrit le fichier du job", _ecrits)
    assert len(_p.operations) == 2, (
        "générer a vidé la liste : on ne pourrait pas regénérer")

    # (d) On peut supprimer, regénérer, sans jamais fermer.
    _p.list_ops.setCurrentRow(0)
    _p._on_remove()
    assert len(_p.operations) == 1, ("la suppression n'a pas eu lieu",
                                     len(_p.operations))
    _p.btn_generer.click()
    assert len(_ecrits) == 2, ("regénérer après suppression n'a pas écrit",
                               _ecrits)

    # (e) Liste vide : le bouton refuse, et ne ferme rien.
    _p._on_clear()
    assert not _p.operations
    _p.btn_generer.click()
    assert len(_ecrits) == 2, (
        "un job VIDE a produit un fichier", _ecrits)
    assert _p.accept() is True, "OK doit fermer même sur une liste vide"
    print("1. OK ferme sans rien écrire (liste de {} gardée) ; le bouton "
          "écrit {} fois, supprime et regénère sans fermer ; liste vide "
          "refusée OK".format(2, len(_ecrits)))
finally:
    tp._write_gcode_with_dialog = _vrai_write
    core.generate_gcode_combined = _vrai_gen
    FreeCAD.closeDocument("EssaiJobCombine")


# --- LES CALQUES : une couleur par mode, une case pour graver ou non ----
# Christophe, 05/08/2026, après avoir vu LightBurn : « il y a une sorte de
# calque pour chaque type de trait ou travail afin de les sélectionner ou
# pas pour la gravure, et aussi grâce à la couleur de voir sur l'écran quel
# job pour quel trait ».
#
# Les Jobs de l'arbre TENAIENT DÉJÀ ce rôle -- un par couple (mode, forme),
# et `ajouter_jobs_au_combine` en faisait déjà un fichier unique. Il
# manquait la couleur et la case.
import laser_jobs as lj                                       # noqa: E402
import Part                                                   # noqa: E402

# TOUT MODE DOIT AVOIR SA COULEUR, sinon sa forme reste de la couleur du
# document et le calque est muet précisément là où on le regarde.
_sans = sorted(set(lj.MODES) - set(lj.COULEURS_MODE))
assert not _sans, ("des modes n'ont aucune couleur de calque : leurs formes "
                   "ne diront rien", _sans)
# Et elles doivent SE DISTINGUER : deux calques de même couleur ne sont
# qu'un calque.
_couleurs = list(lj.COULEURS_MODE.values())
for _i, _a in enumerate(_couleurs):
    for _b in _couleurs[_i + 1:]:
        _ecart = sum(abs(x - y) for x, y in zip(_a, _b))
        # LE SEUIL EST CELUI QUE LA CHARTE PERMET, et il a baissé sciemment.
        # Les couleurs viennent de la roue des barres d'outils (v2.97.0) au
        # lieu de primaires saturées : l'écart minimal passe de 0,44 à 0,25,
        # et c'est le prix de « rester uni par rapport à la barre d'icônes ».
        # 0,20 laisse la marge de mesure sans autoriser deux nuances
        # voisines -- la variante écartée en descendait à 0,23 avec deux
        # clairs chauds côte à côte.
        assert _ecart > 0.20, (
            "deux modes portent des couleurs trop proches pour être "
            "séparées à l'œil", _a, _b, _ecart)

_doc = FreeCAD.newDocument("EssaiCalques")


def _trait(nom):
    o = _doc.addObject("Part::Feature", nom)
    o.Shape = Part.LineSegment(FreeCAD.Vector(0, 0, 0),
                               FreeCAD.Vector(10, 0, 0)).toShape()
    return o


try:
    _a, _b = _trait("Contour"), _trait("Motif")
    _doc.recompute()
    _j1 = lj.creer_ou_maj_job("flat", [_a])
    _j2 = lj.creer_ou_maj_job("curved", [_b])
    assert _j1.Grave is True and _j2.Grave is True, (
        "un job neuf doit être gravé par défaut : sinon une planche préparée "
        "comme avant sortirait vide")

    # DÉCOCHÉ = PAS GRAVÉ, et la raison est NOMMÉE. Un job qui disparaît du
    # fichier sans un mot, c'est une planche ratée qu'on ne s'explique pas.
    tp._COMBINED_OPS[:] = []
    _j1.Grave = False
    _doc.recompute()
    _aj, _ig = lj.ajouter_jobs_au_combine([_j1])
    assert _aj == [] and len(tp._COMBINED_OPS) == 0, (
        "un job décoché est quand même parti dans le job combiné", _aj)
    assert _ig and "décoché" in _ig[0], (
        "le job décoché est ignoré SANS le dire", _ig)

    # SABOTAGE : la case doit être ce qui bloque, et non un refus général.
    # Recoché, le même job doit repasser la porte -- il échouera plus loin,
    # sur la sélection 3D que le harnais ne sait pas bouchonner, et c'est
    # justement la preuve qu'il a dépassé la case.
    _j1.Grave = True
    _doc.recompute()
    try:
        _aj2, _ig2 = lj.ajouter_jobs_au_combine([_j1])
        _passe = not (_ig2 and "décoché" in _ig2[0])
    except AttributeError:
        _passe = True          # tombé APRÈS la case, sur Gui.Selection
    assert _passe, (
        "recoché, le job est toujours refusé pour « décoché » : ce n'est pas "
        "la case qui gouverne, et le contrôle ci-dessus ne prouve rien")

    # UNE PILE DE CALQUES : décocher celui du dessus doit RÉVÉLER celui du
    # dessous. La v2.93 peignait job par job, dernier arrivé gagnant, si
    # bien que décocher un job GRISAIT une forme que deux autres gravaient
    # encore -- Christophe, trois jobs sur un même texte : « quand je décoche
    # gravure oui / non la couleur du dessous ou dessus ne s'affiche pas ».
    _t = _trait("Texte")
    _doc.recompute()
    _jm = lj.creer_ou_maj_job("curved", [_t])
    _jf = lj.creer_ou_maj_job("filled", [_t])
    _jh = lj.creer_ou_maj_job("hatch", [_t])

    def _trait_gagnant():
        """Le mode dont la couleur habille le TRAIT -- la même règle que
        `rafraichir_calques`, rejouée depuis les modes actifs."""
        _actifs = lj.rafraichir_calques(_doc).get(_t.Label, [])
        _g = next((_m for _m in lj.PRIORITE_CALQUE
                   if _m in _actifs and _m not in lj.MODES_HORS_TRAIT), None)
        if _g is None:
            _g = next((_m for _m in lj.PRIORITE_CALQUE if _m in _actifs), None)
        return _g

    # LE TRAIT REVIENT AUX JOBS QUI SUIVENT UN TRAIT. Un remplissage
    # s'exprime par SA SURFACE ; le laisser confisquer aussi le contour
    # rendait le marquage invisible dès qu'on cochait un remplissage.
    # Christophe : « donc je ne verrai jamais le vert sauf quand je cache
    # l'aperçu ? ». C'est SON cas exact qu'on éprouve ici.
    assert _trait_gagnant() == "curved", (
        "avec les trois cochés, le trait doit rester au MARQUAGE : le "
        "remplissage a sa surface et les hachures ont leur propre objet",
        _trait_gagnant())
    _jf.Grave = False
    assert _trait_gagnant() == "curved", (
        "décocher le remplissage ne devrait rien changer au trait")
    _jm.Grave = False
    assert _trait_gagnant() == "hatch", (
        "plus aucun job de trait : les hachures doivent reprendre le "
        "contour, sinon la forme paraît éteinte alors qu'elle sera gravée",
        _trait_gagnant())
    _jh.Grave = False
    assert _trait_gagnant() is None, (
        "tout décoché, la forme devrait passer au gris", _trait_gagnant())
    _jm.Grave = True
    assert _trait_gagnant() == "curved", "recocher un calque ne le ramène pas"
    _jf.Grave = True
    _jh.Grave = True

    # QUI A SA PROPRE GÉOMÉTRIE NE PREND PAS LE CONTOUR. Le remplissage a sa
    # surface, les hachures leur objet « Hachures_… » ; seuls le marquage et
    # les découpes n'existent QUE comme parcours sur la forme.
    assert set(lj.MODES_HORS_TRAIT) == {"filled", "hatch"}, (
        "la liste des modes qui ont leur propre géométrie a changé",
        lj.MODES_HORS_TRAIT)
    for _m7 in ("curved", "flat", "curved_cut"):
        assert _m7 not in lj.MODES_HORS_TRAIT, (
            "« {} » n'existe que comme trait sur la forme : lui retirer le "
            "contour le rendrait invisible".format(_m7))

    # ET L'OBJET DE HACHURES PORTE LA COULEUR DE SON CALQUE, plus le vert en
    # dur hérité de la macro d'origine -- qui entrait en collision avec le
    # vert du MARQUAGE et disait donc le contraire du reste.
    _src_hach = _insp.getsource(core.run_hatch_generation)
    assert "(0.0, 0.8, 0.0)" not in _src_hach, (
        "le vert en dur des hachures est revenu : il se confond avec la "
        "couleur du marquage")
    assert "teinte_atelier" in _src_hach, (
        "l'objet de hachures ne puise pas sa couleur dans la roue")
    assert "hasattr(hatch_obj" not in _src_hach, (
        "hasattr sur ViewObject : VRAI et INUTILE en headless, l'attribut "
        "existe et vaut None")

    # ET LA PILE DOIT ÊTRE COMPLÈTE : un mode absent de la priorité ne
    # gagnerait jamais, donc sa couleur ne s'afficherait jamais.
    assert set(lj.PRIORITE_CALQUE) == set(lj.COULEURS_MODE), (
        "des modes colorés ne figurent pas dans la pile des calques",
        set(lj.COULEURS_MODE) - set(lj.PRIORITE_CALQUE))

    # LA SURFACE D'APERÇU : un contour n'a pas de face, mais la Gravure
    # remplie sait en BÂTIR pour calculer ce qu'elle noircit -- on montre
    # cette surface-là. Christophe : « je le veux car cela a vraiment un sens
    # pratique et utile ».
    _cadre = _doc.addObject("Part::Feature", "Cadre")
    _pts = [FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(20, 0, 0),
            FreeCAD.Vector(20, 10, 0), FreeCAD.Vector(0, 10, 0),
            FreeCAD.Vector(0, 0, 0)]
    _cadre.Shape = Part.Compound([Part.makePolygon(_pts)])
    _doc.recompute()
    assert not _cadre.Shape.Faces, (
        "le fixture doit partir d'une forme SANS face, sinon il ne prouve "
        "rien sur le cas de Christophe")

    _n_bati = [0]
    _vrai_faces = core._faces_from_any_shape
    core._faces_from_any_shape = lambda *a, **k: (
        _n_bati.__setitem__(0, _n_bati[0] + 1), _vrai_faces(*a, **k))[1]
    try:
        _jr = lj.creer_ou_maj_job("filled", [_cadre])
        _ap = lj._apercu_existant(_doc, _jr)
        assert _ap is not None and _ap.Shape.Faces, (
            "aucune surface d'aperçu pour un job de remplissage sur un "
            "contour fermé")
        assert _ap.Shape.Area > 190.0, (
            "la surface d'aperçu ne couvre pas le cadre", _ap.Shape.Area)
        assert getattr(_ap, lj.PROP_APERCU) == _jr.Name, (
            "la surface d'aperçu n'est pas rattachée à son job : on ne "
            "saurait ni la retrouver ni la supprimer")
        assert _ap.Placement.Base.z < 0, (
            "la surface est au même Z que le tracé : le contour disparaîtra "
            "sous elle par moirage")

        # UN MARQUAGE NE REMPLIT RIEN, donc pas de surface : peindre une
        # aire pleine pour un trait promettrait un noir qui n'aura pas lieu.
        _jc = lj.creer_ou_maj_job("curved", [_cadre])
        assert lj._apercu_existant(_doc, _jc) is None, (
            "un job de marquage a posé une surface pleine")
        assert "hatch" not in lj.MODES_APERCU_PLEIN, (
            "les hachures laissent du bois nu entre les traits : les montrer "
            "pleines promettrait un noir qu'elles ne rendent pas")

        # COCHER/DÉCOCHER NE REBÂTIT PAS. 0,17 s par texte : le refaire à
        # chaque clic rendrait la case désagréable.
        _avant = _n_bati[0]
        _jr.Grave = False
        lj.rafraichir_calques(_doc)
        _jr.Grave = True
        lj.rafraichir_calques(_doc)
        assert _n_bati[0] == _avant, (
            "basculer la case reconstruit les faces : {} bâtis de plus"
            .format(_n_bati[0] - _avant))
    finally:
        core._faces_from_any_shape = _vrai_faces

    # Une forme d'UN SEUL job n'est pas signalée comme partagée.
    assert lj.colorer_sources(_j2) == [], (
        "une forme d'un seul job est signalée comme partagée")
    assert lj.colorer_sources(_jm) == ["Texte"], (
        "une forme servant à trois jobs n'est pas signalée",
        lj.colorer_sources(_jm))
    # LA COULEUR DIT QUEL TRAVAIL, pas seulement quel mode. Ce qui noircit
    # une aire se montre REMPLI (la face prend la couleur) ; ce qui marque
    # ou coupe se montre au TRAIT seul -- forcer un solide 3D en fil de fer
    # pour la beauté du calque rendrait le modèle inutilisable.
    # L'ATELIER N'IMPOSE PAS DE LARGEUR DE TRAIT. La v2.94.1 épaississait
    # les modes remplissants faute de savoir montrer la surface ; la v2.95.0
    # la montre, donc le gros trait ne dit plus rien de neuf. Christophe :
    # « le bord large pour les remplis et autre on en a plus besoin ».
    assert "LineWidth" not in _insp.getsource(lj), (
        "le calque impose de nouveau une largeur de trait : c'est un "
        "réglage d'affichage qui n'appartient pas à l'atelier, et l'aperçu "
        "plein dit déjà ce qu'il disait")
    assert not hasattr(lj, "MODES_REMPLIS"), (
        "MODES_REMPLIS n'a plus aucun lecteur depuis que la largeur de "
        "trait est partie : une constante que personne ne lit finit par "
        "être relue de travers")
    # Le gris d'extinction doit être TRÈS clair -- demandé tel quel -- sans
    # quoi une planche à moitié décochée reste illisible.
    assert min(lj.GRIS_ETEINT) > 0.75, (
        "le gris des jobs décochés n'est pas assez clair : les formes "
        "éteintes continuent de réclamer l'attention", lj.GRIS_ETEINT)
    # ET IL DOIT SE DISTINGUER DE TOUTES LES COULEURS DE MODE, sinon un job
    # éteint se lirait comme un job allumé.
    for _m, _c in lj.COULEURS_MODE.items():
        _e = sum(abs(x - y) for x, y in zip(_c, lj.GRIS_ETEINT))
        assert _e > 0.30, (
            "la couleur du mode « {} » se confond avec le gris éteint"
            .format(_m), _c, _e)

    # TROIS RAYONS, PAS UN TAS. Un job se coche, une forme se sélectionne,
    # un aperçu ne se touche jamais : trois natures, trois dossiers.
    _grp = lj._groupe_atelier(_doc)
    _rayons = {_g.Label: [_x.Label for _x in (getattr(_g, "Group", None) or [])]
               for _g in (getattr(_grp, "Group", None) or [])
               if hasattr(_g, "Group")}
    assert len(_rayons) == 3, (
        "« Atelier Laser » n'a pas ses trois rayons", sorted(_rayons))
    _r_jobs = next(v for k, v in _rayons.items() if k == "Jobs")
    _r_formes = next(v for k, v in _rayons.items() if k.startswith("Formes"))
    _r_ap = next(v for k, v in _rayons.items() if k.startswith("Aperçus"))
    assert any("Job " in _l for _l in _r_jobs), ("les jobs ne sont pas rangés",
                                                 _r_jobs)
    assert "Cadre" in _r_formes, ("la forme source n'est pas rangée", _r_formes)
    # LE NOM DIT CE QU'ON CACHE. Le rayon ne contient que des surfaces de
    # remplissage -- il n'existe pas d'aperçu de marquage -- donc « Aperçus »
    # tout court ne disait pas ce qu'on éteint en éteignant le dossier.
    assert any(_k.startswith("Aperçus de remplissage") for _k in _rayons), (
        "le rayon des aperçus ne dit pas ce qu'il contient", sorted(_rayons))
    # Un dossier posé sous un ANCIEN libellé est rattrapé...
    _gap = lj._sous_groupe(_doc, "Apercus")
    _gap.Label = "Aperçus (ne pas graver)"
    lj._sous_groupe(_doc, "Apercus")
    assert _gap.Label == "Aperçus de remplissage", (
        "un dossier créé par une version précédente garde son ancien nom",
        _gap.Label)
    # ...mais un nom choisi par l'utilisateur ne s'écrase pas.
    _gap.Label = "Mes surfaces à moi"
    lj._sous_groupe(_doc, "Apercus")
    assert _gap.Label == "Mes surfaces à moi", (
        "l'atelier écrase le nom que l'utilisateur a donné à son dossier",
        _gap.Label)
    _gap.Label = "Aperçus de remplissage"

    assert any("Aperçu" in _l for _l in _r_ap), (
        "la surface d'aperçu n'est pas rangée", _r_ap)
    # RANGÉ DEUX FOIS = RANGÉ NULLE PART.
    _tous = _r_jobs + _r_formes + _r_ap
    assert len(_tous) == len(set(_tous)), (
        "un objet figure dans deux rayons à la fois", _tous)
    assert not [_x for _x in (getattr(_grp, "Group", None) or [])
                if not hasattr(_x, "Group")], (
        "des objets traînent encore à plat dans « Atelier Laser »")

    # LA SURFACE NE DOIT PAS AVALER LE CONTOUR. Christophe : « le
    # remplissage de couleur masque le contour du marquage ». Ce n'était pas
    # la profondeur : la Gravure remplie gagnant la priorité des calques,
    # les TRAITS portaient déjà sa couleur -- et la surface posée dessous
    # portait exactement la même. Une aire et un chemin ne se peignent pas
    # pareil : même teinte, deux tons.
    for _m6, _i6 in lj._TEINTE_INDICE.items():
        _trait6 = lj.COULEURS_MODE[_m6]
        _surf6 = core.teinte_atelier(_i6, lj.APERCU_SATURATION,
                                     lj.APERCU_VALEUR)
        _e6 = sum(abs(_x - _y) for _x, _y in zip(_trait6, _surf6))
        assert _e6 > 0.50, (
            "la surface d'aperçu du mode « {} » est trop proche de son "
            "trait : le contour disparaîtra dans son propre remplissage"
            .format(_m6), _trait6, _surf6, _e6)
        # ...mais elle doit rester de la MÊME FAMILLE, sinon la surface et
        # son contour se liraient comme deux jobs différents.
        assert _surf6 == core.teinte_atelier(_i6, lj.APERCU_SATURATION,
                                             lj.APERCU_VALEUR), _m6
    # Une seule table d'indices : le trait et la surface ne PEUVENT pas
    # partir dans deux familles.
    assert set(lj._TEINTE_INDICE) == set(lj.COULEURS_MODE), (
        "le trait et la surface ne puisent plus dans la même table")
    # Et la surface reste EN DESSOUS du tracé, assez pour que le tampon de
    # profondeur les départage sur une scène de 100 mm.
    assert lj.RECUL_APERCU_MM >= 0.05, (
        "le recul de la surface est trop faible : le contour clignotera "
        "sous elle", lj.RECUL_APERCU_MM)

    # L'ATELIER RANGE CE QU'IL CRÉE, MÊME SANS JOB. Les Hachures ne créent
    # aucun job -- elles ne produisent que de la géométrie -- si bien que
    # leur objet restait à plat dans l'arbre, à côté du dossier plutôt que
    # dedans. Christophe : « le job hachures_paralleles n'est pas dans
    # Aperçus de remplissage ». Ce n'est pas un aperçu -- un aperçu ne se
    # grave jamais, celui-ci est le tracé même que le laser suivra : sa
    # place est parmi les FORMES À GRAVER.
    _hach = _doc.addObject("Part::Feature", "Hachures_paralleles_1_0_45_0deg")
    _hach.Shape = Part.makePolygon([FreeCAD.Vector(0, 0, 0),
                                    FreeCAD.Vector(9, 0, 0)])
    _doc.recompute()
    assert _hach.getParentGroup() is None, (
        "le fixture doit partir d'une forme À PLAT, sinon il ne prouve rien")
    lj.ranger_forme(_hach)
    _p8 = _hach.getParentGroup()
    assert _p8 is not None and _p8.Label.startswith("Formes"), (
        "une forme fabriquée par l'atelier reste à plat dans l'arbre",
        _p8.Label if _p8 else None)

    # MAIS ON NE CASSE PAS L'ORGANISATION DE L'UTILISATEUR : une forme qu'il
    # a lui-même classée dans un conteneur n'est pas déménagée.
    _mien = _doc.addObject("App::Part", "MonConteneur")
    _sien = _doc.addObject("Part::Feature", "AMoi")
    _sien.Shape = _hach.Shape
    _mien.addObject(_sien)
    lj.ranger_forme(_sien)
    _formes = next(_g for _g in (getattr(_grp, "Group", None) or [])
                   if getattr(_g, "Label", "").startswith("Formes"))
    assert _sien not in (getattr(_formes, "Group", None) or []), (
        "l'atelier a déménagé une forme que l'utilisateur avait classée "
        "lui-même")

    # L'APERÇU NE DOIT JAMAIS DEVENIR UN MOTIF. `Selectable = False` ne
    # bloque que le clic dans la VUE 3D ; un clic dans l'ARBRE passe outre,
    # et les cinq modes lisent la même sélection. Christophe : « si par
    # erreur je clique sur aperçu remplissage puis hachure, cela va faire
    # des hachures dans les remplissages ? »
    import commands as _cmd                                   # noqa: E402

    class _Sel:
        def __init__(self, o):
            self.Object = o

    _apercu = next(_x for _x in _doc.Objects
                   if getattr(_x, lj.PROP_APERCU, None))
    _garde = _cmd._sans_apercus([_Sel(_apercu), _Sel(_cadre)])
    assert [_s.Object for _s in _garde] == [_cadre], (
        "la surface d'aperçu n'est pas écartée de la sélection : elle serait "
        "hachurée comme une pièce")
    assert _cmd._sans_apercus([_Sel(_apercu)]) == [], (
        "une sélection ne contenant QUE des aperçus doit devenir vide")
    # Et le garde ne doit pas manger une sélection normale.
    assert len(_cmd._sans_apercus([_Sel(_cadre), _Sel(_t)])) == 2, (
        "le garde écarte des formes ordinaires")
    # Les CINQ modes doivent le traverser -- en oublier un le laisserait
    # ouvert, et c'est toujours celui-là qu'on clique.
    _src_cmd = _insp.getsource(_cmd)
    assert _src_cmd.count("_sans_apercus(Gui.Selection.getSelectionEx())") == \
        _src_cmd.count("Gui.Selection.getSelectionEx()"), (
        "un mode lit la sélection sans passer par le garde des aperçus")

    print("calques : {} modes colorés et distincts, job décoché ignoré "
          "(« {} »), forme partagée nommée OK".format(
              len(lj.COULEURS_MODE), _ig[0]))
finally:
    FreeCAD.closeDocument("EssaiCalques")
