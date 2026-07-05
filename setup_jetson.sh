#!/bin/bash
set -e

BASE_URL="https://raw.githubusercontent.com/jeon1nseo/FILL-IN/main"

for f in view_camera.py camera_test.py capture_dataset.py fill_detector.py; do
    rm -f "$f"
    wget -q "$BASE_URL/$f" -O "$f"
    echo "받음: $f ($(stat -c%s "$f") bytes)"
done

echo "완료"
