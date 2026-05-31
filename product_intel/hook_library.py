"""Product Intel Hook Core Library."""

from __future__ import annotations

from typing import Any


def hook(
    hook_id: str,
    hook_type: str,
    categories: list[str],
    formats: str,
    photo_de: str,
    photo_fr: str,
    video_de: str,
    video_fr: str,
    risk_notes: str = "",
) -> dict[str, Any]:
    return {
        "hook_id": hook_id,
        "hook_type": hook_type,
        "applicable_categories": categories,
        "applicable_markets": ["DE", "FR"],
        "applicable_content_formats": formats,
        "photo_hook_formula": "{product} + concrete benefit + low-friction reason to care",
        "video_hook_formula": "Open with the product in use, show one clear problem, then reveal the practical payoff.",
        "example_photo_copy_de": photo_de,
        "example_photo_copy_fr": photo_fr,
        "example_video_opening_de": video_de,
        "example_video_opening_fr": video_fr,
        "risk_notes": risk_notes,
    }


HOOK_LIBRARY: list[dict[str, Any]] = [
    hook("H001", "price_shock", ["food", "snacks", "beauty", "home", "electronics"], "both", "Unter 10 EUR und trotzdem praktisch.", "Moins de 10 EUR et vraiment utile.", "Ich dachte nicht, dass das fuer den Preis so praktisch ist.", "Je ne pensais pas que ce serait aussi utile a ce prix.", "Do not invent discounts or original prices."),
    hook("H002", "limited_discount", ["food", "beauty", "fashion", "home"], "both", "Wenn der Rabatt echt im Angebot steht, lohnt sich ein Blick.", "Si la promo est bien affichee, ca vaut le coup d'oeil.", "Nur nutzen, wenn der Deal wirklich im Produktbriefing steht.", "A utiliser seulement si la promo est vraiment fournie.", "Only use when a real discount is provided."),
    hook("H003", "pain_point_hot_weather", ["home appliances", "fans", "cooling", "electronics"], "video", "Wenn es zuhause zu warm wird.", "Quand il fait trop chaud a la maison.", "Der Moment, wenn es draussen heiss ist und drinnen keine Luft steht.", "Le moment ou il fait chaud et l'air ne bouge plus.", "Avoid unsupported wind speed, battery, or cooling claims."),
    hook("H004", "pain_point_messy_home", ["home", "storage", "organisation"], "both", "Wenn zuhause alles herumliegt.", "Quand tout traine a la maison.", "Ich wollte nur diese eine Ecke endlich ordentlich haben.", "Je voulais juste ranger ce coin une bonne fois.", "Do not overclaim space saved unless measured."),
    hook("H005", "pain_point_pet_hair", ["pet supplies", "pets"], "both", "Fuer alle, die Haustier-Chaos kennen.", "Pour ceux qui connaissent le bazar avec les animaux.", "Wenn dein Haustier wieder den Alltag bestimmt.", "Quand ton animal decide encore de l'organisation.", "Avoid health, grooming, or hygiene claims unless supported."),
    hook("H006", "before_after", ["fashion", "beauty", "home", "storage"], "both", "Vorher unscheinbar, danach direkt besser.", "Avant simple, apres beaucoup plus propre.", "Erst ohne, dann mit dem kleinen Upgrade.", "D'abord sans, puis avec le petit detail qui change tout.", "Before/after must not imply unsupported performance."),
    hook("H007", "problem_solution", ["pet supplies", "home", "electronics", "beauty", "fashion"], "both", "Kleines Problem, einfache Loesung.", "Petit probleme, solution simple.", "Das Problem kennt man sofort.", "Le probleme, on le reconnait tout de suite.", "Keep the problem realistic and non-medical."),
    hook("H008", "lazy_solution", ["home", "storage", "beauty", "pet supplies"], "both", "Fuer alle, die es gern unkompliziert haben.", "Pour celles et ceux qui aiment quand c'est simple.", "Ich wollte keine komplizierte Loesung.", "Je ne voulais pas quelque chose de complique.", "Avoid saying it solves everything."),
    hook("H009", "no_installation", ["home appliances", "fans", "home", "storage"], "both", "Ohne Aufbau, direkt nutzbar.", "Sans installation, pret a utiliser.", "Kein Werkzeug, kein Aufbau, einfach hinstellen.", "Pas d'outil, pas de montage, juste a poser.", "Only use when true for the product."),
    hook("H010", "small_space_solution", ["home", "storage", "fans", "cooling"], "both", "Praktisch, wenn man wenig Platz hat.", "Pratique quand on manque de place.", "Kleine Wohnung, kleine Loesung, grosser Unterschied.", "Petit espace, solution simple.", "Do not invent dimensions."),
    hook("H011", "gift_for_him", ["fashion", "electronics", "home", "beauty"], "photo", "Eine kleine Geschenkidee fuer ihn.", "Une idee cadeau simple pour lui.", "Wenn du noch ein kleines Geschenk suchst.", "Si tu cherches encore une petite idee cadeau.", "Avoid gender stereotypes beyond light gifting language."),
    hook("H012", "gift_for_her", ["fashion", "beauty", "home", "pet supplies"], "photo", "Eine kleine Geschenkidee fuer sie.", "Une idee cadeau simple pour elle.", "Wenn ein kleines Detail das Geschenk besser macht.", "Quand un petit detail rend le cadeau plus sympa.", "Avoid sensitive personal claims."),
    hook("H013", "pet_behavior", ["pet supplies", "cats", "dogs"], "video", "Wenn dein Haustier neugierig wird.", "Quand ton animal devient curieux.", "Ich wollte sehen, ob meine Katze es ueberhaupt annimmt.", "Je voulais voir si mon chat allait vraiment s'en approcher.", "Do not guarantee animal behavior or health benefits."),
    hook("H014", "mom_relief", ["home", "storage", "baby", "kids"], "both", "Eine kleine Alltagserleichterung.", "Un petit soulagement au quotidien.", "Wenn der Alltag schon voll genug ist.", "Quand la journee est deja bien remplie.", "Children-related content needs careful review."),
    hook("H015", "summer_season", ["fans", "cooling", "travel", "fashion"], "both", "Sommerteil, das man wirklich nutzt.", "Le petit objet qu'on utilise vraiment en ete.", "Sobald es warm wird, merkt man den Unterschied.", "Des qu'il fait chaud, on comprend l'interet.", "Avoid unsupported cooling performance."),
    hook("H016", "travel_use", ["travel", "electronics", "beauty", "storage"], "both", "Praktisch fuer unterwegs.", "Pratique a emporter.", "Ich packe es ein, weil es kaum Platz braucht.", "Je le prends parce que ca ne prend presque pas de place.", "Do not invent airline or safety compliance."),
    hook("H017", "is_it_worth_it", ["electronics", "beauty", "home", "fashion"], "both", "Ist es das wert?", "Est-ce que ca vaut le coup ?", "Ich teste, ob es wirklich alltagstauglich ist.", "Je teste si c'est vraiment utile au quotidien.", "Keep verdict balanced; avoid fake test claims."),
    hook("H018", "not_an_iq_tax", ["electronics", "home", "beauty"], "video", "Kein Fehlkauf, wenn man genau das braucht.", "Pas un achat inutile si tu en as vraiment besoin.", "Ich wollte wissen, ob das nur Spielerei ist.", "Je voulais savoir si c'etait juste un gadget.", "Avoid insulting users or making unverifiable claims."),
    hook("H019", "daily_usefulness", ["pet supplies", "home", "electronics", "beauty", "food", "fashion"], "both", "Ein kleines Teil fuer jeden Tag.", "Un petit objet utile au quotidien.", "Das ist kein spektakulaeres Teil, aber man nutzt es staendig.", "Ce n'est pas spectaculaire, mais on l'utilise souvent.", "Do not imply universal results."),
    hook("H020", "shelf_value_deal", ["food", "snacks", "beauty", "home"], "photo", "Sieht im Regal unscheinbar aus, ist aber praktisch.", "Discret sur l'etagere, mais pratique.", "Man uebersieht es leicht, bis man es braucht.", "On le remarque peu, jusqu'au moment ou on en a besoin.", "Do not invent shelf life or stock claims."),
]


def get_hook_by_type(hook_type: str) -> dict[str, Any] | None:
    normalized = hook_type.strip().lower()
    for hook_item in HOOK_LIBRARY:
        if hook_item["hook_type"].lower() == normalized:
            return hook_item
    return None


def select_hooks_by_types(hook_types: list[str]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for hook_type in hook_types:
        hook_item = get_hook_by_type(hook_type)
        if hook_item:
            selected.append(hook_item)
    return selected
