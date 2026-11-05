#!/usr/bin/env python3
"""Build gas-prices.json for the Recovery Gang Radio GitHub player.

Sources (both official/public, fetched fresh each run):
- US states + DC: AAA state gas price averages table
  (gasprices.aaa.com/state-gas-price-averages/) - regular, mid-grade
  and premium state averages, $/gallon (diesel is not carried).
- New Brunswick: NBEUB weekly price schedule PDF (current maximum price
  schedule) - self-serve regular, mid-grade and premium, each as the
  total price to the maximum allowable price, cents/litre.

Output: gas-prices.json next to this script, keyed by the region codes
BigDataCloud's reverse geocoder returns (e.g. "CA-NB", "US-ME").
Each region carries a "grades" object with a {low, high} pair per grade
present in the source (US averages are single values, so low == high;
NB regulated prices are genuine ranges). A grade the source does not
publish for a region is omitted, never invented; a region that fails
to parse at all is simply left out - the player hides the gas line for
any region it has no current data for. The build refuses to write a
file with fewer than 50 regions.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "gas-prices.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

USPS = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as fh:
        return fh.read()


def _price(cell):
    try:
        return float(cell.replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def us_regions():
    html = fetch("https://gasprices.aaa.com/state-gas-price-averages/").decode("utf-8", "ignore")
    regions = {}
    # AAA table columns: State | Regular | Mid-Grade | Premium | Diesel.
    for row in re.findall(r"<tr>.*?</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) != 5 or cells[0] not in USPS:
            continue
        grades = {}
        for key, idx in (("regular", 1), ("mid", 2), ("premium", 3)):
            value = _price(cells[idx])
            if value is not None:
                grades[key] = {"low": value, "high": value}
        if not grades:
            continue
        regions["US-" + USPS[cells[0]]] = {
            "label": cells[0], "unit": "usd_gal", "grades": grades,
        }
    return regions


def nb_region():
    pdf = fetch("http://www.nbeub.ca/images/documents/petroleum_pricing/currentmaximumpriceenglish.pdf")
    tmp = "/tmp/nbeub-schedule.pdf"
    with open(tmp, "wb") as fh:
        fh.write(pdf)
    text = subprocess.run(["pdftotext", "-layout", tmp, "-"], capture_output=True, text=True, timeout=60).stdout
    grades = {}
    for key, name in (("regular", "Regular"), ("mid", "Mid-grade"), ("premium", "Premium")):
        m = re.search(name + r" Gasoline\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+([\d.]+)\s+to maximum of\s+([\d.]+)\s+Self-Serve", text)
        if m:
            grades[key] = {"low": float(m.group(1)), "high": float(m.group(2))}
    if not grades:
        return {}
    return {"CA-NB": {"label": "New Brunswick", "unit": "cad_litre", "grades": grades}}


def main():
    regions = {}
    for builder in (us_regions, nb_region):
        try:
            regions.update(builder())
        except Exception as exc:  # one bad source must not sink the file
            print("source failed: %s: %r" % (builder.__name__, exc), file=sys.stderr)
    if len(regions) < 50:
        print("only %d regions built (< 50) - not writing" % len(regions), file=sys.stderr)
        return 1
    payload = {"asof": date.today().isoformat(), "regions": regions}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("wrote %s with %d regions; NB=%s ME=%s" % (OUT, len(regions), regions.get("CA-NB"), regions.get("US-ME")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
