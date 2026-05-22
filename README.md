# FILL:N - 충진량 실시간 감지 AI

공항 기내 액체 소분 기기 **FILL:N**의 비전 기반 실시간 충진량 감지 모듈

## 개요

YOLOv8 + OpenCV를 활용하여 100mL 공병의 충진량을 실시간으로 감지하고, 95% 도달 시 터릿 회전 신호를 출력하는 AI 모듈

```
카메라 → YOLO 바운딩 박스 → 액면 높이 계산 → 95% 도달 → 신호 출력
```

## 기능

- YOLOv8n 기반 공병 실시간 탐지 (바운딩 박스)
- 바운딩 박스 내 액면 높이 추적
- 충진율(%) 실시간 표시
- 95% 도달 시 `STOP - ROTATE` 신호 출력
- 충진 바 시각화

## 실행 환경

- Python 3.10
- Raspberry Pi 5 (8GB) / 개발 환경: MacBook 웹캠

## 설치

```bash
pip install ultralytics opencv-python numpy
```

## 실행

```bash
python3 fill_detector.py
```

