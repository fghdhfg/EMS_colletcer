# -*- coding: utf-8 -*-
"""
build_saturation_profile.py
EMS_colletcer가 모은 병상 스냅샷(beds_*.csv) → 병원별 '포화 프로파일' JSON 생성.

산출물: saturation_profile.json
  - 병원(hpid)별 전체 포화율 + 시간대 버킷별 포화율
  - 앱(app.py)은 이 JSON만 읽어 고정 페널티(+20분)를 데이터 기반 페널티로 대체

설계 의도:
  - 데이터가 적은 지금은 '전체 포화율'이 주로 쓰이고,
    스냅샷이 쌓이면 '시간대 버킷'이 표본수를 채워 자동으로 정교해진다(앱이 알아서 선택).

실행:
  python build_saturation_profile.py                # 현재 폴더의 beds_*.csv 전부
  python build_saturation_profile.py ./ems_data     # 폴더 지정
"""

import glob
import json
import os
import sys
from datetime import datetime

import pandas as pd

# 시간대 버킷: 0=새벽(0~6) 1=오전(6~12) 2=오후(12~18) 3=야간(18~24)
BUCKET_NAMES = {0: "dawn", 1: "morning", 2: "afternoon", 3: "night"}


def hour_bucket(hour: int) -> int:
    return min(hour // 6, 3)


def build(data_dir: str = ".") -> dict:
    # data/ 바로 밑 + data/2026-06/ 같은 월별 하위폴더까지 모두 탐색
    files = sorted(set(
        glob.glob(os.path.join(data_dir, "**", "beds_*.csv"), recursive=True)
        + glob.glob(os.path.join(data_dir, "beds_*.csv"))
    ))
    if not files:
        raise SystemExit(f"beds_*.csv 를 찾지 못함(하위폴더 포함): {os.path.abspath(data_dir)}")

    frames = []
    for f in files:
        df = pd.read_csv(f)
        df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)

    # 정리
    df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce")
    df = df.dropna(subset=["collected_at", "hpid"])
    df["hvec"] = pd.to_numeric(df["hvec"], errors="coerce")
    df = df.dropna(subset=["hvec"])
    df["saturated"] = df["hvec"] <= 0          # 음수/0 = 정원초과 또는 만석
    df["wday"] = df["collected_at"].dt.weekday  # 0=월 ... 6=일
    df["bucket"] = df["collected_at"].dt.hour.map(hour_bucket)

    n_snap = df["collected_at"].nunique()
    span = (df["collected_at"].min(), df["collected_at"].max())

    hospitals = {}
    for hpid, g in df.groupby("hpid"):
        name = str(g["dutyName"].iloc[0])
        overall_n = len(g)
        overall_rate = round(float(g["saturated"].mean()), 3)

        buckets = {}
        for b, gb in g.groupby("bucket"):
            buckets[BUCKET_NAMES[int(b)]] = {
                "n": int(len(gb)),
                "rate": round(float(gb["saturated"].mean()), 3),
            }
        hospitals[str(hpid)] = {
            "name": name,
            "n": int(overall_n),
            "overall_rate": overall_rate,
            "buckets": buckets,
        }

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_files": [os.path.basename(f) for f in files],
        "n_snapshots": int(n_snap),
        "date_range": [span[0].strftime("%Y-%m-%d %H:%M"),
                       span[1].strftime("%Y-%m-%d %H:%M")],
        "bucket_def": "dawn=0-6, morning=6-12, afternoon=12-18, night=18-24",
        "hospitals": hospitals,
    }


if __name__ == "__main__":
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    profile = build(data_dir)
    out = os.path.join(data_dir, "saturation_profile.json")
    with open(out, "w", encoding="utf-8") as fp:
        json.dump(profile, fp, ensure_ascii=False, indent=2)

    print(f"✓ {out} 생성")
    print(f"  스냅샷 {profile['n_snapshots']}개 | 기간 {profile['date_range'][0]} ~ {profile['date_range'][1]}")
    print(f"  병원 {len(profile['hospitals'])}곳")
    # 만성 포화 상위 10곳(표본 충분한 것만)
    rows = [(h["overall_rate"], h["n"], h["name"])
            for h in profile["hospitals"].values() if h["n"] >= 3]
    rows.sort(reverse=True)
    print("\n  [만성 포화율 상위 10]")
    for rate, n, name in rows[:10]:
        print(f"    {rate:5.0%}  (n={n})  {name[:30]}")
