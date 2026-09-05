"""Recette de la 404 personnalisee par langue — preuve du controle M-9 de la MEP (patron P-2).

CE QUE CET OUTIL SERT, ET POURQUOI IL EST GENERIQUE. Le patron P-2 du pilot
(`references\\PATRONS-EPROUVES.md`, TF-0802, decide le 03/09/2026) fait de la 404 personnalisee
par langue un standard d office, et le controle M-9 de `ETAPE-MEP.md` le juge au passage en
production — sur PREUVE : « sortie du controle executable du produit jouant ces trois cas ».
Tant que ce controle est celui du produit, chaque produit le reecrit, ou n en a pas et ne peut
pas prouver M-9. Cette recette est ce controle, ecrit une fois : elle se parametre par la liste
des prefixes de langue et l URL de preproduction, et sa sortie JSON est la piece que le dossier
de MEP joint a M-9. Candidature TF-0803 du registre du pilot, lot
`digit-ai-factory - RETOURS - 20260905a`.

LE FAIT FONDATEUR, mesure : le 404 nu d un serveur de fichiers (page blanche, sans menu ni
langue) a ete servi sur un site multilingue en production du 25/08 au 01/09/2026, vu par
l exploitant et par aucun controle. La 404 est la page que personne ne concoit parce que
personne ne la visite volontairement.

LES TROIS CAS JOUES, dans les termes de M-9 :

  (a) ADRESSE INCONNUE SOUS CHAQUE PREFIXE DE LANGUE — statut 404, jamais 200, avec une page du
      MEME gabarit que les autres (menu present) et dans la langue du prefixe.
  (b) NOINDEX ET ABSENCE DU SITEMAP — la page 404 porte `noindex` (meta robots ou en-tete
      `X-Robots-Tag`) et le sitemap ne liste aucune des adresses inconnues sondees, ni une page
      404 declaree par l operateur.
  (c) RESSOURCE NON-HTML INCONNUE — une image ou un script inconnu rend un 404 NU, jamais une
      page HTML : un navigateur qui attend une image et recoit un document est un defaut, meme
      quand le statut est juste.

LE DOUBLE SENS, qui est la raison d etre de la recette et non son ornement. Un controle qu on ne
voit jamais refuser ne controle rien. Les refus sont donc nommes un par un et chacun est eprouve
au banc (`tests/test_tf_0803_404_par_langue.py`) contre un serveur local qui le porte :

  - un serveur qui rend 200 sur une adresse inconnue : soft-404 indexable — REFUS ;
  - une reponse PENDUE (code 000) : c est le piege MESURE de la realisation de reference —
    envelopper `writeHead` sans envelopper `write()` fait partir le corps nu du serveur avant
    les en-tetes differes, et le client attend jusqu au delai. Le motif du refus le NOMME, parce
    qu un code 000 se lit sinon comme un incident reseau ;
  - une 404 sans menu, ou dans la mauvaise langue : le gabarit n est pas celui des autres pages ;
  - une 404 sans `noindex` : la page d erreur entre en index ;
  - une page HTML servie a la place d un 404 nu sur une ressource non-HTML.

CE QUE LA RECETTE NE MESURE PAS, et le DIT plutot que de le supposer :

  - la DECLARATION de l exclusion du sitemap dans l oracle SEO du produit (M-9 b, seconde
    moitie) : elle vit dans le depot du produit, pas dans une reponse HTTP ;
  - le « meme gabarit » quand la page de reference du prefixe ne porte ni `<nav>` ni le marqueur
    declare par `--marqueur-menu` : sans reference, la comparaison n a pas d objet.

UNE MESURE PARTIELLE N EST PAS UN PASS. Si un seul cas sort NON_MESURABLE, le verdict global est
NON_MESURABLE (code 2) : un verdict qu on ne peut pas prononcer et qu on tait passe pour un
verdict tenu, et c est exactement l erreur que M-9 existe pour empecher.

    uv run python recette/quatre_cent_quatre.py <url-de-preproduction> --prefixes fr,en,nl
    uv run python recette/quatre_cent_quatre.py https://staging.exemple --prefixes fr,en \
        --langue-par-defaut fr --sitemap /sitemap.xml --sortie preuve-m9.json

Sortie : JSON {verdict: PASS|FAIL|NON_MESURABLE, cas: [...]} · exit 0 = les trois cas tenus ·
1 = defaut mesure · 2 = je ne peux pas mesurer.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

#: Le chemin sonde est FIXE, jamais tire au hasard : une preuve de MEP se rejoue a l identique,
#: et une adresse differente a chaque run rendrait deux sorties incomparables.
SEGMENT_INCONNU = "sonde-404-forge-tests"
RESSOURCES_NON_HTML = ("sonde-404-forge-tests.png", "sonde-404-forge-tests.js")
DELAI_DEFAUT = 15

_LIEN = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_NAV = re.compile(r"<nav\b[^>]*>(.*?)</nav>", re.I | re.S)
_LANG = re.compile(r"""<html[^>]*\blang\s*=\s*["']([^"']+)["']""", re.I)
_META_ROBOTS = re.compile(r"""<meta[^>]+name\s*=\s*["']robots["'][^>]*>""", re.I)
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


# ---- Sondage : la seule partie qui parle au reseau -------------------------------------------
def sonder(url: str, delai: int = DELAI_DEFAUT) -> dict:
    """Une requete GET, et TOUT ce qu elle rend — y compris son echec, qui est une mesure.

    `code` vaut 0 quand rien n a pu etre lu. `pendue` distingue le delai depasse (le piege P-2)
    d une adresse injoignable : les deux rendent 0 cote client et ne veulent pas dire la meme
    chose. Aucune exception ne remonte : un sondage qui plante ferait taire les autres cas.
    """
    requete = urllib.request.Request(url, method="GET", headers={"User-Agent": "forge-tests/404"})
    try:
        with urllib.request.urlopen(requete, timeout=delai) as reponse:  # noqa: S310
            corps = reponse.read(200_000).decode("utf-8", "replace")
            return {"url": url, "code": reponse.status, "corps": corps,
                    "entetes": {k.lower(): v for k, v in reponse.headers.items()}}
    except urllib.error.HTTPError as err:  # 404 et consorts passent ici : ce sont des reponses
        corps = err.read(200_000).decode("utf-8", "replace") if err.fp else ""
        return {"url": url, "code": err.code, "corps": corps,
                "entetes": {k.lower(): v for k, v in (err.headers or {}).items()}}
    except TimeoutError:
        return {"url": url, "code": 0, "corps": "", "entetes": {}, "pendue": True,
                "erreur": f"aucune reponse complete en {delai} s"}
    except (urllib.error.URLError, OSError) as err:
        return {"url": url, "code": 0, "corps": "", "entetes": {}, "pendue": False,
                "erreur": str(getattr(err, "reason", err))}


def liens(html: str) -> set[str]:
    """Les cibles de lien d un document, ancres seules ecartees (elles ne font pas un menu)."""
    return {h.strip() for h in _LIEN.findall(html) if h.strip() and not h.strip().startswith("#")}


def liens_de_menu(html: str) -> set[str] | None:
    """Les liens portes par les `<nav>` du document — `None` si le document n en a aucun.

    `None` n est pas un ensemble vide : il dit « pas de reference », et c est ce qui fait sortir
    la moitie « meme gabarit » en NON_MESURABLE au lieu de la declarer tenue par defaut.
    """
    blocs = _NAV.findall(html)
    if not blocs:
        return None
    return {lien for bloc in blocs for lien in liens(bloc)}


def langue(html: str) -> str | None:
    trouve = _LANG.search(html)
    return trouve.group(1).strip().lower() if trouve else None


def porte_noindex(reponse: dict) -> bool:
    """`noindex` par la meta robots OU par l en-tete `X-Robots-Tag` — les deux valent."""
    entete = str(reponse.get("entetes", {}).get("x-robots-tag", ""))
    if "noindex" in entete.lower():
        return True
    balises = _META_ROBOTS.findall(reponse.get("corps", ""))
    return any("noindex" in balise.lower() for balise in balises)


def est_html(reponse: dict) -> bool:
    type_contenu = str(reponse.get("entetes", {}).get("content-type", "")).lower()
    if "text/html" in type_contenu:
        return True
    return "<html" in reponse.get("corps", "").lower()


# ---- Jugement : fonction PURE, et c est elle que le banc eprouve ------------------------------
def _statut_reponse(reponse: dict) -> tuple[str, str] | None:
    """Le refus commun aux deux cas HTTP : pendue, injoignable, ou statut autre que 404."""
    if reponse["code"] == 0 and reponse.get("pendue"):
        return ("FAIL", "reponse PENDUE (code 000) — piege mesure du patron P-2 : envelopper "
                        "`writeHead` sans envelopper `write()` fait partir le corps nu du "
                        "serveur avant les en-tetes differes. Remede d une ligne : avaler les "
                        "ecritures du corps d origine quand la reponse est substituee")
    if reponse["code"] == 0:
        return ("FAIL", f"aucune reponse : {reponse.get('erreur', 'injoignable')}")
    if reponse["code"] == 200:
        return ("FAIL", "statut 200 sur une adresse inconnue — soft-404 indexable. C est le "
                        "refus que cette recette existe pour prononcer")
    if reponse["code"] != 404:
        return ("FAIL", f"statut {reponse['code']} au lieu de 404")
    return None


def juger_adresse_inconnue(reponse: dict, prefixe: str, attendu_lang: str,
                           menu_reference: set[str] | None, marqueur: str | None,
                           reference: dict | None) -> dict:
    """Cas (a) : 404 conserve, page du meme gabarit, langue du prefixe."""
    base = {"cas": "adresse-inconnue", "prefixe": prefixe, "url": reponse["url"],
            "code": reponse["code"]}
    refus = _statut_reponse(reponse)
    if refus:
        return {**base, "verdict": refus[0], "motif": refus[1]}
    if not est_html(reponse):
        return {**base, "verdict": "FAIL",
                "motif": "404 nu sur une adresse de PAGE — le visiteur perd le menu, la charte "
                         "et ses liens de secours ; c est le defaut fondateur du patron P-2"}

    trouvee = langue(reponse["corps"])
    if trouvee is None:
        return {**base, "verdict": "FAIL", "motif": "la page 404 ne declare aucune langue "
                                                    "(`<html lang=…>` absent)"}
    if not (trouvee == attendu_lang or trouvee.split("-")[0] == attendu_lang):
        return {**base, "verdict": "FAIL", "langue": trouvee,
                "motif": f"langue « {trouvee} » sous le prefixe « {prefixe or '/'} » : la langue "
                         f"se choisit au prefixe du chemin, « {attendu_lang} » etait attendu"}

    if marqueur is not None:
        if marqueur not in reponse["corps"]:
            return {**base, "verdict": "FAIL", "langue": trouvee,
                    "motif": f"marqueur de gabarit « {marqueur} » absent de la page 404 — elle "
                             f"n est pas du meme gabarit que les autres"}
        return {**base, "verdict": "PASS", "langue": trouvee,
                "motif": "404 conserve, marqueur de gabarit present, langue du prefixe"}

    if menu_reference is None:
        ref = (reference or {}).get("url", "la page de reference du prefixe")
        return {**base, "verdict": "NON_MESURABLE", "langue": trouvee,
                "motif": f"aucun `<nav>` sur {ref} : le « meme gabarit » n a pas de reference a "
                         f"laquelle se comparer. Declarer un marqueur avec --marqueur-menu"}
    menu_404 = liens_de_menu(reponse["corps"])
    manquants = sorted(menu_reference - (menu_404 or set()))
    if manquants:
        return {**base, "verdict": "FAIL", "langue": trouvee, "liens_de_menu_manquants": manquants,
                "motif": f"{len(manquants)} lien(s) du menu de la page de reference absent(s) de "
                         f"la page 404 — elle n est pas du meme gabarit que les autres"}
    return {**base, "verdict": "PASS", "langue": trouvee,
            "motif": f"404 conserve, menu complet ({len(menu_reference)} lien(s)), langue du "
                     f"prefixe"}


def juger_ressource_non_html(reponse: dict, prefixe: str) -> dict:
    """Cas (c) : une image ou un script inconnu rend un 404 NU, jamais une page."""
    base = {"cas": "ressource-non-html", "prefixe": prefixe, "url": reponse["url"],
            "code": reponse["code"]}
    refus = _statut_reponse(reponse)
    if refus:
        return {**base, "verdict": refus[0], "motif": refus[1]}
    if est_html(reponse):
        return {**base, "verdict": "FAIL",
                "motif": "page HTML servie a la place d un 404 nu — un navigateur qui attend une "
                         "image ou un script recoit un document, et le defaut se voit en console, "
                         "pas a l ecran"}
    return {**base, "verdict": "PASS", "motif": "404 nu, aucun corps HTML"}


def juger_noindex(reponse: dict, prefixe: str) -> dict:
    """Cas (b), premiere moitie : la page 404 porte `noindex`."""
    base = {"cas": "noindex", "prefixe": prefixe, "url": reponse["url"], "code": reponse["code"]}
    if reponse["code"] != 404 or not est_html(reponse):
        return {**base, "verdict": "NON_MESURABLE",
                "motif": "aucune page 404 servie a cette adresse — le `noindex` n a pas de porteur"}
    if not porte_noindex(reponse):
        return {**base, "verdict": "FAIL",
                "motif": "ni meta robots `noindex`, ni en-tete `X-Robots-Tag: noindex` — une page "
                         "d erreur sans noindex entre en index"}
    return {**base, "verdict": "PASS", "motif": "`noindex` porte par la page 404"}


def juger_sitemap(reponse: dict | None, adresses_sondees: list[str],
                  pages_404_declarees: list[str]) -> dict:
    """Cas (b), seconde moitie : le sitemap ne liste ni les adresses inconnues, ni la page 404.

    Sitemap absent ou illisible : NON_MESURABLE, jamais PASS. Un sitemap qu on n a pas lu ne
    prouve pas une absence — il prouve qu on n a pas regarde.
    """
    base = {"cas": "sitemap", "prefixe": "", "url": (reponse or {}).get("url", "")}
    if reponse is None:
        return {**base, "verdict": "NON_MESURABLE", "motif": "aucun sitemap declare"}
    if reponse["code"] != 200:
        return {**base, "verdict": "NON_MESURABLE", "code": reponse["code"],
                "motif": f"sitemap injoignable (code {reponse['code']}) : une absence non lue "
                         f"n est pas une absence prouvee"}
    listees = {u.strip() for u in _LOC.findall(reponse["corps"])}
    chemins = {urllib.parse.urlparse(u).path.rstrip("/") or "/" for u in listees}
    fautives = sorted(
        a for a in adresses_sondees + pages_404_declarees
        if a in listees or (urllib.parse.urlparse(a).path.rstrip("/") or "/") in chemins
    )
    if fautives:
        return {**base, "verdict": "FAIL", "code": 200, "adresses_listees": fautives,
                "motif": "le sitemap liste une adresse qui rend 404 — une page d erreur au "
                         "sitemap est une invitation a l indexer"}
    return {**base, "verdict": "PASS", "code": 200,
            "motif": f"{len(listees)} adresse(s) au sitemap, aucune n est une page 404"}


def synthetiser(cas: list[dict]) -> dict:
    """Le verdict global. Fonction PURE : c est elle que le banc eprouve en premier.

    Ordre des priorites, et il n est pas negociable : un seul FAIL fait FAIL ; sinon un seul
    NON_MESURABLE fait NON_MESURABLE ; aucun cas du tout fait NON_MESURABLE. PASS exige que
    TOUS les cas aient ete joues ET tenus.
    """
    resume = {
        "pass": sum(1 for c in cas if c["verdict"] == "PASS"),
        "fail": sum(1 for c in cas if c["verdict"] == "FAIL"),
        "non_mesurable": sum(1 for c in cas if c["verdict"] == "NON_MESURABLE"),
    }
    if resume["fail"]:
        return {"verdict": "FAIL", "resume": resume,
                "motif": f"{resume['fail']} cas en defaut — le detail est dans `cas[]`, chaque "
                         f"motif nomme ce qui a ete mesure"}
    if not cas:
        return {"verdict": "NON_MESURABLE", "resume": resume,
                "motif": "aucun cas joue — il n y a pas de mesure a prononcer"}
    if resume["non_mesurable"]:
        return {"verdict": "NON_MESURABLE", "resume": resume,
                "motif": f"{resume['non_mesurable']} cas non mesurable(s) : une mesure partielle "
                         f"n est pas un PASS, sans quoi le silence passerait pour un verdict tenu"}
    return {"verdict": "PASS", "resume": resume,
            "motif": f"les {resume['pass']} cas de M-9 sont joues et tenus"}


# ---- Orchestration : parametrage, sondage, jugement -------------------------------------------
def _joindre(base: str, chemin: str) -> str:
    return base.rstrip("/") + "/" + chemin.lstrip("/")


def jouer(base: str, prefixes: list[str], langue_par_defaut: str | None = None,
          sitemap: str | None = "/sitemap.xml", marqueur: str | None = None,
          pages_404: list[str] | None = None, delai: int = DELAI_DEFAUT) -> dict:
    """Joue les trois cas de M-9 sur une instance servie et rend la piece de preuve."""
    cas: list[dict] = []
    adresses_sondees: list[str] = []
    # Les prefixes portent leur langue attendue ; la chaine vide est la racine, dont la langue
    # attendue est celle declaree par --langue-par-defaut (exigence 4 du patron P-2).
    nettoyes = [p.strip("/") for p in prefixes if p.strip("/")]
    sondages: list[tuple[str, str]] = [(p, p) for p in nettoyes]
    if langue_par_defaut:
        sondages.append(("", langue_par_defaut.strip().lower()))

    if not sondages:
        return {"verdict": "NON_MESURABLE", "base": base, "cas": [],
                "resume": {"pass": 0, "fail": 0, "non_mesurable": 0},
                "motif": "aucun prefixe de langue fourni — il n y a rien a sonder"}

    accueil = sonder(base.rstrip("/") + "/", delai)
    if accueil["code"] == 0 and not accueil.get("pendue"):
        return {"verdict": "NON_MESURABLE", "base": base, "cas": [],
                "resume": {"pass": 0, "fail": 0, "non_mesurable": 0},
                "motif": f"instance injoignable a {base} : {accueil.get('erreur')} — rien n a pu "
                         f"etre mesure, et un refus explicite vaut mieux qu un verdict invente"}

    for prefixe, attendu in sondages:
        url_reference = _joindre(base, prefixe + "/") if prefixe else base.rstrip("/") + "/"
        reference = sonder(url_reference, delai)
        menu = liens_de_menu(reference["corps"]) if reference["code"] == 200 else None
        chemin = f"{prefixe}/{SEGMENT_INCONNU}" if prefixe else SEGMENT_INCONNU
        url = _joindre(base, chemin)
        adresses_sondees.append(url)
        page = sonder(url, delai)
        cas.append(juger_adresse_inconnue(page, prefixe, attendu, menu, marqueur, reference))
        cas.append(juger_noindex(page, prefixe))
        for ressource in RESSOURCES_NON_HTML:
            chemin_res = f"{prefixe}/{ressource}" if prefixe else ressource
            url_res = _joindre(base, chemin_res)
            adresses_sondees.append(url_res)
            cas.append(juger_ressource_non_html(sonder(url_res, delai), prefixe))

    reponse_sitemap = sonder(_joindre(base, sitemap), delai) if sitemap else None
    cas.append(juger_sitemap(reponse_sitemap, adresses_sondees, list(pages_404 or [])))

    return {
        "recette": "404 personnalisee par langue (patron P-2)",
        "controle": "M-9 — 404 personnalisee, par langue, statut conserve (ETAPE-MEP.md)",
        "candidature": "TF-0803 (registre du pilot) — lot digit-ai-factory - RETOURS - 20260905a",
        "base": base,
        "prefixes": [p for p, _ in sondages],
        "date_iso": datetime.now(UTC).isoformat(timespec="seconds"),
        "cas": cas,
        "non_mesure": [
            "M-9 (b), seconde moitie : la DECLARATION de l exclusion du sitemap dans l oracle SEO "
            "du produit vit dans le depot du produit, pas dans une reponse HTTP — cette recette "
            "mesure l absence au sitemap, jamais sa declaration",
        ],
        **synthetiser(cas),
    }


CODES = {"PASS": 0, "FAIL": 1, "NON_MESURABLE": 2}


def main(argv: list[str]) -> int:
    analyseur = argparse.ArgumentParser(
        prog="quatre_cent_quatre.py",
        description="Preuve executable du controle M-9 : la 404 personnalisee par langue (P-2).")
    analyseur.add_argument("base", help="URL de preproduction (ex. https://staging.exemple)")
    analyseur.add_argument("--prefixes", required=True,
                           help="prefixes de langue separes par des virgules (ex. fr,en,nl)")
    analyseur.add_argument("--langue-par-defaut", default=None,
                           help="langue attendue a la racine, sans prefixe (exigence 4 de P-2)")
    analyseur.add_argument("--sitemap", default="/sitemap.xml",
                           help="chemin du sitemap ; vide pour ne pas le sonder")
    analyseur.add_argument("--marqueur-menu", default=None,
                           help="chaine qui atteste le gabarit commun, si le site n a pas de <nav>")
    analyseur.add_argument("--page-404", action="append", default=[],
                           help="adresse d une page 404 du produit, cherchee au sitemap "
                                "(repetable)")
    analyseur.add_argument("--delai", type=int, default=DELAI_DEFAUT,
                           help=f"delai par requete en secondes (defaut {DELAI_DEFAUT})")
    analyseur.add_argument("--sortie", default=None,
                           help="fichier ou ecrire la piece de preuve jointe au dossier de MEP")
    args = analyseur.parse_args(argv[1:])

    rapport = jouer(
        args.base,
        [p for p in args.prefixes.split(",") if p.strip()],
        langue_par_defaut=args.langue_par_defaut,
        sitemap=args.sitemap or None,
        marqueur=args.marqueur_menu,
        pages_404=args.page_404,
        delai=args.delai,
    )
    texte = json.dumps(rapport, ensure_ascii=False, indent=1)
    if args.sortie:
        with open(args.sortie, "w", encoding="utf-8") as fichier:
            fichier.write(texte + "\n")
    print(texte)
    return CODES[rapport["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
