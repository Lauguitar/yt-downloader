import streamlit as st
import yt_dlp
import os
import re
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="YouTube Downloader", page_icon="🎥", layout="centered")
st.title("🎥 YouTube Downloader (Cloud-Safe Edition)")


# -------------------------------
# Automatic filename cleaner
# -------------------------------
def clean_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


# -------------------------------
# Progress hook
# -------------------------------
def progress_hook(d):
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes", 0)
        if total:
            progress = downloaded / total
            st.session_state.progress_bar.progress(progress)
            speed = d.get("speed", 0)
            st.session_state.speed_text.text(f"Speed: {round(speed/1024/1024,2)} MB/s")
    elif d["status"] == "finished":
        st.session_state.progress_bar.progress(1.0)
        st.session_state.speed_text.text("Processing file…")


# -------------------------------
# Fetch formats
# -------------------------------
def fetch_formats(url):
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True,
                               "extractor_args": {"youtube": {"player_client": "default"}}}) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        for f in info.get("formats", []):
            # Skip formats that are video-only without audio if JS/DASH required (safe for Cloud)
            if f.get("vcodec") != "none" and f.get("acodec") == "none":
                continue
            label = f"{f.get('format_id')} - {f.get('resolution','audio')}"
            if f.get("filesize"):
                label += f" ({round(f['filesize']/1024/1024,2)} MB)"
            formats.append((label, f.get("format_id"), f))

        return info, formats
    except Exception as e:
        st.error(f"Error fetching formats: {e}")
        return None, []


# -------------------------------
# Download functions
# -------------------------------
def download_single_video(url, fmt, output):
    ydl_opts = {
        "format": fmt,
        "outtmpl": os.path.join(output, "%(title)s.%(ext)s"),
        "windowsfilenames": True,
        "extractor_args": {"youtube": {"player_client": "default"}},
        "progress_hooks": [progress_hook],
        "quiet": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        st.warning(f"Selected format blocked or unavailable: {e}")
        st.info("Automatically selecting best available format…")
        # Fetch available formats
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True,
                               "extractor_args": {"youtube": {"player_client": "default"}}}) as ydl:
            info = ydl.extract_info(url, download=False)
        safe_formats = []
        for f in info.get("formats", []):
            # Cloud-safe: video+audio or audio-only
            if (f.get("vcodec") != "none" and f.get("acodec") != "none") or (f.get("vcodec") == "none" and f.get("acodec") != "none"):
                safe_formats.append(f)
        # Pick the highest resolution / bitrate available
        if safe_formats:
            fallback_fmt = safe_formats[-1]["format_id"]
            st.info(f"Downloading with fallback format: {fallback_fmt}")
            ydl_opts["format"] = fallback_fmt
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        else:
            st.error("No compatible formats available for this video.")



def download_playlist_threaded(playlist_urls, fmt, output, max_threads=4):
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        for link in playlist_urls:
            executor.submit(download_single_video, link, fmt, output)


# -------------------------------
# Streamlit UI
# -------------------------------
url = st.text_input("Enter YouTube Video / Playlist URL")
download_path = st.text_input("Download Folder", value="downloads")

filter_type = st.radio(
    "Type Filter",
    ["All Formats", "Video Only", "Audio Only"],
    horizontal=True
)

if url:
    st.info("Fetching available formats…")
    info, formats = fetch_formats(url)

    if info:
        st.subheader("📄 Info")
        st.write(f"**Title:** {info.get('title','N/A')}")
        st.write(f"**Type:** {'Playlist' if 'entries' in info else 'Single Video'}")

        # Filter formats based on user selection
        if filter_type == "Video Only":
            formats = [(l, fid, f) for l, fid, f in formats if f.get("vcodec") != "none"]
        elif filter_type == "Audio Only":
            formats = [(l, fid, f) for l, fid, f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"]

        if not formats:
            st.warning("No compatible formats available for this selection. Using safe default.")
            formats = [("Safe Default", "bestvideo+bestaudio/best", {})]

        # Format selector
        labels = [l for l, fid, f in formats]
        selected_label = st.selectbox("Choose quality:", labels)
        selected_fmt = dict((l, fid) for l, fid, _ in formats)[selected_label]

        # Initialize progress UI
        if "progress_bar" not in st.session_state:
            st.session_state.progress_bar = st.progress(0)
        if "speed_text" not in st.session_state:
            st.session_state.speed_text = st.empty()

        # Download button
        if st.button("Download"):
            os.makedirs(download_path, exist_ok=True)
            st.session_state.progress_bar.progress(0)
            st.session_state.speed_text.text("Starting…")

            # Playlist
            if "entries" in info:
                st.warning("Playlist detected — downloading with multithreading...")
                playlist_urls = [e["url"] for e in info["entries"] if e]
                try:
                    download_playlist_threaded(
                        playlist_urls,
                        selected_fmt,
                        download_path,
                        max_threads=4,
                    )
                    st.success("Playlist download complete!")
                except Exception as e:
                    st.error(f"Playlist download failed: {e}")
            # Single video
            else:
                try:
                    download_single_video(url, selected_fmt, download_path)
                    st.success("Download completed!")
                except Exception as e:
                    st.error(f"Download failed: {e}")
