import yt_dlp
from typing import Dict, Any

def analyze_url(url: str) -> Dict[str, Any]:
    """
    Analyzes a URL using yt-dlp to extract metadata and available formats.
    Configured with mobile client and custom headers to bypass platform restrictions.
    """
    clean_url = url.strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = f"https://{clean_url}"

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
            if not info:
                raise ValueError("No video information found for this URL.")
            
            # Find best audio stream info
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
    except Exception as e:
        raise ValueError(f"Could not analyze URL: {str(e)}")
