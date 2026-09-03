"""Le catalogue de chaînes, jugé À LA SOURCE — TF-0383.

Lot : question humaine du 19/08/2026, instruite par l'étude d'opportunité
`20260819-etude-opportunite-module-de-traduction.md` du pilot (verdict O3, premier temps).

**LE FAIT, MESURÉ.** Sur un produit client livré dont le `CLAUDE.md` déclare « i18n 7 languages
(fr, en, es, pt, it, ro, pl), auto-detect from browser, **fallback French** » : le catalogue
`web/src/i18n/locales/*.json` porte **245 clés** en français, **245** en anglais — et **95
seulement** en `es`, `it`, `pl`, `pt`, `ro`. Soit **150 clés manquantes par locale, 61 %**, 750
chaînes servies en français par le repli **sans qu'aucun message ne le signale**.

**ET LE PAN `i18n` NE POUVAIT PAS LE VOIR.** Il lit le BUILD SERVI, et sa limite déclarée le dit :
« seule une locale PRÉFIXÉE est jugée sur sa langue ». Ce produit choisit sa langue par détection
navigateur, sans préfixe d'URL : toutes les routes existent dans toutes les locales et le repli
sert du français. Le pan était donc **structurellement aveugle** à cette forme — qui est la forme
DOMINANTE du parc : sur 22 projets, trois portent un catalogue de chaînes et **aucun** n'est un
site à locales préfixées comme celui sur lequel le pan avait été conçu.

**Ce module ne remplace pas le pan, il lui ouvre un second point d'observation.** Le build servi
dit ce que le visiteur reçoit ; le catalogue dit ce que le produit PRÉTEND savoir dire. Les deux
peuvent se contredire, et cette contradiction est un résultat, pas un défaut de mesure.

**Trois contrôles, tous des comparaisons EXACTES, aucun modèle appelé.**

  (d) COMPLÉTUDE — chaque clé de l'UNION des locales existe dans chaque locale. L'union et non
      une locale de référence : choisir la référence serait une inférence, et le pan mesure déjà
      la parité de routes « contre l'UNION des routes de toutes les locales ». Même règle, même
      raison.
  (e) INTÉGRITÉ DES PARAMÈTRES — les mêmes `{{param}}`, `{param}`, `%(param)s` de part et d'autre,
      ni perdus ni inventés. Un paramètre perdu rend un trou dans la phrase ; un paramètre inventé
      rend le littéral. Sur le produit mesuré : 27 paramètres, **0 divergence** — le contrôle
      MAINTIENT un état propre au lieu de rattraper une dette, et c'est le moment le moins cher
      pour l'écrire.
  (f) CONSTANCE DES LIBELLÉS — deux clés dont la valeur source est IDENTIQUE et dont la traduction
      DIFFÈRE dans une même locale. C'est ce que `systeme-de-marque/references/voix.md` prescrit
      déjà (« un libellé, un seul, d'un bout à l'autre du parcours ») et que rien ne jouait.

**Ce que ce module NE juge PAS, et le dire est la condition pour que le reste soit cru** : la
JUSTESSE d'une traduction. La doctrine du socle de marque tranche déjà, et se transpose mot pour
mot : « la justesse d'une voix n'est pas décidable par script… ce qui EST vérifiable, c'est la
constance ». Un catalogue complet, aux paramètres intacts et aux libellés constants peut être
intégralement mal traduit — cela se relit, cela ne se calcule pas.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from forge_tests import exclusions

#: Dossiers où un catalogue de chaînes vit conventionnellement. Découverts sur le disque, jamais
#: supposés — un dossier ajouté demain est vu sans qu'une ligne change ici.
DOSSIERS = ("locales", "messages", "translations", "i18n", "lang", "langs")

#: Coupés à l'entrée : ce contrôle tourne sur TOUT audit, descendre dans les dépendances serait
#: un coût payé partout pour rien.
_EXCLUS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", "dist", "build", "out", ".next",
    ".nuxt", ".svelte-kit", "coverage", "htmlcov", ".pytest_cache", ".ruff_cache", "vendor",
    ".forge", "site-packages",
    # TF-0536/0542/0543 (lot Produit-02 20260823) : le SOCLE commun vient desormais
    # d'une source unique. Le depot portait DIX listes divergentes (7 a 31 entrees) et
    # `input` ne figurait dans AUCUNE : sur un audit reel, 12 constats sur 15 portaient sur
    # `input\` — un site concurrent aspire et une ancienne version du site. Les entrees
    # ci-dessus restent ecrites ici : elles portent le motif de CE pan.
    *exclusions.socle(),
}

#: Un nom de fichier de locale : `fr.json`, `en-GB.json`, `pt_BR.json`.
_NOM_LOCALE = re.compile(r"^([a-z]{2}(?:[-_][A-Za-z]{2,4})?)\.json$")

#: Les trois familles de paramètres rencontrées. `{{x}}` (i18next, vue-i18n), `{x}` (ICU, Intl),
#: `%(x)s` et `%s` (Python, C). Le motif capture le NOM quand il existe : c'est lui qui se compare,
#: pas la position — deux langues n'ordonnent pas leurs paramètres pareil, et l'exiger serait un
#: faux défaut.
_PARAMETRES = (
    re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}"),
    re.compile(r"(?<!\{)\{\s*([A-Za-z_][\w.]*)\s*(?:,[^}]*)?\}(?!\})"),
    re.compile(r"%\(([A-Za-z_]\w*)\)[sdif]"),
)

#: Catalogues qu'on SAIT ne pas savoir lire. Les taire ferait passer un produit à catalogue
#: TypeScript pour un produit sans catalogue — l'absence silencieuse que ce framework interdit.
_NON_LUS = (".ts", ".tsx", ".js", ".mjs", ".yaml", ".yml", ".po", ".xliff", ".xlf", ".properties")


def _aplatir(objet, prefixe: str = "") -> dict[str, str]:
    """Un catalogue imbriqué devient plat : `accueil.titre` → valeur. Les listes sont indexées."""
    plat: dict[str, str] = {}
    if isinstance(objet, dict):
        for cle, valeur in objet.items():
            plat.update(_aplatir(valeur, f"{prefixe}{cle}."))
    elif isinstance(objet, list):
        for rang, valeur in enumerate(objet):
            plat.update(_aplatir(valeur, f"{prefixe}{rang}."))
    elif objet is not None:
        plat[prefixe.rstrip(".")] = str(objet)
    return plat


def catalogues(cible: Path) -> tuple[dict[str, dict[str, dict[str, str]]], list[str]]:
    """Les catalogues LUS, et la liste NOMMÉE de ceux qu'on n'a pas su lire.

    Retour : ({dossier relatif : {locale : {clé plate : valeur}}}, motifs des non-lus).

    Le second membre n'est pas un détail de journal : un catalogue en TypeScript
    (`src/i18n/messages.ts`, forme réelle d'un produit du parc) serait sinon indistinguable d'une
    absence de catalogue, et le pan conclurait « rien à mesurer » sur un produit qui a tout à
    mesurer. On itère sur ce qu'on trouve, ET on déclare ce qu'on ne sait pas lire.
    """
    lus: dict[str, dict[str, dict[str, str]]] = {}
    non_lus: list[str] = []
    if not cible.is_dir():
        return lus, non_lus

    for dossier in sorted(_dossiers_candidats(cible)):
        relatif = dossier.relative_to(cible).as_posix()
        par_locale: dict[str, dict[str, str]] = {}
        autres: list[str] = []
        for fichier in sorted(dossier.iterdir()):
            if not fichier.is_file():
                continue
            trouve = _NOM_LOCALE.match(fichier.name)
            if trouve:
                try:
                    brut = json.loads(fichier.read_text(encoding="utf-8", errors="replace"))
                except json.JSONDecodeError as erreur:
                    non_lus.append(
                        f"`{relatif}/{fichier.name}` : JSON illisible ({erreur.msg}, ligne "
                        f"{erreur.lineno}) — refusé, jamais compté comme locale vide"
                    )
                    continue
                plat = _aplatir(brut)
                if plat:
                    par_locale[trouve.group(1)] = plat
            elif fichier.suffix.lower() in _NON_LUS:
                autres.append(fichier.name)
        if len(par_locale) >= 2:
            lus[relatif] = par_locale
        if autres:
            non_lus.append(
                f"`{relatif}` porte {len(autres)} fichier(s) de catalogue NON LU(S) "
                f"({', '.join(sorted(autres)[:4])}"
                f"{' …' if len(autres) > 4 else ''}) — seul le JSON par locale est comparé ici. "
                "Un catalogue dans un module TypeScript ou un fichier de gettext n est PAS jugé, "
                "et ce silence est déclaré plutôt que confondu avec une absence de catalogue"
            )
    return lus, non_lus


def _dossiers_candidats(cible: Path) -> list[Path]:
    """Découverte sur le DISQUE : tout dossier au nom conventionnel, dépendances coupées."""
    import os

    trouves: list[Path] = []
    for racine, dossiers, _ in os.walk(cible):
        dossiers[:] = sorted(nom for nom in dossiers if nom not in _EXCLUS)
        for nom in dossiers:
            if nom.lower() in DOSSIERS:
                trouves.append(Path(racine, nom))
    return trouves


def parametres(valeur: str) -> set[str]:
    """Les NOMS de paramètres d'une chaîne, toutes familles confondues.

    Un `%s` sans nom est compté par son rang (`%1`, `%2`…) : deux chaînes qui n'en portent pas le
    même NOMBRE divergent, et c'est tout ce qu'on peut affirmer sans nommer ce qu'on ignore.
    """
    noms: set[str] = set()
    for motif in _PARAMETRES:
        noms |= {m.group(1) for m in motif.finditer(valeur)}
    anonymes = len(re.findall(r"%[sdif]", re.sub(r"%\([A-Za-z_]\w*\)[sdif]", "", valeur)))
    noms |= {f"%{rang}" for rang in range(1, anonymes + 1)}
    return noms


#: Segments de clé qui désignent un libellé d'ACTION. `voix.md` §Actions ne prescrit la constance
#: que pour eux ; l'étendre à toutes les chaînes produit du bruit (mesuré : 6 faux positifs sur 6).
SEGMENTS_ACTION = frozenset({
    "action", "actions", "bouton", "boutons", "button", "buttons", "cta", "ctas",
    "commande", "commandes", "verbe", "verbes",
})


def est_action(cle: str) -> bool:
    """Vrai si la clé désigne un libellé d'action, au vu de ses segments.

    Reconnaissance par SEGMENT et non par sous-chaîne : `transaction.total` contient « action »
    sans être une action. Un catalogue qui ne nomme pas ses actions n'est donc pas jugé sur leur
    constance — c'est une limite du catalogue, déclarée, et non un contrôle qui se tait.
    """
    segments = {seg.casefold() for morceau in cle.split(".") for seg in morceau.split("_")}
    return bool(segments & SEGMENTS_ACTION)


def juger(par_locale: dict[str, dict[str, str]]) -> dict:
    """Les trois contrôles sur UN catalogue. Comparaisons exactes, aucun modèle appelé.

    L'union des clés sert de référence : choisir une locale de référence serait une inférence, et
    le pan mesure déjà la parité de routes « contre l UNION des routes de toutes les locales ».
    """
    union = sorted({cle for plat in par_locale.values() for cle in plat})
    manquantes: dict[str, list[str]] = {}
    divergences: list[dict] = []
    inconstances: list[dict] = []

    for locale, plat in sorted(par_locale.items()):
        absentes = [cle for cle in union if cle not in plat]
        if absentes:
            manquantes[locale] = absentes

    # (e) — QUI FAIT FOI ? Deux défauts de ma première écriture, tous deux révélés par les tests.
    #
    # J'avais pris pour référence le jeu de paramètres LE PLUS RICHE (`max(..., key=len)`). Sur
    # deux locales, cela transforme mécaniquement un paramètre INVENTÉ chez l'une en paramètre
    # PERDU chez l'autre : rien ne permet de distinguer les deux sans référence désignée, et
    # prétendre le contraire est une affirmation que la donnée ne porte pas.
    #
    # Règle tenue : la MAJORITÉ STRICTE des locales fait foi. Sans majorité, on nomme le
    # DÉSACCORD sans prendre parti — c'est moins satisfaisant et c'est vrai.
    groupes: dict[frozenset[str], list[str]] = {}
    for cle in union:
        vues = {loc: parametres(plat[cle]) for loc, plat in par_locale.items() if cle in plat}
        if len(vues) < 2:
            continue
        groupes = {}
        for locale, trouves in vues.items():
            groupes.setdefault(frozenset(trouves), []).append(locale)
        if len(groupes) == 1:
            continue
        classes_triees = sorted(groupes.items(), key=lambda kv: (-len(kv[1]), sorted(kv[1])))
        (majoritaire, tenants), *reste = classes_triees
        if len(tenants) > max(len(locs) for _, locs in reste):
            for ensemble, locales in reste:
                for locale in sorted(locales):
                    divergences.append({
                        "cle": cle,
                        "locale": locale,
                        "attendus": sorted(majoritaire),
                        "trouves": sorted(ensemble),
                        "perdus": sorted(majoritaire - ensemble),
                        "inventes": sorted(ensemble - majoritaire),
                        "reference": f"majorite ({', '.join(sorted(tenants))})",
                    })
        else:
            divergences.append({
                "cle": cle,
                "locale": ", ".join(sorted(vues)),
                "attendus": [],
                "trouves": [],
                "perdus": [],
                "inventes": [],
                "reference": "aucune majorite",
                "desaccord": {loc: sorted(par) for loc, par in sorted(vues.items())},
            })

    # (f) — CONSTANCE des libellés d'ACTION, sans locale d'origine élue.
    #
    # Second défaut de ma première écriture : je désignais comme source « la locale qui porte le
    # plus de clés », et sur un nombre égal de clés le choix devenait arbitraire — le contrôle
    # trouvait ou ne trouvait rien selon l'ordre de lecture des fichiers. Un contrôle dont le
    # verdict dépend de l'ordre du disque n'est pas un contrôle.
    #
    # Règle tenue, symétrique : si DEUX clés d'action portent la MÊME valeur dans une locale
    # quelconque, elles doivent porter la même dans toutes les autres. Aucune origine n'est élue,
    # et le constat nomme la locale où la divergence est servie.
    #
    # RESSERRAGE MOTIVÉ PAR UNE MESURE. Comparer TOUTES les clés donnait 6 constats sur un
    # catalogue réel de 245 clés × 7 locales, et 6 FAUX POSITIFS : du français correct — « Tous »/
    # « Toutes », « Approuvé »/« Approuvée » (accord en genre), « Créée le »/« Date de création »
    # (ligne de détail contre en-tête). Un contrôle à ce taux de bruit ne se corrige pas, il se
    # fait ignorer (R-33 bis). La doctrine ne parlait d'ailleurs jamais de toutes les chaînes :
    # `voix.md` §Actions dit « un libellé, un seul, d'un bout à l'autre du parcours ».
    #
    # Ce que le resserrage abandonne, et il faut le dire : un STATUT rendu de deux façons dans un
    # même produit n'est plus vu. Le distinguer d'un accord légitime demande de lire, pas de
    # comparer.
    vues_inconstance: set[tuple[str, tuple[str, ...]]] = set()
    for source in sorted(par_locale):
        par_texte: dict[str, list[str]] = {}
        for cle, valeur in par_locale[source].items():
            if not est_action(cle):
                continue
            norme = " ".join(valeur.split()).casefold()
            if norme:
                par_texte.setdefault(norme, []).append(cle)
        for norme, cles in sorted(par_texte.items()):
            if len(cles) < 2:
                continue
            for locale, plat in sorted(par_locale.items()):
                if locale == source:
                    continue
                rendus = {plat[cle] for cle in cles if cle in plat}
                if len(rendus) > 1:
                    signature = (locale, tuple(sorted(cles)))
                    if signature in vues_inconstance:
                        continue
                    vues_inconstance.add(signature)
                    inconstances.append({
                        "locale": locale,
                        "source": norme,
                        "locale_source": source,
                        "cles": sorted(cles),
                        "rendus": sorted(rendus),
                    })

    return {
        "locales": sorted(par_locale),
        "union": len(union),
        "manquantes": manquantes,
        "divergences": divergences,
        "inconstances": inconstances,
        "comptes": {loc: len(plat) for loc, plat in sorted(par_locale.items())},
    }


NON_JUGE = [
    "i18n catalogue : la JUSTESSE d une traduction n est PAS jugee — ni sa fidelite, ni son "
    "registre, ni sa terminologie. Un catalogue complet, aux parametres intacts et aux libelles "
    "constants peut etre integralement mal traduit. La doctrine du socle de marque le dit deja "
    "pour la voix : « la justesse n est pas decidable par script, ce qui EST verifiable c est la "
    "constance » — et le declarer est la condition pour que les trois controles soient crus",
    "i18n catalogue : seul le JSON par locale est compare (`fr.json`, `en-GB.json`). Un catalogue "
    "dans un module TypeScript, un YAML ou un fichier gettext est NOMME comme non lu, jamais "
    "confondu avec une absence de catalogue — c est la difference entre « je ne sais pas lire » et "
    "« il n y a rien a lire »",
    "i18n catalogue : la completude se mesure contre l UNION des cles de toutes les locales. Une "
    "cle presente dans une seule langue manque donc dans les autres — sur un produit ou la "
    "traduction est en cours PAR CHOIX, l ecart est reel mais il peut etre voulu : il se conteste "
    "par declaration, il ne se devine pas",
    "i18n catalogue : quand les locales ne s accordent pas sur les parametres d une cle, c est la "
    "MAJORITE STRICTE qui fait foi. SANS majorite (deux locales qui divergent, par exemple), le "
    "desaccord est NOMME sans prendre parti : rien ne permet alors de distinguer un parametre "
    "INVENTE d un parametre PERDU, et pretendre le contraire serait une affirmation que la donnee "
    "ne porte pas",
    "i18n catalogue : l ordre des parametres n est PAS compare, seuls leurs NOMS le sont — deux "
    "langues n ordonnent pas leurs parametres pareil, et l exiger serait un faux defaut. Un `%s` "
    "sans nom est compte par son RANG : on n affirme alors que le nombre",
    "i18n catalogue : la constance ne porte que sur les libelles d ACTION, reconnus au SEGMENT de "
    "cle (`action`, `bouton`, `button`, `cta`, `commande`, `verbe`). C est ce que `voix.md` "
    "§Actions prescrit, et l etendre a toutes les chaines produit du bruit : mesure sur un "
    "catalogue reel de 245 cles x 7 locales, 6 constats et 6 FAUX POSITIFS, tous du francais "
    "correct (Tous/Toutes, Approuve/Approuvee, accord en genre). Ce que le resserrage abandonne : "
    "un STATUT rendu de deux facons dans un meme produit n est plus vu — le distinguer d un accord "
    "legitime demande de lire, pas de comparer",
    "i18n catalogue : un catalogue qui ne NOMME pas ses actions (aucun segment `action`/`bouton`/"
    "`cta`) n est pas juge sur leur constance. C est une limite du catalogue, declaree — pas un "
    "controle qui se tait",
    "i18n catalogue : ce module lit les SOURCES, le pan i18n lit le BUILD SERVI. Les deux peuvent "
    "se contredire (un catalogue complet mal cable, un build complet sur catalogue troue) : cette "
    "contradiction est un RESULTAT, pas un defaut de mesure",
]
