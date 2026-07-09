import cv2


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
    # CSI 포트 0, 1 순서로 시도 (실제 프레임이 나오는지까지 확인)
    for sensor_id in (0, 1):
        cap = cv2.VideoCapture(_gst_pipeline(sensor_id), cv2.CAP_GSTREAMER)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"[CAMERA] CSI 카메라(nvarguscamerasrc) 연결됨 - sensor-id={sensor_id}")
                return cap
        cap.release()
        print(f"[CAMERA] sensor-id={sensor_id} 실패")

    print("[CAMERA] CSI 카메라 연결 실패 → USB 웹캠(index 0)으로 재시도")
    return cv2.VideoCapture(0)


cap = open_camera()
if not cap.isOpened():
    raise RuntimeError("카메라를 열 수 없습니다. 연결 상태를 확인하세요.")

print("종료하려면 q 누르세요")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    cv2.imshow("Camera View", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
