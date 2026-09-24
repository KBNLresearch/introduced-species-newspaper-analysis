"""Build Delpher SRU queries from lexicon-expanded word forms."""
from itertools import product

import requests


LEXICON_URL = "https://www.delpher.nl/nl/api/lexicon"


def get_wordforms(terms, session=requests):
    """Return the lexicon variants for each term, preserving response order."""
    response = session.get(
        LEXICON_URL,
        params={"wordform": ",".join(terms)},
        timeout=60,
    )
    response.raise_for_status()
    wordforms = response.json()["wordforms_list"]

    variants = []
    for item in wordforms:
        variants.extend(item["found_wordforms"])
    return list(dict.fromkeys(variants))


def build_prox_query(left_terms, right_terms):
    """Build an OR of every directional PROX combination."""
    return " OR ".join(query for _, _, query in build_prox_queries(
        left_terms, right_terms
    ))


def build_prox_queries(left_terms, right_terms):
    """Yield each directional PROX query together with its two terms."""
    for left, right in product(left_terms, right_terms):
        yield left, right, f'("{left}" PROX "{right}")'


def build_lexicon_prox_query(left_terms, right_terms, session=requests):
    """Expand both term groups with Delpher's lexicon and build a PROX query."""
    left_variants = get_wordforms(left_terms, session=session)
    right_variants = get_wordforms(right_terms, session=session)
    return " OR ".join(query for _, _, query in build_prox_queries(
        left_variants, right_variants
    ))