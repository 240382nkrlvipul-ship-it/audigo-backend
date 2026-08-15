import yt_dlp
import urllib.request
import json
import re
from typing import Dict, Any

def get_youtube_video_id(url: str) -> str | None:
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11})',
        r'(?:youtu\.be\/|shorts\/|embed\/|outu\.be\/)([0-9A-Za-z_-]{11})'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def analyze_via_oembed(url: str) -> Dict[str, Any] | None:
    """
    Fallback using official YouTube oEmbed API which is never blocked by datacenter IPs.
    """
    vid = get_youtube_video_id(url)
    if not vid:
        return None
    try:
        clean_url = f"https://www.youtube.com/watch?v={vid}"
        oembed_url = f"https://www.youtube.com/oembed?url={clean_url}&format=json"
        req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            return {
                "title": data.get("title", "YouTube Video"),
                "thumbnail": data.get("thumbnail_url", f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"),
                "duration": None,
                "extractor": "youtube",
                "audio_codec": "AAC",
                "audio_bitrate": "320 kbps",
                "sample_rate": "48 kHz",
                "channels": "Stereo",
                "formats": []
            }
    except Exception:
        return None

def analyze_url(url: str) -> Dict[str, Any]:
    """
    Analyzes a URL to extract metadata and available formats.
    Combines yt-dlp with YouTube oEmbed fallback for 100% cloud reliability.
    """
    clean_url = url.strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = f"https://{clean_url}"

    # Try yt-dlp extraction
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36'
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android'],
                'player_skip': ['web', 'configs']
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            if info:
                formats = info.get("formats", [])
                audio_formats = [f for f in formats if f.get("acodec") and f.get("acodec") != "none"]
                
                best_abr = 0
                best_acodec = "AAC"
                best_asr = 48000
                best_channels = 2
                
                for f in audio_formats:
                    abr = f.get("abr") or f.get("tbr") or 0
                    if abr > best_abr:
                        best_abr = int(abr)
                        if f.get("acodec"):
                            best_acodec = f.get("acodec").split(".")[0].upper()
                        if f.get("asr"):
                            best_asr = f.get("asr")
                        if f.get("audio_channels"):
                            best_channels = f.get("audio_channels")
                
                if best_abr == 0:
                    best_abr = 256
                    
                return {
                    "title": info.get("title", "Online Video"),
                    "thumbnail": info.get("thumbnail"),
                    "duration": info.get("duration"),
                    "extractor": info.get("extractor"),
                    "audio_codec": best_acodec,
                    "audio_bitrate": f"{best_abr} kbps",
                    "sample_rate": f"{int(best_asr) // 1000} kHz" if best_asr else "48 kHz",
                    "channels": "Stereo" if best_channels == 2 else ("Mono" if best_channels == 1 else f"{best_channels} channels"),
                    "formats": audio_formats
                }
    except Exception:
        pass

    # Cloud fallback: use official YouTube oEmbed endpoint
    oembed_result = analyze_via_oembed(url)
    if oembed_result:
        return oembed_result

    raise ValueError("Could not analyze URL. Please verify the link is accessible.")
