# Hochschul-Insights — Fabric Jumpstart installer (paste into a Fabric notebook)

# === Cell 1 ===
# %pip install -q "git+https://github.com/KornAlexander/fabric-jumpstart.git@main#subdirectory=src/fabric_jumpstart"

# === Cell 2 ===
import importlib.util, pathlib, urllib.request
community = pathlib.Path(importlib.util.find_spec("fabric_jumpstart").origin).parent / "jumpstarts" / "community"
community.mkdir(parents=True, exist_ok=True)
(community / "hochschul-insights.yml").write_text(
    urllib.request.urlopen(
        "https://raw.githubusercontent.com/KornAlexander/hochschul-insights/main/hochschul-insights.yml"
    ).read().decode("utf-8"),
    encoding="utf-8",
)

import fabric_jumpstart as jumpstart
jumpstart.install("hochschul-insights")
