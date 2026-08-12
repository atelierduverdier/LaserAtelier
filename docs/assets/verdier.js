/* ENGENDRÉ — ne pas éditer ici.
   Ce fichier est une copie de kit/verdier.js du dépôt atelierduverdier/site. Toute retouche faite ici sera écrasée : corriger la source, puis relancer outils/diffuser_kit.py. */
/* =========================================================================
   verdier.js — comportements communs de la charte Atelier du Verdier
   =========================================================================
   FICHIER DU KIT, recopié dans chaque site par outils/diffuser_kit.py.
   Ne pas l'éditer dans une copie : elle sera écrasée.
   Source : atelierduverdier/site — kit/verdier.js

   Deux choses seulement : la bascule de thème, et la visionneuse d'images.
   Tout est défensif — chaque site ne contient pas forcément les deux, et
   un kit partagé qui plante sur une page sans bouton casserait TOUTES les
   pages qui suivent dans le même fichier.
   ========================================================================= */

/* ---------- Thème clair / sombre ----------------------------------------
   Le choix est rangé dans un COOKIE, pas dans localStorage, et c'est
   volontaire : localStorage est cloisonné par origine, donc un réglage
   fait sur atelierduverdier.fr ne suivrait pas le visiteur sur
   laser.atelierduverdier.fr. Le cookie est posé sur le domaine parent, il
   traverse les sous-domaines.

   Pas de bandeau de consentement à prévoir pour autant : mémoriser un
   choix d'affichage exprimé par l'utilisateur lui-même fait partie des
   cas que la CNIL dispense de consentement. Aucun traçage, aucun tiers.

   Le repli sur localStorage sert au développement en local (file://),
   où un cookie de domaine ne peut pas être posé. */

(function(){
  var CLE = 'verdier-theme';
  var root = document.documentElement;

  function domaineParent(){
    var h = location.hostname || '';
    var m = h.match(/([^.]+\.[^.]+)$/);          // « laser.x.fr » -> « x.fr »
    return (h && h !== 'localhost' && m) ? '; domain=.' + m[1] : '';
  }

  function lire(){
    var m = document.cookie.match(/(?:^|;\s*)verdier-theme=(light|dark)/);
    if (m) return m[1];
    try { return localStorage.getItem(CLE); } catch(e) { return null; }
  }

  function ecrire(v){
    try {
      document.cookie = CLE + '=' + v + '; path=/; max-age=31536000; SameSite=Lax' + domaineParent();
    } catch(e) {}
    try { localStorage.setItem(CLE, v); } catch(e) {}
  }

  function courant(){
    var a = root.getAttribute('data-theme');
    if (a) return a;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  var choisi = lire();
  if (choisi) root.setAttribute('data-theme', choisi);

  // Plusieurs boutons possibles (en-tête + pied) : on les câble tous.
  var boutons = document.querySelectorAll('.theme-btn');
  for (var i = 0; i < boutons.length; i++){
    boutons[i].addEventListener('click', function(){
      var suivant = courant() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', suivant);
      ecrire(suivant);
    });
  }
})();

/* ---------- Menu en étroit ----------------------------------------------
   Sous 860 px la barre de navigation est repliée derrière un bouton. Le CSS
   fait tout l'affichage ; le JS ne pose qu'une classe et tient
   aria-expanded à jour pour les lecteurs d'écran. */

(function(){
  var btn = document.querySelector('.nav-btn');
  var nav = document.querySelector('.navlinks');
  if (!btn || !nav) return;

  function replier(){
    nav.classList.remove('ouvert');
    btn.setAttribute('aria-expanded', 'false');
  }

  btn.setAttribute('aria-expanded', 'false');

  btn.addEventListener('click', function(e){
    e.stopPropagation();
    var ouvert = nav.classList.toggle('ouvert');
    btn.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
  });

  // Un clic sur un lien, ailleurs, ou Échap referme.
  nav.addEventListener('click', function(e){ if (e.target.tagName === 'A') replier(); });
  document.addEventListener('click', replier);
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape') replier(); });
})();

/* ---------- Visionneuse d'images ----------------------------------------
   S'active sur [data-agrandir], et sur les deux sélecteurs historiques du
   site laser — au chantier 3 le kit remplacera son script en place, il ne
   doit rien lui retirer au passage. */

(function(){
  var lb = document.getElementById('lightbox');
  if (!lb) return;                                  // page sans visionneuse

  var img   = document.getElementById('lbImg');
  var close = document.getElementById('lbClose');
  if (!img) return;

  function ouvrir(src, alt){
    img.src = src; img.alt = alt || '';
    lb.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
  function fermer(){
    lb.classList.remove('open'); img.src = '';
    document.body.style.overflow = '';
  }

  var cibles = document.querySelectorAll('[data-agrandir], .mode .shot img, .diagram img');
  for (var i = 0; i < cibles.length; i++){
    (function(el){
      el.style.cursor = 'zoom-in';
      el.addEventListener('click', function(){ ouvrir(el.currentSrc || el.src, el.alt); });
    })(cibles[i]);
  }

  lb.addEventListener('click', fermer);
  if (close) close.addEventListener('click', function(e){ e.stopPropagation(); fermer(); });
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape') fermer(); });
})();
