# -*- coding: utf-8 -*-
"""Les calques et les jobs : ce qu'on ANNONCE doit être ce qu'on FAIT.

Quatre défauts relevés à la lecture ligne à ligne de `laser_jobs.py` le
02/09/2026, tous mesurés avant d'être décrits, tous de la même famille --
DEUX ENDROITS RÉPONDENT À LA MÊME QUESTION et finissent par ne plus dire
la même chose :

1. l'ordre des calques était appliqué en deux passes (le trait d'abord) et
   annoncé en une seule : sur un texte portant un remplissage ET un
   marquage, le message promettait « Gravure remplie », l'écran montrait le
   Marquage ;
2. supprimer un job repeignait le document en l'écartant -- mais seules les
   formes qu'un AUTRE job visait encore entraient dans le calcul, si bien
   que la forme d'un job unique gardait la couleur d'un calque disparu,
   exactement ce que `onDelete` dit vouloir empêcher ;
3. « DÉCOCHÉ = PAS GRAVÉ » n'était vrai qu'à l'ajout : un job ajouté coché
   puis décoché gardait son opération dans le job combiné, et le fichier
   gravait la forme qu'on venait d'exclure -- celui-là se paie sur le bois ;
4. la reprise des réglages annonçait « gardée telle quelle » une opération
   qu'elle venait de reprendre (job renommé), sous l'annonce de sa reprise.
"""
import inspect
import sys

from harness import preparer

h = preparer()
core = h.core
tp = h.tp
import FreeCAD                                            # noqa: E402
import Part                                               # noqa: E402
import laser_jobs as lj                                   # noqa: E402


def _job(doc, mode, src, nom, grave=True):
    """Un Job nu, sans passer par `creer_ou_maj_job` : on veut choisir le
    mode librement, y compris ceux qui ne s'en créent plus."""
    o = doc.addObject("App::FeaturePython", nom)
    lj.JobLaser(o)
    o.addProperty("App::PropertyString", "Mode", "Job", "")
    o.Mode = mode
    o.addProperty("App::PropertyLinkListGlobal", "Sources", "Job", "")
    o.Sources = [src]
    o.addProperty("App::PropertyStringList", "SousElements", "Job", "")
    o.addProperty("App::PropertyBool", "Grave", "Job", "")
    o.Grave = grave
    o.Label = nom
    return o


# ==========================================================================
# 1. L'ORDRE ANNONCÉ EST L'ORDRE APPLIQUÉ
# ==========================================================================
# On ne compare pas la fonction à elle-même : on prend le message que
# `_dire_disputees` écrit VRAIMENT, on en relit l'ordre, et on vérifie que
# c'est bien ce mode-là qui reçoit la couleur. Un test qui se contenterait
# d'appeler `ordre_calques()` des deux côtés passerait même si les deux
# étaient faux.
_doc = FreeCAD.newDocument("EssaiCalques")
_peints = []
_vrai_peindre = lj._peindre
_vrai_apercu = lj._apercu_calque
lj._peindre = lambda src, mode: _peints.append((getattr(src, "Label", "?"), mode))
lj._apercu_calque = lambda job, rebatir=False: None
try:
    _forme = _doc.addObject("Part::Feature", "Texte")
    _forme.Shape = Part.makeBox(10, 10, 1)
    _forme.Label = "Texte"

    # L'ordre tel que l'utilisateur le LIT dans la vue Rapport.
    _msgs = []
    _vrai_msg = FreeCAD.Console.PrintMessage
    FreeCAD.Console.PrintMessage = lambda t: _msgs.append(t)
    try:
        lj._dire_disputees(None, ["Texte"])
    finally:
        FreeCAD.Console.PrintMessage = _vrai_msg
    _texte = "".join(_msgs)
    assert "ordre : " in _texte, ("le message n'annonce plus d'ordre", _texte)
    _annonce = [m.strip() for m in
                _texte.split("ordre : ", 1)[1].split(")", 1)[0].split(" > ")]
    _par_libelle = {v[0]: k for k, v in lj.MODES.items()}
    _ordre_lu = [_par_libelle[lib] for lib in _annonce]
    assert len(_ordre_lu) == len(lj.MODES), (
        "le message n'annonce pas tous les modes", _annonce)

    # Toutes les combinaisons de jobs cochés : le gagnant doit être le
    # PREMIER de l'ordre annoncé qui est présent. C'est la seule promesse
    # que le message fait, et il la fait pour tous les cas à la fois.
    import itertools
    _modes = list(lj.MODES)
    for _n in (2, 3, 4):
        for _combo in itertools.combinations(_modes, _n):
            _jobs = [_job(_doc, _m, _forme, "J_{}_{}".format(_m, _n))
                     for _m in _combo]
            _doc.recompute()
            _peints[:] = []
            lj.rafraichir_calques(_doc)
            _attendu = next(m for m in _ordre_lu if m in _combo)
            assert _peints and _peints[-1] == ("Texte", _attendu), (
                "jobs {} : le message annonce {}, l'écran montre {}"
                .format(list(_combo), _attendu,
                        _peints[-1][1] if _peints else None))
            for _j in _jobs:
                _doc.removeObject(_j.Name)
            _doc.recompute()
    print("1. l'ordre des calques annoncé est celui qui est appliqué OK")

    # ======================================================================
    # 2. SUPPRIMER LE DERNIER JOB D'UNE FORME L'ÉTEINT
    # ======================================================================
    # Le cas du job UNIQUE, celui que l'ancien code ne voyait pas : avec
    # deux jobs, la forme était repeinte de toute façon et le défaut restait
    # invisible.
    _seul = _job(_doc, "curved", _forme, "Job unique")
    _doc.recompute()
    _peints[:] = []
    lj.rafraichir_calques(_doc, ignorer=_seul)      # ce que fait onDelete
    assert ("Texte", None) in _peints, (
        "la forme d'un job supprimé n'est pas repeinte : elle garde la "
        "couleur d'un calque qui n'existe plus -- {}".format(_peints))

    # Et l'inverse doit rester vrai : un AUTRE job coché reprend la forme,
    # elle ne s'éteint pas pour rien.
    _autre = _job(_doc, "flat", _forme, "Job restant")
    _doc.recompute()
    _peints[:] = []
    lj.rafraichir_calques(_doc, ignorer=_seul)
    assert ("Texte", "flat") in _peints, (
        "la forme s'éteint alors qu'un autre job la grave encore", _peints)
    # ... et elle n'est PAS déclarée partagée : il ne reste qu'un job.
    assert lj.rafraichir_calques(_doc, ignorer=_seul) == {}, (
        "le job écarté compte encore parmi ceux qui se partagent la forme")
    print("2. la forme d'un job supprimé s'éteint, même si c'était son seul "
          "job OK")
finally:
    lj._peindre = _vrai_peindre
    lj._apercu_calque = _vrai_apercu
    FreeCAD.closeDocument("EssaiCalques")


# ==========================================================================
# 3. DÉCOCHÉ = PAS GRAVÉ, MÊME POUR UNE OPÉRATION DÉJÀ EMPILÉE
# ==========================================================================
# C'est le défaut qui se paie sur le bois : la case promet « Inclure ce job
# dans le job combiné », et elle ne tenait cette promesse qu'à l'ajout.
_doc3 = FreeCAD.newDocument("EssaiDecoche")
try:
    _f3 = _doc3.addObject("Part::Feature", "Carre")
    _f3.Shape = Part.makePolygon([FreeCAD.Vector(0, 0, 0),
                                  FreeCAD.Vector(9, 0, 0)])
    _doc3.recompute()
    _j3 = lj.creer_ou_maj_job("curved", [_f3])

    class _FauxPanneau:
        def __init__(self, sel):
            pass

        def _build_combined_operation(self):
            return {"type": "curved", "label": "x", "params": {"n": 1}}

    _vrai_cls = getattr(tp, lj.MODES["curved"][2])
    setattr(tp, lj.MODES["curved"][2], _FauxPanneau)
    try:
        tp._COMBINED_OPS.clear()
        lj.ajouter_jobs_au_combine([_j3])
        assert len(tp._COMBINED_OPS) == 1, "l'opération n'a pas été ajoutée"

        # (a) LA REPRISE DES RÉGLAGES. Le panneau du job combiné la lance à
        #     l'ouverture ET avant d'écrire : c'est là que la case doit
        #     reprendre la main.
        _j3.Grave = False
        _doc3.recompute()
        _repris, _laisses = lj.rafraichir_operations(tp._COMBINED_OPS, _doc3)
        assert not tp._COMBINED_OPS, (
            "l'opération d'un job DÉCOCHÉ reste dans le job combiné : la "
            "forme sera gravée alors qu'on vient de l'exclure -- {}"
            .format(tp._COMBINED_OPS))
        assert not _repris, ("un job décoché ne se reprend pas", _repris)
        assert any("retirée" in _m for _m in _laisses), (
            "le retrait n'est pas annoncé : une opération qui disparaît sans "
            "un mot est aussi mauvaise qu'une opération qui reste", _laisses)

        # (b) ET LE BOUTON « Jobs -> combiné » APPLIQUE LA MÊME RÈGLE : elle
        #     n'est écrite qu'à un seul endroit, donc les deux chemins ne
        #     peuvent pas diverger.
        _j3.Grave = True
        _doc3.recompute()
        lj.ajouter_jobs_au_combine([_j3])
        assert len(tp._COMBINED_OPS) == 1
        _j3.Grave = False
        _doc3.recompute()
        _aj, _ig = lj.ajouter_jobs_au_combine([_j3])
        assert not tp._COMBINED_OPS, (
            "le bouton laisse l'opération d'un job décoché", tp._COMBINED_OPS)
        assert _ig and "décoché" in _ig[0], _ig

        # (c) RECOCHER REND SON OPÉRATION : le retrait n'est pas une
        #     condamnation, c'est l'état de la case.
        _j3.Grave = True
        _doc3.recompute()
        lj.ajouter_jobs_au_combine([_j3])
        assert len(tp._COMBINED_OPS) == 1, (
            "recocher un job ne rend pas son opération", tp._COMBINED_OPS)
    finally:
        setattr(tp, lj.MODES["curved"][2], _vrai_cls)
        tp._COMBINED_OPS.clear()
    print("3. décoché = pas gravé, y compris pour une opération déjà "
          "empilée OK")

    # ======================================================================
    # 4. LA REPRISE DIT CE QU'ELLE A FAIT
    # ======================================================================
    # Une opération reprise après renommage était annoncée « gardée telle
    # quelle » juste sous l'annonce de sa reprise. Le mot venait de
    # l'appelant, qui habillait un motif dont il ignorait le sens.
    setattr(tp, lj.MODES["curved"][2], _FauxPanneau)
    try:
        _j3.Grave = True
        _doc3.recompute()
        tp._COMBINED_OPS.clear()
        lj.ajouter_jobs_au_combine([_j3])
        _ancien = _j3.Label
        _j3.Label = "Mon découpage à moi"          # geste permis, et documenté
        _repris, _laisses = lj.rafraichir_operations(tp._COMBINED_OPS, _doc3)
        assert _repris == [_j3.Label], ("le renommage casse la reprise",
                                        _repris, _laisses)
        assert _laisses and _ancien in _laisses[0], (
            "le renommage n'est pas dit", _laisses)
        assert "gardée telle quelle" not in _laisses[0], (
            "une opération REPRISE est annoncée « gardée telle quelle » : "
            "les deux messages se contredisent -- {}".format(_laisses[0]))
    finally:
        setattr(tp, lj.MODES["curved"][2], _vrai_cls)
        tp._COMBINED_OPS.clear()

    # Et l'appelant n'ajoute plus de verdict de son cru : il imprime la
    # phrase telle qu'elle lui arrive.
    # Le CODE, pas les commentaires : ceux-ci citent le défaut réparé.
    _src = "\n".join(l for l in inspect.getsource(
        tp.TaskPanelCombined._reprendre_reglages).splitlines()
        if not l.lstrip().startswith("#"))
    assert "gardée telle quelle" not in _src, (
        "le panneau réaffirme « gardée telle quelle » pour toutes les "
        "phrases, y compris celles qui disent le contraire")
    # Les phrases sont ENTIÈRES : chacune commence par un guillemet ou porte
    # le nom du job, jamais un fragment à compléter.
    _sj = inspect.getsource(lj.rafraichir_operations)
    assert "gardée telle quelle" in _sj, (
        "les phrases ne disent plus le sort des opérations gardées")
    print("4. la reprise des réglages annonce ce qu'elle a réellement fait OK")
finally:
    FreeCAD.closeDocument("EssaiDecoche")


# ==========================================================================
# 5. UN SEUL GESTE DE RE-SÉLECTION
# ==========================================================================
# Le double-clic et le job combiné le faisaient chacun de leur côté, mot
# pour mot. Deux copies tiennent jusqu'au jour où l'une des deux change.
assert "_reselectionner" in inspect.getsource(lj.ouvrir_job), (
    "le double-clic re-sélectionne à sa façon")
assert "_reselectionner" in inspect.getsource(lj.ajouter_jobs_au_combine), (
    "le job combiné re-sélectionne à sa façon")
for _f in (lj.ouvrir_job, lj.ajouter_jobs_au_combine):
    assert "addSelection" not in inspect.getsource(_f), (
        "{} garde sa propre copie du geste de sélection".format(_f.__name__))
print("5. une seule re-sélection, partagée par le double-clic et le "
      "job combiné OK")

print("calques et jobs OK")
