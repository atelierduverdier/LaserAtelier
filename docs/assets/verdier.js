/* ENGENDRÉ — ne pas éditer ici.
   Ce fichier est une copie de kit/verdier.js du dépôt atelierduverdier/site. Toute retouche faite ici sera écrasée : corriger la source, puis relancer outils/diffuser_kit.py. */
/* =========================================================================
   verdier.js — comportements communs de la charte Atelier du Verdier
   =========================================================================
   FICHIER DU KIT, recopié dans chaque site par outils/diffuser_kit.py.
   Ne pas l'éditer dans une copie : elle sera écrasée.
   Source : atelierduverdier/site — kit/verdier.js

   Trois choses seulement : la bascule de thème, la visionneuse d'images,
   et l'apparition au défilement.
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


/* ---------- Apparition au défilement -------------------------------------
   Les blocs montent doucement en entrant dans le champ, au lieu d'être
   tous là d'emblée.

   LE POINT QUI COMPTE : la classe qui rend un bloc invisible est posée
   ICI, par le script, et seulement après avoir vérifié que le navigateur
   sait l'animer. Écrite dans le HTML, elle aurait laissé une page BLANCHE
   à qui bloque le JavaScript — c'est le piège classique de ce genre
   d'effet, et il ne pardonne pas sur un site de documentation.

   Rien n'est observé au-dessus de la ligne de flottaison : un bloc déjà
   visible au chargement doit l'être tout de suite, pas se mettre à bouger
   sous les yeux du visiteur.

   Le décalage entre voisins (60 ms) donne le petit ruissellement d'une
   rangée de cartes. Au-delà de six, on arrête de décaler : sur une longue
   liste, l'attente se verrait. */

(function(){
  if (!('IntersectionObserver' in window)) return;
  if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var SELECTEUR = [
    'section .sec-tag', 'section > .wrap > h2', 'section > .wrap > .sec-lede',
    'section > .wrap > p', 'section > .wrap > h3',
    '.carte', '.panel', '.figure', '.plan', '.capture',
    '.callout', '.step', '.cols > *', '.liens'
  ].join(',');

  /* LA PORTE D'ENTRÉE DES SATELLITES. Cette liste ne nomme que des classes
     du kit — c'est voulu : le kit ne doit RIEN savoir du balisage d'un site
     hôte. Mesuré le 27/08/2026 en diffusant : le journal PrintNC chargeait
     bien la feuille et le script, et marquait ZÉRO bloc, parce qu'il a ses
     propres noms. Il avait la mécanique sans l'effet.

     C'est donc à l'hôte de se déclarer, avec ses noms à lui :

         <meta name="verdier-mouvement" content=".doc-section, .recit-p">

     Ce qu'il déclare s'AJOUTE à la liste du kit, il ne la remplace pas. */
  var decl = document.querySelector('meta[name="verdier-mouvement"]');
  var sup = decl ? (decl.getAttribute('content') || '').trim() : '';

  var blocs;
  try {
    blocs = [].slice.call(document.querySelectorAll(
      sup ? SELECTEUR + ',' + sup : SELECTEUR));
  } catch (e) {
    /* Un sélecteur mal écrit dans le <meta> ferait tomber TOUT le bloc, et
       rien ne serait révélé — une panne dont la cause est chez l'hôte et
       ne se voit pas d'ici. On se rabat sur la seule liste du kit, qui,
       elle, est connue bonne. */
    blocs = [].slice.call(document.querySelectorAll(SELECTEUR));
  }
  if (!blocs.length) return;

  var haut = window.innerHeight || 800;

  /* DEUX LIMITES, ET ELLES NE RÉPONDENT PAS À LA MÊME QUESTION. Les avoir
     confondues a coûté deux corrections le 27/08/2026 :

     — MARQUER demande « ce bloc est-il hors de l'écran au chargement ? ».
       La réponse est le PLI lui-même. Un bloc qui affleure, même de dix
       pixels, ne doit pas être caché : il laisserait une bande vide en bas
       de l'écran jusqu'au premier défilement. Relevé sur « Documentation »
       et « Glossaire » du journal PrintNC — un bloc à y=839 pour une
       fenêtre de 900, soit 61 px de blanc à l'arrivée sur la page.

     — RÉVÉLER demande « est-il assez entré ? ». La réponse est plus haut,
       à 92 % : un bloc qui pointe d'un pixel n'est pas encore lu.

     `LIGNE` sert donc à l'observateur ET au filet, qui posent bien la même
     question ; le marquage, lui, compare au pli. */
  var LIGNE = 0.92;

  /* LE DÉCALAGE SE CALCULE À L'ENTRÉE, PAS AU MARQUAGE. C'était l'inverse,
     et c'était faux : le rang venait du rang parmi les FRÈRES, ce qui a du
     sens pour une rangée de cartes et aucun pour un article. Mesuré le
     27/08/2026 sur le récit du journal PrintNC — quarante paragraphes tous
     frères, rangs relevés [0,1,2,3,4,5,5,5,5,5] : à partir du sixième,
     chaque bloc traînait 300 ms de retard sur le moment juste. Un
     paragraphe qu'on atteint en lisant doit paraître MAINTENANT.

     Ce qui mérite un décalage, ce n'est pas d'être voisin dans le balisage,
     c'est d'ENTRER EN MÊME TEMPS. L'observateur livre justement par
     paquets : ce qui a franchi la ligne dans la même image. Une rangée de
     cartes arrive donc ensemble et ruisselle ; un paragraphe isolé arrive
     seul, et sans attendre.

     Le paquet est trié de haut en bas — son ordre de livraison ne suit pas
     l'ordre visuel — pour que le ruissellement descende. */
  var obs = new IntersectionObserver(function(entrees){
    var lot = [];
    for (var i = 0; i < entrees.length; i++){
      if (entrees[i].isIntersecting) lot.push(entrees[i]);
    }
    lot.sort(function(a, b){
      var da = a.boundingClientRect, db = b.boundingClientRect;
      return (da.top - db.top) || (da.left - db.left);
    });
    for (var j = 0; j < lot.length; j++){
      var el = lot[j].target;
      el.style.transitionDelay = (Math.min(j, 5) * 60) + 'ms';
      el.classList.add('vu');
      obs.unobserve(el);                     // une fois vu, on n'y revient pas
    }
  }, { rootMargin: '0px 0px -' + Math.round((1 - LIGNE) * 100) + '% 0px',
       threshold: 0.06 });

  function marquer(liste){
    var poses = 0;
    for (var i = 0; i < liste.length; i++){
      var el = liste[i];
      if (el.classList.contains('js-reveal')) continue;   // deja vu passer
      var boite = el.getBoundingClientRect();

      /* UN BLOC NON RENDU NE DOIT JAMAIS ÊTRE MARQUÉ. Le journal PrintNC
         cache 274 éléments derrière ses filtres : `display:none`. Marqué
         `opacity:0`, un tel bloc ne croise jamais le champ — l'observateur
         ne se déclenche donc pas — et le jour où le filtre le rouvre, il
         est INVISIBLE POUR TOUJOURS. Du contenu perdu, sans message.

         Il se trouve qu'un élément non rendu mesure 0 et que son `top` vaut
         0, donc la ligne suivante l'écartait déjà — par accident. Le test
         est maintenant écrit pour ce qu'il fait. */
      if (!boite.width || !boite.height) continue;

      if (boite.top < haut) continue;               // affleure déjà : on n'y touche pas

      /* DEUX INTERDITS, ET ILS NE PROTEGENT PAS LA MEME CHOSE. Les avoir
         fondus en un seul a coute trois versions le 27/08/2026 : trop
         etroit, puis trop large.

         1. PAS DANS UN BLOC DEJA MARQUE. Une carte qui monte pendant que
            sa rangee de liens monte a son tour, ce sont deux mouvements
            pour une seule chose.

         2. PAS DANS UNE CARTE NI UN PANNEAU. Celui-la est le vrai piege :
            `.js-reveal` pose un `transform`, et UN ELEMENT TRANSFORME
            DEVIENT LE BLOC CONTENEUR de ses descendants positionnes en
            absolu. Le recouvrement qui rend une carte entiere cliquable se
            repliait donc sur sa seule rangee de liens — 319 x 74 au lieu
            de 365 x 376, trois quarts de carte morts. Et il ne suffit pas
            de regarder les ancetres MARQUES : les cartes du haut d'une page
            sont au-dessus du pli, donc ecartees, tandis que leur rangee de
            liens tombe dessous et se faisait marquer.

         CE QUE LA VERSION PRECEDENTE INTERDISAIT EN TROP. Elle ecartait
         tout descendant d'un CANDIDAT quelconque. Or `.liens` est dans la
         liste du kit : sur la page de liens, dont les sept cartes `.lien`
         vivent dedans, plus rien ne pouvait etre revele — la page avait
         beau declarer ses classes, elles etaient ecartees en silence. Le
         second interdit ne nomme donc que ce qui porte un recouvrement. */
      var pere = el.parentElement;
      if (pere && (pere.closest('.js-reveal') || pere.closest('.carte,.panel'))) continue;

      /* 3. PAS UN BLOC QUI PORTE UNE VUE 3D. C'est le MEME piege que le
            recouvrement cliquable ci-dessus, par l'autre bout : `.js-reveal`
            pose un `transform`, l'element transforme devient le referentiel
            de ses descendants en position absolue, et <model-viewer> y place
            justement son canvas WebGL partage. Resultat : le modele
            s'affiche, mais il ne repond plus a la souris.
            Mesure du 28/08/2026 sur la page des modeles 3D : cinq cartes sur
            six etaient mortes, et la seule qui tournait encore etait la
            premiere — au-dessus du pli, donc ecartee par le test ci-dessus.
            Le symptome designait la cause. */
      if (el.querySelector && el.querySelector('model-viewer')) continue;

      el.classList.add('js-reveal');
      obs.observe(el);
      poses++;
    }
    return poses;
  }

  marquer(blocs);

  /* LE FILET. Tout ce dispositif n'a qu'un seul mauvais dénouement : un
     bloc marqué `opacity:0` dont l'observateur ne tire jamais, donc du
     CONTENU INVISIBLE — et invisible sans message, ce qui est pire qu'une
     page cassée.

     Ce n'est pas une crainte en l'air. Relevé le 27/08/2026 : dans un
     onglet non affiché, Chrome cesse de délivrer les intersections. Sept à
     onze blocs sont restés à zéro dans le champ, indéfiniment. Un visiteur
     qui ouvre le site dans un onglet d'arrière-plan — ce que fait tout clic
     du milieu — est exactement dans ce cas.

     Le filet balaie donc ce qui est dans le champ et le montre, quelle que
     soit la raison du silence : onglet caché, retour de bfcache,
     navigateur qui throttle. Il se déclenche au retour de visibilité et
     une fois passé un délai. L'observateur reste le chemin normal ; ceci
     ne fait que borner le pire cas. */
  function filet(){
    var restants = document.querySelectorAll('.js-reveal:not(.vu)');
    for (var i = 0; i < restants.length; i++){
      var b = restants[i].getBoundingClientRect();
      /* LA MÊME LIGNE QUE L'OBSERVATEUR, d'où la constante partagée. Si le
         filet se déclenchait plus tôt, il montrerait les blocs AVANT
         l'observateur, sans le décalage entre voisins : il remplacerait
         l'effet au lieu de le rattraper. */
      if (b.top < haut * LIGNE && b.bottom > 0) restants[i].classList.add('vu');
    }
    return document.querySelector('.js-reveal:not(.vu)') !== null;
  }

  /* Le filet suit le défilement, mais de loin : 250 ms de repos entre deux
     passages, quand l'observateur, lui, répond dans l'instant. Dans un
     onglet sain c'est donc TOUJOURS l'observateur qui montre le bloc, et le
     filet ne trouve plus rien à faire. Il se retire dès qu'il ne reste
     aucun bloc marqué — un site parcouru jusqu'au bout ne garde aucun
     écouteur. */
  var dernier = 0;
  function veiller(){
    var t = +new Date();
    if (t - dernier < 250) return;
    dernier = t;
    if (!filet()) {
      window.removeEventListener('scroll', veiller);
      window.removeEventListener('resize', veiller);
      document.removeEventListener('visibilitychange', reveil);
    }
  }
  function reveil(){ if (!document.hidden) { dernier = 0; setTimeout(veiller, 200); } }
  window.addEventListener('scroll', veiller, { passive: true });
  window.addEventListener('resize', veiller, { passive: true });
  document.addEventListener('visibilitychange', reveil);
  setTimeout(function(){ dernier = 0; veiller(); }, 4000);

  /* LE RE-BALAYAGE, pour les pages qui construisent leur vue APRÈS le
     chargement. Relevé le 27/08/2026 sur le journal PrintNC : au chargement,
     ZÉRO de ses 112 blocs de récit est rendu — ils vivent derrière quatre
     cartes, et son propre script les montre au clic. Le kit passe donc trop
     tôt, et repasser tout seul (MutationObserver) reviendrait à deviner.

     L'hôte appelle :  verdierMouvement.rescanner()

     LÀ OÙ IL NE FAUT PAS L'APPELER : sur un filtre ou une recherche. Faire
     APPARAÎTRE EN FONDU des résultats que le visiteur vient de demander,
     c'est lui faire attendre ce qu'il a déjà demandé. Le fondu est fait
     pour un document qu'on parcourt, pas pour une liste qui répond. */
  window.verdierMouvement = {
    rescanner: function(racine){
      var cible = racine || document;
      var trouves;
      try {
        trouves = [].slice.call(cible.querySelectorAll(
          sup ? SELECTEUR + ',' + sup : SELECTEUR));
      } catch (e) {
        trouves = [].slice.call(cible.querySelectorAll(SELECTEUR));
      }
      haut = window.innerHeight || haut;   // la fenêtre a pu changer depuis
      var poses = marquer(trouves);
      if (poses) {
        /* Le filet a pu se retirer si tout était révélé avant ce lot. */
        window.addEventListener('scroll', veiller, { passive: true });
        window.addEventListener('resize', veiller, { passive: true });
        setTimeout(function(){ dernier = 0; veiller(); }, 4000);
      }
      return poses;
    }
  };
})();

/* ---------- La carte entière emmène au lien -----------------------------
   Une carte qui se soulève au survol annonce qu'on peut cliquer dessus.
   Jusqu'ici il fallait viser le lien : l'annonce était fausse.

   POURQUOI ICI ET PAS DANS LE HTML. Le recouvrement est le `::after` d'un
   vrai lien, et c'est ce qui fait tenir tout le reste — clic du milieu,
   « ouvrir dans un nouvel onglet », adresse dans la barre d'état, tabulation
   au clavier. Un `onclick` sur la carte aurait cassé les quatre. Le script
   ne fait que DÉSIGNER quel lien s'étire ; c'est la feuille de style qui
   l'étire.

   LE PREMIER LIEN GAGNE. Sur les fiches du portail c'est toujours « Comment
   il marche », la page d'ici ; les suivants — documentation, manuel, dépôt —
   partent ailleurs et gardent leur clic propre, en passant DEVANT le
   recouvrement.

   CE QU'ON NE TOUCHE PAS : une carte qui est déjà un `<a>` ou un `<button>`
   (le journal PrintNC fait ses quatre cartes d'accueil en boutons), et une
   carte sans aucun lien. */

(function(){
  var blocs = document.querySelectorAll('.carte,.panel');
  for (var i = 0; i < blocs.length; i++){
    var c = blocs[i];
    if (c.querySelector('.carte-cible')) continue;      // deja fait

    /* DEJA CLIQUABLE DE LUI-MEME : on ne pose pas de recouvrement, mais on
       le marque quand meme, parce que c'est cette classe qui autorise le
       souleve. Le journal PrintNC fait ses quatre cartes d'accueil en
       `<button onclick>` : sans cette branche, elles cesseraient de repondre
       au survol alors qu'elles mènent bel et bien quelque part. */
    if (c.tagName === 'A' || c.tagName === 'BUTTON' || c.hasAttribute('onclick')) {
      c.classList.add('carte-cliquable');
      continue;
    }

    /* UN CONTENU QUI SE MANIPULE NE SE RECOUVRE PAS. Le recouvrement est
       un `::after` en `inset:0` : il passe DEVANT tout le contenu de la
       carte. Sur un bloc de texte c'est le but ; sur une vue 3D, ça avale
       la souris et le modèle devient un décor.
       Mesuré le 28/08/2026 sur la page des modèles : seule la carte de
       l'attache tournait — la seule sans lien, donc la seule sans
       recouvrement. Le souleve au survol pose en plus un `transform`, et un
       élément transformé devient le référentiel de ses descendants en
       position absolue : `<model-viewer>` y place son canvas partagé. Deux
       raisons de laisser ces cartes tranquilles ; on ne pose donc NI la
       cible NI la classe. Le lien, lui, reste cliquable normalement. */
    if (c.querySelector('model-viewer,canvas,iframe,video')) continue;

    /* SANS LIEN, PAS DE SOULEVE. Un bloc qui bouge sous le curseur annonce
       un clic ; s'il n'en a pas, il ment. Sur ce site, 21 des 25 panneaux
       sont dans ce cas — ils restent immobiles. */
    var liens = c.querySelectorAll('a[href]');
    if (!liens.length) continue;

    c.classList.add('carte-cliquable');
    liens[0].classList.add('carte-cible');
    for (var j = 1; j < liens.length; j++) liens[j].classList.add('carte-dessus');
  }
})();
