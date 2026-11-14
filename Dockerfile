# Resolve this digest deliberately when updating Wolfi; CI also uses --pull.
FROM cgr.dev/chainguard/wolfi-base@sha256:360896efb0753a5701c48f860e17130c205eae5a264797aa3e7ea126ee2923a7 AS base

FROM base AS python-build
RUN apk add --no-cache python-3.11 py3.11-pip
WORKDIR /build
COPY backend/requirements.txt ./requirements.txt
COPY scripts/normalize_mediapipe_wheel.py ./normalize_mediapipe_wheel.py
RUN python3.11 -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir -r requirements.txt
RUN /opt/venv/bin/python normalize_mediapipe_wheel.py \
    && /opt/venv/bin/python -m pip check \
    && /opt/venv/bin/python -m pip uninstall --yes pip setuptools wheel
COPY backend/app/analysis/pose_landmarker.py /build/backend/app/analysis/pose_landmarker.py
COPY scripts/fetch_pose_models.py /build/scripts/fetch_pose_models.py
RUN /opt/venv/bin/python scripts/fetch_pose_models.py

FROM base AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENCV_FFMPEG_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    PATH=/opt/venv/bin:/usr/bin:/bin \
    HOME=/home/peso \
    PORT=10000
# Keep FFmpeg and its libraries in the signed package inventory used by scans.
RUN apk add --no-cache python-3.11-base libstdc++ libgomp libglvnd glib libexpat1=2.10.0-r0 ffmpeg-9.0=9.0.2-r8 py3-pip-wheel=26.2.2-r2 \
    && rm -rf /usr/lib/python3.11/ensurepip /usr/share/python-wheels \
    && addgroup -g 10001 peso \
    && adduser -D -u 10001 -G peso -h /home/peso peso
COPY --from=python-build /opt/venv /opt/venv
WORKDIR /app
COPY backend/app ./app
COPY --from=python-build /build/backend/app/analysis/models ./app/analysis/models
USER 10001:10001
EXPOSE 10000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000", "--no-proxy-headers"]
