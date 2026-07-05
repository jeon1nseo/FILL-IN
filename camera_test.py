import cv2
from flask import Flask, Response


def open_camera():
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

        ok, buffer = cv2.imencode('.jpg', frame)
        if not ok:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


@app.route('/')
def index():
    return '<html><body><h1>Camera Test</h1><img src="/stream"></body></html>'


@app.route('/stream')
def stream():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == '__main__':
    print("브라우저에서 http://<젯슨 IP>:5000 접속하여 확인하세요 (종료: Ctrl+C)")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
