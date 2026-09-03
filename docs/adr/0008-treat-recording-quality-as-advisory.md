# Treat recording quality as a universal pre-analysis advisory

The backend requires current recording-quality evidence but does not reject an Analysis run because of its verdict. Every upload surface pauses before analysis when confidence is below 85% or a critical tracking check fails, then lets the athlete continue with an accuracy warning or choose another video. This keeps the behavior consistent across native and web without allowing uncertain frames to masquerade as reliable tracking.
