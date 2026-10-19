"""Read-only catalog labels for this installation's item_proto enum."""
import re


def _usable_name(value):
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or re.fullmatch(r'(?:no\s*name|unnamed|none|null|\?+)', text, re.I) or '\ufffd' in text:
        return False
    # Some legacy catalogue entries contain Korean bytes decoded as Latin-1.
    # Do not present those bytes as an English name or invent a translation.
    if re.search(r'[\u00b3\u00ba\u00c6\u00c7\u00d0][\x80-\xff]', text):
        try:
            decoded = text.encode('latin-1').decode('cp949')
            if len(re.findall(r'[\uac00-\ud7af]', decoded)) >= 2:
                return False
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return not any(ord(char) < 32 for char in text)


def item_identity(item, definition=None, english_name=None):
    """Prefer this package's names while retaining old catalogue search terms."""
    original = str(item.get('name') or '').strip()
    seed_name = definition[2] if definition and len(definition) > 2 else None
    candidates = ((english_name, 'installed-english'), (original, 'catalogue'), (seed_name, 'installed-seed'))
    name, source = next(((value.strip(), label) for value, label in candidates if _usable_name(value)),
                        ('Unnamed item #' + str(item['id']), 'unknown'))
    return {'name': name, 'nameSource': source, 'catalogName': original, 'original': seed_name or original,
            'nameStatus': 'unnamed' if source == 'unknown' else 'named',
            'definitionStatus': 'installed-seed' if definition else 'catalogue-only'}


TYPE_KINDS = {
    0: ("other", "unclassified", "Other item"),
    1: ("equipment", "weapon", "Weapon"),
    2: ("equipment", "armour", "Armour & jewellery"),
    3: ("other", "consumable", "Other consumable"),
    4: ("other", "automatic", "Automatic consumable"),
    5: ("materials", "upgrade-material", "Upgrade & crafting material"),
    6: ("other", "special", "Special item"),
    7: ("tools", "tool", "Tool"),
    8: ("other", "lottery", "Lottery item"),
    9: ("other", "currency", "Currency"),
    10: ("stones", "spirit-stone", "Spirit stone"),
    11: ("chests", "container", "Container"),
    12: ("fishing", "fish", "Fish"),
    13: ("tools", "fishing-rod", "Fishing rod"),
    14: ("materials", "resource", "Resource & ore"),
    15: ("fishing", "campfire", "Campfire"),
    16: ("other", "unique", "Unique item"),
    17: ("books", "skill-book", "Skill book"),
    18: ("quest", "quest-item", "Quest item"),
    19: ("other", "polymorph", "Polymorph marble"),
    20: ("chests", "treasure-chest", "Treasure chest"),
    21: ("chests", "key", "Chest key"),
    22: ("books", "forgetting-book", "Forgetting book"),
    23: ("chests", "gift-box", "Gift box & reward chest"),
    24: ("tools", "pickaxe", "Pickaxe"),
    25: ("equipment", "hairstyle", "Hairstyle"),
    26: ("other", "totem", "Totem"),
    27: ("potions", "blend", "Dew & blended consumable"),
    28: ("equipment", "costume", "Costume"),
    29: ("stones", "dragon-stone", "Dragon stone"),
    30: ("stones", "special-dragon-stone", "Special dragon stone"),
    31: ("tools", "extractor", "Dragon stone extractor"),
    32: ("other", "currency", "Currency"),
    33: ("equipment", "ring", "Ring"),
    34: ("equipment", "belt", "Belt"),
    35: ("tools", "herbalist-knife", "Herbalist knife"),
    36: ("potions", "speed-potion", "Speed potion"),
}
USABLE_KINDS = {
    1: ("scrolls", "teleport-scroll", "Teleport & return scroll"),
    2: ("scrolls", "upgrade-scroll", "Upgrade scroll & protection"),
    6: ("fishing", "bait", "Fishing bait"),
    14: ("scrolls", "spirit-scroll", "Spirit stone scroll"),
    17: ("tools", "socket-tool", "Spirit stone & socket tool"),
    18: ("bonus", "bonus-changer", "Bonus changer"),
    19: ("bonus", "bonus-adder", "Bonus adder"),
    20: ("materials", "socket-material", "Socket material"),
    21: ("materials", "refined-ore", "Refined ore"),
    22: ("bonus", "fifth-bonus", "Fifth bonus marble"),
    27: ("potions", "time-elixir", "Time elixir"),
    28: ("potions", "time-elixir", "Time elixir"),
    33: ("books", "recipe-book", "Crafting recipe book"),
}
WEAPONS = ["Sword", "Dagger", "Bow", "Two-handed weapon", "Bell", "Fan", "Arrow", "Lance"]
ARMOUR = ["Body armour", "Helmet", "Shield", "Bracelet", "Shoes", "Necklace", "Earrings"]


def item_metadata(item, row=None):
    """Describe items without trusting the catalog's outdated category names.

    item_proto is seed data, not a query against the running game database.
    Missing definitions use conservative name/category fallbacks.
    """
    text = re.sub(r"[^a-z0-9]", "", item.get("name", "").lower())
    typ = int(row[3]) if row and len(row) > 4 else None
    subtype = int(row[4]) if typ is not None else None
    group, kind, label = TYPE_KINDS.get(typ, ("other", "unclassified", "Other item"))
    if typ == 1 and 0 <= subtype < len(WEAPONS):
        kind, label = "weapon-" + str(subtype), WEAPONS[subtype]
    elif typ == 2 and 0 <= subtype < len(ARMOUR):
        kind, label = "armour-" + str(subtype), ARMOUR[subtype]
    elif typ == 3:
        group, kind, label = USABLE_KINDS.get(subtype, (group, kind, label))
        if subtype == 0:
            group, kind, label = "potions", "recovery-potion", "HP & MP potion"
    # These names distinguish custom consumables sharing a general engine type.
    if group not in ("equipment", "bonus", "books", "stones", "materials", "quest"):
        if "exorcism" in text and "scroll" in text:
            group, kind, label = "scrolls", "exorcism-scroll", "Exorcism scroll"
        elif "potion" in text or "elixir" in text:
            group = "potions"
            if any(word in text for word in ("redpotion", "bluepotion", "healthpotion", "manapotion")):
                kind, label = "recovery-potion", "HP & MP potion"
            elif any(word in text for word in ("greenpotion", "purplepotion", "speedpotion", "potionofspeed")):
                kind, label = "speed-potion", "Speed potion"
            else:
                kind, label = "buff-potion", "Buff & special potion"
        elif group == "other" and "scroll" in text:
            group, kind, label = "scrolls", "other-scroll", "Other scroll"
    if typ is None and group == "other":
        # Only unambiguous legacy catalog groups. "pickaxe", "rod", "ds",
        # "ring" and "special" are misleading labels in this package.
        fallback = {"weapon": 1, "armor": 2, "lottery": 17, "unique": 10, "gacha": 29}
        if item.get("category") in fallback:
            group, kind, label = TYPE_KINDS[fallback[item["category"]]]
    level = None
    if row and len(row) > 23:
        limits = [int(row[i + 1]) for i in (20, 22) if row[i] == "1"]
        level = max(limits) if limits else None
    return {"catalogGroups": [group], "catalogKind": kind, "catalogLabel": label,
            "requiredLevel": level}
