# Runbook

## Local

- Start API: `python -m storeintel.api`
- Start Processor: `python -m storeintel.processor --video ... --camera-id ...`
- Start Dashboard: `streamlit run apps/dashboard/app.py`

## Docker

- `docker compose up --build`

## Troubleshooting

- If YOLO model download is slow, pre-download `yolov8n.pt` into the container image or mount a volume.
- If OpenCV cannot open a video, verify codec support and file path mapping.
