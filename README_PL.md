**Język:** [English](README.md) | Polski

# O projekcie

**Strona projektu:** https://waderlla.github.io/Road_to_the_trophy_2026/

**Droga do Trofeum 2026** to interaktywny projekt analityczny pokazujący, jak w trakcie Mistrzostw Świata w Piłce Nożnej 2026 zmieniają się szanse poszczególnych reprezentacji na zdobycie pucharu.

To nie jest klasyczna tabela wyników. Strona nie pokazuje tylko tego, kto wygrał dany mecz. Jej głównym celem jest odpowiedź na pytanie:

> Kto w danym dniu turnieju ma największą szansę zostać mistrzem świata - i dlaczego?

Projekt łączy dane meczowe, statystyki drużyn, ranking FIFA, terminarz turnieju oraz symulacje komputerowe, aby dzień po dniu pokazywać, jak zmienia się układ sił.

## Co można zobaczyć na stronie?

Na stronie można prześledzić cały turniej dzień po dniu.

Dla wybranej daty dashboard pokazuje m.in.:

- ranking drużyn według szans na mistrzostwo,
- lidera aktualnej prognozy,
- drużyny z największym wzrostem i spadkiem szans,
- wyniki lub zaplanowane mecze danego dnia,
- aktualny etap turnieju,
- drabinkę pucharową,
- historię zmian prawdopodobieństwa,
- szczegółowe dane wybranej reprezentacji.

Po kliknięciu drużyny można zobaczyć jej dodatkowy profil: siłę zespołu, najważniejsze statystyki, prawdopodobnego rywala, szanse dojścia do kolejnych etapów, selekcjonera, kapitana, średni wiek kadry i miejsce w rankingu FIFA.

## Skąd biorą się dane?

Dane nie pochodzą z jednego miejsca. W projekcie użyłam kilku źródeł, bo każde z nich daje inny fragment informacji potrzebny do zbudowania prognozy.

Pierwszym źródłem jest **API-Football** (`https://www.api-football.com/`). Z niego pobierane są przede wszystkim mecze, wyniki, statusy spotkań i podstawowy terminarz. To źródło jest używane w skryptach importujących mecze oraz statystyki meczowe. Z API pochodzą m.in. gole, status meczu oraz statystyki takie jak strzały, strzały celne, posiadanie piłki, podania, faule i kartki.

Drugim źródłem jest **FotMob**, ale nie jako automatyczne API, tylko jako zapisane lokalnie strony HTML. Te pliki są zapisywane ręcznie z przeglądarki i potem przetwarzane przez skrypty projektu. FotMob jest używany w trzech miejscach:

- zapisane strony pojedynczych meczów uzupełniają lub poprawiają wyniki, statusy i statystyki, szczególnie wtedy, gdy API nie ma kompletnych danych;
- zapisana strona terminarza FotMob daje oficjalne daty i godziny przyszłych slotów drabinki pucharowej, nawet zanim znane są drużyny;
- zapisane strony drużyn FotMob dostarczają ranking FIFA, selekcjonerów oraz informacje pomocnicze o kadrach.

Trzecim źródłem pomocniczym jest zapisana strona **Soccer2026 / Bola 2026** (`https://soccer2026.app/pl/schedule`). To z niej można sprawdzić pełny terminarz 104 meczów oraz układ fazy pucharowej. W projekcie jest ona traktowana jako źródło kontrolne dla terminarza i drabinki: pomaga potwierdzić, które sloty fazy pucharowej istnieją, w jakiej kolejności są rozgrywane oraz jakie mają daty i godziny.

Osobną kategorią są **dane wyliczane lokalnie w projekcie**. To nie są dane pobrane z zewnątrz, tylko wartości obliczone na podstawie wcześniejszych informacji. Do tej grupy należą m.in.:

- tabela grupowa,
- kolejność drużyn w grupach,
- drużyny awansujące do fazy pucharowej,
- aktualna drabinka,
- wyeliminowane zespoły,
- dzienne siły drużyn,
- prawdopodobieństwa mistrzostwa po symulacjach.

Wszystkie dane są zapisywane w lokalnej bazie projektu. Dzięki temu dla każdego dnia turnieju można odtworzyć stan wiedzy z tamtego momentu: jakie mecze były już rozegrane, jakie statystyki były znane, kto był jeszcze w turnieju i jak wyglądała prognoza na dalszą część mistrzostw.

## Jak liczone są szanse?

Projekt najpierw ocenia aktualną siłę każdej drużyny. Dopiero potem na podstawie tej siły symuluje możliwy dalszy przebieg turnieju.

Siła drużyny nie jest liczona wyłącznie z wyników. Sam wynik meczu bywa mylący - drużyna może wygrać po jednym szczęśliwym strzale albo przegrać mimo bardzo dobrej gry.

Dlatego model najpierw zamienia surowe statystyki meczowe na sześć ocen drużyny w skali od 0 do 100:

- **atak** - gole, strzały i strzały celne,
- **obronę** - stracone gole, strzały rywala, strzały celne rywala, xG przeciwnika i czyste konta,
- **kontrolę gry** - posiadanie piłki, liczbę podań i celność podań,
- **skuteczność** - gole w stosunku do liczby strzałów i strzałów celnych,
- **dyscyplinę** - faule, żółte kartki i czerwone kartki,
- **formę** - wyniki ostatnich meczów, z większą wagą dla najnowszych spotkań.

Każdy z tych obszarów jest liczony trochę inaczej.

### Atak

Atak nie jest oparty tylko na liczbie bramek. Bramki są ważne, ale bywają losowe. Dlatego model patrzy też na to, czy drużyna regularnie tworzy sytuacje.

W ocenie ataku:

- gole odpowiadają za **50%** oceny,
- wszystkie strzały za **25%**,
- strzały celne za **25%**.

Jeśli drużyna strzela dużo goli i często dochodzi do sytuacji, jej ocena ataku rośnie. Jeśli wygrała przypadkowo, oddając bardzo mało strzałów, model nie podnosi jej siły aż tak mocno.

### Obrona

Obrona też nie jest liczona wyłącznie z liczby straconych goli. Drużyna może nie stracić bramki, ale pozwolić przeciwnikowi na wiele dobrych okazji.

W ocenie obrony:

- stracone gole odpowiadają za **35%**,
- xG przeciwnika za **20%**,
- strzały celne przeciwnika za **20%**,
- wszystkie strzały przeciwnika za **15%**,
- czyste konta za **10%**.

Dzięki temu model rozróżnia drużynę, która naprawdę dobrze broni, od drużyny, która tylko miała szczęście w jednym meczu.

### Kontrola gry

Kontrola gry opisuje, czy drużyna potrafi utrzymywać piłkę i zarządzać tempem meczu.

W ocenie kontroli:

- posiadanie piłki odpowiada za **40%**,
- celność podań za **30%**,
- liczba podań za **30%**.

Ta część modelu premiuje drużyny, które nie tylko bronią i kontratakują, ale potrafią dłużej prowadzić grę.

### Skuteczność

Skuteczność mówi, jak dobrze drużyna zamienia sytuacje na gole.

Model patrzy na:

- gole w stosunku do wszystkich strzałów,
- gole w stosunku do strzałów celnych.

Obie części mają po **50%** wagi.

Tutaj jest jednak ważne zabezpieczenie: skuteczność jest **wygładzana**, czyli model nie ufa w 100% małej próbce danych.

Najprościej mówiąc: gdy drużyna oddała bardzo mało strzałów, jej skuteczność nie jest liczona wyłącznie z tych kilku akcji. Model dokłada do obliczenia pewną liczbę „wirtualnych” strzałów o typowej, przeciętnej skuteczności dla piłki nożnej.

W projekcie wygląda to tak:

- dla skuteczności ze wszystkich strzałów model zakłada typową skuteczność **11%**,
- dla skuteczności ze strzałów celnych model zakłada typową skuteczność **30%**,
- do obu obliczeń dokładane jest **15 wirtualnych strzałów**.

Czyli zamiast liczyć tylko:

```text
gole / strzały
```

model liczy:

```text
(gole + 15 × typowa skuteczność) / (strzały + 15)
```

Przykład: jeśli drużyna oddała 2 strzały i zdobyła 2 gole, surowa skuteczność wyniosłaby:

```text
2 / 2 = 100%
```

Ale po wygładzeniu dla wszystkich strzałów model liczy:

```text
(2 + 15 × 0.11) / (2 + 15)
= 3.65 / 17
= około 21.5%
```

To nadal jest bardzo dobra skuteczność, ale już nie absurdalne 100%. Dzięki temu jeden dziwny mecz nie robi z drużyny automatycznie najbardziej skutecznej reprezentacji turnieju.

Im więcej drużyna oddaje prawdziwych strzałów, tym mniejsze znaczenie mają te „wirtualne” strzały. Na początku turnieju wygładzenie mocno stabilizuje ocenę, a później realne dane coraz bardziej przejmują kontrolę.

Na końcu oba wygładzone wskaźniki - skuteczność ze wszystkich strzałów i skuteczność ze strzałów celnych - są porównywane z wynikami pozostałych drużyn, przeliczane do skali **0–100** i łączone po połowie.

### Dyscyplina

Dyscyplina ma mniejszą wagę, ale nadal wpływa na ocenę drużyny.

Model bierze pod uwagę:

- faule,
- żółte kartki,
- czerwone kartki.

Czerwona kartka jest traktowana mocniej niż żółta. Dyscyplina nie decyduje sama o sile drużyny, ale może lekko obniżyć ocenę zespołu, który gra bardzo ostro i ryzykownie.

### Forma

Forma patrzy na ostatnie mecze drużyny.

Najnowszy mecz waży najwięcej, starsze mniej. Model uwzględnia wynik, różnicę bramek i jakość rywala.

Chodzi o to, żeby zauważyć, że drużyna może rosnąć albo słabnąć w trakcie turnieju, ale jednocześnie nie przereagować na jeden przypadkowy wynik.

### Jak model porównuje drużyny?

Surowe statystyki mają różne skale. Gole, strzały, posiadanie i kartki nie dają się bezpośrednio porównać.

Dlatego każda statystyka jest przeliczana na skalę 0–100 względem pozostałych drużyn w turnieju.

W praktyce:

- wynik około **50** oznacza poziom przeciętny,
- wynik powyżej **50** oznacza wynik lepszy od średniej,
- wynik poniżej **50** oznacza wynik słabszy od średniej.

Model nie używa prostego „najlepszy = 100, najgorszy = 0”, bo to mogłoby sztucznie powiększać małe różnice. Zamiast tego bierze pod uwagę, jak bardzo dana drużyna odbiega od średniej.

### Jak z tych ocen powstaje jedna siła drużyny?

Po policzeniu sześciu obszarów model składa je w jedną wartość: **siłę drużyny**.

Wagi są następujące:

```text
30% - atak
30% - obrona
15% - skuteczność
15% - kontrola gry
 5% - forma
 5% - dyscyplina
```

Najbardziej liczą się atak i obrona, bo one najbezpośredniej wpływają na wynik meczu. Skuteczność i kontrola gry są ważne, ale pomocnicze. Forma i dyscyplina mają mniejszą wagę, żeby model nie przesadzał po jednym nietypowym meczu.

### Dlaczego ranking FIFA jest używany na początku?

Na początku turnieju nie ma jeszcze statystyk z meczów mundialu. Gdyby model niczego nie wiedział o drużynach, wszystkie reprezentacje zaczęłyby z podobną siłą, co byłoby nieprawdziwe.

Dlatego przed pierwszymi meczami model używa punktów rankingu FIFA jako punktu startowego.

Oznacza to, że mocniejsze reprezentacje zaczynają trochę wyżej, a słabsze trochę niżej. Ranking FIFA nie jest jednak traktowany jako prawda absolutna. Jest tylko początkową oceną, która z każdym kolejnym meczem ma coraz mniejsze znaczenie.

Można to rozumieć tak:

- przed pierwszym meczem model mocniej ufa rankingowi FIFA,
- po kilku meczach coraz bardziej ufa realnym wynikom i statystykom z turnieju,
- im więcej danych z mundialu, tym mniejszy wpływ ma punkt startowy.

To zabezpiecza model przed dwoma błędami: przed udawaniem, że wszystkie drużyny są na starcie równe, oraz przed przesadnym reagowaniem na jeden przypadkowy wynik.

## Przyjęte parametry modelu

W projekcie są liczby, które nie pochodzą bezpośrednio z API. Są to **parametry modelu**, czyli świadomie przyjęte ustawienia. Każdy taki parametr ma określoną rolę: stabilizuje obliczenia, ogranicza skrajne wyniki albo mówi modelowi, jak mocno ufać danej informacji.

Dokładne wyliczenia i uzasadnienie każdej z tych liczb na realnych danych projektu znajdują się w [`data/model_parameter_checks.md`](data/model_parameter_checks.md).

To ważne rozróżnienie:

- API dostarcza dane, np. gole, strzały, kartki, posiadanie piłki, ranking FIFA,
- model decyduje, jak te dane przeliczyć na ocenę drużyny,
- parametry mówią modelowi, jak ostro albo łagodnie ma reagować.

### Skala 0–100 i punkt neutralny 50

Oceny drużyn są pokazywane w skali **0–100**.

W tej skali:

- **50** oznacza poziom przeciętny względem innych drużyn,
- wynik powyżej **50** oznacza wynik lepszy od średniej,
- wynik poniżej **50** oznacza wynik słabszy od średniej.

To nie jest ocena szkolna ani procent wykonania zadania. To uproszczona skala porównawcza.

Źródłem metody jest standaryzacja statystyczna, czyli porównywanie wyniku z jego średnią i odchyleniem standardowym. Taki wynik nazywa się **z-score**: [Standard score](https://en.wikipedia.org/wiki/Standard_score).

W projekcie z-score jest potem przeliczany na czytelniejszą skalę 0–100. Środek skali ustawiono na 50, bo dzięki temu łatwo odczytać, czy drużyna jest powyżej, czy poniżej średniej.

### Zakres wpływu rankingu FIFA: 35–72

Ranking FIFA jest używany jako punkt startowy przed pierwszymi meczami.

Model nie pozwala jednak, żeby ranking FIFA dał drużynie od razu skrajnie niską albo skrajnie wysoką ocenę. Dlatego punkt startowy z rankingu FIFA jest ograniczony do zakresu:

```text
minimum: 35
maksimum: 72
```

Dlaczego tak?

Bo ranking FIFA ma pomóc ustawić rozsądny start, ale nie może przesądzać całego turnieju. Gdyby najlepsze drużyny zaczynały blisko 100, a najsłabsze blisko 0, model zbyt mocno ufałby rankingowi sprzed turnieju. Zakres 35–72 zostawia różnicę między mocnymi i słabszymi reprezentacjami, ale nadal daje każdej drużynie miejsce na zmianę oceny po realnych meczach.

Źródłem samego użycia rankingu FIFA jest oficjalna idea rankingu: porównywanie siły reprezentacji narodowych na podstawie wyników meczów. Opis rankingu i jego obecnego systemu punktowego można znaleźć tutaj: [FIFA Men's World Ranking](https://en.wikipedia.org/wiki/FIFA_Men%27s_World_Ranking).

Liczby **35** i **72** są parametrami tego projektu. Nie pochodzą z FIFA. Zostały przyjęte po to, żeby ranking był punktem startowym, a nie wyrokiem.

### Szerokość wpływu rankingu FIFA: 8 punktów za jedno odchylenie

W projekcie ranking FIFA jest najpierw porównywany ze średnią punktów rankingowych wszystkich drużyn. Potem model sprawdza, jak bardzo dana reprezentacja odbiega od tej średniej.

Przyjęto, że jedno odchylenie od średniej przesuwa ocenę startową o około **8 punktów** na skali 0–100.

Dlaczego 8?

Bo to umiarkowana wartość. Ranking FIFA wpływa na start, ale nie dominuje całej oceny. Mocna drużyna zaczyna wyżej, ale nie tak wysoko, żeby słabsza drużyna nie mogła jej dogonić po dobrych meczach.

Źródłem metody jest z-score, czyli mierzenie odległości od średniej w odchyleniach standardowych: [Standard score](https://en.wikipedia.org/wiki/Standard_score).

Liczba **8** jest parametrem projektu. Oznacza siłę przełożenia rankingu FIFA na skalę modelu.

### Przyciąganie do punktu startowego: 3 wirtualne mecze

Na początku turnieju realnych danych jest mało. Po jednym meczu model mógłby zbyt gwałtownie zmienić ocenę drużyny.

Dlatego ocena po pierwszych spotkaniach jest przyciągana do punktu startowego z rankingu FIFA. W kodzie odpowiada za to parametr:

```text
3 wirtualne mecze
```

Można to rozumieć tak: zanim drużyna rozegra większą liczbę meczów, model nadal zachowuje w pamięci jej ocenę startową.

Dlaczego 3?

Bo faza grupowa składa się z trzech meczów. To naturalna jednostka dla turnieju: po jednym meczu model powinien być ostrożny, po dwóch nadal częściowo ostrożny, a po trzech ma już sensowną porcję danych z mundialu.

Metodologicznie jest to podobne do wygładzania przez pseudoobserwacje, czyli dodawania „wirtualnych” obserwacji do małej próbki danych: [Additive smoothing](https://en.wikipedia.org/wiki/Additive_smoothing).

Liczba **3** jest parametrem projektu. Jej zadaniem jest ograniczenie przesadnej reakcji modelu na pojedynczy mecz.

### Skuteczność strzałów: 11% i 30%

Skuteczność jest wygładzana, żeby mała liczba strzałów nie dawała absurdalnych wyników.

Przyjęto dwa punkty odniesienia:

```text
11% - bazowa skuteczność wszystkich strzałów
30% - bazowa skuteczność strzałów celnych
```

Te liczby nie są pobierane z API. Są parametrami modelu.

Dlaczego takie?

Bo są konserwatywnym punktem startowym:

- **11%** oznacza mniej więcej 1 gola na 9 strzałów,
- **30%** oznacza mniej więcej 1 gola na 3 strzały celne.

Chodzi o to, żeby model miał rozsądny punkt odniesienia, zanim zbierze więcej danych z turnieju.

Źródłem idei jest analityka xG, w której każdy strzał można traktować jako prawdopodobieństwo zdobycia gola: [Expected goals](https://en.wikipedia.org/wiki/Expected_goals).

Liczby **11%** i **30%** są parametrami projektu. W razie dalszego rozwoju można je skalibrować na dużym historycznym zbiorze meczów.

### Skuteczność strzałów: 15 wirtualnych strzałów

Do skuteczności model dodaje **15 wirtualnych strzałów**.

To oznacza, że drużyna z bardzo małą liczbą strzałów nie jest oceniana wyłącznie na podstawie kilku akcji.

Dlaczego 15?

Bo to umiarkowana siła wygładzenia. Taka liczba wystarcza, żeby jeden mecz nie wywrócił oceny skuteczności, ale nie jest tak duża, żeby realne strzały drużyny przestały mieć znaczenie.

Źródłem metody jest additive smoothing, czyli dodawanie pseudoobserwacji do małej próbki danych: [Additive smoothing](https://en.wikipedia.org/wiki/Additive_smoothing).

Liczba **15** jest parametrem projektu. Określa, jak mocno model stabilizuje skuteczność na początku.

### Forma: 3 ostatnie mecze i wagi 50% / 30% / 20%

Forma drużyny jest liczona z maksymalnie **3 ostatnich meczów**.

Ich wagi są następujące:

```text
50% - najnowszy mecz
30% - poprzedni mecz
20% - trzeci najnowszy mecz
```

Dlaczego tak?

Bo forma ma pokazywać aktualny trend, a nie całą historię drużyny. Najnowszy mecz mówi najwięcej o bieżącej dyspozycji, ale starsze mecze nadal pomagają odróżnić prawdziwy trend od jednorazowego przypadku.

Liczba **3** pasuje też do struktury turnieju, bo faza grupowa ma trzy mecze. Dzięki temu model może ocenić krótką, turniejową formę drużyny, zamiast mieszać ją z bardzo starą historią.

To jest parametr projektu. Nie pochodzi z zewnętrznej tabeli. Jest decyzją metodologiczną: forma ma być krótka, aktualna i ostrożna.

### Jakość rywala: ograniczenie mnożnika od 0.4 do 2.5

Model bierze pod uwagę, z kim drużyna grała.

Gol strzelony mocnej obronie jest cenniejszy niż gol strzelony bardzo słabej obronie. Podobnie gol stracony przeciwko słabemu atakowi jest bardziej obciążający niż gol stracony przeciwko bardzo mocnemu atakowi.

Żeby ten efekt nie był przesadzony, mnożnik jakości rywala ma ograniczenia:

```text
minimum: 0.4
maksimum: 2.5
```

Dlaczego tak?

Bo bez ograniczeń jeden skrajny wynik albo jedna bardzo niska ocena przeciwnika mogłyby sztucznie wykrzywić cały model. Limity pozwalają uwzględnić jakość rywala, ale chronią przed absurdami.

Liczby **0.4** i **2.5** są parametrami projektu. Ich rola jest techniczna: zabezpieczają model przed skrajnymi mnożnikami.

### Różnica bramek w formie: podział przez 3

W ocenie formy model bierze pod uwagę nie tylko zwycięstwo, remis albo porażkę, ale też różnicę bramek.

Różnica bramek jest dzielona przez **3** i ograniczana do zakresu od -1 do 1.

Dlaczego 3?

Bo zwycięstwo trzema golami jest traktowane jako bardzo mocny sygnał, ale wygrana pięcioma albo sześcioma golami nie powinna zwiększać formy bez końca. Model uznaje więc, że różnica około trzech bramek wystarcza, żeby uznać mecz za wyraźną dominację.

Liczba **3** jest parametrem projektu. Ogranicza wpływ bardzo wysokich wyników.

### Model bramkowy: rozkład Poissona

Do prognozowania liczby goli w meczu używany jest rozkład Poissona.

To popularny rozkład prawdopodobieństwa dla liczby zdarzeń w określonym czasie, np. liczby goli w meczu. Źródło metody: [Poisson distribution](https://en.wikipedia.org/wiki/Poisson_distribution).

Model najpierw szacuje oczekiwaną liczbę goli każdej drużyny, a potem sprawdza prawdopodobieństwa różnych wyników, np. 0:0, 1:0, 1:1, 2:1.

### Maksymalnie 10 goli w modelu meczu

Przy liczeniu wyników pojedynczego meczu model sprawdza wyniki od 0 do **10** goli dla każdej drużyny.

Dlaczego 10?

Bo wyniki powyżej 10 goli jednej drużyny są w piłce nożnej skrajnie rzadkie. Uwzględnianie ich prawie nie zmieniłoby prawdopodobieństw, a zwiększyłoby liczbę obliczeń.

Liczba **10** jest parametrem technicznym projektu. Oznacza praktyczne obcięcie bardzo mało prawdopodobnego ogona rozkładu.

### Średnia bramek: awaryjna wartość 1.3

Model używa średniej liczby goli w turnieju jako punktu odniesienia dla prognozy meczu.

Jeśli w danym momencie nie ma jeszcze wystarczających danych z turnieju, używana jest wartość awaryjna:

```text
1.3 gola na drużynę
```

Dlaczego 1.3?

Bo jest to ostrożny punkt startowy dla piłki nożnej: około 2.6 gola łącznie w meczu. Nie jest to dana z API ani z FIFA. To parametr projektu używany tylko wtedy, gdy brakuje jeszcze realnej średniej z turnieju.

Gdy pojawiają się dane z rozegranych meczów, model używa już średniej turniejowej.

### Liczba symulacji: 10 000

Cały turniej jest symulowany **10 000 razy**.

Dlaczego 10 000?

Bo metoda Monte Carlo działa przez wielokrotne losowanie możliwych scenariuszy. Im więcej symulacji, tym stabilniejszy wynik, ale też dłuższy czas obliczeń.

10 000 to praktyczny kompromis:

- wynik jest dużo stabilniejszy niż przy kilkuset symulacjach,
- obliczenia nadal da się wykonać lokalnie,
- procenty są wystarczająco czytelne dla użytkownika strony.

Źródłem metody jest symulacja Monte Carlo, czyli szacowanie prawdopodobieństw przez wiele losowych powtórzeń: [Monte Carlo method](https://en.wikipedia.org/wiki/Monte_Carlo_method).

Liczba **10 000** jest parametrem projektu. Określa dokładność i koszt obliczeń.

## Dlaczego szanse zmieniają się każdego dnia?

Każdy mecz zmienia sytuację.

Wygrana może zwiększyć szanse drużyny, ale nie zawsze w oczywisty sposób. Liczy się także:

- z kim drużyna zagrała,
- jakim wynikiem zakończył się mecz,
- jak wyglądały statystyki,
- czy drużyna awansowała,
- na kogo może trafić w kolejnej rundzie,
- jak zmieniła się drabinka.

Dlatego czasem drużyna może wygrać mecz, ale jej szanse na mistrzostwo wzrosną tylko nieznacznie. Innym razem wynik innego spotkania może otworzyć łatwiejszą ścieżkę i poprawić sytuację zespołu, który tego dnia wcale nie grał.

## Czym jest symulacja turnieju?

Po przeliczeniu siły drużyn projekt symuluje możliwy dalszy przebieg mistrzostw.

Komputer rozgrywa resztę turnieju tysiące razy. W każdej symulacji możliwe są inne wyniki przyszłych meczów, inne awanse i inna drabinka.

Jeśli dana reprezentacja wygrywa mistrzostwo w wielu takich symulacjach, jej szansa na tytuł jest wysoka. Jeśli wygrywa rzadko, jej szansa jest niska.

Przykład:

> Jeżeli drużyna wygrywa 1900 z 10 000 symulacji, model przypisuje jej około 19% szans na mistrzostwo.

To oznacza, że projekt nie próbuje wskazać jednej pewnej przyszłości. Pokazuje raczej, które scenariusze są najbardziej prawdopodobne na podstawie dostępnych danych.

## Jak prognozowane są pojedyncze mecze?

Do szacowania wyników pojedynczych spotkań używany jest prosty model bramkowy.

Model porównuje:

- siłę ataku jednej drużyny,
- jakość obrony drugiej drużyny,
- średnią liczbę goli w turnieju.

Na tej podstawie szacuje, ile goli może zdobyć każda ze stron, a następnie wylicza prawdopodobieństwo wygranej, remisu i porażki.

Dlatego przy zaplanowanych meczach można zobaczyć prognozę w stylu:

```text
Francja 63% / remis 20% / Kolumbia 17%
```

Nie jest to pewnik. To szacowana szansa wyniku po 90 minutach, wynikająca z aktualnej oceny obu drużyn.

## Co oznaczają procenty?

Procenty na stronie oznaczają prawdopodobieństwo w modelu.

Jeśli drużyna ma:

```text
19% szans na mistrzostwo
```

to znaczy, że w symulacjach komputerowych wygrywała cały turniej w około 19% przypadków.

Jeśli przy meczu widzimy:

```text
48% / remis 24% / 28%
```

to oznacza szacowaną szansę wyniku po 90 minutach:

- 48% - wygrana pierwszej drużyny,
- 24% - remis,
- 28% - wygrana drugiej drużyny.

## Dlaczego model nie zawsze zgadza się z intuicją?

Model patrzy szerzej niż tylko na ostatni wynik.

Bierze pod uwagę:

- siłę drużyny,
- jakość rywali,
- dotychczasowe statystyki,
- możliwą ścieżkę w drabince,
- prawdopodobnych przeciwników w kolejnych rundach.

Dlatego drużyna z niższą pozycją w rankingu może czasem mieć korzystną ścieżkę i większe szanse, niż sugerowałaby sama „siła na papierze”. Z kolei bardzo mocna drużyna może mieć trudniejszą drabinkę i przez to niższe prawdopodobieństwo końcowego triumfu.

## Co pokazuje oś czasu?

Oś czasu pozwala cofnąć się do dowolnego dnia turnieju.

Dla dni przeszłych strona pokazuje stan modelu z tamtego dnia - tak, jakbyśmy wtedy nie znali jeszcze przyszłych wyników.

Dla dni przyszłych strona pokazuje ostatnią dostępną prognozę oraz terminarz zaplanowanych spotkań. Projekt nie udaje, że zna przyszłe wyniki.

## Czy to jest model bukmacherski?

Nie.

Projekt ma charakter analityczny i edukacyjny. Jego celem jest pokazanie, jak można połączyć dane sportowe, prosty model statystyczny i symulację turnieju w interaktywny dashboard.

Model nie uwzględnia wszystkich czynników, które mogłyby mieć znaczenie w profesjonalnym modelu bukmacherskim, takich jak:

- kontuzje,
- przewidywane składy,
- zmęczenie zawodników,
- styl konkretnego przeciwnika,
- decyzje taktyczne,
- informacje z rynku kursów.

Dlatego procenty należy traktować jako prognozę analityczną, a nie gwarancję wyniku.

## Najważniejsze ograniczenia

Każdy model jest uproszczeniem rzeczywistości.

W tym projekcie najważniejsze ograniczenia to:

- dane pochodzą z kilku różnych źródeł,
- część informacji wymaga ręcznego importu,
- dogrywki i rzuty karne są uproszczone,
- ranking FIFA jest tylko punktem startowym, a nie pełnym opisem siły drużyny,
- model nie zna kontuzji ani składów meczowych.

Mimo tych ograniczeń projekt pozwala zobaczyć coś, czego nie pokazuje zwykła tabela wyników: jak każdy kolejny mecz wpływa na szanse całego turnieju.

## Po co powstał ten projekt?

Projekt powstał jako połączenie analizy danych, modelowania statystycznego i wizualizacji sportowej.

Chciałam pokazać, że dane piłkarskie można przedstawić nie tylko jako wyniki i tabele, ale jako dynamiczną historię zmieniających się szans.

W trakcie turnieju każda drużyna ma swoją drogę do trofeum. Ta strona pokazuje, jak ta droga zmienia się dzień po dniu.
