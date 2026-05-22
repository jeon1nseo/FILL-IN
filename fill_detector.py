import cv2
import numpy as np
from ultralytics import YOLO

# 사전학습 모델 (첫 실행 시 자동 다운로드 ~6MB)
model = YOLO('yolov8n.pt')

FILL_THRESHOLD = 95  # 멈출 기준 (%)


def get_fill_percent(frame, x1, y1, x2, y2):
    """바운딩 박스 안에서 액면 높이 계산 → 충진율(%) 반환"""
    margin = int((x2 - x1) * 0.15)
    roi = frame[y1:y2, x1 + margin:x2 - margin]

    if roi.size == 0:
        return 0

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # 엣지 검출로 액면 위치 찾기
    edges = cv2.Canny(gray, 30, 100)

    # 위에서 아래로 스캔 → 엣지 많은 첫 행 = 액면
    liquid_top = h
    for row in range(h):
        if np.sum(edges[row, :]) > w * 8:
            liquid_top = row
            break

    fill = (h - liquid_top) / h * 100
    return min(fill, 100)


def draw_fill_bar(frame, x2, y1, y2, fill):
    """오른쪽에 채워지는 바 시각화"""
    bar_x = x2 + 10
    bar_w = 18
    bar_h = y2 - y1
    fill_h = int(bar_h * fill / 100)
    color = (0, 0, 255) if fill >= FILL_THRESHOLD else (0, 255, 0)

    # 배경 바
    cv2.rectangle(frame, (bar_x, y1), (bar_x + bar_w, y2), (200, 200, 200), 1)
    # 채워진 바
    cv2.rectangle(frame, (bar_x, y2 - fill_h), (bar_x + bar_w, y2), color, -1)
    # 95% 기준선
    threshold_y = y2 - int(bar_h * FILL_THRESHOLD / 100)
    cv2.line(frame, (bar_x - 3, threshold_y), (bar_x + bar_w + 3, threshold_y), (0, 165, 255), 1)


cap = cv2.VideoCapture(0)

print("Fill Level Detector 시작 | 종료: q")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # COCO 사전학습 모델 - bottle 클래스(39번) 탐지
    results = model(frame, classes=[39], conf=0.4, verbose=False)

    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            fill = get_fill_percent(frame, x1, y1, x2, y2)

            color = (0, 0, 255) if fill >= FILL_THRESHOLD else (0, 255, 0)

            # 바운딩 박스
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # 충진율 + confidence
            cv2.putText(frame, f'{fill:.1f}%  conf:{conf:.2f}',
                        (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # 옆에 채워지는 바
            draw_fill_bar(frame, x2, y1, y2, fill)

            # 95% 도달
            if fill >= FILL_THRESHOLD:
                cv2.putText(frame, 'STOP - ROTATE',
                            (x1, y2 + 28), cv2.FONT_HERSHEY_SIMPLEX,
                            0.8, (0, 0, 255), 2)
                print(f"[SIGNAL] 95% 도달 → 터릿 회전")

    cv2.imshow('FILL:N - Fill Level Detector', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
