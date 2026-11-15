"""Runs the five demo cases on the deployed app and records the outputs used in 02_DEMO_CASES.md.

    pip install requests
    python final_demo/qa_scripts/demo_cases.py demo_cases.json
"""
import json, sys, time, requests
B = "https://agrooptimize.onrender.com"
cases=[
 ("1 Normal recommendation", {"location":"Salem","season":"Rabi","year":2024,"total_land_ha":5}),
 ("2 High rainfall", {"location":"Tirunelveli","season":"Rabi","year":2024,"total_land_ha":5}),
 ("3 Low rainfall", {"location":"Nagapattinam","season":"Kharif","year":2024,"total_land_ha":5}),
 ("4 Low budget", {"location":"Salem","season":"Rabi","year":2024,"total_land_ha":5,"budget_rs":100000}),
 ("5 Sustainability", {"location":"Coimbatore","season":"Rabi","year":2024,"total_land_ha":5,"profile":"sustainability"}),
]
out=[]
for name, body in cases:
    t=time.time(); r=requests.post(B+"/api/farm-plans", json={**body,"save_results":True,"client_id":"demo-prep"}, timeout=300).json(); sec=time.time()-t
    rp=r["region_profile"]; fz=r["fuzzy_assessment"]
    top=[]
    for p in r["plans"][:3]:
        top.append({"rank":p["rank"],"mix":[(n,round(a,1)) for n,a in zip(p["crop_names"],p["allocation_percent"]) if a>=1],
                    "closeness":p["composite_score"],"yield_t":round(p["yield_tonnes"],2),"cost":round(p["cost_rs"]),"irrigated_ha":round(p["irrigated_ha"],3),
                    "npk_kg":round(p["env_impact_score"],1),"summary":p["trade_off_summary"]})
    ex=requests.get(f"{B}/api/results/{r['run_id']}/explanation", params={"rank":1}, timeout=120).json()
    ce=[{"crop":c["crop"],"share":c["share_pct"],"counts":c["status_counts"],
         "flags":[(k["id"],k["status"],k["statement"][:160]) for k in c["criteria"] if k["status"] in ("caution","concern")]} for c in ex["crop_evidence"]]
    out.append({"case":name,"input":body,"seconds":round(sec,1),
      "rain":(lambda g: {"actual":g["rainfall"].get("season_actual_mm"),"normal":g["rainfall"].get("season_normal_mm"),"dev":g["rainfall"]["avg_deviation_percent"],"months":g["rainfall"].get("months_used"),"notes":g.get("notes")})(requests.get(B+"/api/region-profile", params={"location":body["location"],"season":body["season"]}, timeout=120).json()),
      "storage":rp["water"]["avg_storage_percent"],"reservoirs":rp["water"].get("reservoirs"),"fert_index":rp["soil"]["fertility_index"],
      "npk":[rp["soil"].get("n_status"),rp["soil"].get("p_status"),rp["soil"].get("k_status")],
      "fuzzy":fz,"candidates":[c["name"] for c in rp["candidate_crops"]],"excluded":[e["crop"] for e in (rp.get("excluded_crops") or [])],
      "n_plans":len(r["plans"]),"pareto":r["meta"]["n_pareto_solutions_found"],"quality":{k:r["meta"]["quality_metrics"].get(k) for k in ("hypervolume_ratio","igd_plus","spread","constraint_satisfaction_rate")},
      "top":top,"ranking":r["meta"].get("topsis",{}).get("label"),
      "confidence":ex["summary"]["confidence_pct"],"recommendation":ex["summary"]["recommendation"],
      "reasons":[x["title"] for x in ex["reasons"]],"risks":[(x["severity"],x["title"]) for x in ex["risks"]],
      "weakest":ex["confidence"].get("weakest_component"),"crop_evidence":ce})
    print(name, sec, top[0]["mix"] if top else None, flush=True)
json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else "demo_cases.json", "w"), indent=1)
