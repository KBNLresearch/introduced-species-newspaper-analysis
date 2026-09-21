#!/usr/bin/env python3
"""Run one hard-coded Delpher SRU query, print the hit count, download the OCR
texts and write a manifest CSV of the SRU metadata (one row per record)."""
import csv
import os
import re
import time
import requests
import xml.etree.ElementTree as ET

# tackle wildcards with https://www.delpher.nl/nl/api/lexicon?wordform=inheems,inlands,plant,struik,buitenlands
# fuzzy search https://jsru.kb.nl/sru/sru?operation=searchRetrieve&version=1.2&maximumRecords=10&x-collection=DDD_artikel&recordSchema=ddd&query=content%20=/fuzzy%20%22inheemsche%22

# PROX query: (allochtoon OR exoot OR exotisch OR invasief OR invasiev OR onkruid OR ruderaal OR uitheems) PROX (plant OR bloem)
QUERY = ("(allochtoon* OR exoot* OR exotisch* OR invasief* OR invasiev* "
         "OR ruderaal OR uitheems*) AND (plant* OR bloem*)")
# OR onkruid*
# Same query, restricted to the 19th and 20th centuries (1800-01-01 .. 1999-12-31).
QUERY_WITH_DATES = QUERY + ' AND date within "01-01-1800 31-12-1999"'

# "Soort bericht" facet (dc:type). Set to the subset you want, or [] for no filter.
# Counts for QUERY: artikel 79592, advertentie 10907,
# illustratie met onderschrift 345, familiebericht 52.
TYPES = ["artikel", "advertentie", "familiebericht", "illustratie met onderschrift"]

PAGE_SIZE = 100
OUT_DIR = "data/invasive_plants_query"
MANIFEST = os.path.join(OUT_DIR, "records.csv")
HEADERS = {"User-Agent": "DelpherBot/1.0 (research)"}

# Metadata kept in the manifest, in column order. Local names as they appear in
# recordData; the dc/dcx/ddd namespace prefixes are dropped when parsing.
FIELDS = ["metadataKey", "date", "type", "title", "papertitle", "page",
          "spatialCreation", "spatial", "source", "edition", "publisher",
          "rights", "ppn", "issued", "yearsdigitized", "pageurl", "paperurl"]

query = QUERY_WITH_DATES
if TYPES:
    query += " AND (" + " OR ".join(f'type="{t}"' for t in TYPES) + ")"

SRU_URL = "https://jsru.kb.nl/sru/sru"
REQUEST_PARAMS = {
    "version": "1.2",
    "operation": "searchRetrieve",
    "query": query,
    "maximumRecords": str(PAGE_SIZE),
    "recordSchema": "ddd",
    "x-collection": "DDD_artikel",
}


def parse_metadata(record_data):
    """Flatten a <srw:recordData> element into {local tag name: text}."""
    out = {}
    for child in record_data:
        tag = child.tag.split("}", 1)[-1]
        if child.text and child.text.strip() and tag not in out:
            out[tag] = child.text.strip()
    return out


def extract_text(content):
    """Turn an OCR response into text, keeping the paragraph structure.

    Delpher article OCR is a <text> document with a <title> and one <p> per
    paragraph; blocks are joined with blank lines so the title stays separable
    from the body. Falls back to a flat dump for ALTO and to tag-stripping for
    anything else.
    """
    s = content.decode("utf-8", "replace")
    if s.lstrip().startswith("<?xml") or "<alto" in s.lower():
        try:
            root = ET.fromstring(s)
            blocks = [" ".join(e.itertext()).strip() for e in root
                      if "".join(e.itertext()).strip()]
            if blocks:
                return "\n\n".join(blocks)
            return " ".join(e.text.strip() for e in root.iter()
                            if e.text and e.text.strip())
        except ET.ParseError:
            pass
    return re.sub(r"<[^>]+>", "", s)


os.makedirs(OUT_DIR, exist_ok=True)
rows = []
start_record = 1
total_records = None
processed_records = 0

with open(MANIFEST, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS + ["filepath", "ocr_url", "viewer_url"])
    w.writeheader()

    while total_records is None or start_record <= total_records:
        params = {**REQUEST_PARAMS, "startRecord": str(start_record)}
        response = requests.get(SRU_URL, params=params, headers=HEADERS, timeout=60)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        if total_records is None:
            total_records = int(root.findtext(
                ".//{http://www.loc.gov/zing/srw/}numberOfRecords", "0"))
            print(f"hits: {total_records}")

        records = root.findall(".//{http://www.loc.gov/zing/srw/}recordData")
        if not records:
            break
        print(f"records {start_record}-{start_record + len(records) - 1} of {total_records}")

        for rec in records:
            processed_records += 1
            meta = parse_metadata(rec)
            mkey = meta.get("metadataKey")
            if not mkey:
                print(f"progress: {processed_records}/{total_records}")
                continue
            filepath = os.path.join(OUT_DIR, mkey.replace(":", "_") + ".txt")
            ocr_url = f"https://resolver.kb.nl/resolve?urn={mkey}:ocr"
            temporary_path = filepath + ".part"
            if os.path.isfile(filepath) and os.path.getsize(filepath) > 0:
                print(f"  have {filepath}")
            else:
                try:
                    r = requests.get(ocr_url, headers=HEADERS, timeout=60)
                    r.raise_for_status()
                    text = extract_text(r.content)
                    if not text.strip():
                        raise ValueError("empty OCR response")
                    with open(temporary_path, "w", encoding="utf-8") as out:
                        out.write(text)
                    os.replace(temporary_path, filepath)
                    print(f"  saved {filepath}")
                except (requests.RequestException, ValueError) as error:
                    print(f"  failed {mkey}: {error}")
                    filepath = ""
                    if os.path.exists(temporary_path):
                        os.remove(temporary_path)
                time.sleep(0.25)
            row = {k: meta.get(k, "") for k in FIELDS}
            row["filepath"] = filepath
            row["ocr_url"] = ocr_url
            row["viewer_url"] = f"https://www.delpher.nl/nl/kranten/view?identifier={mkey}"
            w.writerow(row)
            print(f"progress: {processed_records}/{total_records}")

        f.flush()
        start_record += len(records)

print(f"manifest: {MANIFEST}")
