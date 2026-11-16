import { EventEmitter } from 'expo';
import type { VideoPlayer, VideoPlayerEvents, VideoPlayerStatus, VideoSource, VideoViewProps } from 'expo-video';
import { useCallback, useEffect, useMemo, type CSSProperties } from 'react';
import { StyleSheet } from 'react-native';
import { releaseBrowserMedia } from '../../lib/privateMediaLifecycle';

// A single HTML video owns web playback. Source replacement stays paused and
// never starts an unobserved play promise while a private lease is being changed.
class ReviewPlayer extends EventEmitter<VideoPlayerEvents> {
  element: HTMLVideoElement | null = null;
  source: VideoSource = null;
  loop = false;
  muted = true;
  timeUpdateEventInterval = 0.05;
  playing = false;
  status: VideoPlayerStatus = 'idle';
  position = 0;
  get currentTime() { return this.element?.currentTime ?? this.position; }
  set currentTime(value: number) {
    this.position = value;
    if (this.element) this.element.currentTime = value;
  }
  get duration() { return this.element?.duration || 0; }
  setStatus(status: VideoPlayerStatus) {
    const oldStatus = this.status;
    this.status = status;
    this.emit('statusChange', { status, oldStatus });
  }
  setPlaying(isPlaying: boolean) {
    const oldIsPlaying = this.playing;
    this.playing = isPlaying;
    this.emit('playingChange', { isPlaying, oldIsPlaying });
  }
  play() {
    void this.element?.play().catch((error: DOMException) => {
      // Pause/source replacement may intentionally cancel a pending play.
      if (error.name !== 'AbortError') this.setStatus('error');
    });
  }
  pause() { this.element?.pause(); this.setPlaying(false); }
  async replaceAsync(source: VideoSource) {
    this.pause(); this.source = source; this.position = 0;
    this.applySource();
  }
  applySource() {
    if (!this.element) return;
    const uri = typeof this.source === 'string' ? this.source
      : this.source && typeof this.source === 'object' ? this.source.uri : null;
    this.element.pause();
    if (uri) this.element.setAttribute('src', uri);
    else this.element.removeAttribute('src');
    this.element.load();
    this.setStatus(uri ? 'loading' : 'idle');
  }
}

export function useVideoPlayer(_source: VideoSource, setup?: (player: VideoPlayer) => void): VideoPlayer {
  const player = useMemo(() => {
    const controller = new ReviewPlayer();
    setup?.(controller as unknown as VideoPlayer);
    return controller;
  }, []);
  useEffect(() => {
    const timer = setInterval(() => {
      if (!player.element || player.status !== 'readyToPlay') return;
      player.emit('timeUpdate', { currentTime: player.currentTime, currentLiveTimestamp: null,
        currentOffsetFromLive: null, bufferedPosition: player.duration });
    }, player.timeUpdateEventInterval * 1000);
    return () => { clearInterval(timer); player.pause(); };
  }, [player]);
  return player as unknown as VideoPlayer;
}

export function VideoView({ player, style, contentFit, crossOrigin, onFirstFrameRender }: VideoViewProps) {
  const controller = player as unknown as ReviewPlayer;
  const attachElement = useCallback((element: HTMLVideoElement | null) => {
    if (element === controller.element) return;
    if (controller.element) releaseBrowserMedia(controller.element);
    controller.element = element;
    if (element) { element.muted = controller.muted; element.loop = controller.loop; controller.applySource(); }
  }, [controller]);
  return <video ref={attachElement} crossOrigin={crossOrigin} playsInline preload="metadata" controls={false}
    style={{ ...StyleSheet.flatten(style) as CSSProperties, objectFit: contentFit ?? 'contain' }}
    onLoadedMetadata={() => { controller.currentTime = controller.position; }}
    onCanPlay={() => { controller.setStatus('readyToPlay'); onFirstFrameRender?.(); }}
    onPlay={() => controller.setPlaying(true)} onPause={() => controller.setPlaying(false)}
    onEnded={() => controller.setPlaying(false)}
    onWaiting={() => controller.setStatus('loading')}
    onError={() => { if (controller.source) controller.setStatus('error'); }} />;
}
