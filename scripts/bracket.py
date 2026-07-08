"""Struktura drabinki pucharowej MS 2026 (48 druzyn), odtworzona z realnych
danych: pozycje w tabelach grupowych + realny terminarz 1/16-1/8-cwiercfinal-
polfinal-final, ktory podala uzytkowniczka. Nie jest to zgadywanie - kazdy
mecz 1/16 finalu zostal potwierdzony albo bezposrednio wynikiem w bazie,
albo etykieta grupowa z podanego terminarza (np. "Hiszpania (1H) - Austria
(2J)").

WAZNE UPROSZCZENIE: 8 z 12 trzecich miejsc awansuje do 1/16 finalu, a
FIFA przydziela im konkretnych rywali wg oficjalnej tabeli zaleznej od
TEGO, KTORE dokladnie 8 grup awansowalo (zeby uniknac rewanzu w grupie).
Ta tabela ma dziesiatki wariantow i nie da sie jej tu w pelni odtworzyc.
Zamiast tego przydzielamy trzecie miejsca do stalych "slotow rankingowych"
(3rd-rank-1 = najlepsze trzecie miejsce, ... 3rd-rank-8 = najslabsze z
awansujacych) - dokladnie odtwarza to, co sie realnie wydarzylo, a dla
hipotetycznych wczesnych dni moze w rzadkich przypadkach skojarzyc druzyny
z tej samej grupy w 1/16 finalu zamiast oficjalnego wyjatku FIFA.
"""

# 16 par 1/16 finalu, indeks = kolejnosc w tej liscie (0-15).
# Etykieta '1A' = zwyciezca grupy A, '2A' = drugie miejsce grupy A,
# '3rd-rank-N' = N-te najlepsze z 8 awansujacych trzecich miejsc.
R32_PAIRS = [
    ("1E", "3rd-rank-7"),   # 0
    ("1I", "3rd-rank-2"),   # 1
    ("2A", "2B"),           # 2
    ("1F", "2C"),           # 3
    ("1C", "2F"),           # 4
    ("2E", "2I"),           # 5
    ("1A", "3rd-rank-4"),   # 6
    ("1L", "3rd-rank-1"),   # 7
    ("2K", "2L"),           # 8
    ("1H", "2J"),           # 9
    ("1D", "3rd-rank-5"),   # 10
    ("1G", "3rd-rank-8"),   # 11
    ("1J", "2H"),           # 12
    ("2D", "2G"),           # 13
    ("1B", "3rd-rank-6"),   # 14
    ("1K", "3rd-rank-3"),   # 15
]

# Kazdy slot 1/8 finalu (0-7) to zwyciezcy dwoch konkretnych meczow 1/16.
R16_SLOTS = [
    (0, 1),
    (2, 3),
    (4, 5),
    (6, 7),
    (8, 9),
    (10, 11),
    (12, 13),
    (14, 15),
]

# Cwiercfinaly - pary indeksow slotow 1/8 finalu (0-7).
QF_SLOTS = [
    (0, 1),
    (4, 5),
    (2, 3),
    (6, 7),
]

# Polfinaly - pary indeksow cwiercfinalow (0-3).
SF_SLOTS = [
    (0, 1),
    (2, 3),
]
