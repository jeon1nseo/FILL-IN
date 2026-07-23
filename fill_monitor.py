"""
FILL:N - 충진량 실시간 모니터 (YOLO 없이, 고정 ROI + 캘리브레이션 방식)

사용법:
  1) 실행하면 카메라 화면이 뜸
  2) 마우스로 '병 영역'을 드래그해서 네모로 지정 → Enter/Space
     (영역의 아래=0%, 위=100% 기준)
  3) 실시간으로 수위(%)가 옆 게이지 + 숫자로 표시됨
  4) 95%(병목) 도달 + 몇 프레임 연속 확인되면 빨간 STOP 신호

키:
  r : ROI 다시 지정 (카메라 옮겼을 때)
  t : 화면 90도 회전 (카메라를 눕혀 설치한 경우 병을 똑바로 세움)
  q : 종료
"""

import cv2
import numpy as np
import os
from datetime import datetime
from dataclasses import dataclass
from collections import deque

SAVE_DIR = "results"      # 결과 이미지 저장 폴더
CAPACITY_ML = 100.0       # 병 전체 용량(mL) — ROI가 가득 찼을 때의 액체량
STABILITY_WINDOW = 10     # 신뢰도(안정성) 계산에 쓸 최근 프레임 수


@dataclass
class VisionSample:
    """팀 공통 비전 데이터 형식. 이 파트는 lvl, cb만 채운다."""
    gap: float = None     # (다른 파트 담당)
    lvl: float = None     # 액체량(mL) — 이 파트 담당
    bar: float = None     # (다른 파트 담당)
    dz: float = None      # (다른 파트 담당)
    ca: float = None      # (다른 파트 담당)
    cb: float = None      # LVL 검출 신뢰도(0~1) — 이 파트 담당

FILL_THRESHOLD = 95      # 멈춤 기준 (%)
CONFIRM_FRAMES = 5       # 이 프레임 수만큼 연속 도달해야 신호 (노이즈 방지)

# 흰색 내용물 검출 기준 (HSV). 조명에 따라 j/k 키로 실시간 조정 가능.
WHITE_V_MIN = 140        # 밝기(V) 이 값 이상 = 밝음
WHITE_S_MAX = 70         # 채도(S) 이 값 이하 = 하양/회색 (색이 옅음)
ROW_FILL_RATIO = 0.45    # 한 줄에서 흰 픽셀이 이 비율 이상이면 '내용물 줄'로 인정
                         # (벽에 얇게 묻은 자국은 폭을 적게 차지해서 걸러짐)

# 화면 회전: 카메라를 눕혀 설치했으면 t 키로 맞추세요.
# 0=회전없음, 1=시계90, 2=180, 3=반시계90
ROTATE_STATE = 1
_ROTATE_CODES = {
    1: cv2.ROTATE_90_CLOCKWISE,
    2: cv2.ROTATE_180,
    3: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def read_frame(cap):
    """프레임을 읽고 현재 회전 설정을 적용해서 반환."""
    ret, frame = cap.read()
    if not ret:
        return False, None
    if ROTATE_STATE in _ROTATE_CODES:
        frame = cv2.rotate(frame, _ROTATE_CODES[ROTATE_STATE])
    return True, frame


def _gst_pipeline(sensor_id):
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        "video/x-raw(memory:NVMM), width=1280, height=720, framerate=30/1, format=NV12 ! "
        "nvvidconv flip-method=0 ! "
        "video/x-raw, width=1280, height=720, format=BGRx ! "
        "videoconvert ! "
        "video/x-raw, format=BGR ! appsink drop=1"
    )


def open_camera():
    """CSI 포트 0, 1 순서로 시도 (실제 프레임 확인). 실패 시 USB 웹캠."""
    for sensor_id in (0, 1):
        cap = cv2.VideoCapture(_gst_pipeline(sensor_id), cv2.CAP_GSTREAMER)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"[CAMERA] CSI 카메라 연결됨 - sensor-id={sensor_id}")
                return cap
        cap.release()
        print(f"[CAMERA] sensor-id={sensor_id} 실패")
    print("[CAMERA] CSI 실패 → USB 웹캠(index 0) 재시도")
    return cv2.VideoCapture(0)


def measure_fill(frame, roi):
    """
    ROI 안에서 '흰색 내용물'이 어디까지 찼는지로 충진율(%)을 계산.
    - HSV로 바꿔 '밝고(V높음) 색이 옅은(S낮음)' 픽셀 = 흰색 내용물로 판단
    - 위에서 아래로 스캔, 흰 픽셀이 충분히 많은 첫 줄 = 내용물 표면
    반환: (충진율%, 표면 y좌표, 디버그용 마스크)
    """
    x, y, w, h = roi
    region = frame[y:y + h, x:x + w]
    if region.size == 0:
        return 0.0, None, None

    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    # 흰색: 채도 낮고(0~S_MAX) 밝기 높음(V_MIN~255)
    mask = cv2.inRange(hsv, (0, 0, WHITE_V_MIN), (180, WHITE_S_MAX, 255))

    # 잡음 제거 (작은 흰 점 없애기)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    row_white = mask.mean(axis=1) / 255.0   # 각 줄의 흰 픽셀 비율(0~1)

    # 바닥에서 위로 올라가며 '연속으로 채워진' 구간의 꼭대기를 찾음.
    # 중간에 빈 줄이 gap_tol 이상 연속되면, 그 위는 벽에 묻은 자국으로 보고 무시.
    gap_tol = max(3, int(h * 0.06))
    last_filled = None
    empty_run = 0
    for row in range(h - 1, -1, -1):        # 아래 → 위
        if row_white[row] >= ROW_FILL_RATIO:
            last_filled = row
            empty_run = 0
        else:
            empty_run += 1
            if last_filled is not None and empty_run > gap_tol:
                break

    surface_row = last_filled if last_filled is not None else h
    fill = (h - surface_row) / h * 100
    fill = float(min(max(fill, 0), 100))
    surface_y = y + surface_row

    # 검출 선명도(신뢰도용): 표면 아래(찬 곳)는 하얗고 위(빈 곳)는 안 하얀 정도
    below = float(row_white[surface_row:].mean()) if surface_row < h else 0.0
    above = float(row_white[:surface_row].mean()) if surface_row > 0 else 0.0
    clarity = float(np.clip(below - above, 0.0, 1.0))

    return fill, surface_y, mask, clarity


def draw_overlay(frame, roi, fill, surface_y, triggered):
    x, y, w, h = roi
    color = (0, 0, 255) if fill >= FILL_THRESHOLD else (0, 255, 0)

    # 병 영역 박스
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

    # 95% 기준선 (병목 선)
    threshold_y = y + int(h * (1 - FILL_THRESHOLD / 100))
    cv2.line(frame, (x, threshold_y), (x + w, threshold_y), (0, 165, 255), 1)
    cv2.putText(frame, f'{FILL_THRESHOLD}%', (x + w + 5, threshold_y + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)

    # 현재 수면 선
    if surface_y is not None:
        cv2.line(frame, (x, surface_y), (x + w, surface_y), color, 2)

    # 옆에 채워지는 게이지
    bar_x = x + w + 40
    bar_w = 25
    fill_h = int(h * fill / 100)
    cv2.rectangle(frame, (bar_x, y), (bar_x + bar_w, y + h), (200, 200, 200), 1)
    cv2.rectangle(frame, (bar_x, y + h - fill_h), (bar_x + bar_w, y + h), color, -1)

    # 수치 텍스트
    cv2.putText(frame, f'{fill:.1f}%', (x, y - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

    # 도달 신호
    if triggered:
        cv2.putText(frame, 'STOP - ROTATE', (x, y + h + 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)


def adjust_rotation(cap):
    """회전 맞추기 전용 화면. t로 90도씩 돌리고 Enter/Space로 확정."""
    global ROTATE_STATE
    win = "1단계: 회전 맞추기 (t=회전, Enter=확정, q=종료)"
    print("[1단계] 병이 똑바로 서 보이게 t 키로 회전 → Enter/Space로 확정")
    while True:
        ret, frame = read_frame(cap)
        if not ret:
            raise RuntimeError("카메라 프레임을 읽을 수 없습니다.")
        cv2.putText(frame, f"t: rotate ({ROTATE_STATE})  Enter: OK  q: quit",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.imshow(win, frame)
        key = cv2.waitKey(30) & 0xFF
        if key == ord('t'):
            ROTATE_STATE = (ROTATE_STATE + 1) % 4
        elif key in (13, 32):   # Enter, Space
            break
        elif key == ord('q'):
            cv2.destroyWindow(win)
            return False
    cv2.destroyWindow(win)
    return True


def select_roi(cap):
    """마우스로 병 영역을 지정받음."""
    ret, frame = read_frame(cap)
    if not ret:
        raise RuntimeError("카메라 프레임을 읽을 수 없습니다.")
    print("[2단계] 마우스로 '병 영역'을 드래그한 뒤 Enter 또는 Space")
    win = "2단계: 병 영역 드래그 후 Enter"
    roi = cv2.selectROI(win, frame, showCrosshair=True)
    cv2.destroyWindow(win)
    return roi  # (x, y, w, h)


def main():
    global ROTATE_STATE, WHITE_V_MIN, ROW_FILL_RATIO
    cap = open_camera()
    if not cap.isOpened():
        raise RuntimeError("카메라를 열 수 없습니다.")

    if not adjust_rotation(cap):
        cap.release()
        cv2.destroyAllWindows()
        return
    roi = select_roi(cap)
    if roi[2] == 0 or roi[3] == 0:
        print("영역이 지정되지 않았습니다. 종료합니다.")
        cap.release()
        return

    os.makedirs(SAVE_DIR, exist_ok=True)
    print("모니터링 시작. (r: 다시설정  j/k: 밝기기준  n/m: 표면기준  s: 저장  q: 종료)")
    reached = 0
    fills = deque(maxlen=STABILITY_WINDOW)   # 신뢰도 안정성 계산용

    while True:
        ret, frame = read_frame(cap)
        if not ret:
            break

        fill, surface_y, mask, clarity = measure_fill(frame, roi)

        # ---- VisionSample 로 내보낼 값 계산 ----
        lvl = round(fill / 100.0 * CAPACITY_ML, 2)          # 충진율 → mL
        fills.append(fill)
        if len(fills) >= 3:
            stability = float(np.clip(1.0 - np.std(fills) / 15.0, 0.0, 1.0))
        else:
            stability = 0.0
        cb = round(0.5 * clarity + 0.5 * stability, 2)      # LVL 신뢰도(0~1)
        sample = VisionSample(lvl=lvl, cb=cb)
        # 다른 파트(GAP/BAR/DZ)와 합쳐지거나 하강 판단에 쓰이도록 내보냄
        print(f"LVL={lvl:.2f}mL  CB={cb:.2f}  (fill={fill:.1f}%)")

        # 연속 도달 확인 (노이즈 방지)
        if fill >= FILL_THRESHOLD:
            reached += 1
        else:
            reached = 0
        triggered = reached >= CONFIRM_FRAMES

        if triggered:
            print(f"[SIGNAL] {FILL_THRESHOLD}% 도달 → 터릿 회전 (fill={fill:.1f}%)")

        draw_overlay(frame, roi, fill, surface_y, triggered)
        cv2.putText(frame, f"V_min={WHITE_V_MIN}(j/k)  row={ROW_FILL_RATIO:.2f}(n/m)",
                    (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, f"LVL={lvl:.1f}mL  CB={cb:.2f}",
                    (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("FILL:N - Fill Monitor", frame)

        # 디버그: 흰색으로 검출된 부분(마스크) 보기 — 흰 부분이 실제 크림과 맞는지 확인
        if mask is not None:
            cv2.imshow("mask (white = detected)", mask)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            # 처음부터 다시: 회전 맞추기 → 영역 지정
            if adjust_rotation(cap):
                roi = select_roi(cap)
                reached = 0
        elif key == ord('j'):
            WHITE_V_MIN = max(0, WHITE_V_MIN - 5)     # 더 어두운 것도 흰색으로 인정
        elif key == ord('k'):
            WHITE_V_MIN = min(255, WHITE_V_MIN + 5)   # 더 밝은 것만 흰색으로 인정
        elif key == ord('n'):
            ROW_FILL_RATIO = max(0.05, ROW_FILL_RATIO - 0.05)  # 표면 판정 완화 → 선이 위로
        elif key == ord('m'):
            ROW_FILL_RATIO = min(0.95, ROW_FILL_RATIO + 0.05)  # 표면 판정 엄격 → 선이 아래로
        elif key == ord('s'):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(SAVE_DIR, f"fill_{ts}_{fill:.0f}pct.png")
            cv2.imwrite(path, frame)
            if mask is not None:
                cv2.imwrite(os.path.join(SAVE_DIR, f"fill_{ts}_mask.png"), mask)
            print(f"[SAVE] 저장됨: {path}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
