"""One name per active substance, across the NHI group labels and the TFDA licence formulas.

The two sources name the same substance in different ways: with or without its
salt ("LOSARTAN POTASSIUM", "LOSARTAN"), by a synonym ("THIAMINE", "VITAMIN B1"),
or with the salt in brackets ("BETAMETHASONE (AS VALERATE)"). `Substances` groups
those names so that a product can be looked up by the substance, whatever form the
label or the licence happens to use. Three kinds of evidence join two names:

1. the TFDA ingredient code, whose first eight characters are meant to identify the
   substance. The code alone is not trusted (it also puts VALSARTAN beside
   BUNAZOSIN), so two names under one code are joined only when the names agree
   as well: a spelling variant, a descriptor ("ACETAMINOPHEN CRYSTAL"), or the
   acid and its salt ("FUSIDIC ACID", "SODIUM FUSIDATE");
2. a synonym that a source states itself: "ACETAMINOPHEN (EQ TO PARACETAMOL)",
   "RIBOFLAVIN (=VIT B2)";
3. the name left after a trailing salt or hydrate word is removed, but only when
   that shorter name is itself in use somewhere, so "BENZYL BENZOATE" does not
   become "BENZYL".

4. a single-ingredient product that NHI labels X and whose licence names Y: the
   two are one substance, and they are joined when the names also look alike (Y is
   X with a salt or ester word, the same words in another order, or a spelling
   variant) or the pair is in the reviewed list `SAME`. Pairs that only co-occur
   are not joined, because NHI also files a derivative under its parent
   (FURSULTIAMINE under VITAMIN B1); such a product keeps both names.

Nothing here reads the network. `build_drug_codes.py` feeds it the rows.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher

# Salt, ester and hydrate words that follow the name of the active moiety.
SALT_WORDS = """
HCL 2HCL HBR HYDROCHLORIDE DIHYDROCHLORIDE MONOHYDROCHLORIDE HYDROBROMIDE HYDROIODIDE
MALEATE FUMARATE HEMIFUMARATE SUCCINATE HEMISUCCINATE TARTRATE BITARTRATE CITRATE ACETATE DIACETATE
PHOSPHATE DIPHOSPHATE SULFATE SULPHATE BISULFATE HEMISULFATE NITRATE MONONITRATE
MESYLATE MESILATE METHANESULFONATE BESYLATE BESILATE TOSYLATE MALATE LACTATE GLUCONATE PAMOATE EMBONATE
STEARATE PALMITATE DECANOATE ENANTHATE CYPIONATE PROPIONATE DIPROPIONATE VALERATE 17-VALERATE BUTYRATE
ACETONIDE FUROATE BENZOATE PIVALATE CAPROATE HEXANOATE UNDECANOATE TRIMETHYLACETATE OXALATE HYCLATE XINAFOATE NAPADISYLATE
HIBENZATE DIMALEATE HEMITARTRATE ESTOLATE ETHYLSUCCINATE DIASPARTATE
SODIUM DISODIUM TRISODIUM POTASSIUM DIPOTASSIUM CALCIUM MAGNESIUM ALUMINUM
LYSINE ARGININE TROMETHAMINE TROMETAMOL MEGLUMINE DIETHYLAMINE ERBUMINE OLAMINE
CHLORIDE BROMIDE IODIDE METHYLBROMIDE METHYLSULFATE METILSULFATE
HYDRATE MONOHYDRATE DIHYDRATE TRIHYDRATE HEMIHYDRATE SESQUIHYDRATE PENTAHYDRATE HEPTAHYDRATE HEMIPENTAHYDRATE
ANHYDROUS MICRONIZED MICRONISED BASE SALT STERILE
""".split()
SALT_TAIL = re.compile(r"(?:^|[\s-])(?:" + "|".join(re.escape(w) for w in sorted(SALT_WORDS, key=len, reverse=True))
                       + r"|\d+(?:\.\d+)?\s*H2O|\d+(?:\.\d+)?\s+HYDRATE)$")
SALT_HEAD = re.compile(r"^(?:ANHYDROUS|DRIED|MICRONIZED|MICRONISED|STERILE|PURIFIED|CRYSTALLINE)\s+")
STEREO = re.compile(r"^(?:DL|D|L)-\s*|\s+(?:DL|D|L)-$")

# Names that start with the cation are inorganic or acid salts in their own right
# ("SODIUM CHLORIDE", "FERROUS FUMARATE"): nothing is removed from them.
CATION_FIRST = set("""SODIUM DISODIUM TRISODIUM POTASSIUM DIPOTASSIUM CALCIUM MAGNESIUM ALUMINUM ALUMINIUM AMMONIUM ZINC
FERROUS FERRIC IRON LITHIUM BISMUTH COPPER CUPRIC MANGANESE SILVER BARIUM STRONTIUM COBALT CHROMIUM SELENIUM GOLD
MERCURIC MERCUROUS HYDROGEN SULFUR IODINE DIHYDROXYALUMINUM TOTAL""".split())

# Names whose "salt" word makes a different drug of them.
KEEP_WHOLE = {
    "ISOSORBIDE MONONITRATE", "ISOSORBIDE 5-MONONITRATE", "ISOSORBIDE-5-MONONITRATE", "ISOSORBIDE DINITRATE",
    "ADENOSINE PHOSPHATE", "ADENOSINE TRIPHOSPHATE", "DEXTRAN SULFATE", "DEXTRAN SULFATE SODIUM",
    "CELLULOSE ACETATE", "PYRIDOXAL PHOSPHATE", "CREATINE PHOSPHATE", "GUAIACOL CARBONATE",
}

# Excipients and section markers that the licence formula lists beside the actives.
# They are dropped unless nothing else is left.
EXCIPIENT = re.compile(
    r"^(?:(?:STE?RILE\s+)?WATER FOR INJECTION.*|PURIFIED WATER|WATER|GELATIN|(?:TOTAL )?TITANIUM DIOXIDE|LACTOSE|"
    r"(?:CORN |POTATO |WHEAT |RICE )?STARCH|MAGNESIUM STEARATE|(?:PURIFIED )?TALC(?: SPECIAL)?|POVIDONE|"
    r"HYDROXYPROPYLMETHYLCELLULOSE|CARMELLOSE SODIUM|SODIUM LAURYL SULFATE|BENZYL ALCOHOL|SODIUM HYDROXIDE|"
    r"POTASSIUM HYDROXIDE|CHLOROBUTANOL|DILUENT|EACH SOLVENT CONTAINS|TARTRAZINE|ERYTHROSINE|BRILLIANT BLUE FCF|"
    r"INDIGO CARMINE|SUCROSE|MICROCRYSTALLINE CELLULOSE|METHYLPARABEN|PROPYLPARABEN)$")
SOLVENT_SECTION = re.compile(r"SOLVENT|DILUENT|溶劑|稀釋液", re.I)


# Words that describe the grade or presentation of a substance, not another substance.
DESCRIPTOR = set("""POWDER POWDERED CRYSTAL CRYSTALS CRYSTALLINE FINE COATED GRANULES GRANULAR GRANULATED STERILE DRIED
DRY GEL SOLUTION CONCENTRATE CONCENTRATED DC T/M IN ON GELATIN ENTERIC DICALCIUM DICAL MANNITE SPRAY HUMAN ALCOHOL ANHYDRATE
HYDROUS USP BP EP JP PURIFIED HIGHLY TRITURATION DILUTED LYOPHILIZED WITH MAGNESIUM STEARATE SILICONE RECOMBINANT
HPMC AND STEARIC ACID PELLETS LIQUID PURE COMPRESSIBLE DIRECT""".split())
CATION = r"(?:SODIUM|DISODIUM|POTASSIUM|DIPOTASSIUM|CALCIUM|MAGNESIUM|ALUMINUM|ZINC|AMMONIUM)"


def same_substance(a: str, b: str) -> bool:
    """Do two names that share a TFDA substance code also agree as names?"""
    if a in KEEP_WHOLE or b in KEEP_WHOLE:
        return a == b
    a, b = without_salt(a), without_salt(b)
    if a == b:
        return True
    a2 = re.sub(rf"^{CATION}\s+|\s+{CATION}$", "", a)
    b2 = re.sub(rf"^{CATION}\s+|\s+{CATION}$", "", b)
    for x, y in ((a2, b2), (b2, a2)):
        if x.endswith("IC ACID") and y.endswith("ATE") and x[:-7] == y[:-3]:   # FUSIDIC ACID / FUSIDATE
            return True
        if y.startswith(x + " ") and all(w in DESCRIPTOR or re.search(r"\d|%", w) for w in y[len(x) + 1:].split()):
            return True
    if a2 == b2:
        return True
    return len(min(a, b, key=len)) >= 6 and SequenceMatcher(None, a, b).ratio() >= 0.85


# A different drug although the name starts with the parent's name.
NOT_A_SALT = re.compile(r"BUTYLBROMIDE|BROMOBUTYLATE|N-BUTYL|SILVER|DISULFIDE|ETHINYL|LIPOSOM")


def same_by_name(x: str, y: str) -> bool:
    """X (NHI label) and Y (licence) name one single-ingredient product: are they one name?"""
    if NOT_A_SALT.search(y) and not NOT_A_SALT.search(x):
        return False
    xs, ys = without_salt(x), without_salt(y)
    if xs == ys or ys.startswith(xs + " ") or ys.startswith(xs + "-"):
        return True
    cation = re.compile(rf"^(?:MONO)?{CATION}$")
    if sorted(w for w in ys.split() if not cation.match(w)) == sorted(w for w in xs.split() if not cation.match(w)):
        return True
    squash = lambda t: re.sub(r"[^A-Z0-9]", "", t)
    return len(xs) >= 6 and SequenceMatcher(None, squash(xs), squash(ys)).ratio() >= 0.8


def tidy(name: str) -> str:
    s = unicodedata.normalize("NFKC", name or "").upper().replace("&NBSP;", " ")
    return re.sub(r"\s+", " ", s).strip(" ,;.*")


def read_name(name: str) -> tuple[str, list[str]]:
    """A source's ingredient name -> (name without brackets, synonyms it states).

    "ACETAMINOPHEN (EQ TO PARACETAMOL)" -> ("ACETAMINOPHEN", ["PARACETAMOL"])
    "BETAMETHASONE (AS VALERATE)"       -> ("BETAMETHASONE", [])
    "CYANOCOBALAMIN (VIT B12)"          -> ("CYANOCOBALAMIN", ["VITAMIN B12"])
    """
    s = tidy(name)
    synonyms = []

    def bracket(m: re.Match) -> str:
        inner = m.group(1).strip()
        eq = re.match(r"^(?:EQ\.? ?TO|=)\s*(.+)$", inner)
        vit = re.match(r"^VIT(?:AMINE?)?\.?\s*([A-Z]\d{0,2})$", inner)
        if eq and " + " not in eq.group(1) and not re.search(r"\d\s*(?:MG|MCG|ML|IU|%)", eq.group(1)):
            synonyms.append(eq.group(1).strip())
        elif vit:
            synonyms.append("VITAMIN " + vit.group(1))
        return " "

    s = re.sub(r"\(AS [^()]*\)", " ", s)  # "CEFOPERAZONE(AS SODIUM)STERILE"
    # brackets that close a word group; "BIS(SULPHANYL)PROPANE" and "(RS)-2,3-..." are left alone
    s = re.sub(r"(?<=\S)\s*\(([^()]*)\)(?=\s|\(|$)", bracket, s)
    s = re.sub(r"(?<=\S)\s*\(([^()]*)$", bracket, s)  # bracket the source cut off
    s = re.sub(r"^VIT(?:AMINE?)?\.?\s*(?=[A-Z]\d{0,2}\b)", "VITAMIN ", s.strip())
    s = re.sub(r"\s+", " ", s).strip(" ,;.*")
    return s, [re.sub(r"^VIT(?:AMINE?)?\.?\s*(?=[A-Z]\d{0,2}\b)", "VITAMIN ", tidy(x)) for x in synonyms if tidy(x)]


def without_salt(name: str) -> str:
    """The name with trailing salt and hydrate words removed, however many there are."""
    if name in KEEP_WHOLE or name.split(" ")[0] in CATION_FIRST:
        return name
    s = name
    while True:
        t = SALT_HEAD.sub("", s)
        t = STEREO.sub("", t)
        m = SALT_TAIL.search(t)
        if m and m.start() > 0:
            t = t[:m.start()]
        t = t.strip(" ,")
        if not STEREO.search(t):
            t = t.strip("-")
        if t == s or len(t) < 4:
            return s if len(t) < 4 else t
        s = t


# Synonyms confirmed by hand from the single-ingredient products where the NHI label
# and the licence disagree (left: NHI label, right: licence).
SAME: list[tuple[str, str]] = [
    ("ACETYLSALICYLIC ACID", "ASPIRIN"), ("ACETYLSALICYLIC ACID", "LYSINE ACETYLSALICYLATE"),
    ("SILYMARIN", "EXSICCATED FRUCTUS CARDUI MARIAE EXTRACT"), ("LEUCOVORIN", "FOLINATE"), ("LEUCOVORIN", "FOLINIC ACID"),
    ("SUCRALFATE", "BASIC ALUMINUM SUCROSE SULFATE"), ("SUCRALFATE", "ALUMINUM SUCROSE SULFATE"),
    ("GUAIFENESIN", "GUAIACOL GLYCOLATE"), ("GUAIFENESIN", "GLYCERYL GUAIACOLATE"), ("FACTOR VIII", "ANTIHEMOPHILIC FACTOR"),
    ("POLICRESULEN", "POLYCRESOLSULFONATE"), ("DIPROPHYLLINE", "DYPHYLLINE"), ("DIPROPHYLLINE", "DIHYDROXYPROPYL THEOPHYLLINE"),
    ("ISOPRINOSINE", "METHISOPRINOL"), ("IMMUNOGLOBULIN", "GAMMAGLOBULIN"), ("DEXTROSE", "GLUCOSE"), ("SASAPYRINE", "SALSALATE"),
    ("ESTRADIOL 17-BETA- CYPIONATE", "ESTRADIOL-17-CYCLOPENTYL PROPIONATE"), ("METHYLMETHIONINE", "VITAMIN U"),
    ("BUTYLSCOPOLAMINE", "SCOPOLAMINE-N-BUTYLBROMIDE"), ("BUTYLSCOPOLAMINE", "SCOPOLAMINE BROMOBUTYLATE"),
    ("UROKINASE", "PURIFIED UROKINASE SOLUTION"), ("ERYTHROPOIETIN", "RECOMBINANT HUMAN ERYTHROPOIETIN"),
    ("ERYTHROPOIETIN", "EPOETIN BETA GENETICAL RECOMBINANT"), ("GLUCOSAMINE", "CRYSTALLINE GLUCOSAMINE SULFATE"),
    ("MESALAZINE", "AMINOSALICYLIC ACID META-"), ("GOSERELIN ACEATE", "GOSERELIN ACETATE"),
    ("CICLOPIROX ETHANOLAMINE SALT", "CICLOPIROX OLAMINE"), ("IBANDRONIC ACID", "MONOSODIUM IBANDRONATE MONOHYDRATE"),
    ("IBANDRONIC ACID", "IBANDRONATE SODIUM"), ("ISPAGHULA HUSK", "PSYLLIUM HYDROPHILIC MUCILLOID"),
    ("ISPAGHULA HUSK", "PSYLLIUM HUSK POWDER"), ("ISPAGHULA HUSK", "SIZED MUCILLOID"),
    ("ESTROGEN CONJUGATED", "CONJUGATED ESTROGEN CONCENTRATE"), ("CALCITONIN SALMON", "SALCATONIN"), ("NICOTINIC ACID", "NIACIN"),
    ("BENOXINATE", "OXYBUPROCAINE HCL"), ("PRIMIDONE", "PRIMACLONE"), ("MYCOPHENOLIC ACID", "SODIUM MYCOPHENOLATE"),
    ("LEVAMISOLE", "TETRAMISOLE L(-)- HCL"), ("ARGININE VASOPRESSIN", "ARGIPRESSIN"), ("URSODEOXYCHOLIC ACID", "URSODIOL"),
    ("PENICILLIN V", "PHENOXY METHYL PENICILLIN POTASSIUM"), ("HYALURONIC ACID", "HYALURONATE SODIUM"), ("SALBUTAMOL", "ALBUTEROL"),
    ("THROMBIN", "THROMBASE"), ("SOMATOTROPIN HUMAN", "RECOMBINANT SOMATROPIN"), ("SOMATOTROPIN HUMAN", "BIOSYNTHETIC HUMAN GROWTH HORMONE"),
    ("HUMAN SOMATROPIN", "BIOSYNTHETIC HUMAN GROWTH HORMONE"), ("FACTOR IX", "COAGULATION FACTOR IX"),
    ("CETUXIMAB", "CETUXIMAB, CHIMERIC ANTIBODY"), ("IRON DEXTRAN COMPLEX", "IRON DEXTRAN"), ("DEFER", "DEFERIPRONE"),
    ("TEGAFUR", "N1-(2-TETRAHYDROFURYL)-5-FLUOROURACIL"), ("FLOPROPIONE", "2,4,6-TRIHYDROXYPROPIOPHENONE"),
    ("FLOPROPIONE", "PHLOROPROPIOPHENONE"), ("TANNALBIN", "ALBUMIN TANNATE"), ("NATAMYCIN", "PIMARICIN"),
    ("METHYLERGONOVINE", "METHYLERGOMETRINE HYDROGEN MALEATE"), ("CISPLATIN", "PLATINUM CIS-"),
    ("NITROGLYCERIN", "GLYCERYL TRINITRATE SOLUTION"), ("NITROGLYCERIN", "GLYCERYL TRINITRATE ON LACTOSE"),
    ("NITROGLYCERIN", "NITROGLYCERIN/BETA- LACTOSE"), ("GLYCOPYRROLATE", "GLYCOPYRRONIUM"),
    ("AMINOPHYLLINE", "THEOPHYLLINE ETHYLENEDIAMINE"), ("POLYETHYLENE GLYCOL 4000", "MACROGOL 4000"),
    ("SULFASALAZINE", "SALICYLAZOSULFAPYRIDINE"), ("TRH", "PROTIRELIN"), ("B.C.G. VACCINE", "BACILLUS CALMETTE-GUERIN"),
    ("PROXYPHYLLINE", "7-(B-HYDROXYPROPYL)THEOPHYLLINE"), ("FACTOR VII", "EPTACOG ALFA"), ("ISAVUCONAZOLE", "ISAVUCONAZONIUM SULFATE"),
    ("HEMATIN", "HUMAN HEMIN"), ("ETILEFRIN", "ETHYLPHENYLEPHRINE HCL"),
    ("ALUMINUM DIHYDROXYALLANTOINATE", "DIHYDROXYALUMINIUM ALLANTOINATE"), ("VITAMIN E", "TOCOPHEROL ALPHA-"),
    ("VALPROIC ACID", "DIVALPROEX SODIUM"), ("CENTELLA ASIATICA TITRATED EXTRACT", "CENTELLA ASIATICA"),
    ("PANTOTHENIC ACID", "PANTOTHENATE"), ("PANTOTHENIC ACID", "CALCIUM PANTOTHENATE"), ("SCOPOLAMINE", "HYOSCINE"),
    ("SCOPOLAMINE", "HYOSCINE HYDROBROMIDE"), ("GLYCYRRHIZIC ACID", "GLYCYRRHIZINIC ACID"), ("MAGALDRATE", "MAGALDRAT"),
    ("CHLORPHENIRAMINE", "CHLORPHENIRAMIN"), ("DIMETHICONE", "SIMETHICONE"), ("DIMETHICONE", "DIMETHYLPOLYSILOXANE"),
]


class Substances:
    """Union of names into substances. Add every name first, then `close()`."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.weight: Counter = Counter()       # how many products use the name
        self.preferred: Counter = Counter()    # names the NHI labels use, with their code counts
        self.by_code: dict[str, list[str]] = defaultdict(list)  # TFDA substance code -> names
        self.edges: list[tuple[str, str, str]] = []  # (name, name, why) for review
        self.seen_together: Counter = Counter()  # (NHI name, licence name) on single-ingredient products
        self.closed = False

    def _find(self, a: str) -> str:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def _add(self, a: str) -> None:
        self.parent.setdefault(a, a)

    def _join(self, a: str, b: str, why: str = "") -> None:
        self._add(a), self._add(b)
        if a != b:
            self.edges.append((a, b, why))
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            self.parent[rb] = ra

    def add(self, raw: str, weight: int = 1, code: str = "", preferred: bool = False) -> str:
        """Register a source name; returns the bracket-free name used as its key."""
        name, synonyms = read_name(raw)
        if not name:
            return ""
        self._add(name)
        self.weight[name] += weight
        if preferred:
            self.preferred[name] += weight
        for syn in synonyms:
            self._join(name, syn, "synonym")
        base = code[:8]
        if len(code) >= 8 and base[0].isdigit() and not base.startswith("98"):
            if name not in self.by_code[base]:
                self.by_code[base].append(name)
        return name

    def observe(self, nhi_name: str, licence_name: str) -> None:
        """A single-ingredient product: NHI labels it `nhi_name`, its licence lists `licence_name`."""
        if nhi_name and licence_name and nhi_name != licence_name:
            self.seen_together[(nhi_name, licence_name)] += 1

    def close(self) -> None:
        """Join names that differ only by a salt word, where the short name is in use."""
        for base, same in self.by_code.items():
            for i, a in enumerate(same):
                for b in same[i + 1:]:
                    if same_substance(a, b):
                        self._join(a, b, "code " + base)
        for (x, y), _n in self.seen_together.items():
            if same_by_name(x, y):
                self._join(x, y, "same product")
        for x, y in SAME:
            if x in self.parent and y in self.parent:
                self._join(x, y, "reviewed")
        names = list(self.parent)
        short = {n: without_salt(n) for n in names}
        for n, s in short.items():
            if s != n and s in self.parent:
                self._join(s, n, "salt")
        groups: dict[str, list[str]] = defaultdict(list)
        for n in self.parent:
            groups[self._find(n)].append(n)
        self.canonical: dict[str, str] = {}
        self.members: dict[str, list[str]] = {}
        for members in groups.values():
            total = Counter()
            for n in members:  # a salt form lends its weight to the name without the salt
                total[without_salt(n) if without_salt(n) in self.parent else n] += self.weight[n]
            nhi = [n for n in members if self.preferred[n]]
            if nhi:
                best = max(nhi, key=lambda n: (self.preferred[without_salt(n)] + self.preferred[n], -len(n), n))
                if without_salt(best) in self.parent and self._find(without_salt(best)) == self._find(best):
                    best = without_salt(best)
            else:
                best = max(total, key=lambda n: (total[n], -len(n), n))
            for n in members:
                self.canonical[n] = best
            self.members[best] = sorted(members)
        self.closed = True

    def name(self, raw: str) -> str:
        """Canonical substance name for a source name (after `close()`)."""
        key, _ = read_name(raw)
        return self.canonical.get(key, key)
