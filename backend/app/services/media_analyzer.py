import os
import subprocess
import json
from typing import Dict, Any, Optional

def analyze_media(file_path: str) -> Dict[str, Any]:
    """
    Analyzes a media file using ffprobe and extracts audio/video information.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        info = {
            "has_audio": False,
            "duration": None,
            "audio_codec": None,
            "audio_bitrate": None,
            "sample_rate": None,
            "channels": None
        }

        # Check format level duration
        if "format" in data and "duration" in data["format"]:
            info["duration"] = float(data["format"]["duration"])

        # Find first audio stream
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "audio":
                info["has_audio"] = True
                info["audio_codec"] = stream.get("codec_name")
                
                # Get bitrate (can be in stream or format)
                bitrate = stream.get("bit_rate")
                if not bitrate and "format" in data:
                    bitrate = data["format"].get("bit_rate")
                
                if bitrate:
                    info["audio_bitrate"] = f"{int(bitrate) // 1000} kbps"
                
                sample_rate = stream.get("sample_rate")
                if sample_rate:
                    info["sample_rate"] = f"{int(sample_rate) // 1000} kHz"
                
                channels = stream.get("channels")
                if channels:
                    info["channels"] = "Stereo" if channels == 2 else ("Mono" if channels == 1 else f"{channels} channels")
                
                break

        return info

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFprobe analysis failed: {e.stderr}")
    except json.JSONDecodeError:
        raise RuntimeError("Failed to parse FFprobe output")
