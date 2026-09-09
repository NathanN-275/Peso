# Resolve this digest deliberately when updating Wolfi; CI also uses --pull.
FROM cgr.dev/chainguard/wolfi-base@sha256:918a593b8268c222afd4e2c4f06860ac984e60719b4697e4c71d796bc8fcd042 AS base

FROM base AS ffmpeg-build
RUN apk add --no-cache build-base pkgconf nasm curl xz x264-dev
WORKDIR /build
# Official release source, verified before extraction and compilation.
RUN curl --fail --location --retry 3 https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz -o ffmpeg.tar.xz \
    && echo 'cf38e0e28c7e5605942c4a77755349b0145804a397af37eb1fb4c77cb237f635  ffmpeg.tar.xz' | sha256sum -c - \
    && tar -xJf ffmpeg.tar.xz --strip-components=1 \
    && ./configure --prefix=/opt/ffmpeg --enable-gpl --enable-libx264 \
      --disable-autodetect --disable-doc --disable-debug --disable-ffplay \
    && make -j2 \
    && make install

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
    PATH=/opt/venv/bin:/opt/ffmpeg/bin:/usr/bin:/bin \
    HOME=/home/peso \
    PORT=10000
RUN apk add --no-cache python-3.11-base libstdc++ libgomp x264-libs libglvnd glib \
    && rm -rf /usr/lib/python3.11/ensurepip /usr/share/python-wheels \
    && addgroup -g 10001 peso \
    && adduser -D -u 10001 -G peso -h /home/peso peso
COPY --from=ffmpeg-build /opt/ffmpeg /opt/ffmpeg
COPY --from=python-build /opt/venv /opt/venv
WORKDIR /app
COPY backend/app ./app
COPY --from=python-build /build/backend/app/analysis/models ./app/analysis/models
USER 10001:10001
EXPOSE 10000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
