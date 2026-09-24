#!/usr/bin/env python3
"""Print Delpher hit counts for lexicon-expanded PROX term pairs."""
import csv
import os
import xml.etree.ElementTree as ET

import matplotlib.pyplot as plt
import requests

from query_builder import build_prox_queries, get_wordforms


terms_invasive = [
    "allochtoon",
    "exoot",
    "exotisch",
    "invasief",
    "invasiev",
    "onkruid",
    "ruderaal",
    "uitheems",
]

terms_target = [
    "bloem",
    "plant",
    "struik",
]

SRU_URL = "https://jsru.kb.nl/sru/sru"
HEADERS = {"User-Agent": "DelpherBot/1.0 (research)"}
TYPES = ["artikel", "advertentie", "familiebericht", "illustratie met onderschrift"]
OUTPUT_DIR = "data/invasive_plants_query"
COUNTS_CSV = os.path.join(OUTPUT_DIR, "prox_hit_counts.csv")
HEATMAP_PNG = os.path.join(OUTPUT_DIR, "prox_hit_counts.png")


def get_hit_count(query, session=requests):
    """Run a count-only SRU query and return its number of records."""
    params = {
        "version": "1.2",
        "operation": "searchRetrieve",
        "query": query,
        "maximumRecords": "0",
        "recordSchema": "ddd",
        "x-collection": "DDD_artikel",
    }
    response = session.get(SRU_URL, params=params, headers=HEADERS, timeout=60)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    return int(root.findtext(
        ".//{http://www.loc.gov/zing/srw/}numberOfRecords", "0"
    ))


def lowercase_variants(variants):
    """Keep variants that contain no uppercase letters, without duplicates."""
    return list(dict.fromkeys(
        variant for variant in variants if variant == variant.lower()
    ))


def main():
    left_variants = lowercase_variants(get_wordforms(terms_invasive))
    right_variants = lowercase_variants(get_wordforms(terms_target))
    counts = {}
    total_hits = 0

    for left, right, prox_query in build_prox_queries(
        left_variants, right_variants
    ):
        query = prox_query + ' AND date within "01-01-1800 31-12-1999"'
        if TYPES:
            query += " AND (" + " OR ".join(
                f'type="{item}"' for item in TYPES
            ) + ")"
        hits = get_hit_count(query)
        counts[(left, right)] = hits
        total_hits += hits
        print(f'"{left}" PROX "{right}": {hits}')

        reverse_query = (
            f'("{right}" PROX "{left}")'
            ' AND date within "01-01-1800 31-12-1999"'
        )
        if TYPES:
            reverse_query += " AND (" + " OR ".join(
                f'type="{item}"' for item in TYPES
            ) + ")"
        reverse_hits = get_hit_count(reverse_query)
        print(f'"{right}" PROX "{left}": {reverse_hits}')
        print("\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(COUNTS_CSV, "w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["left_term", "right_term", "hits"])
        for (left, right), hits in counts.items():
            writer.writerow([left, right, hits])

    figure_width = max(10, len(right_variants) * 0.45)
    figure_height = max(6, len(left_variants) * 0.3)
    figure, axis = plt.subplots(figsize=(figure_width, figure_height))
    matrix = [
        [counts[(left, right)] for right in right_variants]
        for left in left_variants
    ]
    image = axis.imshow(matrix, aspect="auto", cmap="YlGnBu")
    threshold = image.norm.vmax / 2 if image.norm.vmax else 0
    for row_index, row in enumerate(matrix):
        for column_index, hits in enumerate(row):
            color = "white" if hits > threshold else "black"
            axis.text(
                column_index,
                row_index,
                f"{hits:,}",
                ha="center",
                va="center",
                color=color,
                fontsize=8,
            )
    axis.set_xticks(range(len(right_variants)), right_variants, rotation=90)
    axis.set_yticks(range(len(left_variants)), left_variants)
    axis.set_xlabel("Target term")
    axis.set_ylabel("Invasive term")
    axis.set_title(f"Delpher PROX hit counts (total: {total_hits:,})")
    figure.colorbar(image, ax=axis, label="Hits")
    figure.tight_layout()
    figure.savefig(HEATMAP_PNG, dpi=180)
    plt.close(figure)

    print(f"total hits across combinations: {total_hits}")
    print(f"counts CSV: {COUNTS_CSV}")
    print(f"heatmap: {HEATMAP_PNG}")


if __name__ == "__main__":
    main()
