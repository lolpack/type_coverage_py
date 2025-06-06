import json
import requests
from collections import defaultdict
from typing import Any
from tabulate import tabulate

# This script checks which packages with the `Typing :: Typed` classifier actually have stubs.
package_report = None
with open("package_report.json", "r") as f:
    package_report = json.load(f)


def check_typed_classifier(package_name: str) -> tuple[bool, bool]:
    # Fetch the package metadata from PyPI
    pypi_url = f"https://pypi.org/pypi/{package_name}/json"
    response = requests.get(pypi_url)
    response.raise_for_status()

    # The API returns a JSON response, so 'data' is a dictionary
    data: dict[str, Any] = response.json()
    return "Typing :: Typed" in data['info']['classifiers'], "Typing :: Stubs Only" in data['info']['classifiers']


badge_total = 0
stubs_only_total = 0

non_badge = defaultdict[tuple[bool, bool, bool, bool, bool], list[str]](list)
badge = defaultdict[tuple[bool, bool, bool, bool, bool], list[str]](list)
for package, package_info in package_report.items():
    has_typed_classifier, has_stubs_only_classifier = check_typed_classifier(package)
    key = (package_info["HasPyTypedFile"], package_info["HasTypeShed"], package_info["HasStubsPackage"], package.startswith("types-") or package.endswith("-stubs"), has_stubs_only_classifier)
    if has_stubs_only_classifier:
        stubs_only_total += 1
    if has_typed_classifier:
        badge_total += 1
        badge[key].append(package)
    else:
        non_badge[key].append(package)

print("Has Typing :: Typed", badge_total)
print("Has Typing :: Stubs Only", stubs_only_total)

print("Has Badge")
table = False
rows: list[list[bool | int]] = []
for ((py_typed, typeshed, stubs, stubs_name, stubs_classifier), pkgs) in badge.items():
    rows.append([len(pkgs), py_typed, typeshed, stubs, stubs_name, stubs_classifier])
    if table:
        continue
    print(True, *rows[-1])
    for pkg in pkgs:
        print(pkg)
if table:
    print(tabulate(rows, headers=['Count', "Has py.typed", "Has typeshed", "Has stubs", "-stubs or types-", "Typing :: Stubs Only"]))

print("No Badge")
rows = []
for ((py_typed, typeshed, stubs, stubs_name, stubs_classifier), pkgs) in non_badge.items():
    rows.append([len(pkgs), py_typed, typeshed, stubs, stubs_name, stubs_classifier])
    if table:
        continue
    print(False, *rows[-1])
    for pkg in pkgs:
        print(pkg)
if table:
    print(tabulate(rows, headers=['Count', "Has py.typed", "Has typeshed", "Has stubs", "-stubs or types-", "Typing :: Stubs Only"]))
