import Constants, { AppOwnership } from 'expo-constants';
import * as ImagePicker from 'expo-image-picker';
import * as VideoThumbnails from 'expo-video-thumbnails';
import { useEffect, useRef, useState } from 'react';
import { Alert, Linking, Platform } from 'react-native';
import { useAuth } from '../../context/AuthContext';
import {
  fetchAnalysisResult,
  fetchVideoStatus,
  testBackendConnection,
  triggerVideoAnalysis,
} from '../../lib/backendApi';
import {
  cleanupUploadedVideoForAnalysis,
  uploadVideoForAnalysis,
} from '../../lib/videoUpload';
import type { UploadVideoForAnalysisResult } from '../../lib/videoUpload';
import { VideoSetupSelection } from '../constants/videoSetup';
import { VideoAnalysisResult, VideoAnalysisStatus } from '../types/videoAnalysis';

export function isAnalysisInProgress(status: VideoAnalysisStatus | null) {
  return status === 'queued' || status === 'processing';
}

export function useUploadVideoSession() {
  const { user, session } = useAuth();
  const isWeb = Platform.select<boolean>({ web: true, default: false }) ?? false;
  const [permissionStatus, setPermissionStatus] = useState<ImagePicker.PermissionStatus | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [setupModalVisible, setSetupModalVisible] = useState(true);
  const [videoSetup, setVideoSetup] = useState<VideoSetupSelection | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [uploading, setUploading] = useState(false);
  const [analysisVideoId, setAnalysisVideoId] = useState<string | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<VideoAnalysisStatus | null>(null);
  const [analysisResult, setAnalysisResult] = useState<VideoAnalysisResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [thumbnailUri, setThumbnailUri] = useState<string | null>(null);
  const [displayedVideoSizeBytes, setDisplayedVideoSizeBytes] = useState<number | null>(null);
  const analysisStartInFlightRef = useRef(false);
  const analysisQueuedForVideoRef = useRef<string | null>(null);

  const handleSelectedVideo = (asset: ImagePicker.ImagePickerAsset) => {
    analysisStartInFlightRef.current = false;
    analysisQueuedForVideoRef.current = null;
    setSelectedVideo(asset);
    setAnalysisVideoId(null);
    setAnalysisStatus(null);
    setAnalysisResult(null);
    setErrorMessage(null);
    setStatusMessage(null);
    setDisplayedVideoSizeBytes(
      typeof asset.fileSize === 'number' && !Number.isNaN(asset.fileSize) ? asset.fileSize : null
    );
  };

  const handleStartAnalysis = async () => {
    if (analysisStartInFlightRef.current || uploading || isAnalysisInProgress(analysisStatus)) {
      return;
    }

    if (analysisResult) {
      setStatusMessage(null);
      setErrorMessage(null);
      return;
    }

    if (analysisVideoId && analysisQueuedForVideoRef.current === analysisVideoId) {
      return;
    }

    if (!selectedVideo) {
      setStatusMessage(null);
      setErrorMessage('Choose a video before starting analysis.');
      return;
    }

    if (!videoSetup) {
      setSetupModalVisible(true);
      setStatusMessage(null);
      setErrorMessage('Select an exercise and camera angle before starting analysis.');
      return;
    }

    if (!user || !session?.access_token) {
      setStatusMessage(null);
      setErrorMessage('You must be logged in to upload and analyze a video.');
      return;
    }

    setErrorMessage(null);
    setStatusMessage(null);
    setUploading(true);
    analysisStartInFlightRef.current = true;
    let uploadedVideo: UploadVideoForAnalysisResult | null = null;

    try {
      setStatusMessage('Checking backend connection...');
      await testBackendConnection();

      const uploadResult = await uploadVideoForAnalysis({
        asset: selectedVideo,
        exercise: videoSetup.exercise,
        angle: videoSetup.angle,
        onStatusChange: setStatusMessage,
      });
      uploadedVideo = uploadResult;

      setDisplayedVideoSizeBytes(uploadResult.uploadedFileSizeBytes);
      setAnalysisVideoId(uploadResult.videoId);
      setAnalysisStatus(uploadResult.status);

      setStatusMessage('Starting analysis...');
      console.log('[analysis] starting backend analysis', uploadResult.videoId);
      const queuedResponse = await triggerVideoAnalysis(uploadResult.videoId, session.access_token);
      analysisQueuedForVideoRef.current = uploadResult.videoId;
      setAnalysisStatus(queuedResponse.status);
      setStatusMessage(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to upload and analyze this video.';
      const triggerFailedAfterUpload = Boolean(uploadedVideo);

      if (uploadedVideo) {
        setStatusMessage('Cleaning up upload...');
        await cleanupUploadedVideoForAnalysis({
          videoId: uploadedVideo.videoId,
          storagePath: uploadedVideo.storagePath,
        });
        setAnalysisVideoId(null);
        setAnalysisStatus(null);
      }

      setStatusMessage(null);
      setErrorMessage(
        triggerFailedAfterUpload
          ? 'Upload succeeded, but analysis could not start. The upload was cleaned up; please try again.'
          : message.includes('row-level security policy')
          ? `${message}. Apply the latest videos RLS migration to your Supabase project.`
          : message
      );
      analysisStartInFlightRef.current = false;
    } finally {
      setUploading(false);
    }
  };

  const launchPicker = async () => {
    if (pickerOpen || uploading) {
      return;
    }

    setPickerOpen(true);

    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['videos'],
        allowsEditing: false,
        quality: 1,
        ...(Platform.OS === 'ios'
          ? {
              videoExportPreset: ImagePicker.VideoExportPreset.H264_1280x720,
            }
          : {}),
      });

      if (result.canceled) {
        return;
      }

      const nextAsset = result.assets[0];

      if (nextAsset) {
        handleSelectedVideo(nextAsset);
      }
    } finally {
      setPickerOpen(false);
    }
  };

  const promptForSettings = () => {
    Alert.alert(
      'Camera roll access needed',
      'Peso needs access to your camera roll to upload videos.',
      [
        {
          text: 'Accept',
          onPress: () => {
            void requestPermission(true);
          },
        },
        {
          text: 'Settings',
          onPress: () => {
            void Linking.openSettings();
          },
        },
      ],
      { cancelable: true }
    );
  };

  const syncPermissionStatus = async () => {
    const currentPermission = await ImagePicker.getMediaLibraryPermissionsAsync();
    setPermissionStatus(currentPermission.status);
    return currentPermission;
  };

  const requestPermission = async (forcePrompt = false) => {
    if (isWeb) {
      await launchPicker();
      return;
    }

    const currentPermission = await syncPermissionStatus();

    if (currentPermission.granted) {
      await launchPicker();
      return;
    }

    if (currentPermission.canAskAgain || forcePrompt) {
      const requestedPermission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      setPermissionStatus(requestedPermission.status);

      if (requestedPermission.granted) {
        await launchPicker();
        return;
      }
    }

    if (!isWeb) {
      promptForSettings();
    }
  };

  useEffect(() => {
    if (__DEV__ && Platform.OS === 'ios' && Constants.appOwnership === AppOwnership.Expo) {
      console.warn(
        '[UploadVideoScreen] Video compression requires a native iOS build. Expo Go will not support react-native-compressor. Rebuild with `npx expo run:ios`.'
      );
    }
  }, []);

  useEffect(() => {
    void syncPermissionStatus();
  }, []);

  useEffect(() => {
    if (!selectedVideo?.uri) {
      setThumbnailUri(null);
      return;
    }

    if (isWeb) {
      setThumbnailUri(null);
      return;
    }

    let active = true;

    const generateThumbnail = async () => {
      try {
        const time = typeof selectedVideo.duration === 'number'
          ? Math.max(0, Math.min(selectedVideo.duration / 3, 1500))
          : 1000;
        const thumbnail = await VideoThumbnails.getThumbnailAsync(selectedVideo.uri, {
          time,
          quality: 0.7,
        });

        if (!active) {
          return;
        }

        setThumbnailUri(thumbnail.uri);
      } catch (error) {
        if (__DEV__) {
          console.warn('Unable to generate video thumbnail.', error);
        }

        if (active) {
          setThumbnailUri(null);
        }
      }
    };

    void generateThumbnail();

    return () => {
      active = false;
    };
  }, [isWeb, selectedVideo]);

  useEffect(() => {
    if (!analysisVideoId || !session?.access_token) {
      return;
    }

    if (analysisStatus === 'failed') {
      return;
    }

    if (analysisStatus === 'completed' && analysisResult) {
      return;
    }

    let active = true;

    const poll = async () => {
      try {
        const statusResponse = await fetchVideoStatus(analysisVideoId, session.access_token);

        if (!active) {
          return;
        }

        setAnalysisStatus(statusResponse.status);

        if (statusResponse.status === 'failed') {
          analysisStartInFlightRef.current = false;
          analysisQueuedForVideoRef.current = null;
          setStatusMessage(null);
          setErrorMessage('Analysis failed. Check the backend logs and try another upload.');
          return;
        }

        if (statusResponse.status === 'completed') {
          try {
            const analysisResponse = await fetchAnalysisResult(analysisVideoId, session.access_token);

            if (!active) {
              return;
            }

            setAnalysisResult(analysisResponse.result_json);
          } catch (error) {
            if (__DEV__) {
              console.warn('Analysis result not ready yet.', error);
            }
          }
        }
      } catch (error) {
        if (__DEV__) {
          console.warn('Polling video analysis status failed.', error);
        }
      }
    };

    void poll();
    const intervalId = setInterval(() => {
      void poll();
    }, 4000);

    return () => {
      active = false;
      clearInterval(intervalId);
    };
  }, [analysisResult, analysisStatus, analysisVideoId, session?.access_token]);

  const handleModalContinue = async (selection: VideoSetupSelection) => {
    setVideoSetup(selection);
    setSetupModalVisible(false);
    setErrorMessage(null);
    setStatusMessage(null);

    if (!selectedVideo) {
      await requestPermission(true);
    }
  };

  const handlePickVideoPress = () => {
    if (uploading) {
      return;
    }

    if (permissionStatus === 'granted') {
      void launchPicker();
      return;
    }

    void requestPermission(true);
  };

  const handleReviewDiscarded = () => {
    analysisStartInFlightRef.current = false;
    analysisQueuedForVideoRef.current = null;
    setSelectedVideo(null);
    setAnalysisVideoId(null);
    setAnalysisStatus(null);
    setAnalysisResult(null);
    setErrorMessage(null);
    setStatusMessage(null);
    setThumbnailUri(null);
    setDisplayedVideoSizeBytes(null);
  };

  const canStartAnalysis =
    Boolean(selectedVideo && videoSetup) &&
    !uploading &&
    !isAnalysisInProgress(analysisStatus) &&
    analysisStatus !== 'completed';

  return {
    analysisResult,
    analysisStatus,
    analysisVideoId,
    canStartAnalysis,
    displayedVideoSizeBytes,
    errorMessage,
    handleModalContinue,
    handlePickVideoPress,
    handleReviewDiscarded,
    handleStartAnalysis,
    selectedVideo,
    setSetupModalVisible,
    setupModalVisible,
    statusMessage,
    thumbnailUri,
    uploading,
    videoSetup,
  };
}
