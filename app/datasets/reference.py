"""Reference (metadata) tables - not measurements.

district_reservoir_map: which reservoir serves which district. This is hydrological metadata
(the reservoir's location district), recorded with its basis. Entries marked 'location' state the district
in which the dam is situated; they must be verified against the TN Water Resources Department command-area
lists (scraper S5 / S12). Reservoirs outside Tamil Nadu are not mapped to any district."""
DISTRICT_RESERVOIR_MAP = [
    ("coimbatore", "aliyar", "location"), ("coimbatore", "parambikulam", "location"), ("coimbatore", "sholayar", "location"),
    ("tiruppur", "thirumurthy", "location"), ("tiruppur", "amaravathi", "location"),
    ("erode", "bhavanisagar", "location"), ("salem", "mettur", "location"),
    ("krishnagiri", "krishnagiri", "location"), ("tiruvannamalai", "sathanur", "location"),
    ("theni", "vaigai", "location"), ("theni", "periyar", "location"),
    ("tirunelveli", "manimuthar", "location"), ("tirunelveli", "papanasam", "location"),
    ("kanniyakumari", "pechiparai", "location"), ("kanniyakumari", "perunchani", "location"),
]
