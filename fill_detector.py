import cv2
import numpy as np
from ultralytics import YOLO
from flask import Flask, Response

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


def open_camera():
    """젯슨 CSI 카메라(라즈베리파이 카메라 모듈) 우선 시도, 실패 시 USB 웹캠으로 폴백"""
    gst_pipeline = (
        "nvarguscamerasrc sensor-id=0 ! "
        "video/x-raw(memory:NVMM), width=1280, height=720, framerate=30/1, format=NV12 ! "
        "nvvidconv flip-method=0 ! "
        "video/x-raw, width=1280, height=720, format=BGRx ! "
        "videoconvert ! "
        "video/x-raw, format=BGR ! appsink drop=1"
    )
    cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
    if cap.isOpened():
        print("[CAMERA] CSI 카메라(nvarguscamerasrc) 연결됨")
        return cap

    print("[CAMERA] CSI 카메라 연결 실패 → USB 웹캠(index 0)으로 재시도")
    return cv2.VideoCapture(0)


cap = open_camera()
if not cap.isOpened():
    raise RuntimeError("카메라를 열 수 없습니다. 연결 상태를 확인하세요.")

app = Flask(__name__)


def generate_frames():
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

        ok, buffer = cv2.imencode('.jpg', frame)
        if not ok:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


@app.route('/')
def index():
    return '<html><body><h1>FILL:N - Fill Level Detector</h1><img src="/stream"></body></html>'


@app.route('/stream')
def stream():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == '__main__':
    print("브라우저에서 http://<젯슨 IP>:5000 접속하여 확인하세요 (종료: Ctrl+C)")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
