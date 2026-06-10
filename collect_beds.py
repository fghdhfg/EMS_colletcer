# -*- coding: utf-8 -*-
"""
응급실 실시간 가용병상 수집기 (서울 전체)
- 국립중앙의료원 응급의료기관 정보 조회 서비스 API 호출
- 30분 간격(GitHub Actions cron)으로 실행되어 data/ 폴더에 일별 CSV로 누적 저장
- 인증키는 환경변수 SERVICE_KEY 로 주입 (data.go.kr의 'Decoding' 키 사용)
"""

import csv
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import requests

BASE_URL = "https://apis.data.go.kr/B552657/ErmctInfoInqireService/getEmrrmRltmUsefulSckbdInfoInqire"
STAGE1 = "서울특별시"          # 수집 범위: 서울 전체 (STAGE2 비우면 시 전체)
NUM_OF_ROWS = 100             # 서울 응급의료기관 수는 100개 미만이라 1페이지로 충분

KST = timezone(timedelta(hours=9))

# 저장할 필드 (필요시 추가/삭제)
FIELDS = [
    "collected_at",   # 수집 시각 (KST)
    "hpid",           # 병원 ID
    "dutyName",       # 병원명
    "hvidate",        # 병원측 정보 갱신 시각
    "hvec",           # 응급실 일반병상 잔여 (핵심!)
    "hv2",            # 내과중환자실
    "hv3",            # 외과중환자실
    "hvoc",           # 수술실
    "hvncc",          # 신경중환자실
    "hvgc",           # 일반입원실
    "hvctayn",        # CT 가용 여부
    "hvmriayn",       # MRI 가용 여부
    "hvangioayn",     # 혈관촬영기 가용 여부
    "hvventiayn",     # 인공호흡기 가용 여부
    "hvamyn",         # 구급차 가용 여부
    "hvs01",          # 일반병상 총수 (포화율 계산용 분모)
]


def fetch_seoul_beds(service_key: str) -> list[dict]:
    params = {
        "serviceKey": service_key,
        "STAGE1": STAGE1,
        "pageNo": 1,
        "numOfRows": NUM_OF_ROWS,
    }
    resp = requests.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    result_code = root.findtext(".//resultCode")
    if result_code != "00":
        msg = root.findtext(".//resultMsg")
        raise RuntimeError(f"API 오류 resultCode={result_code}, msg={msg}")

    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for item in root.iter("item"):
        row = {"collected_at": now}
        for f in FIELDS[1:]:
            row[f] = item.findtext(f, default="")
        rows.append(row)
    return rows


def append_csv(rows: list[dict]) -> str:
    """data/YYYY-MM/beds_YYYYMMDD.csv 에 누적 (일 단위 파일로 쪼개 저장)"""
    now = datetime.now(KST)
    dir_path = os.path.join("data", now.strftime("%Y-%m"))
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, f"beds_{now.strftime('%Y%m%d')}.csv")

    file_exists = os.path.exists(file_path)
    with open(file_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)
    return file_path


def main() -> int:
    service_key = os.environ.get("SERVICE_KEY", "").strip()
    if not service_key:
        print("ERROR: 환경변수 SERVICE_KEY 가 설정되지 않았습니다.", file=sys.stderr)
        return 1

    rows = fetch_seoul_beds(service_key)
    if not rows:
        print("WARNING: 수신된 병원 데이터가 0건입니다.", file=sys.stderr)
        return 0

    path = append_csv(rows)
    print(f"OK: {len(rows)}개 병원 저장 -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
