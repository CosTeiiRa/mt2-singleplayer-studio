"""Plain-English item help. Never infer special scroll behavior from its name.

"Guide" entries describe standard Metin2 mechanics, not verified live rules.
References and the seed/catalog naming conflicts are documented in README.md.
"""

KIND_HELP = {
    "bonus-changer": "Rerolls existing normal equipment bonuses (slots 1–5). Replaces the current rolls; it does not add a new bonus slot.",
    "bonus-adder": "Attempts to add another normal equipment bonus, up to four bonuses. Keeps existing bonuses; use a fifth-bonus marble for the fifth slot.",
    "fifth-bonus": "Attempts to add the fifth normal bonus to equipment that already has four. It does not reroll the existing bonuses.",
    "teleport-scroll": "Travel consumable. Its destination and whether it records a location depend on the particular scroll.",
    "upgrade-scroll": "Equipment refinement consumable. Its exact success chance, failure protection and eligible equipment are not documented for this ID.",
    "spirit-scroll": "Used with socketed Spirit Stones. The exact removal and recovery behavior is not documented for this ID.",
    "exorcism-scroll": "Removes the waiting period before reading another skill book. It does not guarantee that the next book succeeds.",
    "recovery-potion": "Restores HP or MP when consumed. The amount depends on the potion; known recovery values are shown below.",
    "speed-potion": "Temporary speed consumable. Green potions normally increase attack speed; purple potions normally increase movement speed.",
    "buff-potion": "Consumable that provides a temporary effect. Exact effect strength and duration are not documented for this ID.",
    "blend": "Blended consumable or dew that provides a temporary effect. Its effect and duration depend on the server's blend configuration.",
    "time-elixir": "Time-related consumable. Its compatible system and exact duration are not documented for this ID.",
    "upgrade-material": "Ingredient used in equipment upgrades or crafting. The recipe determines the required quantity and what it produces.",
    "resource": "Gathered resource or ore used in processing, upgrades or crafting. Check the relevant recipe for its use.",
    "refined-ore": "Processed ore used in compatible accessory sockets. The bonus and duration depend on the accessory and server rules.",
    "socket-material": "Material used to prepare a socket on a compatible accessory. It does not add a normal equipment bonus.",
    "skill-book": "Read to train a skill. The required skill, learning chance and waiting period depend on the book and server rules.",
    "forgetting-book": "Used to remove training from a compatible skill. The exact eligible skill depends on this book.",
    "recipe-book": "Recipe item used by a crafting system. The associated recipe determines the materials and result.",
    "spirit-stone": "Socket into compatible equipment to add its stone-specific bonus. Socketing rules and success depend on the server.",
    "dragon-stone": "Dragon Stone Alchemy equipment. Equip or refine it through the alchemy system; its grade and bonuses determine its effect.",
    "special-dragon-stone": "Special item for Dragon Stone Alchemy. Exact compatible use is not documented for this ID.",
    "container": "Container with configured rewards. Check its chest contents in the drop editor to see the available items.",
    "treasure-chest": "Treasure chest with configured rewards. A compatible key may be required; check the chest configuration.",
    "gift-box": "Open to receive rewards from its configured reward group. Contents and probabilities depend on that group.",
    "key": "Opens a compatible chest. The matching chest is not documented for this ID.",
    "fishing-rod": "Equip for fishing and use suitable bait. Its level and the server's fishing rules affect its use.",
    "pickaxe": "Equip for mining ore veins. Progression and eligible veins depend on the mining system.",
    "herbalist-knife": "Tool used by the herbalism system to gather plants.",
    "bait": "Used while fishing with a fishing rod.",
    "fish": "Fishing catch. Depending on the fish, it may be opened, grilled or used in a recipe.",
    "campfire": "Used to prepare a fire for grilling compatible fish.",
    "extractor": "Extraction tool for Dragon Stone Alchemy. Exact recovery chance and compatible use depend on the tool.",
    "socket-tool": "Tool for Spirit Stones or equipment sockets. Exact recovery behavior is not documented for this ID.",
    "quest-item": "Used by a quest or scripted system. Its exact purpose depends on the quest that consumes or checks it.",
    "currency": "Currency used to pay for items or services in its associated system.",
    "costume": "Wearable appearance item. Any additional bonuses and expiry depend on the costume.",
    "hairstyle": "Changes the character's hairstyle when used or equipped. Restrictions and expiry depend on the item.",
    "belt": "Wearable belt. Its bonuses and additional inventory functions depend on its grade and server rules.",
    "ring": "Wearable ring. Its fixed bonuses and duration depend on the item.",
    "polymorph": "Used by the polymorph system to transform the character. The form and duration depend on the marble.",
}
EQUIPMENT_HELP = "Wearable equipment. Its item type, grade and built-in bonuses determine its effect; this is a catalog entry, not a rolled inventory item."
UNKNOWN_HELP = "No reliable effect description is available for this item. Use its ID to check the game's tooltip or the Singleplayer wiki."

# ID-specific explanations use installed definitions plus the referenced guide.
SCROLL_HELP = {
    "25040": "Used for equipment refinement. In standard Metin2, failure keeps the item but lowers its upgrade grade by one.",
    "25041": "The installed seed identifies this as a Blessing Scroll. Standard Blessing Scroll behavior protects the item from destruction, but failure can lower its upgrade grade.",
    "25042": "The installed seed identifies this as Magic Stone. Standard Magic Stone behavior protects both the item and its upgrade grade when refinement fails.",
    "71021": "Scroll for early equipment upgrades. The standard Metin2 guide describes guaranteed success up to +4; this version's exact eligibility is not confirmed.",
    "71032": "Equipment upgrade scroll. In standard Metin2, it improves the success chance and protects against destruction, but failure can lower the upgrade grade.",
    "70039": "Equipment upgrade aid. In standard Metin2, it uses an improved success table and protects against destruction; failure can still lower the upgrade grade.",
    "22000": "Returns the character to town when used.",
    "22001": "Returns the character to town when used.",
    "22010": "Travel scroll used to record a location and return to it. Destination restrictions depend on the server.",
    "22011": "Travel scroll used to record a location and return to it. Destination restrictions depend on the server.",
}
NAME_NOTES = {
    "25041": "Name mismatch in the older catalogue: Magic Stone referred to #25041. The installed package calls this Blessing Scroll. Do not assume downgrade protection from the older name.",
    "25042": "Name mismatch in the older catalogue: Ritualstein referred to #25042. The installed package calls this Magic Stone. Ritual Stone level restrictions are not confirmed for this ID.",
}


def item_description(item, row=None):
    kind = item.get("catalogKind", "unclassified")
    ident = str(item.get("id", ""))
    confirmed = bool(row and len(row) > 35)
    text = SCROLL_HELP.get(ident) if confirmed and kind in ("upgrade-scroll", "teleport-scroll") else None
    text = text or KIND_HELP.get(kind)
    if not text and item.get("catalogGroups") == ["equipment"]:
        text = EQUIPMENT_HELP
    source = "guide" if text else "unknown"
    if not confirmed and text:
        source = "catalog"
    note = NAME_NOTES.get(ident, "") if confirmed and kind == "upgrade-scroll" else ""
    if ident in ("71151", "76023", "71152", "76024") and confirmed:
        note = "Standard Green Magic / Green Strength restriction: weapons and body armour requiring level 40 or below. This server's exact limit is not exposed by the seed definition."
    facts = []
    if confirmed:
        facts.append(["Definition", "Present in installed seed"])
        level = item.get("requiredLevel")
        if level:
            facts.append(["Required level", str(level)])
        if row[3:5] == ["3", "0"]:
            hp, mp = int(row[30]), int(row[31])
            if hp > 0 or mp > 0:
                text = "Restores " + " and ".join(f"{amount:,} {stat}" for amount, stat in ((hp, "HP"), (mp, "MP")) if amount > 0) + " when consumed, according to the installed seed."
                source = "definition"
    elif source == "catalog":
        note = "General category guide. This ID has no definition in the installed seed, so its precise effect and restrictions are unverified."
    return {"text": text or UNKNOWN_HELP, "note": note, "source": source, "facts": facts}
