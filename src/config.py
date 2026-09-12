from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Gemensam synlig start för pris-, score- och strategihistorik. 2 september
# 2019 är första handelsdagen i september och ligger efter avslutad Q2-säsong.
HISTORY_START_DATE = "2019-09-02"
