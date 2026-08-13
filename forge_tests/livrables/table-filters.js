/* Copie verbatim D-12 du composant filtres du socle digit-ai-page-html
   (assets/table-filters.js, skill installé) — provenance : forge-agents, resynchronisée le
   2026-08-13 (TF-0175 : lignes [data-detail] ignorées). Le chargeur préfère l'asset du
   skill installé ; cette copie est le repli pour un poste sans skill. */
/* Digit-AI — Filtres de colonne sur tableaux de données.
   Socle commun : voir references/composant-filtres-tableau.md (checklist G1-G6).
   Viewer-only : le JS ne s'exécute pas à l'export WeasyPrint, la regle @media print
   du livrable doit reafficher tr[data-tf-hidden]. */
(function (root) {
  'use strict';

  var SEUIL_LIGNES = 8;

  function norm(s) {
    return String(s == null ? '' : s)
      .normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
  }

  function corps(table) {
    var tb = table.tBodies && table.tBodies[0];
    /* TF-0175 : une ligne [data-detail] est le DÉPLIANT pleine largeur de la ligne qui la
       précède — elle ne porte pas de données de colonnes et ne compte ni ne se filtre. */
    return tb ? Array.prototype.slice.call(tb.rows).filter(function (tr) {
      return !tr.hasAttribute('data-detail');
    }) : [];
  }

  function valeur(tr, i) {
    var td = tr.cells[i];
    return td ? td.textContent.trim() : '';
  }

  /* Une colonne est categorielle si ses valeurs se repetent : cardinalite < nb lignes.
     Un th peut forcer (data-filter-col) ou exclure (data-filter-col="off"). */
  function colonnesFiltrables(table, lignes) {
    var ths = table.tHead ? Array.prototype.slice.call(table.tHead.rows[0].cells) : [];
    var out = [];
    ths.forEach(function (th, i) {
      var forcee = th.getAttribute('data-filter-col');
      if (forcee === 'off') return;
      var distinctes = {}, n = 0;
      lignes.forEach(function (tr) {
        var v = valeur(tr, i);
        if (!(v in distinctes)) { distinctes[v] = 1; n++; }
      });
      if (forcee !== null || (n > 1 && n < lignes.length)) out.push({ th: th, index: i, valeurs: Object.keys(distinctes).sort() });
    });
    return out;
  }

  function bouton(col, id) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'tf-btn';
    b.setAttribute('aria-expanded', 'false');
    b.setAttribute('aria-controls', id);
    b.setAttribute('aria-label', 'Filtrer ' + col.th.textContent.trim());
    b.textContent = '▾';
    return b;
  }

  function panneau(col, id) {
    var p = document.createElement('div');
    p.className = 'tf-panel';
    p.id = id;
    p.hidden = true;
    p.setAttribute('role', 'group');
    p.setAttribute('aria-label', 'Filtrer ' + col.th.textContent.trim());

    var rech = document.createElement('input');
    rech.type = 'search';
    rech.className = 'tf-search';
    rech.placeholder = 'Rechercher…';
    rech.setAttribute('aria-label', 'Rechercher une valeur');

    var actions = document.createElement('div');
    actions.className = 'tf-actions';
    var tous = document.createElement('button');
    tous.type = 'button'; tous.className = 'tf-all'; tous.textContent = 'Tous';
    var aucun = document.createElement('button');
    aucun.type = 'button'; aucun.className = 'tf-none'; aucun.textContent = 'Aucun';
    actions.appendChild(tous); actions.appendChild(aucun);

    var opts = document.createElement('div');
    opts.className = 'tf-opts';
    col.valeurs.forEach(function (v) {
      var lab = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.className = 'tf-opt';
      cb.value = v;
      cb.checked = true;                    /* etat initial : tout coche, aucun filtre actif */
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(' ' + (v === '' ? '(vide)' : v)));
      opts.appendChild(lab);
    });

    p.appendChild(rech); p.appendChild(actions); p.appendChild(opts);
    return { panneau: p, recherche: rech, tous: tous, aucun: aucun, options: opts };
  }

  function init(table) {
    if (!table || table.getAttribute('data-tf-ready') === '1') return null;
    if (table.getAttribute('data-filterable') === 'off') return null;

    var lignes = corps(table);
    var cols = colonnesFiltrables(table, lignes);
    if (!cols.length) return null;

    var id = table.id || ('tf-' + Math.random().toString(36).slice(2, 8));
    table.id = id;
    var compteur = document.querySelector('[data-tf-count-for="' + id + '"]');
    var etats = [];

    function appliquer() {
      var visibles = 0;
      lignes.forEach(function (tr) {
        var ok = etats.every(function (e) {
          return e.selection[valeur(tr, e.col.index)] === true;
        });
        if (ok) { tr.removeAttribute('data-tf-hidden'); tr.style.display = ''; visibles++; }
        else {
          tr.setAttribute('data-tf-hidden', ''); tr.style.display = 'none';
          /* la ligne de détail suit le sort de sa ligne mère : masquée ET repliée */
          var det = tr.nextElementSibling;
          if (det && det.hasAttribute('data-detail')) { det.hidden = true; }
        }
      });
      etats.forEach(function (e) {
        var actif = Object.keys(e.selection).some(function (k) { return !e.selection[k]; });
        e.bouton.classList.toggle('tf-on', actif);
      });
      if (compteur) {
        compteur.textContent = visibles + ' ligne' + (visibles > 1 ? 's' : '') +
          ' sur ' + lignes.length;
        compteur.classList.toggle('zero', visibles === 0);
      }
    }

    cols.forEach(function (col, k) {
      var pid = id + '-tf-' + k;
      var b = bouton(col, pid);
      var ui = panneau(col, pid);
      var selection = {};
      col.valeurs.forEach(function (v) { selection[v] = true; });
      var etat = { col: col, bouton: b, selection: selection };
      etats.push(etat);

      col.th.style.position = col.th.style.position || 'relative';
      col.th.appendChild(b);
      col.th.appendChild(ui.panneau);

      b.addEventListener('click', function () {
        var ouvert = b.getAttribute('aria-expanded') === 'true';
        fermerTout();
        if (!ouvert) { b.setAttribute('aria-expanded', 'true'); ui.panneau.hidden = false; ui.recherche.focus(); }
      });

      ui.recherche.addEventListener('input', function () {
        var q = norm(ui.recherche.value);
        Array.prototype.forEach.call(ui.options.children, function (lab) {
          lab.hidden = q !== '' && norm(lab.textContent).indexOf(q) === -1;
        });
      });

      /* Tous / Aucun portent sur les valeurs actuellement visibles dans la liste. */
      function masse(valeurCible) {
        Array.prototype.forEach.call(ui.options.children, function (lab) {
          if (lab.hidden) return;
          var cb = lab.querySelector('.tf-opt');
          cb.checked = valeurCible;
          selection[cb.value] = valeurCible;
        });
        appliquer();
      }
      ui.tous.addEventListener('click', function () { masse(true); });
      ui.aucun.addEventListener('click', function () { masse(false); });

      ui.options.addEventListener('change', function (ev) {
        var cb = ev.target;
        if (!cb.classList.contains('tf-opt')) return;
        selection[cb.value] = cb.checked;
        appliquer();
      });

      ui.panneau.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape') { fermerTout(); b.focus(); }
      });
    });

    function fermerTout() {
      etats.forEach(function (e) {
        e.bouton.setAttribute('aria-expanded', 'false');
        var p = document.getElementById(e.bouton.getAttribute('aria-controls'));
        if (p) p.hidden = true;
      });
    }

    document.addEventListener('click', function (ev) {
      if (!table.contains(ev.target)) fermerTout();
    });

    table.setAttribute('data-tf-ready', '1');
    appliquer();
    return { appliquer: appliquer, fermerTout: fermerTout };
  }

  function initAll(racine) {
    var scope = racine || document;
    return Array.prototype.map.call(
      scope.querySelectorAll('table[data-filterable]'),
      function (t) { return init(t); }
    );
  }

  root.DigitAITableFilters = { init: init, initAll: initAll, SEUIL_LIGNES: SEUIL_LIGNES };
})(typeof window !== 'undefined' ? window : this);
