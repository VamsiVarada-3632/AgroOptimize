"""TNAU 'Crop Production Guide - Agriculture' - full agronomy master (verbatim quotes).

Source (official, Tamil Nadu Agricultural University): https://agritech.tnau.ac.in/pdf/AGRICULTURE.pdf  (460 PDF pages;
printed page = pdf page - 12). Text read from the PDF with pdf.js through the browser pane (the shell cannot reach the host).
Every non-NULL text value is a verbatim quote from the PDF text layer (spacing of 'P 2 O 5' etc. as printed);
`evidence_pages` maps each populated field to the pdf page it came from. A field the guide does not give for the crop
is NULL (None). Nothing is estimated. Water requirement (mm) and soil pH ranges are not given for these crops in the guide.
"""
from __future__ import annotations

SOURCE_URL = "https://agritech.tnau.ac.in/pdf/AGRICULTURE.pdf"
RETRIEVED_AT = "2026-11-12"
PRINTED_OFFSET = 12

TEXT_FIELDS = ["season", "duration", "water_requirement", "irrigation_frequency", "recommended_soil", "soil_ph", "seed_rate",
               "spacing", "fertilizer_schedule", "harvest_time", "expected_yield", "suitable_districts", "suitable_rainfall"]
COLUMNS = ["crop", "guide_section", *TEXT_FIELDS, "n_kg_ha", "p_kg_ha", "k_kg_ha", "npk_by_condition", "extraction_notes", "evidence_pages", "source_url", "retrieved_at"]

_NE = "Vellore, Thiruvannamalai, Cuddalore, Villupuram, Thiruvallur and Kancheepuram"
_NW = "Salem, Namakkal, Dharmapuri and Krishnagiri"
_W = "Coimbatore, Erode, Karur, Tiruppur, Theni and Dindigul"
_CD = "Trichy, Thanjavur, Thiruvarur, Nagapattinam, Pudukkottai Perambalur and Ariyalur"
_SZ = "Madurai, Sivagangai, Virudhunagar, Ramanathapuram Tirunelveli and Thoothukudi"
_MERGE = "(printed in one merged cell with the North Eastern Zone row)"

SAME_AS_SEASON = "@SEASON"  # district lists for this crop are printed inside the season/pattam table; resolved by build

RECORDS = [
    dict(
        crop="Sorghum", guide_section="MILLETS / 1. Sorghum (printed p65-80)",
        season=f"North Eastern Zone: Jan-Feb (Thaipattam) April - May ( Chithiraipattam) June-July (Adipattam) Sep-Oct (Puratassipattam); North Western Zone and Western Zone: {_MERGE}; Cauvery Delta Zone: Jan-Feb (Thaipattam) April - May ( Chithiraipattam) June-July (Adipattam); Southern Zone: Jan-Feb (Thaipattam) April - May ( Chithiraipattam) Sep-Oct (Puratassipattam)",
        duration="Duration (Days) 95-100 95-105",
        irrigation_frequency="Stages No. of Irrigation Days of Transplanting / Sowing of Crop Transplanted Direct Sown Light Soils i. Irrigate for germination 1 1 st day 1 st day or establishment 2 4 th day 4 th day Regulate irrigation 1 15 th day 15 th day during vegetative phase 2 28 th day 28 th day iii. Flowering phase (copious irrigation) 1 40 th day 40 th day 2 52 nd day 52 nd day 3 .. 64 th day iv. Maturity phase (Control irrigation) 1 65 th day 76 th day 2 .. 88 th day v. Stop irrigation thereafter .. .. Heavy soils i. Irrigate for germination 1 1 st day 1 st day or establishment 2 4 th day 4 th day ii. Regulate irrigation 1 17 th day 17 th day during vegetative phase 2 30 th day 30 th day iii. Flowering phase (give 1 40 th day 45 th day copious irrigation) 2 52 nd day 60 th day 3 .. 75 th day iv. Maturity phase (Control irrigation) 1 72 nd day 90 th day v. Stop irrigation thereafter",
        seed_rate="In the case of pure crop of sorghum, maintain the seed rate at 10kg/ha.",
        spacing="Spacing: 45 x 15 cm Population: 15/m 2",
        fertilizer_schedule="Apply N @ 50:25:25 % at 0, 15 and 30 DAS and full dose of P 2 O 5 and K 2 O basally before sowing and if basal application is not possible the same could be top dressed within 24 hours.",
        harvest_time="When the crop matures the leaves turn yellow and present a dried up appearance. The grains are hard and firm. At this stage, harvest the crop by cutting the earheads separately.",
        expected_yield="Grain yield (kg/ha) Rainfed 3123 2400 Irrigated - 3360",
        suitable_districts=f"North Eastern Zone: {_NE}; North Western Zone: {_NW}; Western Zone: {_W}; Cauvery Delta Zone: {_CD}; Southern Zone: {_SZ}",
        suitable_rainfall="Rainfall mm 400 - 600",
        evidence_pages="season:77;duration:77;irrigation_frequency:84;seed_rate:82;spacing:82;fertilizer_schedule:81;harvest_time:85;expected_yield:78;suitable_districts:77;suitable_rainfall:77",
    ),
    dict(
        crop="Cumbu", guide_section="MILLETS / 2. Cumbu (printed p81-91)",
        season=f"North Eastern Zone: Jan-Feb (Thaipattam) April - May ( Chithiraipattam) June-July (Adipattam) Sep-Oct Puratassipattam); North Western Zone and Western Zone: {_MERGE}; Cauvery Delta Zone: Jan-Feb (Thaipattam) April - May ( Chithiraipattam) June-July (Adipattam); Southern Zone: Jan-Feb (Thaipattam) April - May ( Chithiraipattam) Sep-Oct (Puratassipattam)",
        duration="Duration (Days) 75-80 85-90",
        seed_rate="place 5 kg of seed, allowing them to fall 4 - 5 cm apart (Use higher seed rate of 5 kg to offset mortality). The optimum population should be 1,45,000 per ha. Use increased seed rate upto 12.5 kg per hectare in shoot fly endemic area",
        spacing="Adopt the spacing of 45 x 15 cm for all varieties / hybrids. If pulse is intercropped, adopt a spacing of 30 x 15 cm for cumbu and 30 x 10 cm for pulses.",
        fertilizer_schedule="Apply the recommended N in three splits as 25:50:25 per cent at 0.15 and 30 DAS and full dose of phosphorus and potassium basally.",
        harvest_time="SYMPTOMS OF MATURITY i. Leaves will turn yellow and present a dried appearance. ii. Grains will be hardened. HARVESTING i. Cut the earheads separately. ii. Cut the straw after a week, allowing it to dry and stack it in the field till it can be transported.",
        expected_yield="Grain yield (kg/ha) Rainfed 2707 2923 Irrigated 3728 3526",
        suitable_districts=f"North Eastern Zone: Vellore, Thiruvannamalai, Cuddalore, Villupuram, Thiruvallur, Kancheepuram; North Western Zone: Salem, Namakkal, Dharmapuri, Krishnagiri; Western Zone: {_W}; Cauvery Delta Zone: {_CD}; Southern Zone: {_SZ}",
        suitable_rainfall="Rainfall mm 250 - 350",
        evidence_pages="season:93;duration:93;seed_rate:98;spacing:98;fertilizer_schedule:96;harvest_time:99;expected_yield:93;suitable_districts:93;suitable_rainfall:93",
    ),
    dict(
        crop="Ragi", guide_section="MILLETS / 3. Ragi (printed p92-102)",
        season="North Eastern, North Western, Western and Cauvery Delta Zones: Dec-Jan (Marghazipattam) April-May (Chithiraipattam) June-July (Adipattam); Southern Zone (Madurai and Theni): Dec-Jan (Marghazipattam) April-May (Chithiraipattam) Sep-Oct (Puratassipattam); Southern Zone (Sivagangai, Virudhunagar, Ramanathapuram, Tirunelveli and Thoothukudi): Sep-Oct (Puratassipattam); Hilly and High Altitude Zone (Ooty): Dec-Jan (Marghazipattam) June-July (Adipattam) Sep-Oct (Puratassipattam)",
        duration="Duration (days) 115 105-110 120 – 125",
        seed_rate="the recommended seed rate is 10 kg/ha",
        spacing="Adopt a spacing of 30x10 cm for planting. Adopt 22.5 x 10 cm spacing for direct sowing.",
        fertilizer_schedule="Apply half the dose of N and full dose of P 2 O 5 basally before sowing and the remaining 50% in two equal splits at 25-30 and 40-45 days after sowing is recommended.",
        harvest_time="Ragi crop does not mature uniformly and hence the harvest is to be taken up in two stages. ii. When the earhead on the main shoot and 50% of the earheads on the crop turn brown, the crop is ready for the first harvest.",
        expected_yield="Grain yield (kg/ha) Irrigated -- 2892 3461 Rainfed 2527 2794 2950",
        suitable_districts="North Eastern Zone: Vellore, Thiruvannamalai, Cuddalore, Villupuram, Thiruvallur and Kancheepuram; North Western Zone: Salem, Namakkal, Dharmapuri and Krishnagiri; Western Zone: Coimbatore, Erode, Karur, Tiruppur and Dindigul; Cauvery Delta Zone: Trichy, Thanjavur, Thiruvarur, Nagapattinam, Pudukkottai, Perambalur and Ariyalur; Southern Zone: Madurai and Theni; Sivagangai, Virudhunagar, Ramanathapuram, Tirunelveli and Thoothukudi; Hilly and High Altitude Zone: Ooty",
        suitable_rainfall="Rainfall mm 500 - 1000",
        evidence_pages="season:104;duration:104;seed_rate:111;spacing:108;fertilizer_schedule:107;harvest_time:109-110;expected_yield:105;suitable_districts:104;suitable_rainfall:104",
    ),
    dict(
        crop="Maize", guide_section="MILLETS / 4. Maize (printed p103-116)",
        season=f"North Eastern Zone: Jan-Feb (Thaipattam) April - May Chithiraipattam) June-July (Adipattam) Sep-Oct (Puratassipattam); North Western Zone and Western Zone: {_MERGE}; Cauvery Delta Zone: Jan-Feb (Thaipattam) April - May Chithiraipattam) June-July (Adipattam); Southern Zone (Madurai and Virudhunagar): Jan-Feb (Thaipattam) June-July (Adipattam) Sep-Oct(Puratassipattam); Southern Zone (Sivagangai, Ramanathapuram, Tirunelveli and Thoothukudi): Sep-Oct(Puratassipattam); High rainfall zone (Kanyakumari) and Hilly and High Altitude Zone (Ooty): Jan-Feb (Thaipattam) June-July (Adipattam) Sep-Oct(Puratassipattam)",
        duration="Duration (days) 110 85 – 95",
        irrigation_frequency="WATER MANAGEMENT Maize crop is sensitive to both moisture stress and excessive moisture, hence regulate irrigation according to the requirement. Ensure optimum moisture availability during the most critical phase (45 to 65 days after sowing); otherwise yield will be reduced by a considerable extent.",
        seed_rate="adopt the seed rate of 20 kg/ha for CO 1 and TNAU Maize Hybrid CO 6 and 25 kg /ha for COBC 1.",
        spacing="Adopt a spacing of 25 cm between plants in the rows which are 60 cm apart.",
        fertilizer_schedule="Apply half of N and full dose of P 2 O 5 and K 2 O with enriched FYM as basal along with Azospirillum (10 packets/ha). Top dress remaining half of N at tasseling.",
        harvest_time="The sheath covering the cob will turn yellow and dry at maturity. The seeds become fairly hard and dry. At this stage the crop is ready for harvest",
        expected_yield="Grain yield (kg/ha) Irrigated 7600 Rainfed 5500 5500",
        suitable_districts=f"North Eastern Zone: Vellore, Thiruvannamalai, Cuddalore, Villupuram, Thiruvallur, Kancheepuram; North Western Zone: {_NW}; Western Zone: {_W}; Cauvery Delta Zone: {_CD}; Southern Zone: Madurai and Virudhunagar; Sivagangai, Ramanathapuram, Tirunelveli and Thoothukudi; High rainfall zone: Kanyakumari; Hilly and High Altitude Zone: Ooty",
        suitable_rainfall="Rainfall mm 500 - 750",
        evidence_pages="season:115;duration:116;irrigation_frequency:121;seed_rate:119;spacing:119;fertilizer_schedule:123;harvest_time:123;expected_yield:116;suitable_districts:115;suitable_rainfall:115",
    ),
]

RECORDS += [
    dict(
        crop="Redgram", guide_section="PULSES / 1. Redgram (printed p125-133)",
        season="Vaigasi Pattam (May-June) Krishnagiri, Dharmapuri, Salem, Erode, Coimbatore Dindigul, Theni and Madurai CO(Rg) 7, CO 8, CO 9; Adi/Avanipattam (June - August) Vellore, Thiruvannamalai, Salem, Namakal, Perumbalur, Ariyalur, Madurai, Dindigul, Theni, Pudukkottai and Sivaganga June 15th to July 15th sowing CO 8, CO 9; Purattasipattam (September – October) Vellore, Tiruvannamalai, Dharmapuri, Salem, Namakkal, Erode, Coimbatore, Madurai, Dindigul, Theni Pudukkottai, Sivagangai, Perumbalur, Ariyalur Co (Rg) 7 and VBN(Rg) 3; Markazhipattam (Winter Irrigated) All districts except The Nilgiris and Kanyakumari Co (Rg) 7 and VBN(Rg) 3; Chithiraipattam (Summer Irrigated) All districts except The Nilgiris and Kanyakumari; Wetland bunds Co (Rg) 7 and VBN(Rg) 3 BSR 1",
        duration="Duration (days) 120-130 100-105 Perennial",
        seed_rate="SEED RATE System Long duration Short duration Low Fertility High Fertility Low Fertility High Fertility Sole Crop 8 5 13 10 Mixed Crop 3 3 5 5 Bund Crop 50 g / 100 meter Long duration varieties: CO 6, CO 8, Vamban 2, LRG 41 Short duration varieties : CO (Rg) 7, VBN (Rg) 3 Bund Crop : BSR 1",
        spacing="Variety Pure crop Mixed crop Low fertility High fertility CO(Rg) 7 45 cm x 30 cm 60 cm x 30 cm 120 cm x 30 cm Vamban (Rg) 3, APK 1 45 cm x 20 cm 60 cm x 20 cm 120 cm x 30 cm CO 6, CO 8, Vamban 2, LRG 41 90 cm x 30 cm 120 - 150 x 30 cm 240 cm x 30 cm Bund Crop 60 cm for BSR 1 and 30 cm for others.",
        fertilizer_schedule="If soil test is not done, apply fertilizers basally before sowing a) Apply fertilizers basally before sowing. Rainfed : 12.5 kg N + 25 kg P 2 O 5 + 12.5 kg K 2 O +10 kg S*/ha Irrigated : 25 kg N + 50 kg P 2 O 5 + 25 kg K 2 O + 20 kg S*/ha",
        harvest_time="Harvest the whole plants when 80% of the pods mature. Heap for 2 – 3 days Dry and process.",
        expected_yield="Grain yield(kg/ha) Rainfed (kg/ha) 950 880 0.75 to 1.0 kg of green pods/plant Irrigated (kg/ha) 1168 1530 -",
        suitable_districts=SAME_AS_SEASON,
        suitable_rainfall="Rainfall mm 600 - 1400",
        evidence_pages="season:137;duration:138;seed_rate:138;spacing:140;fertilizer_schedule:139;harvest_time:141;expected_yield:138;suitable_districts:137;suitable_rainfall:137",
    ),
    dict(
        crop="Blackgram", guide_section="PULSES / 2. Blackgram (printed p134-144)",
        season="Adipattam (June-August) All districts except Kanyakumari and Nilgiris VBN 6, VBN 8; Puratasipattam (September-November) Vellore, Tiruvannamalai Dharmapuri, Salem, Namakkal, Perambalur, Erode, Coimbatore, Madurai, Dindigul, Theni, Pudukottai,, Sivagangai, Ramanathapuram, Virudhunagar, Thoothukudi and Tirunelveli VBN 6, MDU 1, CO 6, VBN 8, VBN 10; Markazhi – Thaipattam(Winter Irrigated) All districts except Kanyakumari and Nilgiris VBN 6, CO 6, VBN 8, VBN 10; Rice fallows (January) Thanjavur,Tiruvarur, Nagapattinam, Cuddalore, Villupuram and Kanchipuram ADT 3, ADT 6, KKM 1, VBN 6, VBN 9; Chithiraipattam (Summer Irrigated) Thanjavur, Tiruvarur, Nagapattinam, Cuddalore, Villupuram, Tiruchirappalli, Perambalur, Thiruvallur, Kancheepuram, ADT 5, VBN 8",
        duration="Maturity duration (days) 65-70 65-70 70-75 70-75",
        irrigation_frequency="Irrigate immediately after sowing, followed by life irrigation on third day. Irrigate at intervals of 7 to 10 days depending upon soil and climatic conditions. Flowering and pod formation stages are critical periods when irrigation is a must.",
        seed_rate="SEED RATE Quantity of seed required kg/ha VARIETIES Pure crop Mixed crop VBN 6, VBN 8, ADT 5, CO 6, MDU 1 20 10 ADT 3, ADT 6, KKM 1 (Rice fallows) 25 .. Optimum plant population 3,25,000/ha",
        spacing="For irrigated crop dibble the seeds adopting 30 x 10 cm spacing For rainfed crop dibble the seeds adopting 25 cm x 10 cm spacing",
        fertilizer_schedule="If soil test is not done, apply fertilizers basally before sowing a) Apply fertilizers basally before sowing. Rainfed : 12.5 kg N + 25 kg P 2 O 5 + 12.5 kg K 2 O +20 kg S*/ha Irrigated : 25 kg N + 50 kg P 2 O 5 + 25 kg K 2 O + 40 kg S*/ha",
        harvest_time="Picking the matured pods, drying and processing Uprooting or cutting the whole plants, heaping, drying and processing",
        expected_yield="Grain yield (kg/ha) - - Rainfed 850 988 1230 - Irrigated 890 871 - 1130",
        suitable_districts=SAME_AS_SEASON,
        suitable_rainfall="Rainfall mm 400 – 600",
        evidence_pages="season:146;duration:147;irrigation_frequency:151;seed_rate:148;spacing:151;fertilizer_schedule:149;harvest_time:154;expected_yield:147;suitable_districts:146;suitable_rainfall:146",
    ),
    dict(
        crop="Greengram", guide_section="PULSES / 3. Greengram (printed p145-153)",
        season="Adipattam (June - July) All districts except Kanyakumari and Nilgiris CO(Gg) 7, VBN(Gg) 2, VBN(Gg) 3, CO 8, VBN 4; Puratasipattam (September - October) Kanchipuram, Tiruvallur, Dharmapuri, Vellore, Tiruvannamalai, Salem, Namakkal, Cuddalore, Villupuram, Thiruchirapalli, Perumbalur, Erode, Coimbatore, Madurai, Dindigul, Theni, Pudukottai, Pudukkottai, Sivagangi, Ramanthapuram, Virudhunagar, Thothukudi and Thirunelveli, Co(Gg) 7, VBN(Gg) 2, VBN(Gg) 3, CO 8, VBN 4; Margazhi-Thai Pattam (December – January) All districts except Kanyakumari and Nilgiris VBN(Gg)3, CO(Gg) 7, CO 8; Rice fallows (January - February) Thanjavur, Tiruvarur, Nagapattinam, Cuddalore, ADT 3; Summer (February - March) Thanjavur, Tiruvarur, Nagapattinam, Cuddalore, Villupuram, Tiruchirapalli, Perambalur, Thiruvallur, Kanchipuram VBN(Gg) 3, CO(Gg) 7, CO 8, VBN 4",
        duration="Maturity duration (days) 60-65 55- 60 65-70 65-75 70-75 65-70",
        irrigation_frequency="Irrigate immediately after sowing, followed by life irrigation on third day. Irrigate at interval of 7 to 10 days depending upon soil and climatic conditions. Flowering and pod formation stages are critical periods when irrigation is a must.",
        seed_rate="SEED RATE Particulars Quantity of seed required kg/ha All varieties Pure crop 20 Mixed crop 10 Rice fallows - ADT 3 30 --",
        spacing="Dibble the seeds adopting a spacing of 30 x 10 cm. For bund crop dibble the seeds at 30 cm spacing.",
        fertilizer_schedule="If soil test is not done , Apply fertilizers basally before sowing. Rainfed : 12.5 kg N + 25 kg P 2 O 5 + 12.5 kg K 2 O +20 kg S*/ha Irrigated : 25 kg N + 50 kg P 2 O 5 + 25 kg K 2 O + 40 kg S*/ha",
        harvest_time="Picking the matured pods, drying and processing Uprooting or cutting the whole plants, heaping ,drying and processing",
        expected_yield="Grain yield (kg/ha) Rainfed (kg/ha) 980 - 750 775 500 (rice fallow) 936 Irrigated (kg/ha) - 845 900 880 - 1251",
        suitable_districts=SAME_AS_SEASON,
        suitable_rainfall="Rainfall mm 600 - 800",
        evidence_pages="season:156;duration:156;irrigation_frequency:159;seed_rate:157;spacing:159;fertilizer_schedule:158;harvest_time:163;expected_yield:157;suitable_districts:156;suitable_rainfall:156",
    ),
]

RECORDS += [
    dict(
        crop="Groundnut", guide_section="OILSEEDS / 1. Groundnut (printed p181-197)",
        season="Zone/ District/Season Sowing Month: I. Western Zone (Irrigated) Coimbatore, Tiruppur Chithiraipattam April-May; Erode,Theni,Dindigul Margazhipattam Dec- Jan; Western Zone (Rainfed) Coimbatore,Tiruppur, Erode, Theni, Dindigul Anippattam June- July; II. Southern Zone (Irrigated) Ramanathapuram, Thirunelveli Thaippattam Jan- Feb; Karur, Pudukkottai, Madurai, Virudhunagar Margazhipattam Dec- Jan; Sivagangai Ayppasipattam Oct- Nov; Southern Zone (Rainfed) Karur, Pudukkottai, Madurai, Sivagangai Anippattam June-July; Virudhunagar Adippattam July-Aug; Ramanathapuram, Thirunelveli Purattasipattam Sep- Oct; Thoothukudi Karthigaipattam Nov- Dec; III. North Eastern Zone (Irrigated) Villupuram Chithiraipattam April-May; Thiruvallur, Kancheepuram Margazhipattam Dec- Jan; Cuddalore Ayppasipattam Oct- Nov; Vellore, Thiruvannamalai Karthigaipattam Nov- Dec; Thiruvallur, Cuddalore, Vellore Anippattam June-July; Kancheepuram Adippattam July-Aug; Thiruvannamalai Purattasipattam Sep- Oct; Villupuram Karthigaipattam Nov- Dec; IV. North Western Zone (Irrigated) Perambalur, Ariyalur Margazhipattam Dec- Jan; Namakkal, Dharmapuri Vaigasipattam May- June; Salem, Krishnagiri Karthigaipattam Nov- Dec; North Western Zone (Rainfed) Namakkal Vaigasipattam May- June; Salem, Dharmapuri, Krishnagiri Anippattam May- June; Perambalur, Ariyalur Adippattam July-Aug; V. Delta Zone (Irrigated) Thiruchirapalli, Thanjavur, Thiruvarur, Nagapattinam Margazhipattam Dec- Jan; Delta Zone (Rainfed) Thiruchirapalli Anippattam June-July; Thanjavur, Nagapattinam Margazhipattam Dec- Jan",
        duration="Duration (days) 100-105 120-125",
        irrigation_frequency="WATER MANAGEMENT Schedule the irrigation at 0.40 and 0.60 IW/CPE ratio during vegetative and reproductive phase respectively. Regulate irrigation as per the growth phase of the crop. Pre-flowering phase : 1 to 25 days Flowering phase : 26 to 60 days Maturity phase: 61 to 105 days Regulate irrigation based on physiological growth phases. Pegging, flowering and pod development phases are critical for irrigation during which period adequate soil moisture is essential. Irrigate as follows: i) Sowing or pre-sowing ii) Life irrigation, 4 - 5 days after sowing. iii) 20 days after sowing iv) At flowering give two irrigations v) At pegging stage give",
        seed_rate="SEED RATE Use 120 kg/ha of kernels, 175 kg/ha of kernels for bold seeded varieties.",
        spacing="Adopt a spacing of 30 cm between rows and 10 cm between plants. Wherever groundnut ring mosaic (bud necrosis) is prevalent, adopt a spacing of 15cm x 15 cm.",
        fertilizer_schedule="If soil test is not done, follow the blanket recommendation. N P K 25 50 75 kg/ha 80 kg S as gypsum on 45 DAS ... N and K in three splits viz., 50 % N & K as basal + 25 % N and K at 20 DAS + 25 % N and K at 45 DAS is recommended.",
        harvest_time="Observe the crop, considering its average duration. Drying and falling of older leaves and yellowing of the top leaves indicate maturity. Pull out a few plants at random and shell the pods. If the inner shell is brownish black and not white, then the crop has matured.",
        expected_yield="Average Yield of Pods kg/ha Rainfed 1613 1916 Irrigated 2580 2403",
        suitable_districts=SAME_AS_SEASON,
        suitable_rainfall="Rainfall mm 500 - 700",
        evidence_pages="season:192-193;duration:194;irrigation_frequency:203;seed_rate:197;spacing:197;fertilizer_schedule:199;harvest_time:198;expected_yield:194;suitable_districts:192-193;suitable_rainfall:192",
    ),
]

RECORDS += [
    dict(
        crop="Sesame", guide_section="OILSEEDS / 2. Sesame (printed p198-205)",
        season="Zone/ District/Season Sowing Varieties Month: I. Western Zone (Irrigated) Coimbatore, Thiruppur, Erode Masipattam Feb- March VRI (Sv) 2, TMV 7, VRI 3; Western Zone (Rainfed) Coimbatore,Thiruppur, Erode, Dindigul Anippattam June- July TMV 7; Theni Karthigai Nov- Dec VRI(Sv) 2, TMV 7; II. Southern Zone (Irrigated) Thirunelveli, Karur Chithiraipattam Apr- May VRI (Sv) 2, TMV 7; Pudukkottai Margazhi Dec- Jan VRI (Sv) 2, TMV 7, VRI 3; Southern Zone (Rainfed) Madurai Anipattam June-July TMV 7; Virudhunagar, Pudukkottai, Adippattam July-Aug TMV 7; Karur Purattasipattam Sep- Oct VRI(Sv) 2, TMV 7; Ramanathapuram, Sivagangai, Thirunelveli, Thoothukudi Karthigaipattam Nov- Dec VRI(Sv) 2, TMV 7; III. North Eastern Zone (Irrigated) Kancheepuram, Cuddalore, Vellore Margazhipattam Dec- Jan VRI (Sv) 2, TMV 7, VRI 3; Thiruvannamalai Masipattam Feb- March VRI (Sv) 2, TMV 7, VRI 3; Villupuram Chithiraipattam Apr- May VRI (Sv) 2, TMV 7; Thiruvallur Anipattam June-July TMV 7; North Eastern Zone (Rainfed) Vellore, Thiruvannamalai Anippattam June-July TMV 7; Kancheepuram, Cuddalore Adippattam July-Aug TMV 7; Thiruvallur Purattasipattam Sep- Oct VRI (Sv) 2, TMV 7; Villupuram Karthigaipattam Nov- Dec VRI (Sv) 2, TMV 7; IV. North Western Zone (Irrigated) Namakkal Margazhipattam Dec- Jan VRI (Sv) 2, TMV 7, VRI 3; Salem, Perambalur, Ariyalur Masipattam Feb- March VRI (Sv) 2, TMV 7, VRI 3; North Western Zone (Rainfed) Salem,Namakkal, Dharmapuri, Krishnagiri Anippattam June-July TMV 7; Perambalur, Ariyalur Adippattam July-Aug TMV 7; V. Delta Zone (Irrigated) Thanjavur, Thiruchirapalli Masipattam Feb- March VRI (Sv) 2, TMV 7, VRI 3; Thiruvarur Chithiraipattam Apr- May VRI (Sv) 2, TMV 7; Delta Zone (Rainfed) Thanjavur, Thiruvarur, Nagapattinam Thaippattam Jan- Feb TMV 7; Thiruchirapalli Purattasipattam Sep- Oct VRI (Sv) 2, TMV 7",
        duration="Duration (days) 80-85 80-85 75-80",
        irrigation_frequency="Irrigate at sowing and give life irrigation 7 days after sowing depending on the soil and climatic condition and allow excess water to percolate. Give one pre-flowering irrigation (25 days): One at flowering and one or two at pod setting. An irrigation at flowering period is critical.",
        seed_rate="Adopt a seed rate of 5 kg/ha.",
        spacing="Give a spacing of 30 cm between rows and 30 cm between plants. For rice fallows, seeds are broadcasted and thinned to maintain 11 plants/m 2",
        fertilizer_schedule="If soil tests are not available, follow the blanket recommendations. Rainfed: Apply 23:13:13 kg NPK/ha or 17:13:13 kg NPK/ ha + 3 packets of Azospirillum (600 g/ha) and 3 packets (600 g/ha) of Phosphobacteria or 6 packets of Azophos (1200 g/ha). Irrigated: Apply 35:23:23 kg NPK/ha or 21:23:23 kg NPK/ha + 3 packets of Azospirillum (600 g/ha) and 3 packets (600 g/ha) of Phosphobacteria or 6 packets of Azophos (1200 g/ha)",
        harvest_time="Observe the crop, considering the average duration of the crop. Twenty five per cent of the leaves from the bottom are shed and the top leaves loose their colour and turn yellow at maturity. The colour of the stem turns yellow. The colour of the capsules turn yellow upto the middle. Harvest before the bottom capsules turn brown.",
        expected_yield="Average Yield (kg/ha) Rainfed 650-700 850 - Irrigated 700-750 920 995 (Margazhipattam) 1055 (Masi pattam)",
        suitable_districts=SAME_AS_SEASON,
        suitable_rainfall="Rainfall mm 450 - 500",
        evidence_pages="season:209-210;duration:210;irrigation_frequency:213;seed_rate:213;spacing:213;fertilizer_schedule:211;harvest_time:213-214;expected_yield:210-211;suitable_districts:209-210;suitable_rainfall:209",
    ),
]

RECORDS += [
    dict(
        crop="Sunflower", guide_section="OILSEEDS / 4. Sunflower (printed p216-223)",
        season="A. Rainfed 1. Adipattam (Jun-July) Variety : COSFV 5 Coimbatore, Erode, Salem, Namakkal, Tirunelveli, Dindigul, Dharmapuri, Hybrid : COH 3. Tiruchirapalli, Perambalur, Karur 2. Karthigaipattam(Oct- Nov) Cuddalore, Villupuram, Virudhunagar, Sivagangai , Variety : COSFV 5 Ramanathapuram, Madurai, Dindigul, Hybrid : COH 3 Theni, Tiruchirapalli, Perambalur, Karur, Tirunelveli B. Irrigated 1. Adipattam (July-August) Coimbatore, Erode, Salem, Namakkal,Tirunelveli, Variety : COSFV 5 Dindigul, Dharmapuri, Tiruchirapalli, Hybrid : COH 3 Perambalur, Karur 2. Karthigaipattam (Nov-Dec) Cuddalore, Villupuram, Virudhunagar, Variety : COSFV 5 Sivagangai , Ramanathapuram, Madurai, Hybrid : COH 3 Dindigul,Theni, Tiruchirapalli, Perambalur, Karur, Tirunelveli 3. Margazhipattam (Dec-Jan) Salem, Namakkal, Dharmapuri, Erode, Variety : COSFV 5 Coimbatore, Madurai, Dindigul, Theni, Hybrid : COH 3 Tirunelveli, Thoothukudi 4. Chithiraipattam (April - May) Variety : COSFV 5 Coimbatore, Erode, Dharmapuri, Salem, Namakkal, Tiruchirapalli, Perambalur, Karur Hybrid : COH 3",
        duration="Duration (days) 85-90 90-95",
        irrigation_frequency="Irrigate immediately after sowing followed by an irrigation on 4 – 5 th day and later at interval of 7 to 8 days according to soil and climatic conditions at seeding, flowering and seed development stage.",
        seed_rate="SEED RATE Rainfed Irrigated Varieties 7 kg/ha 6 kg/ha Hybrids 5 kg/ha 5 kg/ha",
        spacing="Spacing : Hybrids : 60 cm x 30cm Varieties : 45 cm x 30cm",
        fertilizer_schedule="If soil test recommendations are not available, follow the blanket NPK/ha for both irrigated and rainfed crops. Season Blanket recommendation of Nutrients (kg/ha) N P 2 O 5 K 2 O Hybrids IRRI 60 90 60 RF 40 50 40 Varieties IRRI 60 30 30 RF 40 50 40",
        harvest_time="Observe the bracts on the backside of the capitula. When they turn lemon yellow, the heads harden and the crop is ready for harvest.",
        expected_yield="Yield (kg/ha) Rainfed 1500 2150 Irrigated 1700 2410",
        suitable_districts=SAME_AS_SEASON,
        suitable_rainfall="Rainfall mm 350 - 600",
        evidence_pages="season:227;duration:228;irrigation_frequency:231;seed_rate:230;spacing:231;fertilizer_schedule:228;harvest_time:231;expected_yield:228;suitable_districts:227;suitable_rainfall:227",
    ),
]

RECORDS += [
    dict(
        crop="Cotton", guide_section="FIBRE CROPS / 1. Cotton (printed p253-284)",
        season="Irrigated (Main) Winter Irrigated (Aug – Sep) Coimbatore, Erode, Madurai, Dindigul, Theni, Salem, Namakkal MCU 5, MCU 5VT, Suraj, MCU 13, Surabhi, Suvin, CO 14; Dharmapuri MCU 5, MCU 5VT, Suraj, MCU 13, Surabhi, CO 14; Cuddalore, Villupuram LRA 5166, SVPR 2, SVPR 4, Surabhi, CO 14; Madurai, Virudhunagar, Tirunelveli, Trichy, Salem, Erode, Dindigul SVPR 5; Summer – Irrigated (Feb – Mar) Erode MCU 5, MCU 12, MCU 13, Surabhi; Madurai, Virudhunagar, Dindigul, Tirunelveli, Thoothukudi, Theni, Ramanathapuram, Sivagangai, MCU 5, SVPR 2, SVPR 4, Surabhi, SVPR 5, SVPR 6; Rainfed (Sep – Oct) Madurai, Dindigul, Theni, Ramanathapuram, Virudhunagar, Sivagangai, Tirunelveli, Thoothukudi, Dharmapuri, Perambalur, Trichy LRA 5166, K11, KC 2, SVPR 2,KC 3, SVPR4, K12; Rice Fallow Thanjavur, Tiruvarur, Nagapattinam, Karur, Cuddalore and Villupuram MCU 7, SVPR 3",
        duration="early duration (135-140 days)",
        irrigation_frequency="Regulate irrigation according to the following growth phases of the crop. Germination Phase(1-15 days) Irrigate for germination 1 Immediately after sowing; and establishment 2 Give a life irrigation on 5th day of sowing; Vegetative phase (16-44 days) Regulate 1 Irrigate on the 20th or 21st day of sowing, three days after hoeing and weeding",
        seed_rate="Seed Rate Adopt the following seed rates for different varieties/hybrids Varieties / Hybrids Quantity of seed (Kg/ha) With fuzz Delinted Naked MCU 5, MCU 7, MCU 12, MCU 13 15.00 7.50 .. SVPR 2 15.00 .. .. KC 2 20.00 15.00 .. SUVIN .. .. 6.00",
        spacing="In a pure crop of cotton, adopt the spacing as below for the different varieties. Varieties / hybrids Spacing ( cm) Between rows Between plants MCU 5, MCU 12, MCU 13 75 30 LRA 5166, SVPR 2 KC 2 45 15 SUVIN 90 45 MCU 7, SVPR 3 60 or 75 * 30 * Fertile soils",
        fertilizer_schedule="If soil test recommendations are not available, follow the blanket recommendation for the different varieties. Varieties / Hybrids Quantity of fertilizers (Kg/ha) N P 2 O 5 K 2 0 MCU 7, SVPR 3 60 30 30 MCU 5, MCU 12, MCU 13,Suvin, SVPR 2 80 40 40. If basal application could not be done, apply on the 25 th day after sowing. Apply 50 per cent of N and K full dose of P 2 O 5 as basal and remaining ½ N and K at 40 – 45 DAS for varieties. For hybrids apply N in three splits viz ., basal, 45 and 65 DAS.",
        harvest_time="Harvest at frequent intervals, at less than 7 days interval. Harvest in the morning hours upto 10 to 11 a.m only when there is moisture so that dry leaves and bracts do not stick to the kapas and lower the market value. Pick kapas from well burst bolls only.",
        expected_yield="Mean yield of seed (kg/ha): MCU 5 1850; MCU 7 1330; MCU 12 2000; MCU 13 2200; CO 14 1768; SVPR 2 2000; SVPR 3 1800; SVPR 4 1800; SVPR 5 1845; SVPR6 2312; KC 2 1000; KC 3 1080; MCU 5 VT 2500 kg/ha",
        suitable_districts=SAME_AS_SEASON,
        suitable_rainfall="Rainfall mm 500 - 700",
        evidence_pages="season:264;duration:265-266;irrigation_frequency:274;seed_rate:271;spacing:271-272;fertilizer_schedule:269;harvest_time:276;expected_yield:265-266;suitable_districts:264;suitable_rainfall:264",
    ),
]

RECORDS += [
    dict(
        crop="Rice", guide_section="1. RICE (printed p1-64)",
        season="I. Cauvery Delta Zone: Thanjavur/Tiruvarur Kuruvai (Jun -Jul), Samba (Aug), Late Samba / Thaladi (Sep -Oct), Navarai (Dec -Jan); Nagapattinam Late Kuruvai (July), Samba (Aug – Sep), Semi dry cultivation in Thanjavur, Thiruvarur and Nagapattinam August, September; Tiruchirapalli Kuruvai (Jun -Jul), Samba / Thaladi (Aug -Sep), Summer (Dec.); Flood affected areas (Aug-Sep). II. North Eastern Zone: Kanchipuram/Tiruvallur Sornavari (April -May), Samba/ Late Samba (Aug- Sep), Navarai (Dec -Jan), Rainfed direct seeded and Semi-dry (July - Aug); Vellore/Tiruvannamalai Sornavari (April-May), Samba (Aug), Navarai (Dec -Jan); Cuddalore/ Villupuram Sornavari (April -May), Samba (Aug), Navarai (Dec-Jan), Delta regions of Cuddalore Samba (Aug), Late samba/Thaladi (Sep-Oct). III. Western zone: Coimbatore/Tiruppur/Erode Kar (May - Jun), Samba /Late Samba (Aug - Sep), Navarai (Dec -Jan); Karur/Perambalur/Ariyalur Kuruvai (Jun -Jul), Samba (Aug), Late Samba / Thaladi (Sep -Oct), Navarai (Dec -Jan); Delta regions of Karur Late Samba (Sep -Oct); Delta regions of Ariyalur Samba (Aug), Late samba/Thaladi (Sep-Oct). IV. North Western Zone: Salem/Namakkal Kar (May - Jun), Samba (Aug), Navarai (Dec - Jan); Dharmapuri/ Krishnagiri Kar (May -Jun), Samba/Late Samba (Aug - Oct), Navarai (Dec- Jan). V. High Altitude zone: The Nilgiris Samba (Jul -Aug). VI. Southern zone: Pudukottai Kuruvai (Jun -Jul), Samba (Aug), Late Samba/Thaladi (Sep - Oct), Rainfed direct seeded/ Semi-dry (Jul -Aug), Delta regions (Sep -Oct); Madurai/Dindigul/Theni Kar (May -Jun), Samba/ Late Samba (Aug- Sep), Navarai (Dec -Jan), Semi-dry (Jul -Aug); Ramanathapuram Samba (Aug), Rainfed direct seeded & Semidry (Jul -Aug); Virudhunagar Samba (Sep-Oct), Rainfed direct seeded (Jul -Aug); Sivaganga Semi-dry (Jul –Aug); Tirunelveli, Thoothukudi Early kar (Apr - May), Kar (May -Jun), Pishanam/Late Pishanam (Sep-Oct.), Semi dry (July- Aug); Drought affected areas (Ramanathapuram, Virudhunagar, Tiruvallur& parts of Madurai). VII. High Rainfall zone: Kanyakumari Kar (May –Jun), Pishanam / Late samba (Sep – Oct), Semi-dry (Jul – Aug). Kuruvai/Navarai/Sornavari : Short duration; late samba/thaladi : Medium duration; Samba : long duration",
        seed_rate="Wet nursery: Select 20 cents (800 m 2 ) of land area near to water source for raising seedlings for one hectare. Seed rate 30 kg for long duration 40 kg for medium duration 60 kg for short duration varieties and 20 kg for hybrids",
        spacing="Soil Medium and low fertility High fertility Duration Short Medium Long Short Medium Long Spacing (cm) Hills / m 2 15x10 66 20x10 50 20x15 33 20x10 50 20x15 33 20x20 25",
        fertilizer_schedule="Short duration varieties ( dry season ) a) Cauvery delta & Coimbatore tract 150 50 50 b) For other tracts 120 40 40 Medium and long duration varieties ( wet season ) 150 50 50 Hybrid rice 175 60 60 Low N responsive cultivars (like Improved White Ponni) 75* 50 50 * For Ponni, N should be applied in three splits at AT, PI and H stages** in addition to GLM or FYM application.",
        suitable_districts=SAME_AS_SEASON,
        suitable_rainfall="Rainfall mm 1000 - 4500",
        extraction_notes="PENDING (present in the guide, not yet extracted): duration and expected_yield (per-variety tables, printed p5-11), irrigation_frequency (water-management section printed p25-26), harvest_time",
        evidence_pages="season:13-17;seed_rate:29;spacing:32;fertilizer_schedule:33;suitable_districts:13-17;suitable_rainfall:13",
    ),
]

RECORDS += [
    dict(
        crop="Sugarcane", guide_section="7. SUGARCANE (printed p286-308)",
        season="Sugarcane is grown chiefly in the main season (December - May) in the entire State. In parts of Tiruchirapalli, Perambalur, Karur, Salem, Namakkal and Coimbatore districts, it is also raised during the special season (June - September). SEASON, PERIOD OF PLANTING 1. Main season i) Early : Dec - Jan ii) Mid : Feb - March iii) Late: April – May 2. Special season : June - July All early season varieties are suitable for special season.",
        duration="Variety Duration (Month) Cane Yield (t/ha) CCS % CCS (t/ha) CoG 94077 11 133.2 13.50 17.60 Co 86032 10-12 110.0 13.00 14.30 CoSi (SC) 6 10-11 142.0 13.10 18.60 TNAU SC Si 7 10-11 156.0 13.40 20.90 TNAU SC Si 8 11-12 146.0 12.90 18.00 CoC 25 10-12 145.7 12.77 18.62 CoG 6 10-12 140.6 13.34 18.39",
        irrigation_frequency="Irrigate the crop depending upon the need during different phases of the crop. Later, irrigation can be provided at 0.75, 0.75 and 0.50 IW/CPE ratio during tillering, grandgrowth and maturity phases respectively. The irrigation intervals in each phase are given below: Days of irrigation interval Stages Tillering phase (36 to 100 days) 8 10 Grand growth phase (101 - 270 days) 8 10 Maturity phase (271 - harvest) 10 14",
        seed_rate="SEED RATE 75000 two-budded setts/ha.",
        spacing="Form ridges and furrows with a spacing of 80 cm between rows with spade.",
        fertilizer_schedule="If soil test is not done, follow blanket recommendation of NPK @ 300:100:200 kg/ha Apply super phosphate (625 kg/ha) along the furrows and incorporate with hand hoe.",
        harvest_time="Early varieties have to be harvested at 10 to 11 months age and mid-season varieties at 11 to 12 months age. Harvest the cane at peak maturity. Cut the cane to the ground level for both plant and ratoon crops.",
        expected_yield="Variety Duration (Month) Cane Yield (t/ha) CCS % CCS (t/ha) CoG 94077 11 133.2 13.50 17.60 Co 86032 10-12 110.0 13.00 14.30 CoSi (SC) 6 10-11 142.0 13.10 18.60 TNAU SC Si 7 10-11 156.0 13.40 20.90 TNAU SC Si 8 11-12 146.0 12.90 18.00 CoC 25 10-12 145.7 12.77 18.62 CoG 6 10-12 140.6 13.34 18.39",
        suitable_districts="Sugarcane is grown chiefly in the main season (December - May) in the entire State. In parts of Tiruchirapalli, Perambalur, Karur, Salem, Namakkal and Coimbatore districts, it is also raised during the special season (June - September).",
        suitable_rainfall="Rainfall mm 2500 - 3000",
        extraction_notes="PENDING: further variety tables (cane yield, duration, maturity group) printed p288-290 (Co 0212, Co 06022, Co 09004 and later) not yet extracted",
        evidence_pages="season:297;duration:297;irrigation_frequency:308;seed_rate:303;spacing:300;fertilizer_schedule:301;harvest_time:313;expected_yield:297;suitable_districts:297;suitable_rainfall:297",
    ),
]

RECORDS += [
    dict(
        crop="Bengalgram", guide_section="PULSES / 6. Bengalgram (printed p162-165)",
        season="November (Winter season) Rainfed Vellore, Tiruvannamalai, Salem, Namakkal, Tiruchirapalli, Perambalur, Karur, Dharmapuri, Pudukottai, Erode, Coimbatore, Madurai, Dindigul, Theni, Virudhunagar, Ramanathapuram, Sivagangai, Tirunelveli, Thoothukudi CO 4",
        duration="Duration (days) 85",
        seed_rate="SEED RATE CO 3 - 90 kg/ha. CO 4 - 75 kg/ha.",
        spacing="Dibble the seeds by adopting a spacing of 30 cm x 10 cm.",
        fertilizer_schedule="Apply fertilizers basally before sowing. Rainfed : 12.5 kg N + 25 kg P 2 O 5 + 12.5 kg K 2 O +10 kg S*/ha Irrigated : 25 kg N + 5 kg P 2 O 5 + 25 kg K 2 O + 20 kg S*/ha",
        expected_yield="Grain yield (kg/ha) Rainfed 1150",
        suitable_districts=SAME_AS_SEASON,
        suitable_rainfall="Rainfall mm 500 - 800",
        extraction_notes="PENDING: main-crop harvest and irrigation text not located (the only harvest passage found, p176, sits in the seed-production section and was not taken)",
        evidence_pages="season:173;duration:173;seed_rate:173;spacing:174;fertilizer_schedule:174;expected_yield:173;suitable_districts:173;suitable_rainfall:173",
    ),
]

RECORDS += [
    dict(
        crop="Soybean", guide_section="PULSES / 9. Soya bean (printed p174-178)",
        season="DISTRICT/SEASON VARIETIES Adipattam (June - July) Purattasipattam (Sep. - Oct.) Masipattam (February - March) Rice fallows Co(Soy)3. SEASON The crop can be grown in South-West and North-East monsoon seasons. The middle of July is the optimum time of sowing for rainfed Soyabean in North Western Zone.",
        duration="Duration (days) 90-100",
        irrigation_frequency="Irrigate immediately after sowing. Give life irrigation on 3 rd day. Further irrigation at intervals of 7 - 10 and 10 - 15 days during summer and winter season respectively to be given depending on soil and weather conditions.",
        spacing="Dibble the seeds at a depth of 2 - 3 cm adopting a spacing of 30 x 5 cm.",
        fertilizer_schedule="Apply 20 kg N and 80 kg P 2 O 5 and 40 kg K 2 O per ha 40 kg of S as gypsum (220 kg/ha) as basal dressing. [Rainfed soybean:] If soil test recommendation is not available adopt blanket recommendation of 20:40:20:20 NPKS kg/ha, if adequate moisture is available. Apply entire dose of N, P, K and S as basal.",
        harvest_time="Yellowing of leaves and shedding, indicate the maturity of the crop. Cut the entire plant when most of the pods have turned yellow, drying and processing.",
        expected_yield="Grain yield (Kg/ha) Rainfed - Irrigated 1700",
        suitable_rainfall="Rainfall mm 600 - 750",
        npk_by_condition="irrigated main crop (pdf p186): N 20 P2O5 80 K2O 40 S 40; rainfed blanket (pdf p187): N 20 P2O5 40 K2O 20 S 20",
        extraction_notes="seed_rate not located in the main soybean section; suitable_districts: the guide names only 'North Western Zone' (rainfed), no district list. NOTE agronomy_tnau.csv carries only the rainfed 20:40:20 blanket (p187); the irrigated 20/80/40 dose on p186 is not in that file.",
        evidence_pages="season:185-187;duration:185;irrigation_frequency:186;spacing:186;fertilizer_schedule:186-187;harvest_time:186;expected_yield:185;suitable_rainfall:185",
    ),
]
