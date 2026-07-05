import cv2


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
