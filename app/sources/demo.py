"""Demo library: invented titles (no real film, no poster), shown while
Jellyfin is not connected, so the whole quiz can be tried."""

from __future__ import annotations

from ..model import Episode, Title, series_progress

# id, name, year, minutes, rating, classification, genres, played, overview
MOVIES = [
    ("demo-m01", "Le Phare des brumes", 2019, 112, 7.4, "12", ["Mystère", "Thriller"], False,
     "Une gardienne de phare reçoit chaque nuit des signaux d'un bateau que personne n'a jamais vu entrer au port."),
    ("demo-m02", "Les Gaufres de Mamie Lou", 2022, 94, 6.8, "Tous publics", ["Comédie", "Famille"], True,
     "Trois cousins reprennent la roulotte à gaufres de leur grand-mère le temps d'un été à la côte, et tout part de travers."),
    ("demo-m03", "Orbite basse", 2016, 138, 7.9, "12", ["Science-Fiction", "Drame"], False,
     "Coincée seule dans une station en perdition, une ingénieure a quatre-vingt-dix minutes pour revenir sur Terre."),
    ("demo-m04", "Le Dernier Tram", 2011, 101, 6.5, "Tous publics", ["Romance", "Comédie"], False,
     "Deux inconnus ratent le dernier tram et traversent la ville à pied, de minuit jusqu'au lever du jour."),
    ("demo-m05", "Ligne de crête", 2021, 126, 7.1, "16", ["Guerre", "Drame"], False,
     "Hiver 1944. Une poignée de soldats doit tenir un col de montagne en attendant des renforts qui n'arrivent pas."),
    ("demo-m06", "Petit Renard et la Lune", 2020, 82, 7.6, "Tous publics", ["Animation", "Famille"], True,
     "Un renardeau décide d'aller rendre visite à la Lune, persuadé qu'elle s'ennuie toute seule là-haut."),
    ("demo-m07", "Brouillard sur l'Escaut", 2008, 117, 6.9, "16", ["Policier", "Thriller"], True,
     "Un commissaire proche de la retraite rouvre une affaire classée sur les quais d'Anvers."),
    ("demo-m08", "Fanfare !", 2023, 98, 6.3, "Tous publics", ["Musique", "Comédie"], False,
     "La fanfare d'un village a six semaines pour se qualifier au concours national. Elle n'a plus de trompettiste."),
    ("demo-m09", "La Maison du fond", 2014, 96, 6.1, "16", ["Horreur"], False,
     "Une famille s'installe dans une maison bon marché. Trop bon marché."),
    ("demo-m10", "Grand Bleu Arctique", 2018, 88, 8.0, "Tous publics", ["Documentaire"], False,
     "Une année entière sous la banquise, avec les phoques, les orques et une équipe de plongeurs têtus."),
    ("demo-m11", "Le Casse du siècle (ou presque)", 2001, 109, 6.7, "Tous publics", ["Comédie", "Policier"], True,
     "Quatre retraités montent le cambriolage de la banque qui a ruiné leur club de pétanque."),
    ("demo-m12", "Signal faible", 2024, 131, 7.3, "12", ["Science-Fiction", "Mystère"], False,
     "Une radioastronome capte un message qui semble venir de son propre observatoire, avec dix ans d'avance."),
]

# id, name, year, rating, classification, genres, overview, seasons [(episodes, minutes)], watched count, in progress (minutes)
SERIES = [
    ("demo-s01", "Les Voisins du 3e", 2019, 7.2, "Tous publics", ["Comédie", "Sitcom"],
     "La vie d'un immeuble bruxellois où tout le monde sait tout sur tout le monde.", [(10, 24), (10, 24), (8, 26)], 13, 0),
    ("demo-s02", "Zone grise", 2021, 8.1, "16", ["Thriller", "Crime"],
     "Une enquêtrice infiltrée dans un réseau de contrebande ne sait plus très bien de quel côté elle est.", [(8, 52), (8, 55)], 0, 0),
    ("demo-s03", "Atelier Céramique", 2023, 6.9, "Tous publics", ["Téléréalité", "Documentaire"],
     "Dix potiers amateurs, un atelier, une épreuve par semaine.", [(6, 45)], 2, 18),
    ("demo-s04", "Les Archives de Valmont", 2015, 7.8, "12", ["Mystère", "Drame"],
     "Une archiviste découvre que les dossiers de sa petite ville ont été réécrits pendant des décennies.", [(10, 48), (10, 50), (10, 47)], 26, 0),
    ("demo-s05", "Kiko et Bulle", 2017, 7.0, "Tous publics", ["Animation", "Famille"],
     "Deux poissons-clowns explorent un récif bien plus grand que prévu.", [(26, 12)], 26, 0),
    ("demo-s06", "Station Polaire", 2024, 7.5, "12", ["Science-Fiction", "Drame"],
     "Douze scientifiques, six mois de nuit, et une découverte qu'ils ne peuvent pas signaler.", [(6, 58)], 0, 0),
    ("demo-s07", "Cuisine de garde", 2012, 6.6, "Tous publics", ["Cuisine", "Comédie"],
     "Un chef étoilé reprend la cantine d'un hôpital. Les infirmières ne sont pas impressionnées.", [(8, 30), (8, 30)], 9, 0),
    ("demo-s08", "Le Front de l'Est", 2010, 8.3, "16", ["Guerre", "Drame"],
     "Le destin de quatre frères pris dans la guerre, d'une saison à l'autre.", [(6, 62), (6, 60)], 0, 0),
]


def _episodes(seasons, watched: int, in_progress_min: float) -> list[Episode]:
    eps = [Episode(season=0, number=1, name="Spécial", runtime_min=20)]  # ignored by the quiz
    n = 0
    for s, (count, minutes) in enumerate(seasons, start=1):
        for e in range(1, count + 1):
            played = n < watched
            position = in_progress_min if (n == watched and in_progress_min) else 0.0
            eps.append(Episode(season=s, number=e, name=f"Épisode {e}", runtime_min=minutes, played=played, position_min=position))
            n += 1
    return eps


def catalogue() -> list[Title]:
    out = []
    for id_, name, year, minutes, rating, cert, genres, played, overview in MOVIES:
        out.append(Title(id=id_, kind="movie", name=name, source="demo", year=year, rating=rating,
                         official_rating=cert, genres=genres, overview=overview, runtime_min=minutes, played=played))
    for id_, name, year, rating, cert, genres, overview, seasons, watched, progress in SERIES:
        prog = series_progress(_episodes(seasons, watched, progress))
        out.append(Title(id=id_, kind="series", name=name, source="demo", year=year, rating=rating,
                         official_rating=cert, genres=genres, overview=overview, runtime_min=prog.avg_episode_min,
                         played=watched > 0, series=prog))
    return out
