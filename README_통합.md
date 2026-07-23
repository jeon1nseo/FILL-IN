# FILL:N 비전(충진량) 통합 가이드

비전 파트가 **"용기가 다 찼는지"를 True/False**로 알려줍니다.
이 값을 VisionSample의 **VB(LVL 플래그)** 에 넣어 아두이노로 보내면 됩니다.

---

## 1. 넘겨받는 파일 (2개)

| 파일 | 설명 |
|---|---|
| `fill_monitor.py` | 비전 본체 (`FillDetector` 클래스 포함) |
| `fill_config.json` | 캘리브레이션 설정 (카메라 위치/ROI 등) |

> 두 파일은 **같은 폴더**에 두세요. 통합 코드도 같은 폴더(또는 import 가능한 경로)에 두면 됩니다.

---

## 2. 준비 (딱 한 번)

- 카메라는 **젯슨의 CSI 카메라**를 사용합니다.
- 실행은 **젯슨 자체 터미널**(모니터에 연결된 터미널)에서 하세요. (SSH 터미널은 카메라 EGL 문제로 안 됩니다.)
- `fill_config.json`이 이미 있으면 그대로 쓰면 됩니다.
  카메라 위치가 바뀌었으면 아래로 재캘리브레이션 후 다시 쓰세요:
  ```bash
  /usr/bin/python3 fill_monitor.py     # 창에서 병 영역 드래그 → w(저장) → q(종료)
  ```

---

## 3. 사용법 (핵심)

```python
from fill_monitor import FillDetector

det = FillDetector()          # fill_config.json 읽고 카메라 염 (한 번만)

while True:
    full = det.is_full()      # ★ True = 용기 다 참 / False = 아직

    # ↓↓↓ 이 full 값을 VisionSample의 VB(LVL 플래그)에 넣으세요 ↓↓↓
    sample.vb = full          # (또는) VIS 프레임 만들 때:  VB = 1 if full else 0

    # ... 나머지(gap/bar/dz 등)와 함께 VIS 프레임을 시리얼로 아두이노에 전송 ...

det.release()                 # 종료 시
```

- `is_full()`는 **매 프레임 호출**하면 됩니다 (내부에서 카메라 한 장 읽고 판단).
- True 조건: 충진율 95% 이상이 **5프레임 연속**일 때 (한 번 튀는 노이즈로 오작동 방지).

---

## 4. VisionSample / VIS 프레임에 넣기

- 비전 파트 담당 필드는 **VB 하나**입니다. (LVL 플래그)
- `full == True`  →  **VB = 1**
- `full == False` →  **VB = 0**
- GAP / BAR / DZ / VA / VC / VS 등 나머지는 각 파트에서 채웁니다.

예시(형식은 실제 프로토콜에 맞게):
```
VIS ... VB=1 ...     # 용기 다 찼을 때
VIS ... VB=0 ...     # 아직 안 찼을 때
```

---

## 5. 참고 (동작 원리, 안 읽어도 됨)

- YOLO/학습 없이 **HSV 색 분할**로 흰색 내용물의 높이를 측정합니다.
- 캘리브레이션 때 지정한 ROI(병 영역) 안에서, 바닥부터 연속으로 찬 높이를 계산합니다.
- 카메라가 고정 안 돼도 됩니다 — 위치가 바뀌면 재캘리브레이션(`w` 저장)만 하면
  통합 코드는 그대로 동작합니다. (설정 파일만 갱신됨)

---

## 6. 문의

- 비전 판단 기준(95%, 5프레임)이나 mL 환산 등은 조정 가능합니다.
- `is_full()` 외에 LVL 숫자(mL)가 필요하면 말해주세요 — 함수 추가 가능합니다.
