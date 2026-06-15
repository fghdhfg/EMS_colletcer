# -*- coding: utf-8 -*-
"""
build_platform_summary.py  (EMS_colletcer 에서 실행)

소방안전 빅데이터 플랫폼 '전국 구급 현황(ems-incidents)' 최근 표본을 받아
  1) 현장 체류시간 (현장도착 grndsArvl → 현장출발 grndsDptre) 평균/중앙값
  2) 중증 비율 (심정지/중증외상/중증증상)
을 계산해 data/platform_summary.json 으로 저장한다.

앱은 이 작은 json만 읽어 빠르게 표시(원본 1,430만건을 앱이 직접 안 받음).

키: 환경변수 BIGDATA119_KEY (GitHub Actions Secret).
"""

import json
import os
import statistics
from datetime import datetime, timezone

from fire_bigdata import get_records, EMS_INCIDENTS, total_count

SAMPLE_PAGES = 15      # 100 → 15 (1500건이면 평균·비율엔 충분)
PAGE_SIZE = 100
OUT_PATH = os.path.join("data", "platform_summary.json")

# 중증으로 볼 증상구분(ptnSymSeNm) 키워드
SEVERE_SYM = ("심정지", "심혈관", "뇌혈관", "뇌출혈", "호흡곤란", "의식장애", "쇼크", "중증")


def _to_minutes(ymd, tm):
    """YYYYMMDD + HHMMSS(또는 HHMM) → datetime. 실패 시 None."""
    if not ymd or not tm:
        return None
    ymd = str(ymd).strip()
    tm = str(tm).strip()
    if len(ymd) != 8:
        return None
    tm = tm.zfill(6)[:6]            # HHMMSS 로 정규화
    try:
        return datetime.strptime(ymd + tm, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def main():
    stay_minutes = []          # 현장 체류시간(분) 목록
    n = 0
    n_cardiac = 0              # 심정지
    n_trauma = 0              # 중증외상
    n_severe_sym = 0          # 중증 증상

    for page in range(1, SAMPLE_PAGES + 1):
        try:
            # sort 없이 표본 추출 (1,430만건 ORDER BY는 느려 타임아웃 위험)
            recs = get_records(EMS_INCIDENTS, filters=None,
                               page=page, size=PAGE_SIZE)
        except Exception as e:
            print(f"[page {page}] 수집 실패: {e}")
            break
        if not recs:
            break
        for r in recs:
            n += 1
            # 현장 체류시간
            arv = _to_minutes(r.get("grndsArvlYmd"), r.get("grndsArvlTm"))
            dpt = _to_minutes(r.get("grndsDptreYmd"), r.get("grndsDptreTm"))
            if arv and dpt:
                diff = (dpt - arv).total_seconds() / 60.0
                if 0 <= diff <= 180:        # 0~3시간 사이만 유효(이상치 제거)
                    stay_minutes.append(diff)
            # 중증 분류
            if (r.get("hrtarstNm") or "").strip():
                n_cardiac += 1
            if (r.get("srilOncrNm") or "").strip():
                n_trauma += 1
            sym = (r.get("ptnSymSeNm") or "")
            if any(k in sym for k in SEVERE_SYM):
                n_severe_sym += 1

    # 전국 전체 건수(빠른 total)
    try:
        national_total = total_count(EMS_INCIDENTS)
    except Exception:
        national_total = None

    summary = {
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "national_total": national_total,
        "sample_size": n,
        "stay_minutes": {
            "count": len(stay_minutes),
            "avg": round(statistics.mean(stay_minutes), 1) if stay_minutes else None,
            "median": round(statistics.median(stay_minutes), 1) if stay_minutes else None,
        },
        "severe": {
            "cardiac_arrest_pct": round(100 * n_cardiac / n, 1) if n else None,
            "severe_trauma_pct": round(100 * n_trauma / n, 1) if n else None,
            "severe_symptom_pct": round(100 * n_severe_sym / n, 1) if n else None,
        },
    }

    os.makedirs("data", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("저장:", OUT_PATH)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
